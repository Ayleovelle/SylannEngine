# v3 Real-Data Collection + Probe Re-Run Harness — Specification

- Status: DRAFT for ratification. Author track: v3 student core (BroadCore-S / PEL-Core).
- Companion to: `docs/design/adr-0001-v3-core-go-no-go.md` (the decision this spec executes),
  `docs/design/v3-student-pipeline-tdd.md` (TDD v4 §9), `training/student_core/RESULTS.md`.
- Date: 2026-06-25.

## 0. Why this artifact exists (spike verdict) + the P0 boundary

The pre-P0 spike (`RESULTS.md`) returned a deliberate non-verdict: a learned core reading the message
decodes the assessor's read far better than the field's **fixed pre-nudge transform** (Probe 2,
0.209 vs 0.533), **but** (a) that win does **not** beat trivial persistence on the realistic
autocorrelated slice (0.200 vs 0.197), (b) the binding field+nudge baseline was never run, and (c)
everything is synthetic data where the message was constructed to carry the latent. The field is
simultaneously the data generator and the baseline, so it cannot produce data proving its own
replacement wins (ADR §1). Verdict consequence: **collect real assessor-labeled traffic and re-run
the probes on it.**

**The P0 boundary (stated identically in ADR §4).** Everything in this spec — the CORE2 sink, the
salt fix, the JSONL→parquet adapter, the probe additions — is **Phase-0-collection: authorized,
additive, default-off, NOT P0.** P0 (the cell / distillation / online-residual / serving-int8 / brain
re-distillation / cost-gating / kill program) stays **gated** behind the real-data result. This spec
builds the *instrument that reads the gate*, not the thing behind it.

This document specifies four artifacts:
1. **CORE2 capture schema** — the real-traffic equivalent of `simulate_corpus.py`'s per-tick log.
2. **Privacy & governance sequencing** — what MUST land before a single real row is written.
3. **The probe re-run harness** — how the probes consume real CORE2 data (with the two additions the
   spike's probes are missing).
4. **The cross-repo deploy runbook** — HELD; not executed until the owner's explicit go.

Invariant: the real CORE2 parquet must present **byte-identical column names, dtypes, and
list-widths** to what `simulate_corpus.py` emits, so the probes run with minimal edits (the two
*additions* in §3.4 are the only probe changes, and they are additive — they do not alter the
synthetic-path columns).

---

## 1. CORE2 capture schema

### 1.1 Columns the probes consume (ground truth)

`spike_ntap.load_sessions` (`spike_ntap.py:41-66`) and the inline re-derivation in
`spike_predict_assessor.main` (`spike_predict_assessor.py:132-154`) read these columns from the
parquet, grouped by `session`, sorted by `tick`:

| column | width | read at | consumed by |
|---|---|---|---|
| `session` | 1 (group key) | `spike_ntap.py:45`, `:132` | session grouping + split |
| `is_iid` | 1 bool | `spike_ntap.py:50` | autocorrelated-vs-control split |
| `tick` | 1 int | `sort_values(["session","tick"])` | temporal order |
| `ts` | 1 float | `spike_ntap.py:57-60` | `dt = log1p(clip(diff(ts)/60,0,60))` |
| `a_valence,a_arousal,a_wound_risk,a_confidence` | 4 | `spike_ntap.py:51` | targets |
| `surprise` | 1 | `spike_ntap.py:52` | feature |
| `z_prev` | 8 (list) | `spike_predict_assessor.py:145` | message-only feature |
| `base_pre_nudge` | 8 (list) | `spike_predict_assessor.py:146` | Probe-2 field-pre-nudge baseline (idx `[2,1]`) |
| `z_post` | 8 (list) | `spike_ntap.py:53` | field+nudge baseline input |
| `scar_mod` | 8 (list) | `spike_ntap.py:54`, `:147` | feature |
| `hdc8` | 8 (list) | `spike_ntap.py:55` | V4 message-bandwidth ablation |
| `hdc64` | 64 (list) | `spike_ntap.py:56` | Vfull message-bandwidth ablation |

WIDE HDC width = 64 per D-12 (on synthetic data V0 0.250 → V4 0.244 → Vfull 0.209; the 4–8-float
bottleneck loses the *injected* latent — the *real-text* size of this effect is unknown until CORE2).
CORE2 logs **both** `hdc8` and `hdc64` so the real-data run can re-measure the gap.

### 1.2 CORE2 per-assessed-tick row (the capture target)

One row per **assessed** tick (an assessor call happened; skipped ticks have no `a_*` label and are
not rows). Leakage-free: every field is computable from information available at or before the field
consumes *this* tick's assessment; nothing reads a future tick.

```
CORE2 row (FEATURE_SCHEMA_VERSION = 2):
  # --- envelope (stamped by sink.record_tick, NOT the kernel) ---
  schema_version : int            # == 2 for CORE2
  session_hash   : str(16-hex)    # salted SHA-256(session_key); raw key never written
  assessor_version : str          # NEW (digest V3): freeze-and-record; STOP campaign on change

  # --- temporal / grouping ---
  tick           : int            # self.turns
  dt             : float          # inter-assessed-tick elapsed SECONDS (raw; the probe applies
                                  #   its own log1p/clip — store raw, the adapter rebuilds ts)

  # --- field state (the learned core's recurrent surface) ---
  z_prev         : list[float](8) # base BEFORE _evolve_base (prior committed base = z_post of t-1)
  base_pre_nudge : list[float](8) # base AFTER _evolve_base, BEFORE the assessment nudge
  z_post         : list[float](8) # base AFTER the nudge = the existing par1 emotion 8 (see §1.3)
  scar_mod       : list[float](8) # per-dim scar modulation scalars
  surprise       : float          # field surprise for this tick

  # --- assessor labels (targets) ---
  a_valence,a_arousal,a_wound_risk,a_confidence : float

  # --- decision metadata (NOT a model input) ---
  decision_action: str            # self.last_decision["action"]

  # --- message: HDC density ONLY, WIDE per D-12 ---
  hdc8           : list[float](8)
  hdc64          : list[float](64) # NEVER raw text, NEVER an invertible sentence embedding
```

`is_iid` and the latent `mood` are **synthetic-only** and never captured. Real data has no planted
control flag; the harness derives an autocorrelated/control split empirically (§3.3) and materializes
an `is_iid` column the probes read.

### 1.3 Field → kernel-tick capture map

Citations marked **[verified]** are confirmed against the current code (citation truth table);
citations marked **[PROPOSED]** are *capture points for code that does not yet exist* — they are
design targets, not verified anchors. The kernel tick is `sylanne_core/compute/kernel.py`; the spine
is `resonance_integration.py`.

| CORE2 field | in v1 sink? | capture point | leakage-free rationale |
|---|---|---|---|
| `session_hash` | yes | `telemetry/sink.py:153` **[verified]** | salted hash; raw key never written |
| `schema_version` | yes (=1→2) | `telemetry/sink.py:152` **[verified]** | bump to 2 |
| `tick` | yes | `kernel.py:951` **[verified]** | counter |
| `a_*` (4) | yes | `kernel.py:978-981` **[verified]** | this tick's assessor read (the target) |
| `surprise` | yes (`f_surprise`) | `kernel.py:963` **[verified]** | post-process, this tick |
| `decision_action` | yes | `kernel.py:982` **[verified]** | decided this tick |
| `z_post` (8) | **reuses `f_*` emotion** | `kernel.py:298 → _capture_telemetry (:927)` **[verified]** | par1 already logs the committed emotion 8; CORE2 maps them to `z_post` (rename, not new capture) |
| `z_prev` (8) | NEW | read `scar_state.base` BEFORE `computation.process(...)` (`kernel.py:265-270`) **[PROPOSED]** | prior base before `_evolve_base` mutates it |
| `base_pre_nudge` (8) | NEW | `_CaptureSpine` override snapshots `scar_state.base` on entry to `_apply_assessment_to_engine` (`:588`), after `_evolve_base`, before the in-place nudge (`:625-633`) **[PROPOSED; pattern verified in `simulate_corpus.py:60-72`]** | mid-process, pre-nudge |
| `scar_mod` (8) | NEW | `[scar_state.modifier(d) for d in range(8)]` after `process()`, before `_capture_telemetry` **[PROPOSED]** | post-process modifier |
| `dt` (raw s) | NEW | `event.now − previous_event["now"]`, after `previous_event` updates, before capture **[PROPOSED]** | elapsed time, no future info |
| `hdc8`/`hdc64` | NEW | `density_features(encoder.encode_text(text), {8,64})` from the current message, at/before `process()` **[PROPOSED]** | current message only; density does not reconstruct text (claim **unverified** — see §2.4) |

**Genuinely new numeric surface beyond the v1 sink:** `z_prev`(8) + `base_pre_nudge`(8) + `scar_mod`(8)
+ `hdc8`(8) + `hdc64`(64) + `dt`(1) = **97 new dims**. `z_post`(8) is **not** new — it is the existing
par1 emotion 8, re-exposed under the `z_post` name (exact equivalence of "observe() emotion" vs
"post-nudge `scar_state.base`" is to be **asserted by a parity test at schema ratification**, not
assumed). The exact final count is pinned when the schema is frozen (runbook step 1).

**Implementation note.** `base_pre_nudge` cannot be read from `_capture_telemetry` alone: base is
mutated in place inside `_apply_assessment_to_engine` (`:625-633`) and `ScarredState` uses
`__slots__`, so the snapshot must be taken inside the spine via the subclass-override pattern the
spike validated (`simulate_corpus.py:60-72`). The CORE2 sink therefore ships a thin capture-spine
seam, not a post-hoc reader.

### 1.4 Forward-only, append-only schema discipline

The v1 sink already encodes the discipline (`telemetry/sink.py:32-33`; `AFFECT_CONTEXT_FIELDS`
`:37-64`). CORE2 extends it, adding no new mechanism:

- **Bump `FEATURE_SCHEMA_VERSION` 1 → 2** (`telemetry/sink.py:33`); every later change bumps again.
- **Append only.** New fields append to the row dict and the canonical column list; the stable key
  order is **extended, never reordered or edited in place**.
- **Mixed-corpus rule — one mechanism, not two.** v1 rows lack the 97 dims; the
  `core2_to_corpus.py` adapter (§3.2) **excludes v1 rows from probe parquets** (a probe needing
  `hdc*`/`base_pre_nudge` cannot use them). The append-only column list is for the *offline matrix
  assembler*; the probe path simply drops `schema_version < 2`. (The earlier draft's "null-fill
  up-projection *and* exclude" was redundant — exclusion is the single load-bearing rule for probes.)
- **Input vs label vs metadata.** Inputs: `z_prev, base_pre_nudge, z_post, scar_mod, surprise, hdc8,
  hdc64, dt`. Labels: `a_*`. Metadata: `tick, session_hash, assessor_version, decision_action,
  schema_version`. `AFFECT_CONTEXT_FIELDS` (the model-input emotion/body feature tuple) is extended
  for the new *inputs* only; labels/metadata stay outside it.

---

## 2. Privacy & governance sequencing

Real CORE2 traffic is **multi-user, content-sensitive data**. The richest re-identification surface
is `(session_hash, base_pre_nudge, a_*)`: `base_pre_nudge` is a persistent per-session fingerprint
(an 8-float compression of prior interaction history), `a_*` are assessor outputs one step from raw
semantics, and the HDC vectors encode semantic structure. None of this may be collected until the
items below land, **in order**.

### 2.1 R1 PREREQUISITE — fix the salt (D14 correction) — BLOCKS ALL COLLECTION

The config docstring (`config.py:203-205`) claims *"If empty, a per-process random salt is used."*
**This is false.** `anonymize_session` (`telemetry/sink.py:74`) computes
`SHA-256(f"{salt}:{session_key}")` with the salt passed through unchanged; with the default
`training_data_salt=""` (`config.py:217`) there is **no per-process random salt anywhere** — the hash
is `SHA-256(":"+session_key)`, **deterministic and globally stable across every process and
deployment**, violating the contract's "cannot be correlated across deployments"
(`telemetry/sink.py:70-73`). This is the D14 reversal: empty salt is **stable / cross-deploy-linkable**,
not random. The fix MUST land in `sylanne_core` before any collection, picking exactly one:

- **(a) per-process-random-on-empty:** generate a random salt at sink construction
  (`secrets.token_hex`) when empty. Makes the docstring true; cross-run grouping is intentionally
  unstable — **and deletion-by-`session_hash` becomes impossible** (the salt is unknown/unstored).
- **(b) refuse-enable-on-empty:** raise at construction when `training_data_sink=True` and
  `training_data_salt==""`. Fail closed.

**Governance resolution of the (a)/(b) conflict (closes a draft gap):** real *deployment* collection
(§4) **MUST use option (b) + an explicit, stable, non-empty per-deployment salt** — never empty —
*because* §2.3 right-to-deletion requires the operator to recompute `session_hash` from the salt.
Option (a) is acceptable **only for non-collecting / dev runs** where no deletion obligation exists.
Until (a)-or-(b) is merged **with tests**, collection is forbidden.

### 2.2 Default-off and at-rest protections (already partly in place)

- **Default-off.** `training_data_sink: bool = False` (`config.py:215`); a disabled sink opens no
  file and every method is a single-bool no-op (`telemetry/sink.py:115`, `:149`).
- **0o600** dataset file on POSIX (`telemetry/sink.py:124-126`).
- **Path confinement** to `<data_dir>/telemetry` (`_resolve_under_base`, `telemetry/sink.py:78-88`).
- **No network egress** — stdlib file append only.

### 2.3 Governance the harness adds

- **Consent as a sink-enable PRECONDITION (not a policy note).** A per-session consent flag must be
  present/true before any row is written; absent consent → no row (fail closed), the same way the
  salt fix gates enablement. Multi-session boxes may mix consenting and non-consenting users under one
  deployment salt; the per-session consent gate is what prevents collecting the latter. "Disclosure
  exists" is **enforced**, not assumed.
- **Retention window + tombstone / right-to-deletion (best-effort, scoped honestly).** Rows past the
  retention window (proposed 90 days; ratify per deployment) are purged by a rotation job. A deletion
  request resolves to a `session_hash` the **operator** recomputes from the user-presented session
  identifier + the deployment's stable salt (option (b)); matching rows are tombstoned. **Two honest
  limits:** (i) under option (a) this is impossible (§2.1); (ii) **affect already distilled into a
  shipped core cannot be un-baked** — tombstones cover raw logs only, so a retention/eligibility
  window must gate rows *before* distillation and post-distill deletion is best-effort.
- **Minimum-N before promotion.** No re-distilled core trained on real CORE2 may promote to any
  downstream until the corpus reaches the ADR §6 pilot-derived minimum-N on **held-out sessions** and
  both probes clear the §3.4 PASS bar. Below that, a trained core is a research artifact only.

### 2.4 HDC inversion / re-identification — UNVERIFIED, must test before enabling

The claim "`hdc8`/`hdc64` density never reconstructs raw text" is **asserted, not tested**, and it is
load-bearing for the entire privacy posture (a 64-float semantic vector + the `base_pre_nudge`
fingerprint may be more linkable than claimed). **Verification task (precondition of enabling
collection):** empirically test nearest-neighbour recovery / linkage of `hdc64` against a message
bank; treat "non-invertible" as **unproven** until it passes. If it fails, narrow the HDC width or
the capture.

---

## 3. The probe re-run harness

### 3.1 Core principle: probes run with minimal, additive edits

`spike_ntap.py` runs **unchanged**. `spike_predict_assessor.py` runs unchanged **except** for the two
*additions* in §3.4 (a steelmanned field+nudge baseline and a coded PASS gate — neither exists
today). The additions do not alter the columns the synthetic path uses. The harness otherwise only
**converts CORE2 JSONL into the exact parquet** and **enforces the leakage guards** the synthetic
generator gave for free.

### 3.2 JSONL → probe-parquet adapter (the main new code)

`training/student_core/core2_to_corpus.py` (new) reads the appended JSONL and emits a parquet with
exactly the §1.1 columns. All mechanical:

- Map `session_hash` → dense integer `session` id so `groupby("session")` matches the synthetic path.
- Pass through `tick, a_*, surprise, z_prev, base_pre_nudge, z_post, scar_mod, hdc8, hdc64`
  unchanged (names + list-widths).
- Synthesize `ts` from `dt`: cumulative-sum `dt` per session gives a monotone `ts` whose `np.diff`
  reconstructs the same `dt`, so the probe's existing `log1p(clip(diff(ts)/60,...))` transform
  (`spike_ntap.py:57-60`, `spike_predict_assessor.py:150-152`) is preserved untouched.
- Materialize `is_iid` empirically (§3.3).
- Drop sessions with `< 3` ticks up front (the probes drop them anyway: `spike_ntap.py:47`,
  `spike_predict_assessor.py:138`) so power-analysis counts are honest.
- **Exclude `schema_version < 2` rows** (§1.4).

### 3.3 Leakage guards (enforced by the harness, verified, not assumed)

- **Session-level split.** The probes split by session index, not row (`spike_ntap.py:247-250`,
  `spike_predict_assessor.py:157-160`). The harness **asserts no `session` id is in both partitions**
  before handing over the parquet. Primary guard — without it within-session autocorrelation leaks.
- **Prediction-vs-input decorrelation, tightened.** `a_{t+1}` (NTAP target) is injected into nothing
  at `t`; but on real data **`z_prev` carries the previous tick's assessor nudge** (the nudge writes
  `a_*` into base every assessed tick, and `z_prev` = `z_post` of `t-1`), so `a_{t-1}` legitimately
  enters the inputs. That is signal (it is why persistence is the binding baseline), **not** target
  leakage — but a capture bug could leak the *current* `a_t` into an input. Guard: compute
  `corr(prediction, each a_*-bearing input column)` on held-out and **flag at > 0.7, abort at >
  0.95**; additionally run an explicit check that no input column equals the current-tick `a_*`
  within float tolerance.
- **Field-ablation control (new — closes a red-team gap).** Before trusting any Probe-2 win, fit a
  baseline that predicts the target from `x_t` **without** the learned core (e.g. ridge on the raw
  inputs). If it matches the student, the "win" is reconstructable from the inputs alone and is not
  evidence the core adds anything — investigate before claiming value.
- **Variance floor.** Reject feature columns with held-out variance `< 1e-6` (constant column = capture
  bug). **Note honestly:** `1e-6` catches only *exactly-constant* columns, not low-information ones;
  it does **not** protect against a flat/degenerate assessor. A per-target minimum signal-variance
  check (ratify the threshold) is a separate, stronger guard to add if a target looks uninformative.

### 3.4 Real-data PASS bar (Probe 2 is the gate) — and the two probe additions it requires

**The PASS gate does not exist in the probe today.** `spike_predict_assessor.py` only `print`s; the
only coded gate (`rel>=0.15 AND abs>=0.02 AND rel_ac>=0.15`) is **NTAP's** (`spike_ntap.py:284`) and
it tests vs `best_base = min(persistence, field-ridge, field-gbm)`. The harness MUST add to
`spike_predict_assessor.py`:

1. **A steelmanned field+nudge baseline** (ridge + GBM on `z_post + prior a_* + surprise`, mirroring
   `spike_ntap.baseline_field`). The spike's Probe 2 ships only field-pre-nudge + persistence; the
   PASS bar requires beating the *steelmanned* baseline too.
2. **A coded PASS gate evaluated on the autocorrelated slice:**

> **PASS (real):** on real held-out **autocorrelated** sessions, the predict-assessor student
> (`Vfull`) beats **BOTH** persistence **AND** the steelmanned field+nudge baseline by **≥ 15%
> relative AND ≥ 0.02 absolute** MAE, with all §3.3 guards green.

Both clauses are required: beating persistence alone can be near-trivial; beating field-pre-nudge
alone can be the field's fixed transform, not the core's competence. **The autocorrelated slice is
mandatory** — on synthetic data the student loses to persistence there (ADR §1.4), so the realistic
slice is exactly where the bar bites.

**Skippable-fraction — an upper-bound proxy, NOT "the Phase-M ROI".** `score()['skippable']` =
`(err.max(1) < 0.1).mean()` (`spike_predict_assessor.py:108`) = fraction of held-out ticks where both
valence/arousal land within 0.1, on synthetic data. Report it as **an optimistic upper bound under a
0.1 dual-dim tolerance**, not as deployable ROI: (i) it ignores the **asymmetric cost of wrong skips**
(a missed `wound_risk` spike is not symmetric with a missed valence — a skip policy needs a
`wound_risk` floor / asymmetric-cost analysis first); (ii) realized Phase-M savings are **net of the
exploration floor** `ρ_floor` (digest C7/U3): ceiling `= (1 − ρ_floor)·gateable`, which the gross
skippable-fraction does not subtract.

### 3.5 Probe 1 (NTAP) — report-only diagnostic (reconciled with ADR §4)

**Probe 1 is a diagnostic, not a gate** (single source of truth: ADR §4). It is the
cross-tick-memory test, and the spike proved it is **un-evaluable on synthetic Markovian data**
(`a_{t+1} ≈ ρ·a_t + noise`, AR(1) on mood at `simulate_corpus.py:99` with `ρ=0.85` set at `:129`;
`a_*` derive from the mood via `synth_assessor` `:104-111` — the `a_{t+1}≈0.85·a_t` form is an
approximation, not a literal code line). Real human traffic is non-Markovian, so only real CORE2 data
can fairly ask whether cross-tick memory adds a leakage-free increment over "field + reactive nudge".
Probe 1 runs unchanged and **reports** its increment; a real-data PASS is evidence the synthetic run
*could not* produce, and it **informs** the Ring-1-vs-Phase-M-only scoping — but it does **not** by
itself block or grant GO.

### 3.6 Minimum-N / power — see ADR §6 (no number is invented here)

The collection target (sessions, not ticks — the split is per session) is the ADR §6 pilot-derived N.
**No fixed N is claimed in this spec.** The §2.3 minimum-N gate references the ADR §6 pilot output;
until the pilot measures `σ_d`, `m` (at the real assessor-call rate), and `ρ_icc`, the target is
"≥30-session pilot first, then re-derive (or escalate per ADR §6.4)."

---

## 4. Cross-repo DEPLOY RUNBOOK — HELD (NOT EXECUTED)

> **This runbook is NOT executed.** It touches the plugin repo `G:/Sylanne-next` and, once run,
> begins collecting real-user data. It runs **only** on the owner's explicit go. Listing the steps is
> specification, not authorization. Two hard-block gates appear inline: the
> **[[no-premature-downstream]]** gate (do not wire the plugin to a moving SDK target) and the
> **privacy gate** (R1 salt fix §2.1 + consent §2.3 + the HDC-inversion test §2.4) which must all
> land before any salt is set or any row is collected.

1. **Ratify the CORE2 schema (§1).** Freeze the column list, widths, `FEATURE_SCHEMA_VERSION = 2`,
   and pin the final new-dim count (incl. the `z_post`-equals-`f_emotion` parity assertion). Nothing
   moves in either repo until ratified — this is the anchor the no-premature-downstream gate protects.

2. **Land in `sylanne_core` (SDK), one ratified release, with tests:** the CORE2 sink (97 new dims +
   capture-spine seam for `base_pre_nudge`, §1.3) behind the default-off flag; **the R1 salt fix
   (§2.1)**; the **consent gate (§2.3)**; the `FEATURE_SCHEMA_VERSION` bump + append-only discipline
   (§1.4); `core2_to_corpus.py` + the §3.2–3.3 guards; the §3.4 probe additions (field+nudge baseline
   + PASS gate). Tests: salt-on-empty (refuse or random per chosen option), consent-absent no-op,
   0o600, path confinement, schema-version stamping, disabled-sink no-op.

3. **[[no-premature-downstream]] GATE.** Do NOT touch the plugin until step 2 is a **tagged, stable**
   SDK release. The plugin never vendors a moving SDK target.

4. **Atomic whole-directory vendored-SDK swap in `G:/Sylanne-next`.** Replace the plugin's vendored
   `sylanne_core` wholesale with the step-2 release. Run the plugin's test suite before enabling
   anything.

5. **PRIVACY GATE re-check + enable.** Confirm the R1 fix, consent gate, and HDC-inversion test
   (§2.4) are the versions now vendored. Set `training_data_sink = True` and a **stable, non-empty,
   per-deployment `training_data_salt`** (option (b); never empty). Complete multi-user disclosure.
   First row is written only after all of this is green.

6. **Collect to minimum-N (ADR §6).** Accumulate real assessed-tick rows until the pilot-derived N
   (held-out sessions) is reached, enforcing the retention window + deletion path (§2.3) throughout.
   Honor the assessor-version freeze (ADR §7): STOP/invalidate if the assessor version changes.

7. **Run the probes.** `core2_to_corpus.py` → probe-parquet (§3.2); then `spike_ntap.py` (unchanged)
   and `spike_predict_assessor.py` (with the §3.4 additions) against it. Apply the §3.3 guards; read
   the §3.4 PASS bar and the skippable upper bound; Probe 1 reports the now-fairly-evaluable memory
   increment (§3.5). Record GO/NO-GO in a successor ADR.

**Rollback — config side AND data side.** Config rollback halts **future** writes only:

```
git -C G:/Sylanne-next checkout -- vendor/sylanne_core <plugin-config-with-sink-flag>
```

This restores the prior vendored SDK + config (sink default-off). **It does NOT un-collect rows
already written.** On an incident-triggered rollback (e.g. salt/consent misconfig found post-hoc),
the runbook MUST **also tombstone/quarantine the corpus collected under the suspect config** via the
§2.3 deletion path — "halting collection" ≠ "undoing it." The step-2 SDK release is independently
tagged, so re-applying the swap is just re-running step 4.

**Restating the hold:** none of steps 1–7 are executed by this document. The runbook fixes the order
— ratify → SDK land (incl. salt + consent + HDC test) → no-premature-downstream gate → atomic swap →
privacy-gated enable → collect to N → run probes — so the gates fire at the right steps and rollback
(config + data) is defined.
