# TDD: SylannEngine v3 — Learned Emotional Core ("PEL-Core" / broad student)

- **Status: v4 (GATED on real-data collection).** Supersedes v3.1. A 66-agent / 6-dimension
  adversarial review (2026-06-25) returned 22 findings incl. 2 blockers; an 11-agent digest
  consolidated them (`v3-review-digest.md`); a pre-P0 spike ran and returned a **gated verdict**
  ratified in **`adr-0001-v3-core-go-no-go.md`**: *do not enter P0 on the offline spike; gate on
  collecting real assessor-labeled traffic and re-running the probes.* This v4 folds every accepted
  fix + the spike learnings, re-sequences the program so **Phase-0-collection comes before P0**, and
  marks **P0 as gated**.
- **The boundary (load-bearing):** the CORE2 telemetry sink + salt fix + adapter + probe harness are
  **Phase-0-collection — authorized, additive, default-off, NOT P0** (`v3-realdata-harness-spec.md`).
  **P0 (cell / distillation / online-residual / serving-int8 / brain / cost-gating / kill) stays
  gated** behind the real-data result.
- Author: Sylanne (design), Ayleovelle (owner/reviewer). Last updated: 2026-06-25.
- Scope: SDK `sylanne_core` (branch `next-gen` / `feat/v3-core`) + plugin `Sylanne-next`
  (`sylanne_alpha`).
- Decision log:
  - **D-1 = BROAD** — the student replaces the emotion core, not just `_decide`.
  - **(b) = brain loop committed** — the shared core continually re-distills real assessor-labeled
    traffic, *not* a one-shot clone of the field.
  - **North star = retire the `seed=42` field from the RUNTIME** (live core, fallback, stability),
    **demoting, not deleting, its source** to a frozen offline `reference_teacher`. Deleting the
    source is the one *truly* irreversible white-train; field out of the live path, source kept
    forever as the regeneration oracle. (Caveat: a scoped `ScarModulator` survives, fork U1.)
  - **Spike verdict (ADR-0001) = gate on real data.** The field is both data generator and baseline,
    so it cannot generate data proving its own replacement; the go/no-go cannot be settled offline.

---

## 0. What changed (v3.1 → v4) and why

1. **The spike ran; the program is now gated.** A reusable headless generator
   (`training/student_core/simulate_corpus.py`) drove the real field over 2000 synthetic sessions
   (~62k ticks). Two probes (`spike_ntap.py`, `spike_predict_assessor.py`) produced a **deliberate
   non-verdict** (ADR-0001):
   - **Probe 1 (NTAP, cross-tick memory): FAIL** — the student cannot beat the steelmanned field+nudge
     baseline (0.215 vs 0.203). Structural: synthetic field data is Markovian, the field's reactive
     state already captures the increment. *This empirically confirms the theater critique.*
   - **Probe 2 (predict-assessor, Phase-M payoff): PARTIAL PASS, synthetic only** — a trained core
     reading the WIDE HDC (0.209) far beats the field's **fixed pre-nudge transform** (0.533), but
     **does NOT beat trivial persistence on the autocorrelated/realistic slice** (0.200 vs 0.197), and
     **the binding field+nudge baseline was never run** in that probe. D-12 confirmed *mechanically*
     (V0 0.250 → V4 0.244 → Vfull 0.209).
   - **Consequence:** offline can't de-risk this (field = generator + baseline). The real gate is
     **collect real assessor-labeled traffic + re-run the probes** (`v3-realdata-harness-spec.md`).
2. **The "field is semantic-blind" claim is corrected.** The field's pre-nudge base **has** seen the
   message (via `HDC → ssm_input → _evolve_base`); it simply lacks a *learned* message→affect map. The
   defensible claim: the field's fixed transform doesn't recover the assessor's read; a trained core
   does (so the target is learnable, not already produced by the field).
3. **All 22 review findings + completeness items are resolved in the §6 ledger** (with the digest's
   overstatement corrections preserved), including two the review missed entirely — **concurrency**
   and **int8 PTQ reproducibility** — and one **fabricated citation** the digest itself introduced,
   now corrected (there is **no** breaker at `resonance_integration.py:387-426`; D15).
4. **Citations re-verified.** `_evolve_base` is **defined** at `scar_algebra.py:276`, **called** in
   `step()` at `scar_algebra.py:402` (the v3 phrasing conflated them). `state_persistence.py`
   (`_VALID_SUBSYSTEMS`) is **plugin-only** (`G:/Sylanne-next`), not in the SDK.

Everything else from v2/v3 (PEL-Core, the I/O flip, the three teaching stages, the cost trajectory,
the kill north star) stands — but **behind the real-data gate**.

---

## 1. Executive summary

Build **BroadCore-S**: a ~3.4K-param **recurrent** emotion cell over an 8-dim emotion latent that
replaces `ScarredState._evolve_base` (the fixed `seed=42` MLP) + the `_apply_assessment_to_engine`
nudge + the `observe()` readout. It produces `scar_state.base[0..7]` from **(assessor affect + HDC-of-
message + prior emotion state + time/body scalars)** — the **I/O flip**: par1's `f_*` emotion features
are the core's **outputs**, never its inputs. Everything downstream (void/resonance/HGT/expression,
`_decide`, `_guard`, par1/par2) runs **unchanged** on the student's base.

Served as **pure-numpy int8** (`.npz` < 8 KB, no torch) in 2 vCPU / 2 GB / no-GPU multi-session.
**Ring 1 does NOT remove `resonate()`** (it stays unchanged), so Ring 1 is justified by
**learnability, not latency**. Default-off behind `student_model_enabled`; any failure falls back
through a layered fallback chain.

Three teaching stages: **(A) offline field-distillation** (day-1 parity), **(B) continual
re-distillation of real assessor-labeled traffic** (the brain), **(C) online per-session
assessor-corrective residual** (bounded). Reward purity holds: par2 `accepted/ignored/rejected` drives
the **timing** loop only, **never** the emotion-core loss.

**Gating reality (v4):** this whole build is **P0 and is GATED** (ADR-0001). The first authorized step
is **Phase-0-collection** (CORE2 sink + salt fix + adapter + probe additions, all default-off); P0
proceeds **iff the real-data Probe 2 passes** against persistence **and** a steelmanned field+nudge
baseline on the autocorrelated slice. **The endgame** (Phase K: retire the field from the runtime,
keep its source as a frozen `reference_teacher`) is reached only after P4 + Phase B.

This is **Ring 1**. Ring 2 / 3 are gated future cycles. Body / `_decide` / `_guard` / `affect_debt` /
`hot_pool` are **never** touched.

---

## 2. Goals / Non-goals

### Goals
- **G-core** — replace the `seed=42` emotion MLP with a **learned recurrent core**, field-equivalent
  on day one, then improving by distilling the assessor.
- **G-brain** — commit **continual re-distillation of real assessor traffic** (CORE2) plus a bounded
  online per-session residual.
- **G-serve** — CPU-only, no-torch, < 1 MB RSS, low-µs inline in 2c2g multi-session; **no latency
  regression** in Ring 1 (Ring 1 keeps `resonate()`; the latency win is deferred to Ring 2).
- **G-safe** — additive / default-off; GREEN-frozen public API intact; snapshot/restore
  backward-compatible. Until Phase K the field is the instant runtime fallback **and** the offline
  teacher; after Phase K the runtime fallback is **pinned-npz + analytic floor** and the field source
  is retained **only** as the frozen offline `reference_teacher`.
- **G-onebrain** — **no split-brain**: one backend drives BOTH par1 telemetry AND the prompt surface
  the LLM sees (the wrapper exposes `.engine`).
- **G-cost** — confidence-gate the assessor at maturity so we call the LLM **less** than v1/v2.
- **G-retire** — get the `seed=42` formula out of the runtime under the Phase-K gates, source demoted
  (not deleted).
- **G-durable** — a two-tier durable-asset + versioning/migration contract so an SDK update **never**
  wastes training (§9).
- **G-gate** — **prove value on real data before building**: Phase-0-collection then the Probe-2 gate
  (ADR-0001); never enter P0 on synthetic/field-generated evidence.

### Non-goals
- NOT replacing the **assessor** (semantic organ + online teacher); the core does **affect dynamics**
  only.
- NOT touching `_decide`/`_guard`/body/`affect_debt`/`hot_pool`.
- NOT Ring 2/3 in v3.0. NOT cloud or at-serving training; no torch/onnx/ggml at serving (§7).
- NOT using assessor wound-delta or par2 reward in the **emotion-core** loss.
- **NOT deleting the field *source*** — demoted to a frozen offline `reference_teacher`. What is
  deleted (Phase K) is the field's presence in the **live runtime path**.
- NOT non-text input modalities in this cycle (text-only; non-text turns excluded from the corpus).

---

## 3. Background & grounding facts (verified in code)

- **The emotion core** = `ScarredState._evolve_base` (**defined** `scar_algebra.py:276-306`,
  **called** in `step()` at `scar_algebra.py:402`), fixed `seed=42`, spectrally-normalized (each
  `‖W‖₂≤0.7` via `max_sigma=0.7` at `scar_algebra.py:231-232` ⇒ two-layer product `<0.49`):
  `base_t = tanh(W2·tanh(W1·[base_{t-1}; modulated_input]))`. **Boundedness is the final `tanh`**
  (`scar_algebra.py:304`), structural and provable; the `<0.49` is *convergence*, not boundedness.
  `step()` is called **1..N times/tick** by `VoidScarEngine.process` (`void_scar_engine.py:182,186`);
  the per-tick `_evolve_base` floor is **1**.
- **Two emotion-mutating paths, both in the kill-list:**
  - `ResonanceSpine._apply_assessment_to_engine` (`resonance_integration.py:588-647`): gain
    `(0.4+0.6·confidence)·0.3`; in-place **clamped** writes `base[2]=max(-1,min(1,base[2]+valence·
    gain))` (`:627`), `base[1]` (`:629`), `base[0]` (`:631`); wound-step if `wound_risk>0.7`; void
    pressure nudges (`:636-641`).
  - `ComputationSpine.apply_assessment` (`computation_spine.py:511-565`): the same wound/void nudges
    **plus** intent handling for **撒娇/生气** via `base[0,3]` — behavior `ResonanceSpine` lacks.
    `_DEFAULT_SPINE` falls back to `ComputationSpine` on import failure (`kernel.py:47-53`), so this
    path is reachable.
- **The I/O flip**: par1's `f_warmth..f_plasticity_ratio` are the field's **outputs**; the core's
  inputs are the **causes** (assessor `a_*`, HDC-of-message, prior `base`, time/body).
- **`base_pre_nudge` is NOT message-blind.** Snapshotted after `_evolve_base` but before the nudge, it
  has already incorporated this tick's message via `HDC → ssm_input` (`resonance_integration.py:413-
  423`). Its 0.533 spike MAE means the field's *fixed* transform doesn't decode the message to the
  assessor's read — not that it never saw the message.
- **`.engine` is load-bearing for the prompt**: `kernel._computation_emotion_overlay`
  (`kernel.py:605-612`) calls `self.computation.engine.observe()`. A wrapper omitting `.engine` ⇒
  split-brain (telemetry=student, prompt=field).
- **par1 is endpoint-only telemetry, not the brain's corpus.** `_capture_telemetry`
  (`kernel.py:927-986`, called at `kernel.py:298`) writes one row per assessed tick: 26 `f_*` + 4
  `a_*` + `decision_action` + `tick`. It does **not** log prior base `z_{t-1}`, the per-step
  transition chain, any message embedding, or `dt`. ⇒ par1 retrains the *shipped* contract at best;
  the brain needs the **CORE2 stream** (`v3-realdata-harness-spec.md`).
- **Versioning today is thin.** `FEATURE_SCHEMA_VERSION=1` (bare int, no migration,
  `telemetry/sink.py:33`); positional `AFFECT_CONTEXT_FIELDS` (`:37-64`); **no**
  `model_version`/manifest/sha256 on any `.npz`; the only runtime fallback guard catches
  `ImportError`. par2 / `BroadCoreRuntime` / int8-`.npz` serving / shadow flag are **SPEC-ONLY**.
- **Salt is mis-documented (D14).** `training_data_salt=""` (`config.py:217`) yields
  `SHA-256(":"+session_key)` (`telemetry/sink.py:74`) — **stable / cross-deploy-linkable**, the
  *opposite* of the docstring's "per-process random" (`config.py:203-205`). No `delete_session()`.
- **`state_persistence.py` (`_VALID_SUBSYSTEMS`) is plugin-only** (`G:/Sylanne-next`), absent from the
  SDK. **V1 (no-split-brain) verified GREEN this session** via the plugin's emotion-read path
  (`llm_request_pipeline.py:1601` → `host.kernel.computation.engine.observe()`, the same spine
  instance the kernel mutates). The `EngineFacade.engine` forwarding (`engine_adapter.py:129`) is a
  related plugin-repo claim not separately re-verified; both live out of SDK-audit scope.
- **Reuse:** `MetaLearner.update` (`meta_learner.py:198-260`); `train_model_torch.py`→`.npz` export; a
  1M-row teacher-labeled text corpus (**V2: asserted, not counted/schema-checked**). **No trained
  teacher `.pt`** ⇒ EmotiCore KD is dead (C8: delete `λ_kd`).

---

## 4. Architecture (broad / Ring 1)

```
 user msg ─► plugin ─► assessor (remote LLM: a_valence/arousal/wound_risk/confidence/flags)
                         ▼
   SDK kernel.tick(assessment):
     ResonanceSpine.process / BroadCoreRuntime.process  (same signature, same result dict)
        ├─ HDC encode, predictive-coding gate            (UNCHANGED — feeds core input)
        ├─ EMOTION CORE  ◄── the only thing replaced
        │    if student.ready and enabled:
        │       base[0..7] = BroadCore_S.step(a_*, hdc, prior base, dt/body)   # numpy, µs
        │       (REPLACE base[0,1,2] only; PRESERVE wound/scar/void/撒娇·生气)  # fix B4 (not "skip nudge")
        │    else:                                                             # fallback chain (§5.3):
        │       base = field._evolve_base(...) + nudge   (pre-Phase-K)
        │            └─ post-Phase-K: pinned-npz → analytic floor (NO field in runtime)
        ├─ void/scar topology, sheaf, HGT, boundary, field.resonate(), Φ      (UNCHANGED, on base)
        ├─ observe() / .engine.observe()  ◄── BOTH driven by the student base   # fix #1 (no split-brain)
        ▼
     result dict → _decide/_guard/par1/par2/prompt  (ALL UNCHANGED)

 BRAIN LOOP (what makes it learn, not clone):
   (A) offline: real field headless → full-transition corpus → distill to day-1 parity
   (B) continual: capture real (x_t → assessor a_*) on live traffic (CORE2, default-off)
                  → periodically RE-DISTILL the SHARED core
   (C) online: per-tick predict-then-correct vs assessor a_* → bounded per-session residual

 REGENERATION ORACLE (why the source survives the kill):
   frozen reference_teacher (= demoted field) + versioned simulate_corpus parquet
   → can re-emit the FULL transition corpus for ANY future architecture, forever.

 THE GATE (v4): Phase-0-collection (CORE2) → re-run Probe 2 on REAL data
                → PASS ⇒ enter P0;  FAIL/escalate ⇒ STOP (ADR-0001).
```

Invariants: the student **augments the producer of `base`**, nothing downstream changes shape; **one
shared read-only core** + tiny per-session residual; the field **leaves the runtime** at Phase K but
its **source is retained**; reward (par2) never touches the emotion loss.

---

## 5. Component design

### 5.1 BroadCore-S model (architectural boundedness — fixes the false-equivalence, blocker #1)

A gated recurrent cell over the 8-dim emotion latent `z` whose boundedness and contraction are
**closed-form architectural properties** (validated as the spike's `BroadCoreS`, `spike_ntap.py:79-
101`):

```
x_t (~40 floats, fixed order, all causes-of-emotion, never field outputs):
  [0:4]  a_valence[-1,1], a_arousal[0,1], a_wound_risk[0,1], a_confidence[0,1]
  [4:8]  HDC-of-message density (WIDE per D-12; deterministic, text-free, non-invertible*)
  [8]    surprise (PredictiveCodingGate)
  [9:17] scar-modulation summary (the field's modulate() factor, scar_algebra.py:352-363)
         REQUIRED for tick-parity (hypothesized; gated by the A3 ablation). NOTE: z_{t-1} is NOT
         in x_t — it enters ONLY via the recurrent term below. Feeding it here too was blocker #1.
  [17:25] dt(log), turns(log), proactive/repair flags, needs, sovereignty, affect_debt
  [25:40] reserved zeros (loader asserts feature_order)
cell:
  h    = tanh(x_t · Win)
  u    = tanh(z_{t-1} · Wrec_sn + h · Wout)         # Wrec_sn spectrally-normed: σ(Wrec_sn) ≤ 0.9
  z_t  = (1 - α) · z_{t-1} + α · u                  # α ∈ (0,1), learned-but-clamped, per-dim sigmoid
heads: emotion = z_t (8); aux/resonance via σ/softplus.  NO should_express head in Ring 1 (B10).
```
\* the non-invertibility of the HDC density is **unverified** and must be tested before collection
(harness §2.4).

**Why boundedness is structural and contraction is certifiable (the K3 gate):**
- **Structural boundedness (unconditional).** `u ∈ [-1,1]^8` (final `tanh`); if `z_{t-1} ∈ [-1,1]^8`
  then `z_t = (1-α)z_{t-1} + α·u ∈ [-1,1]^8` (convex combination). `[-1,1]^8` is **forward-invariant**
  — closed-form, no clamp. (Clamp rejected: clamp ≠ contraction; it permits rail-oscillation.)
- **Contraction — ONLY because `z_{t-1} ∉ x_t`.** The Jacobian is exactly
  `∂z_t/∂z_{t-1} = (1-α)I + α·diag(tanh'_u)·Wrec_sn`, so `‖J‖₂ ≤ (1-α)+α‖Wrec_sn‖₂`. With the design
  pin **`σ(Wrec_sn) ≤ 0.9`**: `‖J‖₂ ≤ (1-α)+0.9α = 1−0.1α < 1` **for every `α∈(0,1]`** — contractive
  with no α-dependent slack needed. *(This is the student's single `Wrec`, distinct from the field's
  two-layer 0.49 product; the two bounds are unrelated.)* Blocker #1: the v3 draft also fed `z_{t-1}`
  via `x_t[9:17]`, adding an unbounded `Win·diag(tanh'_h)·Wout` path the Jacobian dropped — fixed by
  removing `z_{t-1}` from `x_t`.
- **Certification on the SERVED weights, not f32.** Power iteration estimates `σ_max` from *below*, so
  train-side **spectrally-normalize `Wrec`** to the pin and **re-verify at LOAD on the dequantized
  int8 weights**: exact `np.linalg.norm(Wrec_deq,2) < 1` (with margin), `α∈[ε,1-ε]`, wrapped in
  try/except → **RefuseLoad** (R4). K3's exit gate is this static check on the *served* int8 weights —
  **never** val-set MAE. The torch→numpy int8 boundary itself is a golden-vector CI (U1/V4, §6).
- ~3.4K params; int8 `.npz` < 8 KB; f32 recurrent state to bound int8 drift.

### 5.2 Teaching (the three stages)

- **(A) Offline field-distillation — day-1 parity.** `simulate_corpus.py` imports the real field (no
  plugin/network) and runs it over domain-randomized sequences (a_* full ranges incl. `wound_risk>
  0.7`; prior-base across `[-1,1]^8`; dt across the clamp). It logs the **tick-granular** transition
  `(pre-tick base, full inputs incl. a_* + scar-mod, post-tick base, dt)` — **Tier-1 durable** (§9).
  **Teacher determinism (U3): GREEDY expression policy, frozen RNG, sorted scar iteration**; two
  generation runs must be byte-identical before P0. Train with truncated BPTT (≈16-tick windows),
  AdamW + CosineAnnealingLR, owner GPU; PTQ → int8. **Loss:**
  `SmoothL1(z, field_emotion_8)·1.0 + SmoothL1(res, field_res_4)·0.5 + SmoothL1(aux, field_aux_5)·0.3`
  — **no** `BCE(should_express)` (B10), **no** `λ_kd` (C8, EmotiCore is dead), **no** `contraction_reg`
  (architectural). **Gate:** int8 emotion MAE vs field ≤ 0.03, res MAE ≤ 0.05, traj-corr ≥ floor —
  **note: the 0.03 gate needs a session-clustered power treatment** (per ADR §6), not a bare
  threshold, especially since dropping the BCE/KD heads recalibrates the loss landscape (R5).
- **(B) Continual re-distillation — the brain (the (b) commitment).** The **CORE2 capture stream**
  (`v3-realdata-harness-spec.md`, default-off) logs real `x_t → a_*` joined by `(session_hash, tick)`,
  **input-complete** (Tier-2). Periodically re-train the **shared core** with real `a_*` so it
  distills the LLM's real semantics. **Leakage-free target = divergence `d_t = a_t − base_pre_nudge`**
  (C6, the shared `base_pre_nudge` instrument), with a **field-ablation control** asserting `d_t` is
  not reconstructable from `x_t` alone, and a **KS** covariate-shift gate before any re-distilled core
  promotes. *This is the line between brain and theater — in scope, not deferred.*
- **(C) Online per-session residual — personalization.** Predict-then-correct: the core predicts `z`;
  the assessor's `a_valence/a_arousal` correct the driven dims via a **bounded plastic readout bias**
  `b_res` (≤17 floats, elastic ≤30% drift, EMA — **no backprop at serving**), injected **pre-tanh**
  (`u = tanh(… + b_res)`, A9) so it stays in `[-1,1]^8` and is invisible to the A1 Jacobian; riding
  the existing snapshot; **session-local** (concurrency-tested, §11).

Reward purity: par2 `accepted/ignored/rejected` feeds the **timing** loop only; never (A)/(B)/(C).

### 5.3 Serving runtime & integration

- **`BroadCoreRuntime`** wraps the live spine: same `process(...)` signature and result shape;
  delegates `to_dict/from_dict/feedback`; **exposes `.engine`** (engine-shim `observe()` returns the
  **student** emotion — fix #1; contract test asserts overlay==telemetry).
- The replacement **seam is inside `ScarredState`**: a runtime-only `_core_fn` (set via
  `set_core_model()`, **never serialized**, like `_telemetry_sink`); `None` ⇒ the `seed=42` MLP exactly
  as today (pre-Phase-K).
- **Layered fallback chain** (a single `.npz` is NOT a sufficient fallback — K2):
  `student core → pinned last-good .npz → hardcoded analytic floor` (a ~20-line pure-Python identity/
  EMA core, no file load). An **implemented runtime guard** wraps **both `.npz` load and per-tick
  compute** in try/except (catching `FileNotFoundError`/`ValueError`/numpy load errors/`NaN`, not just
  `ImportError`). Load gate: `sha256` → 1-step int8-vs-f32 parity → `feature_order`/
  `input_contract_hash` → ready. A **contraction circuit-breaker** (`‖Δbase‖`-spike ⇒ drop to the next
  tier) lands **before canary** (fix #5). **The contraction breaker is greenfield** — there is **no**
  existing breaker at `resonance_integration.py:387-426` (D15: those lines are personality-overlay /
  HDC / predictive-coding gate / VoidScar `process()`); it scopes to **non-proven** modes only
  (corrupt/NaN/int8-edge/load-bug), and a trip on the **proven** path = precondition-violation
  **ALARM → rollback**, which does **not** contradict the §5.1 proof.
- **Failure matrix (U4/M3):** every cell (corrupt/truncated/NaN/wrong-shape/load-error) has a tested
  outcome; default = **fall back to the full field path, alert, never crash, never serve NaN**.
- **Ownership of coherence/void_pressure/active_voids** (fix #4): Ring 1 keeps them field-computed on
  the student base + asserts downstream tolerance; emitted from the student only in Ring 2.
- **Concurrency (U2/M2 — one of the two scariest, review-missed):** the shared core array is
  **read-only** (assert non-writeable); `b_res` is strictly **session-local**; core hot-swap is
  **atomic** (load new obj, swap ref under lock, never mutate in place); copy-on-snapshot; `b_res`
  invalidated atomically with a swap. Stress test asserts per-session trajectories match solo **within
  tolerance (`< 1e-9` per element) under a pinned single-thread BLAS** (bit-identity is not guaranteed
  under BLAS thread variance, so tolerance + pinned threads, not "bit-identical").

### 5.4 par2 (timing) loop — carried unchanged. See Appendix A1.

---

## 6. Review-resolution ledger (all 22 findings + completeness; MUST land for Ring 1 / P0)

Verdicts are the digest's **re-verified** ones; overstatement corrections are marked **[CORRECTED]**
so v4 never re-introduces them. Spike-derived numbers are **synthetic, pre-P0 targets — not
real-world results.**

### Cluster-A — boundedness / contraction (A1, A3, A9)
| ID | Verdict | Fix (file:line) | Test |
|---|---|---|---|
| **A1** | Real bug; `z_{t-1}` out of `x_t` correct & sufficient; cert uncertified until load recheck. | §5.1 cell; load-time exact-norm cert on **dequant int8** → RefuseLoad. | Static K3 test `(1-α)+α‖Wrec_deq‖<1` on served weights; train-side `σ(Wrec)≤0.9`. |
| **A3** | Confirmed cause; "MAE≤0.03 impossible without scar-mod" **[CORRECTED → hypothesized, gated by ablation]** (asserted, not yet measured). | scar-mod summary in `x_t[9:17]` (input-side, no contract break); producer fork **U1**. | Ablation: with/without `x_t[9:17]`; assert without > 0.03 floor, with ≤ 0.03 held-out. |
| **A9** | **[CORRECTED] — spec-only, NOT a current bug.** The existing nudge **already per-element clamps**: `max(-1,min(1,…))` at `resonance_integration.py:627/629/631`. Future residual only. | When Stage-C lands: `b_res` **pre-tanh** inside `BroadCore.step()`; never a post-hoc `base[i]=` write (kills the `:625` alias). | Property test `z_t∈[-1,1]^8` ∀`b_res`; grep-gate no post-tanh `base` residual write. |

### Cluster-B — tick / nudge / expression / KD contract (B4, B2, B10, C8)
| ID | Verdict | Fix (file:line) | Test |
|---|---|---|---|
| **B4** | Confirmed (incl. ComputationSpine vacuous-test). **Resolve before B2.** | Per-side-effect **REPLACE-vs-PRESERVE** in both spines (`resonance_integration.py:588-647`, `computation_spine.py:511-565`): student REPLACES `base[0,1,2]` only; PRESERVE wound/scar/void/撒娇·生气/`expression.accumulate`. | Spine-specific tests: student drives `base[0,1,2]` AND each side-effect fires exactly once. |
| **B2** | Confirmed; floor=1; tick-level **forced** (per-call welds core into the field ⇒ Phase K impossible). **[Grounding CORRECTED]** `_evolve_base` defined `:276`, called `:402`. | Tick-level recurrent map; target = final post-tick base after both `step()`s (`void_scar_engine.py:182,186`) + B4-preserved side-effects; corpus tick-granular. Coupling add-on → **U4**. | Tick-parity ≤0.03 held-out; assert exactly one inference/tick. |
| **B10** | Confirmed hidden behavior change (`should_express` = bifurcation+HGT-veto+bandit, not `z[6]>thr`). | DROP the `should_express` head in Ring 1; remove `BCE·0.2` (same loss line as C8); fix #6 → monitor-only. | Assert no `should_express` head, no BCE term; shadow-log (not gate) expression divergence. |
| **C8** | Confirmed — EmotiCore is an orphan `.pyc`, `λ_kd=0` always; cited teacher is a 128-dim text Transformer (category mismatch). | DELETE `λ_kd·EmotiCore_soft` + the "λ_kd=0/no teacher" clauses (same line as B10); CI grep-gate. | grep-gate fails if `EmotiCore`/`lambda_kd` reappears; loss has no KD term. |

### Cluster-C — corpus / leakage / cost / theater (C6, C7, C11)
| ID | Verdict | Fix | Test |
|---|---|---|---|
| **C6** | Real; mechanism **[CORRECTED]** — par1 logs **post-nudge `f_*`**, does NOT copy `x_t`'s `a_*`; "student copies `x_t a_*`" is FALSE. The real (weaker) leak: same-tick `a_*` is both input and inside the nudged target. | Stage-B target = `d_t = a_t − base_pre_nudge` (shared instrument, logged at the pre-nudge point near `:625`); KS → admission only; promote on held-out MAE on `d_t`; manifest carries `assessor_version`. Fork **U2**. | Leakage guards: `corr(pred d_t, a_*-bearing inputs)` flag>0.7/abort>0.95; **field-ablation control** (predict `d_t` from `x_t` alone must fail); variance floor; session-split. |
| **C7** | Confirmed gap (cost-gating starves the labels the brain needs). | Mandatory assessor-call **exploration floor `ρ_floor`** on gated-away ticks, stratified on `(conf,surprise)`; savings ceiling `(1−ρ_floor)·gateable`. Magnitude → **U3/D-8**; **global token-bucket** not per-session (R2). | Gated-away ticks still sample at rate ≥ `ρ_floor`/stratum; burst test cannot exceed the global budget. |
| **C11** | Confirmed circular — field already injects `a_*` every tick, so distilling post-nudge `f_*` shows zero increment. | ROI = predict `d_t` (or next-tick `a_{t+1}`) **before** the LLM call. **Add an independent ROI readout (`a_{t+1}`)** so C11 is not validated by the same `base_pre_nudge` construction it shares with C6. The real-data Probe 2 gate (ADR-0001) is the pass condition. | Probe re-run on **real** data beats persistence **and** steelmanned field+nudge by ≥15% rel ∧ ≥0.02 abs on the autocorrelated slice; report skippable as an **upper bound**, net of `ρ_floor`. |

### Cluster-D — versioning / lifecycle / salt / breaker / latency (D12, D13, D14, D15, D5, D16)
| ID | Verdict | Fix | Test |
|---|---|---|---|
| **D12** | Partial — gap real; residual-snapshot claim premature. | `_core_fn` runtime-only; per-session `b_res` rides snapshot with `core_version`; every `.npz` carries a manifest `{model_version, schema_version, input_contract_hash, sha256, quant_recipe, …}`; unknown schema ⇒ **refuse**, not silent v1. | Unknown `schema_version`/hash-mismatch ⇒ RefuseLoad + keep prior pinned + alert. |
| **D13** | Partial — materializes once Stage-C exists. | On re-distill bump `core_version`; `restore()` discards `b_res` on mismatch; add `core_version` to residual to/from_dict. | Round-trip: residual under version A restored under B ⇒ discarded; same ⇒ preserved. |
| **D14** | Confirmed; **[CORRECTED] failure mode REVERSED** — `salt=""` is **STABLE/cross-deploy-linkable** (`telemetry/sink.py:74`, `config.py:217`), not per-process-random. | Pick: per-process-random-on-empty OR refuse-enable-on-empty; deployment collection **MUST use refuse + explicit stable salt** (deletion needs it). Add `delete_session()`/tombstone. Gates R1. | Empty-salt ⇒ refuse-enable; `delete_session()` tombstones. |
| **D15** | Partial — **[CORRECTED, fabrication removed]:** there is **NO** breaker/limiter at `resonance_integration.py:387-426` (verified: personality/HDC/gate/VoidScar process). The contraction breaker is **greenfield**, no sibling to conflate. | New `‖Δbase‖` breaker, non-proven modes only, before canary; trip on proven path = ALARM→rollback. State it does NOT contradict §5.1. | Fault-injection (NaN/corrupt/int8-edge) trips the new breaker → next tier. |
| **D5** | Partial — conclusion right; **[CORRECTED]** the Kuramoto/Hopfield loop is **RETIRED PRIOR CODE**, not a Ring-2 add. | Doc-only: Ring 1 keeps single-pass `resonate()` UNCHANGED (no win, no regression); Ring 2 eliminates it. | Ring-1 latency p50/p95/p99 SLO: no regression. |
| **D16** | Enumeration (plugin/corpus). | Before Phase K verify in `G:/Sylanne-next`: `.engine` forwarding, same spine instance, residual subsystem (`state_persistence._VALID_SUBSYSTEMS`, **plugin-only**), 1M corpus exists & schema-matches. **V1 done (§3); V2/V3/V5 open.** | Plugin contract test: `EngineFacade.engine` = student backend; corpus census. |

### Completeness (review-missed findings, new risks, unverified, modalities)
| ID | Verdict | Fix | Test |
|---|---|---|---|
| **U1/V4** int8 PTQ reproducibility | **CRITICAL.** Cert proven on f32-torch, served on numpy int8; two paths, no pinned recipe, σ_max can flip after the gate. | Pin `{quant_scheme, per_channel, rounding, accumulator}` in manifest; refuse-load on mismatch; cert re-runs on dequant int8 (A1). | **Golden-vector CI**: numpy-serve == f64-ref `<1e-6` across numpy versions + on the 2c2g box. |
| **U2/M2** concurrency | **CRITICAL** (tied most-dangerous); zero review finding. | §5.3 concurrency block (read-only core, session-local `b_res`, atomic hot-swap, copy-on-snapshot). | N-session stress: per-session trajectories match solo `<1e-9`, pinned single-thread BLAS; hot-swap-mid-tick race. |
| **U3** teacher determinism | HIGH. | GREEDY policy, frozen RNG, sorted scars in `simulate_corpus.py`. | Two gen runs byte-identical before P0. |
| **U4/M3** failure matrix | HIGH (§5.3). | Tested outcome per cell; default fall-back-to-field, alert, no NaN. | Each cell → defined outcome; no NaN reaches the result dict. |
| **U5/M4** observability | MED-HIGH. | stdlib-only: student-vs-field divergence, `b_res` drift, per-tier fallback rate, breaker/refuse counters, brain-loop staleness (`kernel.py:927-986`). | Each counter increments on its event; staleness fires when stale. |
| **U6** dt/timestamp | MED. | Decide α `dt`-scaled vs fixed; restate the §5.1 bound; log numeric `dt` (D-13). | First-tick-after-restore (large `dt`) stays bounded; corpus-vs-serve `dt` match. |
| **R1** PII surface | New (from fixes). `base_pre_nudge`+`a_*` is the richest surface; depends on D14. | Default-off + **D14 fix first** + consent gate + HDC-inversion test (harness §2.4). | Sink refuses to enable while salt empty/stable or consent absent. |
| **R2** ρ_floor DoS | New. | Global token-bucket, not per-session prob. | Burst: N sessions cannot exceed the global budget. |
| **R3** spine asymmetry | New. Trained on one spine, served on both (撒娇/生气). | Stratify corpus by spine; parity-gate both. | Emotion MAE≤0.03 on both spine paths. |
| **R4** SVD boot error | New. | Wrap the norm cert in try/except → RefuseLoad. | Degenerate `Wrec` ⇒ RefuseLoad, not crash. |
| **R5** loss-head recalibration | New. Dropping BCE/KD shifts the 0.03 calibration. | Re-tune the P1 gate after head removal (with ADR §6 power treatment). | Re-run P1 gate post-removal; threshold still separates. |
| **V1** plugin `.engine` | **Verified GREEN this session** (plugin emotion-read path, §3). Keep as regression guard. | None. | Overlay==telemetry; `EngineFacade.engine`=student (plugin-side). |
| **V2/V3/V5** | Unverified: V2 1M corpus not counted; V3 no `assessor_version` field; V5 current field contractivity (power-iter underestimate). | Count+schema corpus (V2); add `assessor_version` (V3, lands with D12); exact-norm load recheck on the field (V5). | Census; manifest has `assessor_version`; exact `‖W‖₂` on field weights. |
| **M1** corpus privacy lifecycle | Modality. Plaintext JSONL, no deletion. | Encryption/retention/deletion/egress policy; 0o600; tombstone (D14). | Retention enforced; `delete_session()` tombstones; no egress. |
| **M5** .npz integrity | Modality. Brain loop writes cores the runtime loads. | `np.load(allow_pickle=False)` always; sha256 + atomic write. | Tampered/non-atomic `.npz` ⇒ RefuseLoad. |

**Resolution order:** B4 → B2 (B2's target depends on B4's preserved side-effects). C8 + B10 edit the
**same loss line** — land together behind one CI grep-gate (no partial land). The `base_pre_nudge`
instrument lands **once** (shared C6 + C11; plus the independent `a_{t+1}` readout for C11). The
manifest/contract-hash bump lands **once** (D12 + D13 `core_version` + V3 `assessor_version` + sha256 +
U1/V4 quant recipe). A9 pre-tanh residual + A1 contraction are **mutually reinforcing** — `b_res` is
additive and constant in `z_{t-1}`, invisible to the Jacobian.

**Overstatements the digest corrected — do NOT re-introduce:** A9 (spec-only, nudge already clamps);
D14 (`salt=""` is stable, not random); D15 (**no** breaker at `:387-426`); D5 (Kuramoto loop is
retired code); C6 ("copies `x_t a_*`" is false); A3 ("info-theoretically impossible" → hypothesized);
and all spike numbers are synthetic targets, not results.

---

## 7. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Model | tiny recurrent cell (~3.4K), convex-combo + spectrally-normed `Wrec` | boundedness+contraction architectural & provable (§5.1) |
| Training | PyTorch (truncated BPTT, AdamW+cosine), owner GPU only | reuses `train_model_torch.py` + numpy export; never shipped |
| Quant | int8 per-tensor symmetric PTQ + **pinned recipe in manifest + golden-vector CI** | `.npz` < 8 KB; gated by parity; closes the torch→numpy boundary (U1/V4) |
| Serving | pure numpy int8, inline | no torch/onnx; no latency regression Ring 1 (resonate() stays; win at Ring 2) |
| Online residual | bounded plastic readout bias (elastic ≤30%, EMA), session-local | no backprop at serving; concurrency-safe (§5.3) |
| Corpus | sim full-transition parquet (Tier-1); CORE2 `x_t→a_*` (Tier-2), default-off | §9 two-tier durable asset |
| Registry | flat `models/` + `manifest.json` + Git-LFS | repro/provenance/migration, zero infra |
| Fallback floor | ~20-line pure-Python analytic core compiled into source | survives a bad `.npz`; the true last resort |
| Tests/lint/types | pytest+pytest-asyncio, ruff(+ASYNC), mypy --strict | AstrBot §10/§11 |

---

## 8. Phase K — retiring the field from the runtime (the kill, gated)

Only after the learned core is proven (P4 + Phase B). A **two-release quarantine**, never a one-shot
delete. All six gates must pass.

- **K1 — runtime teacher replaced** (learned core drives `base` by default, proven through P4+Phase B).
- **K2 — fallback replaced + floored** (pinned-npz backed by the analytic floor; runtime guard wraps
  load+compute; fault-injection CI proves the floor engages).
- **K3 — stability made architectural** (§5.1 static proof on served int8 weights; never val-MAE).
- **K4 — both spines enumerated** (`ResonanceSpine` + `ComputationSpine` 撒娇/生气 either learned or
  formally dropped as a signed-off behavior change).
- **K5 — post-deletion config proven** (validation window with the field import **physically disabled
  (flag off)** so the actual shipped fallback chain takes real traffic + injected faults + a
  cold-start cohort `base=0`; prove *what you ship*, not "core + field-fallback").
- **K6 — quarantine-then-delete across two releases** (Release N: field flagged off, dead, shipped,
  rollback = flip the flag; Release N+1: `git rm` the field from the live path, toggle deleted LAST).
  **The field source is NOT removed** — moved to `training/reference_teacher/` (frozen, version-
  pinned, import-only, no runtime path) as the regeneration oracle (§9).

**Field-source custody (the most-irreversible artifact gets the most governance — completeness gap):**
the frozen `reference_teacher` has a named owner, a fixed storage location, a recorded **sha256 pin**,
and a **CI "no-delete" guard** that fails any change removing it. The thing declared the one
irreversible white-train must not be lost to an accidental `git rm`.

**Why source-retention is mandatory:** the field is the only deterministic, infinite generator over
the full state space; real corpora are an on-distribution sample. Deleting the source makes
off-distribution data (future wider clamps, D-7 dims, Ring 2) permanently unregenerable.

---

## 9. Data lifecycle & anti-wasted-training contract

**Claim (scoped, true): updating the SDK never wastes training** — learning lives in durable data + a
deterministic generator; weights are a regenerable cache.

**Two-tier durable asset**
- **Tier-1 — Regeneration oracle (retrains ANY architecture; covers off-distribution).** Frozen
  `reference_teacher` (demoted field source) + the versioned `simulate_corpus` full-transition
  parquet. *Why the source can't be `git rm`'d.* Kept forever.
- **Tier-2 — Real-semantics corpus (retrains the SHIPPED contract; on-distribution).** CORE2
  (`x_t → a_*`, input-complete; schema and capture in `v3-realdata-harness-spec.md`) + par1 (endpoint
  diagnostics). The brain's food; the thing the field can never generate.

**Retracted:** "par1 alone retrains any future architecture." par1 is endpoint-only; broader needs are
regenerated from Tier-1.

**SDK-update decision table**
| Change | Action | Wasted? |
|---|---|---|
| No core-IO-contract change | weights load as-is (`input_contract_hash` matches) | none |
| Same contract, retrain wanted | replay Tier-2 (CORE2) → retrain shipped contract | compute only |
| New architecture / wider dims | regenerate from Tier-1 + re-fold Tier-2 real labels | compute only |

**Versioning / migration (must land before Phase K):** every `.npz` carries a manifest
`{model_version(semver), schema_version, feature_order, input_contract_hash, torch_version,
numpy_version, seed, quant_recipe, assessor_version, sha256}`. Load policy: hash match ⇒ load-as-is;
mismatch ⇒ auto-retrain **iff** corpus schema ⊇ required inputs, **else refuse + keep prior pinned +
alert**. Auto-retrain is **gated, not auto-promote** (must beat the prior pinned core on a frozen
held-out set — KS + MAE + trajectory — reproducible via pinned seeds/lib-versions). The pinned-last-
good `.npz` is contract-pinned and **regenerated on every contract change**.

**Corpus schema discipline (forward-only):** append-only columns, nullable appends,
`FEATURE_SCHEMA_VERSION` bump each append; schema-aware loader up-projects old rows; mixed-schema
training parity CI. (Fixes the silent "fall back to v1 on unknown version" mis-parse.)

**Input-completeness one-way doors (settle before more collection):**
- **D-12 (message bandwidth).** Carry the message as **WIDE HDC density** (numeric, non-invertible*),
  and **widen via D-7** (assessor emits more numeric affect dims) — **never** raw text or invertible
  sentence embeddings (re-identification breaks no-PII). The spike confirmed width matters
  *mechanically* (V0→V4→Vfull); the *real-text* size is open. **Recommend yes.** *non-invertibility
  unverified (harness §2.4).
- **D-13 (time).** Log numeric `dt` per row **now** (non-PII; sim parquet already carries it).
  **Recommend yes.**

---

## 10. Phased rollout (re-sequenced for the v4 gate; each reversible; kill switch = flag → fallback)

| Phase | Work | Gate |
|---|---|---|
| **Phase 0 — Collection (AUTHORIZED NOW, NOT P0)** | CORE2 sink + salt/consent fix + `core2_to_corpus.py` + probe additions, all default-off (`v3-realdata-harness-spec.md`); deploy runbook HELD | privacy gates green (R1 salt, consent, HDC-inversion test); ≥30-session pilot → ADR §6 N |
| **★ REAL-DATA GATE (ADR-0001)** | re-run Probe 2 on real data vs persistence **and** steelmanned field+nudge, autocorrelated slice | **PASS ⇒ enter P0; FAIL/escalate ⇒ STOP** |
| **P0** | `simulate_corpus.py` (full per-step + dt) → Tier-1 parquet + manifest; **deterministic teacher (U3)** | — (offline) |
| **P1** | train BroadCore-S (BPTT) → int8 `.npz` + manifest | int8 emotion MAE ≤0.03 (**power-treated, ADR §6**), res ≤0.05, traj-corr ≥ floor, **numpy==torch golden-vector (U1)**, **K3 static contraction proof** |
| **P2 Shadow** | `BroadCoreRuntime` computes+logs, field drives; student-vs-field on real traffic | base + expression divergence ≤ thr; KS OK |
| **P3 Canary** | student drives `base` for a canary %; circuit-breaker + layered fallback + residual + **concurrency stress (U2)** on | trajectory stability; expression divergence ≤ small %; latency/RSS SLOs; per-session isolation `<1e-9` |
| **P4 Promote Ring 1** | student is the core by default; online residual on; auto-rollback armed | sustained SLOs |
| **Phase B (brain)** | CORE2 re-distillation vs assessor; KS-gated promote; **field-ablation control** | re-distilled core beats prior on held-out real traffic on `d_t` |
| **Phase M (cost)** | confidence-gate the assessor; **`ρ_floor` exploration via global token-bucket** | LLM-call rate ↓ vs v1/v2 (net of `ρ_floor`), affect quality held |
| **Phase K (retire field)** | execute K1–K6; demote source to `reference_teacher` with custody (§8) | all six kill gates green |

Ring 2 / 3 are separate future cycles. Vendor cutover (owner, separate session): atomic whole-
directory swap, keep assessor knob, backup + smoke test + one-command rollback (config **and** data
side, harness §4).

---

## 11. Standards / observability / testing / governance

- **Standards**: Conventional Commits + trunk + English; ruff(+ASYNC) + mypy strict;
  pytest+pytest-asyncio; review checklist. v3 line = `next-gen` / `feat/v3-core`.
- **Observability** (stdlib-only, no egress): Tier-1+Tier-2 corpus growth, student-vs-field
  base/resonance/expression divergence, int8 parity, **per-tier fallback rate**, contraction-breaker /
  refuse-load counters, residual drift, latency p50/p95/p99, RSS, assessor-call rate (Phase M, net of
  `ρ_floor`), re-distillation version + KS deltas, **brain-loop staleness**, manifest/contract-hash on
  every load.
- **Testing**: parity (numpy==torch **golden-vector**, U1), static contraction proof (K3),
  no-split-brain (overlay==telemetry), assessment REPLACE/PRESERVE (**both spines**, B4),
  contraction-breaker + **failure matrix** (U4), fault-injection fallback (K2), cold-start cohort (K5),
  mixed-schema corpus parity (§9), **residual instance-locality under 2c2g concurrency `<1e-9`** (U2),
  **deterministic teacher byte-identical** (U3), **field-ablation leakage control** (C6), shadow-
  divergence, snapshot round-trip ±residual (D13), `.npz` integrity (M5), load test. par2 carried.
- **Governance**: opt-in default-off (`student_model_enabled`, CORE2 sink); **consent gate as an
  enable precondition**; no PII / no text / no raw embeddings / no egress; `0o600`; salted hash join
  (**D14 fix first**); retention + tombstone right-to-deletion (best-effort; raw logs only — distilled
  weights non-revocable); model registry (manifest semver + sha256 + contract-hash); CORE2 multi-user
  disclosure + minimum-N (ADR §6) before a re-distilled core promotes; **assessor-version freeze per
  campaign** (ADR §7).

---

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Theater** (clone gains nothing) | Phase B continual re-distillation; **the real-data gate (ADR-0001) blocks P0 until value is shown on non-field data** |
| **Spike's synthetic win doesn't transfer** | gate on real data; Probe 2 must beat persistence + steelmanned field+nudge on the autocorrelated slice |
| **Deleting the field source ⇒ irreversible white-train** | demote, never delete; frozen `reference_teacher` w/ custody (§8/§9) |
| **Stability swap to a weaker guarantee** | architectural boundedness + spectrally-normed `Wrec`, static proof on served int8 (§5.1, K3) |
| **int8 PTQ flips the cert (torch→numpy)** | pinned quant recipe + golden-vector CI + load-time exact-norm recheck (U1/V4) |
| **Concurrency races (shared core / hot-swap / `b_res`)** | read-only core, session-local residual, atomic swap, `<1e-9` isolation test (U2) |
| **Bad `.npz` bricks every fresh install** | layered fallback + analytic floor + fault-injection CI (K2) |
| **Prove core+field-fallback but ship core+npz-fallback** | K5 validation window with field import disabled |
| **Second spine (撒娇/生气) un-killed** | K4 both-spine kill-list + signed-off behavior decision |
| **No model_version/migration / mixed-schema rot** | manifest + contract-hash + gated auto-retrain + forward-only columns (§9) |
| **PII / re-identification (`base_pre_nudge`+`a_*`)** | D14 salt fix first + consent gate + HDC-inversion test + retention/tombstone (R1/M1, harness §2) |
| **`ρ_floor` cost-DoS** | global token-bucket (R2) |
| Split-brain / step-chain desync / a_* double-apply / coherence desync / expr flips | ledger §6 fixes |
| No teacher `.pt` | `λ_kd` deleted (C8); field-distill + assessor sufficient |

---

## 13. Open decisions for the owner

- **D-1 RESOLVED**: broad scope, Ring 1, brain loop committed.
- **D-retire RESOLVED (v3)**: field out of the runtime (Phase K), source demoted to a frozen
  `reference_teacher`.
- **Gate RESOLVED (v4 / ADR-0001)**: do not enter P0 on the spike; collect real data, re-run Probe 2.
- **Owner forks (ledger §6):** **U1** scar-mod producer post-Phase-K (rec: scoped `ScarModulator` stub,
  no seed=42 MLP) · **U2** leakage-free target (rec: `d_t` + independent `a_{t+1}` readout; **only U2
  touches the spike**) · **U3** `ρ_floor` magnitude (bind `N_min` to D-8) · **U4** coupling magnitude in
  `x_t` (rec: reactive — add only if P1 MAE fails) · **U5** input-only vs state-gated cell (rec:
  input-only, closed-form Jacobian).
- **D-7 (assessor extension):** more numeric affect dims (curiosity/intimacy/boundary). Backward-
  compatible; lifts the D-12 bottleneck. **Recommend yes.**
- **D-8 (Phase M aggressiveness)** · **D-9 (online residual reach)** · **D-10 (CORE2 governance:
  retention, disclosure, minimum-N)** · **D-11 (Ring 2 trigger)** · **D-12 (message bandwidth — widen
  via D-7, never embeddings; recommend widen)** · **D-13 (log `dt` now — recommend yes)**.

---

## Appendix A1 — par2 timing loop (carried spec)

SDK: `+report_reach_outcome(session_id, originating_tick, outcome, *, dispatch_ts=None,
observed_ts=None, latency_turns=-1, apply_online=False) -> bool`; `+Par2Sink`
(`reach_outcomes.jsonl`, `PAR2_SCHEMA_VERSION=1`); `+SylanneConfig reach_outcome_sink/path`;
`+host_payload originating_tick/guard_allowed` (additive read-only); `+SYLANNE_CAPABILITIES`. Plugin:
`awaiting_par2_outcome` store (persisted, restart-safe), arm on `bridge.dispatch()=={dispatched:True}`
∧ `guard_allowed` ∧ `decision.action=='reach_out'`, classify from the reply tick's assessment,
`ignored` on a default-4h timeout sweep. Reward stays discrete; never wound-delta; never into emotion
loss.

## Appendix A2 — key file pointers

SDK: `scar_algebra.py:276` (`_evolve_base` **def**, boundedness = final `tanh` `:304`), `:402`
(`_evolve_base` **call** in `step()`), `:231-232` (`max_sigma=0.7`), `:352-363` (`modulate`);
`void_scar_engine.py:182,186` (per-tick `step()` chain) `:211-233` (`observe`);
`resonance_integration.py:343-511` (`process`, HDC→ssm at `:413-423`) `:588-647`
(`_apply_assessment_to_engine`, clamped writes `:627/629/631`) `:886-939` (`_build_result`);
`computation_spine.py:511-565` (`apply_assessment`, **撒娇/生气**); `kernel.py:47-53` (`_DEFAULT_SPINE`
fallback) `:265-270` (`process` call) `:298` (`_capture_telemetry` call) `:605-612`
(`_computation_emotion_overlay` → `.engine.observe()`) `:927-986` (`_capture_telemetry`);
`telemetry/sink.py:33` (`FEATURE_SCHEMA_VERSION`) `:37-64` (`AFFECT_CONTEXT_FIELDS`) `:74`
(`anonymize_session`); `meta_learner.py:198-260` (`update`); `config.py:215-217` (`training_data_*`).
**Plugin (`G:/Sylanne-next`, out of SDK scope):** `engine_adapter.py:129` (`EngineFacade`),
`llm_request_pipeline.py:1601` (emotion read — V1 verified GREEN), `state_persistence.py`
(`_VALID_SUBSYSTEMS`), `proactive_bridge.py:301` (`dispatch`), `main.py:1106` (`on_message`).
