# TDD: SylannEngine v3 — Learned Emotional Core ("PEL-Core" / broad student)

- Status: Draft v2 (BROAD scope — supersedes the narrow-student v1 draft)
- Author: Sylanne (design), Ayleovelle (owner/reviewer)
- Last updated: 2026-06-25
- Scope: SDK `sylanne_core` (branch `next-gen`) + plugin `Sylanne-next` (`sylanne_alpha`)
- Decision log: **D-1 = BROAD** (the student replaces the emotion core, not just `_decide`);
  **(b) = brain loop committed** (the shared core continually re-distills real
  assessor-labeled traffic — *not* a one-shot clone of the field).

---

## 0. What changed from v1 (narrow) and why

The v1 draft scoped the student narrowly: a 30-feature→6-action MLP that imitates
`kernel._decide`. An adversarial review of the **broad** scope was brutally clear and the
owner accepted it: **distilling the existing resonance field is, by itself, theater** — it
clones a deterministic `seed=42` contraction MLP and *gains zero new behavior*. The only
thing that makes this a **brain** rather than a learned mask is the part the first design
**deferred**: the **shared core continually re-trained on real assessor-labeled traffic**.

This v2 commits that loop as the product. The student is **PEL-Core**: a small **recurrent
learned emotion core** that replaces the `seed=42` MLP, bootstrapped to field-parity
offline, then **kept improving by distilling the remote assessor's real affective
judgments** on live conversations, and personalized per-session online. The field is never
deleted — it is the offline distillation teacher *and* the instant runtime fallback.

**Cost trajectory (owner's observation, now a design goal):** at bootstrap the assessor
LLM call is the **same cost v1/v2 already pay** — collecting the training corpus is a free
byproduct. At maturity the core has distilled the assessor, so we **confidence-gate** the
assessor: call the LLM only when the fast core is uncertain. The brain therefore *pays for
itself* by reducing LLM calls below today's baseline (§8, Phase M).

---

## 1. Executive summary

Build **BroadCore-S**: a ~3.4K-param **recurrent** emotion cell (GRU-style over an 8-dim
emotion latent) that replaces `ScarredState._evolve_base` (the fixed `seed=42` MLP) + the
`_apply_assessment_to_engine` bias + the `observe()` readout. It produces `scar_state.base[0..7]`
(the 8-dim emotion) from **(assessor affect + HDC-of-message + prior emotion state +
time/body scalars)** — the **I/O flip**: the par1 `f_*` emotion features are now the
core's **outputs**, never its inputs. Everything downstream (the field's
void/resonance/HGT/expression machinery, `_decide`, `_guard`, par1/par2) runs **unchanged**
on the student's base.

Served as **pure-numpy int8** (`.npz` < 8 KB, sub-µs inline, **no torch**) in 2 vCPU / 2 GB /
no-GPU multi-session; it is a **latency win** (it replaces the field's iterative
Kuramoto/Hopfield `resonate()` loop). Default-off behind `student_model_enabled`; any
failure falls instantly back to the live field.

Three teaching stages: **(A) offline field-distillation** (day-1 parity, unlimited free
data from owned deterministic code), **(B) continual re-distillation of real
assessor-labeled traffic** (the brain — the shared core surpasses the field by learning the
assessor's real semantics), **(C) online per-session assessor-corrective residual** (bounded
personalization). The reward purity rule holds: par2 `accepted/ignored/rejected` drives the
**timing** loop only and **never** enters the emotion-core loss.

**This is "Ring 1"** — the smallest replacement that realizes the learned-core vision.
Ring 2 (learn the resonance block) and Ring 3 (full tick) are gated future cycles. Body /
`_decide` / `_guard` / `affect_debt` / `hot_pool` are **never** touched.

---

## 2. Goals / Non-goals

### Goals
- G1 — Replace the `seed=42` emotion MLP with a **learned recurrent core** that is
  **field-equivalent on day one** and then **improves** by distilling the assessor.
- G2 — Make it a **real brain**: commit the **continual re-distillation of real
  assessor-labeled traffic** (CORE2 stream) so the shared core exceeds the field, plus a
  bounded **online per-session** assessor-corrective residual.
- G3 — Serve **CPU-only, no-torch, < 1 MB RSS, sub-µs inline** in 2c2g multi-session;
  a **latency win** vs the field tick.
- G4 — **Additive / default-off**, GREEN-frozen public API intact, snapshot/restore
  backward-compatible, field retained as teacher + instant fallback.
- G5 — **No split-brain**: the same backend drives BOTH the par1 telemetry *and* the prompt
  surface the LLM sees (the wrapper exposes `.engine`).
- G6 — **Cost goal (maturity):** confidence-gate the assessor so the trained core lets us
  call the LLM less than v1/v2 — the brain reduces cost, not just "feels smarter."
- G7 — Adopt explicit engineering standards (commits/lint/types/tests + data governance +
  model registry + acceptance gates), incl. the 7 required fixes from the adversarial review.

### Non-goals
- NOT replacing the **assessor** (semantic organ + online teacher) or making the core do
  text/semantics. The core does the **affect/emotion dynamics** only.
- NOT touching `_decide`/`_guard`/body/`affect_debt`/`hot_pool` (timing is the par2 loop).
- NOT Ring 2/3 in v3.0 (resonance-block / full-tick learning are gated later cycles).
- NOT cloud or at-serving training; no torch/onnx/ggml at serving (§7).
- NOT using assessor **wound-delta** or par2 reward in the **emotion-core** loss
  (hard adversarial lesson — reward belongs to the timing loop only).
- NOT deleting the resonance field (it is the distillation teacher and the fallback).

---

## 3. Background & grounding facts (verified in code)

- The emotion core is **`ScarredState._evolve_base`** (`scar_algebra.py:276-306`) with
  fixed `seed=42`, spectrally-normalized (`‖W1‖·‖W2‖ < 0.49`) → a **deterministic
  contraction map**: `base_t = tanh(W2·tanh(W1·[base_{t-1}; modulated_input]))`. Plus
  `ResonanceSpine._apply_assessment_to_engine` (`resonance_integration.py:588-647`) which
  nudges `base[0/1/2]` + void pressure from the assessor. `observe()` reads `base[0..7]`.
- **The I/O flip**: par1's `f_warmth..f_plasticity_ratio` are the field's **outputs**, so a
  core that *produces* them cannot *consume* them. The core's inputs are the **causes** of
  emotion: assessor `a_*`, HDC-of-message, prior `base`, time/body scalars.
- **Per-tick is a chain, not one step**: `VoidScarEngine.process` calls `step()` **2..N
  times/tick** (one per Γ-coupling wound + the main event, `void_scar_engine.py:182,186`),
  each re-evolving `base` **and** mutating scar/void/circuit-breaker state. The bootstrap
  corpus must log the **full per-step (pre,post) transition chain**, not just the endpoint.
- **`.engine` is load-bearing for the prompt**: `kernel._computation_emotion_overlay`
  (`kernel.py:612`) calls `self.computation.engine.observe()` directly to build the prompt
  fragment the LLM sees. A wrapper that omits `.engine` produces a **split-brain**
  (telemetry = student, prompt = field).
- Already built / reuse: par1 `DistillationSink`; `MetaLearner` online residual
  (`accepted/ignored/rejected`, elastic ≤30% drift, serialized); train-torch→export-`.npz`→
  numpy-serve pattern (`EmotiCoreStudentLite`); 1M-row teacher-labeled text corpus.
  **No trained teacher `.pt` in repo** (`train_teacher.log` crashed) → EmotiCore KD is
  optional (`λ_kd=0`).
- Plugin: vendors SDK at `_engine/sylanne_core`; `EngineFacade` (`engine_adapter.py:129`)
  is the unused student slot; par2 send-confirm = `ProactiveBridge.dispatch()=={dispatched:True}`.

---

## 4. Architecture (broad / Ring 1)

```
 user msg ─► plugin ─► assessor (remote LLM: a_valence/arousal/wound_risk/flags)
                         │  (same LLM cost as v1/v2 at bootstrap)
                         ▼
   SDK kernel.tick(assessment):
     ResonanceSpine.process / BroadCoreRuntime.process  (same signature, same result dict)
        ├─ HDC encode, predictive-coding gate            (UNCHANGED — feeds core input)
        ├─ EMOTION CORE  ◄── the only thing replaced
        │    if student.ready and enabled:
        │       base[0..7] = BroadCore_S.step(a_*, hdc, prior base, dt/body)   # numpy, µs
        │       (skip _apply_assessment_to_engine — a_* already consumed)      # fix #3
        │    else:
        │       base[0..7] = seed42_MLP._evolve_base(...) + assessment nudge    # field fallback
        ├─ void/scar topology, sheaf, HGT, boundary, field.resonate(), Φ      (UNCHANGED, on base)
        ├─ observe() / .engine.observe()  ◄── BOTH driven by the student base   # fix #1 (no split-brain)
        ▼
     result dict (emotion 8 + resonance + ...) → _decide/_guard/par1/par2/prompt  (ALL UNCHANGED)

 BRAIN LOOP (what makes it learn, not clone):
   (A) offline: run the real field headless → (x→base) corpus → distill to day-1 parity
   (B) continual: capture real (x→assessor-affect) on live traffic (CORE2, default-off)
                  → periodically RE-DISTILL the SHARED core so it exceeds the field
   (C) online: per-tick predict-then-correct vs assessor a_* → bounded per-session residual
```

Invariants: the student **augments the producer of `base`**, nothing downstream changes
shape; **one shared read-only** core + tiny per-session residual; the **field stays** as
teacher + fallback; reward (`par2`) never touches the emotion loss.

---

## 5. Component design

### 5.1 BroadCore-S model

A **gated recurrent cell** over the 8-dim emotion latent `z` (because the field is a
recurrent contraction map; a stateless MLP cannot reproduce hysteresis / `affect_debt`-like
integration):
```
x_t (~40 floats, fixed order, all causes-of-emotion, never field outputs):
  [0:4]  assessor a_valence[-1,1], a_arousal[0,1], a_wound_risk[0,1], a_confidence[0,1]
  [4:8]  HDC-of-message compressed (4 floats, deterministic, text-free)
  [8]    surprise (PredictiveCodingGate, kept as input)
  [9:17] prior emotion z_{t-1}[0..7]   (the recurrent carry = scar_state.base)
  [17:21] dt(log), turns(log), proactive_flag, repair_flag
  [21:25] need_contact, need_repair, sovereignty, affect_debt   (from kernel pre-process)
  [25:40] reserved zeros (forward-compat; loader asserts feature_order)
cell:  h = tanh(x_t·Win);  h ⊙= σ(z_{t-1}·Uz + h·Uh);  z_t = clamp(tanh(z_{t-1}·Wrec + h·Wout), -1, 1)
heads off [z_t; h]:  emotion = z_t (8) ; aux(coherence,void_pressure,active_voids,surprise,boundary_stability)=σ/softplus(40→5)
                     resonance(energy,sync_order,phi,plasticity_ratio)=softplus/σ(40→4)
                     should_express = (z_t[6] > learned_threshold)   # deterministic, reproducible
```
~3.4K params; int8 `.npz` < 8 KB; f32 working < 32 KB. A **contraction regularizer**
(effective spectral radius < 1) replaces the field's explicit spectral normalization so the
recurrence **cannot diverge**.

### 5.2 Teaching (the three stages)

- **(A) Offline field-distillation — day-1 parity.** `training/student_core/simulate_corpus.py`
  imports `ScarredState`+`VoidScarEngine`+`ResonanceSpine` directly (no plugin/network) and
  runs the real field over **domain-randomized sequences** (a_* across full ranges incl.
  `wound_risk>0.7` trauma spikes; prior-base across `[-1,1]^8`; dt across the clamp; HDC from
  sampled/real text). It logs the **full per-step (pre-base, modulated-input, post-base)
  transition chain** (fix #2) so the student learns the exact map incl. the multi-`step()`
  per tick. Train BroadCore-S with **truncated BPTT** (≈16-tick windows), AdamW +
  CosineAnnealingLR, on the owner's local GPU. PTQ → int8. **Loss:**
  `SmoothL1(z, field_emotion_8)·1.0 + SmoothL1(res_head, field_res_4)·0.5 +
  SmoothL1(aux_head, field_aux_5)·0.3 + BCE(should_express)·0.2 + λ_kd·EmotiCore_soft +
  contraction_reg`. **Gate:** int8 emotion MAE vs field ≤ 0.03, resonance MAE ≤ 0.05,
  trajectory correlation ≥ floor ("no worse than the field on day one").
- **(B) Continual re-distillation — the brain (the (b) commitment).** A **CORE2 capture
  stream** (`Par2Sink`-style, default-off, same salt) logs, on **real assessed ticks**,
  `(x_t  →  assessor a_*)` joined by `(session_hash, tick)`. Periodically (offline, owner's
  GPU) **re-train the shared core** with the assessor's real `a_*` as the target on the
  driven dims, so the core distills the LLM's **real semantics** and **surpasses** the
  hand-coded field. A **covariate-shift (KS)** gate compares real vs sim marginals before any
  re-distilled core is promoted. *This is the line between brain and theater — it is in
  scope, not deferred.*
- **(C) Online per-session residual — personalization.** Predict-then-correct: each tick the
  core predicts `z`; the assessor's `a_valence/a_arousal` (and the field's own nudge as a soft
  target) correct the 3 driven dims via a **bounded plastic readout bias** (≤17 floats,
  elastic ≤30% drift, EMA — **no backprop at serving**), riding the existing snapshot.

Reward purity: par2 `accepted/ignored/rejected` feeds the **timing** loop
(`report_reach_outcome` → `MetaLearner`) only; it **never** enters (A)/(B)/(C) emotion loss.

### 5.3 Serving runtime & integration

- **`BroadCoreRuntime`** wraps the live `ResonanceSpine`: same `process(text, timestamp,
  assessment=None, **kwargs)` signature, same result-dict shape, so `kernel._tick_inner` is
  untouched and backend-agnostic. It **delegates `to_dict()/from_dict()/feedback()`** to the
  wrapped field (snapshot + `MetaLearner` serialization byte-unchanged) and **exposes
  `.engine`** as an engine-shim whose `observe()` returns the **student** emotion (fix #1 —
  prompt and telemetry share one backend; contract test asserts
  `_computation_emotion_overlay() == telemetry emotion`).
- The replacement **seam is inside `ScarredState`**: an optional runtime-only `_core_fn`
  callable (set via `set_core_model()`, never serialized, like `_telemetry_sink`); `None` ⇒
  the `seed=42` MLP exactly as today.
- **Fallback state machine** (load → `sha256` → 1-step int8-vs-f32 parity self-test →
  `feature_order` check → ready); any failure or per-tick exception ⇒ `field.process(...)`.
  A **runtime contraction circuit-breaker** (clamp `base∈[-1,1]` + `‖Δbase‖`-spike ⇒ field
  fallback) lands **before canary** (fix #5).
- **Ownership of coherence/void_pressure/active_voids** (fix #4): Ring 1 keeps them
  **field-computed on the student base** and asserts downstream tolerance; they are emitted
  from the student only in Ring 2. Documented, not implicitly desynced.

### 5.4 par2 (timing) loop — carried unchanged from v1

par2 (the reach-outcome label that joins to the originating `reach_out` tick) is **unchanged
by the broad scope**: one additive default-off `engine.report_reach_outcome(session_id,
originating_tick, outcome, *, apply_online=False)` (corpus-only by default; `apply_online=True`
routes to `host.kernel.computation.feedback` → `MetaLearner`), join key
`(session_hash, originating_tick)`, plugin `awaiting_par2_outcome` store armed on
`bridge.dispatch()=={dispatched:True}`, classified from the reply tick's assessment, `ignored`
on timeout. See §A1 for the carried spec. par2 supervises **timing**, never the emotion core.

---

## 6. Required fixes from the adversarial review (all MUST land for Ring 1)

1. **Wrapper exposes `.engine`** (engine-shim `observe()` → student emotion) + forward
   `apply_personality`/`embodiment_bounds`; contract test: overlay == telemetry emotion.
2. **Full per-step transition corpus** (log every `_evolve_base` call's `(pre, input, post)`,
   since `VoidScarEngine.process` re-evolves base 2..N times/tick); decide+test whether the
   student replaces every call or only the readout.
3. **Skip `_apply_assessment_to_engine` when the student is active** (it already consumes
   `a_*`); unit test asserting single application of valence/arousal.
4. **Pin ownership of coherence/void_pressure/active_voids** (Ring 1: field-computed + assert
   downstream tolerance; never implicitly desynced).
5. **Runtime contraction circuit-breaker** (clamp + `‖Δbase‖`-spike → field) **before** canary;
   gated on trajectory stability, not per-tick MAE alone.
6. **Shadow gate includes expression-decision divergence** (`should_express`, hgt-gated path),
   not only base/resonance MAE.
7. **Snapshot round-trip CI both directions**, with and without `_broad_core_residual`.

---

## 7. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Model | tiny **recurrent** cell (GRU-style, ~3.4K params) | the field is a recurrent contraction map; a stateless MLP loses the dynamics; recurrence is ~free and IS the per-session state |
| Training | **PyTorch** (truncated BPTT, AdamW+cosine), owner GPU only | reuses `train_model_torch.py` + `export_to_numpy()`; never shipped |
| Quant | int8 per-tensor symmetric PTQ | `.npz` < 8 KB; trivial numpy dequant; gated by parity test; f32 runtime state to bound recurrent int8 error |
| Serving | **pure numpy** int8, inline | no torch (~300-400 MB), no onnx/ggml; proven by `EmotiCoreStudentLite`; latency win vs field |
| Online residual | bounded plastic readout bias (elastic ≤30%, EMA) reusing `MetaLearner` discipline | no backprop at serving; rides existing snapshot |
| Corpus | sim: stdlib JSONL → parquet (training-side); CORE2: `Par2Sink`-style default-off | unlimited free sim data; real-traffic stream for the brain loop |
| Registry | flat `models/` + `manifest.json` + sha256 (Git-LFS) | repro/provenance, zero infra |
| Tests/lint/types | pytest+pytest-asyncio, ruff(+ASYNC), mypy --strict | AstrBot §10/§11; SDK already mypy-strict |

---

## 8. Phased rollout (Ring 1; each reversible, kill switch = flag → field)

| Phase | Work | Gate |
|---|---|---|
| **P0** | `simulate_corpus.py` (full per-step chain) → parquet + manifest | — (offline) |
| **P1** | train BroadCore-S (BPTT) → int8 `.npz` + manifest | int8 emotion MAE ≤ 0.03, res MAE ≤ 0.05, traj-corr ≥ floor, numpy==torch parity |
| **P2 Shadow** | `BroadCoreRuntime` computes+logs but field drives; compare student-vs-field on real traffic (par1 cols = field targets) | rolling base+expression divergence ≤ thr; KS covariate-shift OK |
| **P3 Canary** | student drives `base` for a canary %; circuit-breaker + per-tick try/except → field; assessor-correction residual on | trajectory stability; expression divergence ≤ small %; latency/RSS SLOs |
| **P4 Promote Ring 1** | student is the emotion core by default; online residual on; auto-rollback armed | sustained SLOs |
| **Phase B (brain loop)** | CORE2 real-traffic capture on; periodic shared-core **re-distillation** vs assessor; KS-gated promote of each new core version | re-distilled core beats prior on held-out real traffic |
| **Phase M (maturity / cost)** | **confidence-gate the assessor**: when the core's predicted affect is high-confidence + low-surprise, skip/defer the LLM assessor call; call it on uncertainty/novelty | LLM-call rate ↓ vs v1/v2 with affect quality held |

Ring 2 (resonance block) / Ring 3 (full tick) are **separate future P0–P4 cycles**, only
after Ring 1 + Phase B prove out. Vendor cutover (owner, separate session): atomic
whole-`_engine/sylanne_core` swap, keep assessor knob, backup + smoke test + one-command
rollback.

---

## 9. Standards / observability / testing / governance (carried + delta)

- **Standards**: Conventional Commits + trunk-based + English (§9); ruff(+ASYNC) + mypy
  strict (§10); pytest+pytest-asyncio (§11); review checklist (§13). v3 line = `next-gen`.
- **Observability** (stdlib-only, no egress, via `health()`/diagnostics + JSONL metrics):
  corpus growth (sim + CORE2), **student-vs-field base/resonance/expression divergence**,
  int8 parity, fallback rate, contraction-breaker trips, residual drift, per-tick latency
  p50/p95/p99, RSS, **assessor-call rate** (Phase M), re-distillation version + KS deltas.
- **Testing**: parity (numpy==torch), **no-split-brain** (overlay==telemetry), assessment
  no-double-apply, contraction-breaker, shadow-divergence, snapshot round-trip ±residual,
  load test (N sessions, 2c2g budget). par2 attribution (arm/resolve/restart/reset) carried.
- **Governance**: opt-in default-off (`student_model_enabled`, CORE2 sink); no PII / no text /
  no egress; `0o600`; salted hash join; retention + tombstone right-to-deletion;
  model registry (semver + sha256 + feature_order check forces degradation on mismatch).

---

## 10. Risks & mitigations (broad-specific top)

| Risk | Mitigation |
|---|---|
| **Theater** (clone-the-field gains nothing) | **Phase B** continual re-distillation on real assessor traffic is committed, not deferred — the core is *trained to beat the field* |
| Split-brain (telemetry vs prompt) | fix #1 wrapper `.engine` + contract test |
| Per-tick `step()`-chain desync | fix #2 full per-step corpus + decide single-vs-readout replacement |
| `a_*` double-apply | fix #3 skip-guard + test |
| Recurrent int8 divergence over long sessions | f32 runtime state + clamp + contraction reg + circuit-breaker + long-horizon CI |
| coherence/void/active_voids desync | fix #4 field-computed in Ring 1, asserted tolerance |
| Expression timing flips while base MAE tiny | fix #6 expression-divergence shadow gate |
| Mid-session fallback hands field stale void/scar state | keep field void/scar bookkeeping live in shadow/canary; documented decision |
| Two spine classes (`ResonanceSpine`/`ComputationSpine`) | wrapper + corpus target whichever is `_DEFAULT_SPINE`; assert at build |
| Uncorrected dims (tension/curiosity/boundary) drift online | only the 3 assessor-driven dims get online correction; others anchored to the distilled prior + contraction reg; bound residual |
| No teacher `.pt` | `λ_kd=0`; field-distill + assessor are sufficient |

---

## 11. Open decisions for the owner

- **D-1 RESOLVED**: broad scope, **Ring 1** (emotion core), **brain loop committed** (Phase B).
- **D-7 (assessor extension):** to ground more than 3/8 dims online, extend the assessor
  output schema (add e.g. curiosity/intimacy/boundary continuous fields). Backward-compatible
  prompt change. **Recommend yes** (it directly widens what the brain can learn) — your call.
- **D-8 (Phase M aggressiveness):** how hard to confidence-gate the assessor (cost↓ vs affect
  fidelity). A cost/quality dial only you set.
- **D-9 (online residual reach):** keep online correction to the 3 driven dims, or let it
  touch more once D-7 lands?
- **D-10 (governance):** retention window; opt-in disclosure for the CORE2 real-traffic stream
  (multi-user data); minimum-N before a re-distilled core may promote.
- **D-11 (Ring 2 trigger):** what proof from Ring 1 + Phase B greenlights learning the
  resonance block (skipping the Kuramoto/Hopfield loop for more latency win)?

---

## Appendix A1 — par2 timing loop (carried spec)

SDK: `+report_reach_outcome(session_id, originating_tick, outcome, *, dispatch_ts=None,
observed_ts=None, latency_turns=-1, apply_online=False) -> bool`; `+Par2Sink`
(`reach_outcomes.jsonl`, `PAR2_SCHEMA_VERSION=1`, row `{schema_version, session_hash,
originating_tick, outcome, dispatch_ts, observed_ts, latency_turns}`); `+SylanneConfig
reach_outcome_sink/reach_outcome_path`; `+host_payload originating_tick/guard_allowed`
(additive read-only); `+SYLANNE_CAPABILITIES`. Plugin: `awaiting_par2_outcome` store
(persisted, restart-safe), arm on `bridge.dispatch()=={dispatched:True}` ∧ `guard_allowed` ∧
`decision.action=='reach_out'`, classify from the reply tick's assessment, `ignored` on a
default-4h timeout sweep. Reward stays discrete; never wound-delta; never into emotion loss.

## Appendix A2 — key file pointers

SDK: `scar_algebra.py:218-306` (`seed=42` `_evolve_base`), `void_scar_engine.py:182,186`
(per-tick `step()` chain) `:211-233` (`observe`), `resonance_integration.py:343-511`
(`process`) `:588-647` (`_apply_assessment_to_engine`) `:886-939` (`_build_result`)
`:985` (`MetaLearner` serialize), `kernel.py:265` (`process` call) `:612`
(`_computation_emotion_overlay` → `.engine.observe()`), `telemetry/sink.py:37`
(`AFFECT_CONTEXT_FIELDS`), `meta_learner.py:198` (`update`), `config.py:183`.
Plugin: `engine_adapter.py:129` (`EngineFacade`), `proactive_bridge.py:301` (`dispatch`),
`main.py:1106` (`on_message`), `state_persistence.py` (`_VALID_SUBSYSTEMS`).
