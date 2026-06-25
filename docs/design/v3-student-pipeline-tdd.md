# TDD: SylannEngine v3 — Student Pipeline (corpus → train → serve, par2 reach-outcome loop)

- Status: Draft (for owner review)
- Author: Sylanne (design), Ayleovelle (owner/reviewer)
- Last updated: 2026-06-25
- Scope: SDK `sylanne_core` (branch `next-gen`) + plugin `Sylanne-next` (`sylanne_alpha`)
- Related: par1 telemetry sink (built, `next-gen`), vendor-stability audit (GREEN)

---

## 1. Executive summary

We are building the **v3 "student"**: a small, CPU-only, offline-trained model that the
SDK can serve inside a **2 vCPU / 2 GB-RAM / no-GPU, multi-session** box. The student
learns the **affect + timing policy** (numeric state features → action) from a
privacy-safe corpus, is corrected per-session online by the existing `MetaLearner`, and
is taught by the remote **assessor** (the semantic organ). Semantics stay with the
assessor; the student never produces text.

Three tiers, already partly in place:

```
            (offline, owner's local GPU)         (remote API)
   teacher ───────────────► student ◄──────────── assessor
   v2.1 EmotiCore           30 feats→action       LLM: valence/arousal/
   (text→emotion,           ~12K-param MLP         wound_risk/flags
   corpus auto-labeler)     int8 .npz, numpy       + online corrective
        │                   served in 2c2g            teacher signal
        │ labels                  ▲  ▲                    │
        ▼                         │  │ par1 features      │ a_* labels
   corpus_labeled.jsonl     par1 corpus ──── join ──── par2 reach-outcome
   (1M rows, exists)        (built, default-off)   (this TDD: new)
```

What already exists (do **not** rebuild): the **par1 `DistillationSink`** (numeric
feature + assessor-affect capture, default-off, privacy-safe), the **`MetaLearner`**
online residual (`accepted/ignored/rejected`, elastic-regularized), the
**train-torch → export-`.npz` → numpy-serve** pattern (proven by `EmotiCoreStudentLite`),
and 1M+ rows of teacher-labeled text corpus.

What this TDD adds: **par2** (the async reach-outcome label loop across both repos), the
**student model + offline training pipeline**, the **numpy serving runtime** behind the
unused `EngineFacade`, the **phased reversible rollout**, and the **engineering
standards / observability / governance** around all of it.

**The single biggest decision for the owner** is the **student's scope** — narrow
(imitate `_decide`'s affect+timing policy, a safe drop-in) vs broad (replace the whole
resonance tick as the learned core). See §14, Decision D-1. This TDD recommends and
specs the **narrow** scope for v3.0 and treats broad as a gated v3.1.

---

## 2. Goals / Non-goals

### Goals
- G1 — Close the **par2 loop** end-to-end: a discrete, action-contingent outcome
  (`accepted | ignored | rejected`) that joins back to the exact par1 row that caused it
  (the tick where `decision.action == "reach_out"` and `guard.allowed`), correct under
  async delay, multi-session concurrency, and process restarts on both repos.
- G2 — Ship a **CPU-only, no-torch, low-RAM** student artifact (int8 `.npz`, pure-numpy
  forward, sub-ms/inference) that loads **once** shared read-only across all sessions.
- G3 — Define the **local offline training loop** (PyTorch on the owner's GPU, no cloud):
  par1 JSONL → tensors → train → int8 `.npz` + manifest, reproducible, leakage-free.
- G4 — **Additive / default-off** everywhere on the SDK side; honor the GREEN-frozen
  public API + backward-compatible snapshot/restore.
- G5 — Privacy-by-construction for multi-user data: no raw text, no PII, no network
  egress; the only identity token is the existing salted `SHA-256(salt:key)[:16]`.
- G6 — A **fully reversible phased rollout** with a kill switch to native `_decide()` at
  every stage, plus observability and acceptance gates.
- G7 — Adopt explicit **engineering standards** (commits / lint / types / tests +
  data governance + model registry + acceptance gates).

### Non-goals
- NOT replacing the **assessor** — it stays the semantic oracle and online teacher; the
  student maps numeric features to an action, it never emits text/semantics.
- NOT replacing **EmotiCore** (text→emotion) — that is the offline corpus auto-labeler,
  it never runs at 2c2g serving.
- NOT **cloud / offline-at-serving** training — training is local-GPU only; serving does
  zero backprop.
- NOT using **assessor wound-delta** (or any `a_*` delta) as the reward — the reward is
  the discrete `accepted/ignored/rejected` action class only (hard adversarial lesson).
- NOT introducing **torch / onnxruntime / ggml** at serving (justified in §7).
- NOT changing the **par1 schema** (`AFFECT_CONTEXT_FIELDS`, `FEATURE_SCHEMA_VERSION=1`).
- NOT a **sequence model** in v3.0 (per-tick tabular; short-context is a gated v3.1 option).

---

## 3. Background & current state (grounding facts)

These are verified facts from the codebase, not assumptions:

- **par1 row** (`FEATURE_SCHEMA_VERSION=1`, written by `DistillationSink`,
  `sylanne_core/telemetry/sink.py`): `{schema_version, session_hash[16hex], tick, 26 f_*
  floats in AFFECT_CONTEXT_FIELDS order, a_valence, a_arousal, a_wound_risk, a_confidence,
  decision_action:str}`. Captured **only on assessed ticks**
  (`kernel.py:_capture_telemetry`, gated `sink is not None and assessment is not None`).
  It captures **all** assessed ticks, not only `reach_out` — the reach filter is applied
  **offline** at corpus-build time.
- **Student input** = the 30-vector `[26 f_*] ++ [a_valence, a_arousal, a_wound_risk,
  a_confidence]` in `AFFECT_CONTEXT_FIELDS` order. **Target** = `decision_action` ∈
  `{repair, withdraw, reach_out, express, explore, wait}` (the deterministic
  `kernel._decide` oracle).
- **`MetaLearner`** (`sylanne_core/compute/meta_learner.py`) already implements
  `update(outcome)` for exactly `accepted/rejected/ignored`, with EMA + elastic ≤30%-of-seed
  regularization + exploration noise, and is already serialized in
  `ResonanceSpine.to_dict()`. **This is the per-session online residual — do not reinvent it.**
- **`ResonanceSpine.feedback(outcome, …)`** (`resonance_integration.py:795`) is the real
  feedback bus (drives `MetaLearner.update`, scar healing, relationship deltas). It is
  **NOT engine-public**; any use needs an explicit new wrapper (no fabricated path).
- **par2 hook** is `host.on_proactive_check` (`host.py:146`) — the *only* path that
  consumes interruption-budget. The plugin's `derive_should_send` reconstructs intent
  **without** consuming budget — par2 must **not** hook there (double-count hazard).
- **Plugin** (`Sylanne-next`) vendors the SDK at
  `sylanne_alpha/_engine/sylanne_core`; consumes it through `engine_adapter.py`. The
  **`EngineFacade`** (`engine_adapter.py:129`) is **defined but unused** — the designated
  slot for the student backend. The definitive "message was sent" signal is
  `ProactiveBridge.dispatch()` returning `{"dispatched": True}` (`proactive_bridge.py:301`).
  No three-way outcome classifier exists today (only binary answered/unanswered).
- **Serving facts**: AstrBot is a single async event loop; hosts are a
  `BoundedDict(maxsize=200)` LRU; eviction = snapshot to disk via `AlphaRuntime.save`
  (atomic `fsync`+`os.replace`); **no torch imported** (`force_backend='python'`).
- **Training assets**: `training/` holds a **superseded** text→emotion stack
  (`generate_data.py`, `train_model*.py`, `perception_v1.npz`) plus `EmotiCore`
  (teacher/student-lite, source `.pyc`-only) and **1M+ rows** of teacher-labeled corpus.
  **No trained teacher `.pt` exists in-repo** (`train_teacher.log` crashed 2026-06-02);
  the owner's external v2.1 teacher must be located, or the affect-KD term is dropped.

---

## 4. Architecture overview

The student is a **drop-in policy** inside the existing tick, not a new organ:

```
 user msg ─► plugin (engine_adapter / EngineFacade)
              │  assessment (remote assessor: a_valence/arousal/wound_risk/flags)
              ▼
        SDK: host.on_request → kernel.tick(assessment)
              │  build 30-vec x (26 f_* + 4 a_*)
              ├─ if student.ready and enabled:
              │     action,probs,p_reach = student.predict(x, residual_bias)   # numpy, µs
              │  else:
              │     action = kernel._decide()                                  # heuristic fallback
              ├─ _guard()/cooldown/budget/sovereignty  (UNCHANGED — student never bypasses)
              ├─ par1 DistillationSink.record_tick(...)  (assessed ticks, default-off)
              ▼
        surface → plugin business layer (UNCHANGED keys)

 proactive: host.on_proactive_check → should_send → ProactiveBridge.dispatch
              └─ on {dispatched:True}: plugin arms awaiting_par2[session]      # par2 attribution
 next user msg / timeout:
              plugin classifies accepted/ignored/rejected
              └─ engine.report_reach_outcome(session, originating_tick, outcome, apply_online?)
                    ├─ Par2Sink.record_outcome(...)               # corpus label (default)
                    └─ if apply_online: host.kernel.computation.feedback(outcome)  # → MetaLearner
```

Key invariants:
- The student **augments** `_decide`; `_guard` and par1 capture are untouched → GREEN
  contract + adversarial-lesson wiring preserved.
- One **shared read-only** student; per-session personalization is the **existing**
  `MetaLearner` residual → flat RAM across 200 sessions, no new snapshot field for the model.
- par2 attribution lives **plugin-side** (the only actor that sees both send and reply),
  in its own atomic store — never appended to `.alpha.json`.

---

## 5. Component design

### 5.1 Data pipeline (par1 + par2 + offline join)

- **par2 join key = `(session_hash, originating_tick)`.** Both already exist in every
  par1 row; `tick` is `kernel.turns`, snapshot-persisted, so the join is **restart-safe
  by construction** with **no `FEATURE_SCHEMA_VERSION` bump** and **no new identity token**.
- **par2 is a separate append-only stream** `reach_outcomes.jsonl`, written by a new
  `Par2Sink` modeled byte-for-byte on `DistillationSink` (thread-safe `Lock`, `0o600`,
  `_resolve_under_base` traversal guard, same salt). **Never** rewrite par1 in place
  (append-only + open `0o600` handle ⇒ corruption hazard) and **never** put pending state
  in `.alpha.json`.
- **Offline join** (`training/build_corpus.py`): read par1 shards → filter
  `decision_action=='reach_out'` → left-outer-join par2 on `(session_hash, originating_tick)`
  → apply deletion tombstones → emit a **parquet** shard + manifest. The reach filter is
  enforced **twice** (plugin only arms after a confirmed reach_out dispatch; builder filters
  par1) so a label can never land on a non-reach row.
- **Write format = sharded JSONL** (stdlib, 2c2g-safe), **corpus format = parquet**
  (pyarrow, **training-side only**, never shipped to serving). Rotate JSONL at 64 MB / daily.
- **Volume**: ~300-400 B/par1-row; e.g. 50 opted-in users × ~200 assessed ticks/day ≈
  10k rows/day ≈ 3-4 MB/day raw (~1 MB zstd-parquet) — JSONL is comfortable for years.
  par2 rows are tiny and far fewer (reach ticks only).

par2 row (`PAR2_SCHEMA_VERSION=1`):
```
{schema_version:1, session_hash:str16, originating_tick:int,
 outcome:"accepted"|"ignored"|"rejected", dispatch_ts:float, observed_ts:float,
 latency_turns:int}   # no text, no event_id, no a_* (those are par1 features)
```

### 5.2 par2 cross-repo loop (SDK + plugin)

**SDK (additive, default-off):**
- `SylanneConfig`: `reach_outcome_sink: bool = False`, `reach_outcome_path: str|None = None`
  (basename under `<data_dir>/telemetry`), reusing `training_data_salt` (must match par1
  salt for joinability — `__post_init__` warns if par2 on while par1 off).
- New `Par2Sink` + `engine._build_par2_sink()` (mirrors `_build_telemetry_sink`).
- **One** new engine-public method — the unified, reconciled signature:
  ```python
  async def report_reach_outcome(
      self, session_id: str, originating_tick: int,
      outcome: Literal["accepted","ignored","rejected"], *,
      dispatch_ts: float|None=None, observed_ts: float|None=None,
      latency_turns: int=-1, apply_online: bool=False,
  ) -> bool:
      """Persist the par2 corpus label (default). If apply_online=True, ALSO route
      to host.kernel.computation.feedback(outcome) (the real spine bus → MetaLearner).
      Returns False (zero-cost) when the par2 sink is disabled / session unknown.
      Validates outcome enum; never calls a fabricated path."""
  ```
  **Default `apply_online=False`** → corpus-only, zero runtime mutation (lowest risk).
  `apply_online=True` is the explicit opt-in that closes the online residual loop.
- **Additive read-only surface**: `host_payload['originating_tick'] = self.turns` and
  `host_payload['guard_allowed'] = bool(last_guard["allowed"])` so the plugin arms par2
  with the exact join key without reaching into kernel internals. (Adding keys is
  vendor-audit-confirmed safe; existing readers ignore extra keys.)

**Plugin (`Sylanne-next`, additive):**
- New `SessionStateStore` container `awaiting_par2_outcome: BoundedDict(maxsize=50)`,
  persisted under a new `'par2'` subsystem key (atomic save), restored on session load.
- **Arm** exactly once, when `ProactiveBridge.dispatch()` returns `{"dispatched": True}`
  AND `host_payload.should_send` AND `guard_allowed` AND `decision.action=='reach_out'`.
  Store `{originating_tick, dispatch_ts, session_key, ttl_deadline}`.
- **Resolve** at `on_message` (`main.py:1106`, earliest signal) or a periodic timeout
  sweep. Classify from the **reply tick's existing assessment** (no extra LLM call):
  - `accepted` = substantive reply within window + positive engagement (length /
    continuation / non-dismissive flags),
  - `rejected` = explicit dismissal / stop / annoyed flag,
  - `ignored` = no reply before `ttl_deadline` (timeout sweep; startup sweep drains
    sidecars after restart).
  Then pop and `await engine.report_reach_outcome(...)`.
- **Capability negotiation**: top-level `SYLANNE_CAPABILITIES` frozenset (e.g.
  `"reach_outcome_v1"`) + a vendored-version pin; the plugin feature-detects before
  calling, so a new vendored SDK never breaks an old plugin and vice versa.

### 5.3 Student model & offline training

- **Model** (`StudentMLP`, ~12-40K params): `Linear(30→128) tanh → Linear(128→64) tanh`
  then three heads: `action_head(64→6)` softmax, `reach_head(64→1)` calibrated sigmoid,
  `affect_head(64→4)` auxiliary (reproduce `a_*`). Per-tick i.i.d. tabular — no
  attention/recurrence (30 unordered numeric features have no sequence structure;
  `f_affect_debt`/`f_cooldown` already encode history as scalars).
- **Supervision (reconciled, no fabricated KD)**:
  `L = CE(action) + λ_r·BCE(reach) + λ_a·SmoothL1(affect) + λ_kd·MSE(affect, teacher_soft)`.
  Action head is supervised on `decision_action` (the deterministic kernel oracle).
  The **teacher provides affect soft-targets only** (it is text→emotion, has **no action
  head**); `λ_kd=0` if no teacher checkpoint is located. par2 outcomes enter as an
  **optional reach-head re-weighting** term, never a wound-delta reward.
- **Bootstrap data**: run the real kernel **headless** with `training_data_sink=True` over
  domain-randomized stimulus streams → genuine par1 rows with **true** oracle labels,
  before real opt-in data exists. Mix in real par1 later, gated by a covariate-shift (KS)
  check on marginals so a sim-only model is never promoted to real traffic blindly.
- **Split GROUPED by `session_hash`** (no session straddles train/val/test) — enforced in
  `build_corpus.py`, asserted in `eval.py`.
- **New package** `training/student/`: `simulate_corpus.py`, `build_corpus.py` (→ parquet
  + manifest), `model.py`, `train.py` (AdamW + CosineAnnealingLR, multi-task, group-split,
  early-stop on val action-agreement), `quantize.py` (PTQ + optional QAT), `export.py`
  (state_dict → int8 `.npz` + manifest), `eval.py` (gate runner), `registry.py`. Old
  text-perception scripts move to `training/legacy/`.

### 5.4 Serving @ 2c2g

- **Runtime = pure numpy** (`StudentRuntime` / `NumpyStudent`, `sylanne_core/student/`),
  loaded from int8 `.npz`, in-process, **no thread** (forward ≈ 4K MACs ≈ single-digit µs
  ⇒ runs inline in the async loop). Justification vs onnx/ggml in §7.
- **Shared read-only** weights loaded once. **Per-session residual = existing
  `MetaLearner`** state mapped to a small **6-logit bias** (`|bias| ≤ ~1.5` logits),
  bounded by MetaLearner's elastic ≤30% drift cap. The residual rides the **existing**
  snapshot (`computation.to_dict()` already serializes `meta_learner`) — **no new
  per-session model state, no schema bump**. (A runtime-only `_student_runtime` field on
  the kernel mirrors `_telemetry_sink`; an additive `_student_residual` 6-vec is the only
  optional new snapshot key, default `None` ⇒ heuristic-equivalent.)
- **Integration at `EngineFacade`** (the unused slot), **not** by editing
  `SylanneAlphaHost` or the frozen API. The student outputs a policy distribution the
  kernel maps to an action; `_guard`/cooldown/budget/sovereignty/par1-capture all unchanged.
- **Graceful degradation** is a start-time state machine: load `.npz` → verify `sha256` →
  1-row int8-vs-reference **parity self-test** → `ready`; any failure ⇒ `backend='heuristic'`,
  plus a per-tick `try/except` falling to `_decide()`. "No model" / "model off" is
  behaviorally identical to today.
- **Online teacher loop**: the remote assessor's `a_*` feed the student's **features**
  (never the reward); par2 discrete outcomes feed `MetaLearner.update()` via
  `report_reach_outcome(..., apply_online=True)`. No backprop at serving.

---

## 6. Interfaces & schemas (summary)

| Surface | What | Compatibility |
|---|---|---|
| `SylanneConfig` | `+reach_outcome_sink:bool=False`, `+reach_outcome_path:str\|None=None`, `+student_model_enabled:bool=False`, `+student_model_path:str\|None=None` | additive, safe defaults |
| `SylanneEngine` | `+async report_reach_outcome(...)`; `+SYLANNE_CAPABILITIES` | additive, default-off |
| `host_payload` | `+originating_tick:int`, `+guard_allowed:bool` | additive read-only keys |
| kernel snapshot | `+_student_residual:list[float]\|None` (optional) | `dict.get` default `None`, no schema bump |
| `Par2Sink` | new internal writer, `reach_outcomes.jsonl` | internal, not in `__all__` |
| `StudentRuntime` | new internal numpy runtime | internal, not in `__all__` |
| Plugin | `+awaiting_par2_outcome` store, `+'par2'` subsystem, arm/resolve/classifier, `EngineFacade` student wiring | downstream, owner-driven |

Student `.npz` (`STUDENT_SCHEMA_VERSION=1`): per-layer int8 weights + f32 scales/biases,
`feature_mean/std[30]`, `feature_order` (== `AFFECT_CONTEXT_FIELDS ++ a_*`), `class_order`
(== 6 actions), `reach_temperature`. Sidecar `manifest.json`: `model_id`, semver,
`feature_schema_version`, `data_hash`, `git_sha`, `seed`, torch/cuda versions, gate
results, `promotion_state`, `parent_model_id`, `sha256`.

---

## 7. Recommended tech stack (with justification)

| Layer | Choice | Why |
|---|---|---|
| Training | **PyTorch** (AdamW + CosineAnnealingLR), owner local GPU only | reuses `train_model_torch.py` + `export_to_numpy()`; cost-free; never shipped |
| Quantization | **int8 per-tensor symmetric** PTQ (+ optional QAT) | `w_f32 = scale·w_i8` trivial in numpy; ~4× shrink; precedent in `EmotiCoreStudentLite`; gated by parity test |
| Model format | **`.npz`** (`np.savez_compressed`) + `manifest.json` | proven in-repo (`perception_v1.npz`); self-describing; one mmap-friendly load; no protobuf/onnx graph |
| Serving runtime | **pure numpy** `NumpyStudent` | **no torch (~300-400 MB)**, no onnxruntime (~15-40 MB + native dep + per-session arena RAM) — for a <50 KB / 4K-FLOP MLP the graph-opt benefit is **noise** while the dep cost is real against 2 GB. numpy is already a dep. |
| Online residual | **existing `MetaLearner`** | already does `accepted/rejected/ignored` + elastic reg + serialization; reinventing risks the "no backprop at serving" rule |
| Eviction/persist | **existing `AlphaRuntime`** atomic snapshot + `BoundedDict` LRU | recon-confirmed idle-evict mechanism; residual rides it |
| par2 writer | **stdlib JSONL** `Par2Sink` | byte-for-byte the GREEN-audited `DistillationSink` pattern; zero deps; crash-safe lines |
| Offline corpus | **parquet (pyarrow)** + zstd, sharded | columnar projection / predicate pushdown / repro shards; **training-side only** |
| Registry | flat `models/` + `manifest.json` + SHA-256 (Git-LFS for `.npz`) | no MLflow/W&B server fits a solo, local, offline workflow; manifest + hash = repro + provenance |
| Tests/lint/types | **pytest + pytest-asyncio** (`asyncio_mode=auto`), **ruff(+ASYNC)**, **mypy --strict** | AstrBot dev standard §10/§11; SDK already mypy-strict |

**ONNX / ggml are explicitly rejected** for v3.0 serving and kept only as a documented
escape hatch if a future student exceeds ~1-2M params or adopts sequence-over-ticks modeling.

---

## 8. Phased rollout (all reversible; kill switch = config flag → `_decide`)

| Phase | Work | Gate to advance | Reversible? |
|---|---|---|---|
| **P0 Collect** | owner vendors `next-gen` (separate session); enable `training_data_sink` (+ par2 sink); accumulate corpus | corpus rows ≥ N, par2 coverage ≥ M% | yes (flag off) |
| **P1 Bootstrap-train** | headless sim corpus → train StudentMLP → int8 `.npz` + manifest | full **gate suite** (below) on held-out test | n/a (offline) |
| **P2 Shadow** | student infers but **does not act**; log student-vs-`_decide` and student-vs-assessor agreement on real traffic | rolling agreement ≥ floor over a window; covariate-shift KS ≤ threshold | yes |
| **P3 Canary** | student acts for a small session subset behind `student_model_enabled` + canary % | canary agreement/SLOs hold; no guard-divergence regressions | yes (flag/percent) |
| **P4 Promote** | student default for affect+timing map; `MetaLearner` residual on via `apply_online=True` | sustained SLOs; auto-rollback armed | yes (instant flag → `_decide`) |

**Model acceptance gate suite** (all must pass on the held-out, session-grouped test split,
run on the **int8** artifact): action-agreement vs `_decide` ≥ 0.97 (with per-class
`reach_out` recall reported, not just accuracy); reach ECE ≤ 0.05; replay guard-decision
divergence ≤ 0.5%; p99 inference latency ≤ 1 ms (CI); RSS delta < 5 MB; int8-vs-f32
argmax-agreement ≥ 99%; no session-hash leakage; covariate-shift KS ≤ threshold. **Auto-rollback**:
if rolling student-vs-`_decide` agreement drops below the floor over a window in P3/P4,
flip back to `_decide`.

**Vendor cutover (owner, separate session)** — the safe procedure: (1) back up
`sylanne_alpha/_engine/sylanne_core`; (2) replace the **whole directory** atomically with
`next-gen` (never file-by-file — a half-new tree calls `set_telemetry` on an old kernel →
`AttributeError`); (3) keep the assessor knob in its current state (a swap is behaviorally
inert unless assessor is on); (4) smoke test: process one message, assert no exception +
capability present; (5) rollback = restore the backup dir.

---

## 9. Engineering standards & conventions

- **Commits/branches** (AstrBot §9): Conventional Commits, English subject+body,
  trunk-based short-lived `feat/`/`fix/`/`docs/`/`chore/` branches, squash-merge.
  v3 integration line = `next-gen`.
- **Lint/types** (§10): `ruff format` + `ruff check` (add **ASYNC** ruleset),
  `mypy --strict` on `sylanne_core`; pure-logic helpers fully typed.
- **Tests** (§11): pytest + pytest-asyncio (`asyncio_mode=auto`); fakes for LLM + proactive
  plugin; frozen-clock fixture for timeout sweeps.
- **Data governance**: opt-in default-off (`training_data_sink`, `reach_outcome_sink`); no
  PII / no raw text / no network egress; `0o600` files; salt stored **outside**
  `<data_dir>/telemetry`; `salt_fingerprint = SHA-256(salt)[:8]` in each manifest so the
  builder fails loud on cross-salt joins; documented retention window; **right-to-deletion**
  by appending the anonymized `session_hash` to a tombstone file (builder excludes; a
  compaction pass physically purges raw shards within an SLA).
- **Model registry / reproducibility**: every `.npz` carries a `manifest.json`
  (semver + `sha256` + feature/class order + `data_hash` + `git_sha` + seed + env);
  promotion = moving a `current` pointer; a `feature_order` mismatch at load forces
  degradation (prevents feeding a misordered vector).

---

## 10. Observability (stdlib-only, no network egress)

Metrics emitted to a local JSONL metrics log + an in-process counter snapshot surfaced via
the existing `engine.health()` / diagnostics: corpus growth (par1/par2 rows/day, par2
label coverage %, class histogram), student health (inference p50/p95/p99 latency, fallback
rate, int8 parity), agreement (student-vs-`_decide`, student-vs-assessor, drift of the
per-session residual), resource (RSS delta, host-eviction rate), and governance counters
(tombstone count, orphan-label count). Optional `prometheus-client` only if the owner
already runs Prometheus — off by default.

---

## 11. Testing strategy

- **Unit**: `Par2Sink` (write/disabled/no-PII/traversal/rotation), `report_reach_outcome`
  (enum validation, default-off zero-cost, `apply_online` routing), `NumpyStudent`
  (numpy==torch parity within 1e-4 + argmax-identical, int8 dequant, residual bias add).
- **Integration**: arm→resolve par2 across a fake proactive send + fake reply; restart
  between dispatch and reply resolves via sidecar; `reset()` mid-wait drops the entry
  (no mis-join); the par2 row's `originating_tick` equals the par1 `reach_out` tick.
- **Contract**: introspect `process/feedback/snapshot/restore` signatures + result keys
  unchanged with student/par2 enabled; snapshot round-trip with `_student_residual`
  byte-stable; an **old** snapshot (no key) restores cleanly.
- **Eval/gates**: the full §8 gate suite in CI on a fixture model.
- **Load**: `asyncio.gather` over N synthetic sessions measuring p50/p95 latency + RSS
  under the 2 vCPU / 2 GB budget.

---

## 12. Risks & mitigations (top)

| Risk | Mitigation |
|---|---|
| Two send paths double-count par2 | arm **only** on `bridge.dispatch()=={dispatched:True}` (budget path); assert arm-count == confirmed-send count |
| Restart loses in-flight attribution | atomic sidecar at arm time + startup sweep resumes timeout accounting |
| `reset()` tick reuse mis-joins | drop awaiting entries on `reset()`; builder `(session_hash, tick)` unique-latest dedup |
| Train/serve numerical divergence | mandatory CI parity test (numpy==torch, argmax-identical) gates the model build |
| Corpus scarcity at launch | bootstrap via headless kernel sim (true oracle labels), then mix real par1 under a KS gate |
| Salt mismatch silently empties join | par2 reuses `training_data_salt`; builder verifies `salt_fingerprint` across shards, **fails loud** |
| Residual drift → degenerate always-reach | MetaLearner elastic 30% cap + logit clamp + drift circuit-breaker resets residual |
| Snapshot/contract drift | shared read-only student, no required new snapshot field; round-trip CI test both directions |
| No teacher checkpoint | affect head trains on `a_*` alone (`λ_kd=0`); teacher KD optional |
| **Oracle-imitation low value** | if `_decide` is already cheap, the student's win is only calibration + residual substrate — see Decision D-1 |
| Right-to-deletion completeness | tombstone excludes at build + scheduled compaction purges raw shards within SLA (deletion by anonymized hash) |
| Vendored-version skew | `SYLANNE_VENDOR_VERSION` pin + `SYLANNE_CAPABILITIES` feature-detect + post-cutover smoke test |

---

## 13. What is reused vs built-new

- **Reuse (do not rebuild)**: `DistillationSink` + par1 schema; `MetaLearner` residual;
  `train_model_torch.py` `export_to_numpy()`; `EmotiCoreStudentLite` NumpyInference/int8
  pattern; `AlphaRuntime` atomic snapshot + LRU eviction; `corpus_labeled.jsonl` (1M rows,
  teacher-labeled) for the **corpus-labeler** role.
- **Build new**: `Par2Sink` + `report_reach_outcome` + the 2 host_payload keys (SDK);
  `awaiting_par2_outcome` store + arm/resolve/classifier + `EngineFacade` student wiring
  (plugin); `StudentMLP` + `training/student/` package; `NumpyStudent` serving runtime;
  the offline `build_corpus.py` join + parquet; the registry + gate suite + observability.
- **Supersede** (move to `training/legacy/`): `generate_data.py`, `train_model*.py`,
  `perception_v1.npz` (text→emotion, wrong task). `EmotiCore` stays as the corpus labeler.
- **Recover/decide**: `EmotiCore`/`sylann_v3` source is `.pyc`-only — rewrite the ~30-line
  NumpyInference/int8 helper rather than decompile; locate the external v2.1 teacher.

---

## 14. Open decisions for the owner (genuine forks)

- **D-1 (scope — the big one):** Is the student the **narrow** affect+timing policy
  (imitate `_decide`; safe drop-in; this TDD) or the **broad** learned core that **replaces
  the whole resonance tick** (the original v3 "real brain" vision)? Recon says the tick is
  already cpu-cheap, so the narrow student's value is mostly *calibrated reach probability +
  a differentiable substrate for the residual*, not raw speed. **Recommendation:** ship
  narrow for v3.0 (low risk, proves the corpus→train→serve→online loop), gate broad as v3.1.
- **D-2 (online loop timing):** Does `report_reach_outcome` run **corpus-only**
  (`apply_online=False`) for v3.0, with online `MetaLearner` routing deferred — or close the
  online loop immediately? **Recommendation:** corpus-only first (no runtime mutation),
  flip `apply_online=True` at P4.
- **D-3 (acceptance SLOs / asymmetry):** the numeric promote bars, and is **false-silence**
  (stay quiet when she should reach out) worse than **false-reach**? This weights
  `reach_out` recall vs overall agreement — a personality/UX call.
- **D-4 (governance):** retention window for raw shards; opt-in disclosure wording for
  multi-user data; minimum-N before a real-data student may be promoted.
- **D-5 (`ignored` semantics):** the timeout (default: next user message OR 4 h) that
  decides when silence becomes `ignored` — encodes her patience/clinginess and shapes the
  class balance.
- **D-6 (teacher):** locate the external v2.1 teacher checkpoint (enables affect-KD), or
  accept `λ_kd=0` (affect head on `a_*` alone).

---

## 15. Appendix — key file pointers

SDK (`G:\SylannEngine`): `sylanne_core/telemetry/sink.py:37` (`AFFECT_CONTEXT_FIELDS`),
`compute/kernel.py:927` (`_capture_telemetry`), `:988` (`_decide`), `:895`
(`_reach_threshold`), `compute/meta_learner.py:198` (`update`), `compute/host.py:146`
(`on_proactive_check`), `compute/resonance_integration.py:795` (spine `feedback`),
`engine.py:383` (`_build_telemetry_sink`), `config.py:183` (config), `training/` (superseded
text stack + `EmotiCore` `.pyc` + 1M-row corpus).
Plugin (`G:\Sylanne-next`): `sylanne_alpha/engine_adapter.py:129` (`EngineFacade`),
`:34` (`SEND_ACTIONS`), `proactive_bridge.py:301` (`dispatch`), `main.py:1106` (`on_message`),
`session_state_store.py` (stores), `state_persistence.py` (`_VALID_SUBSYSTEMS`).
