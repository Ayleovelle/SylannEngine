# v3 TDD — Adversarial Review Digest

> **Status (2026-06-25): FOLDED INTO v4.** This digest's findings are now resolved in
> `v3-student-pipeline-tdd.md` §6 (the review-resolution ledger), with the go/no-go decision in
> `adr-0001-v3-core-go-no-go.md` and the collection gate in `v3-realdata-harness-spec.md`. It is kept
> as the audit trail. **Two corrections a later adversarial pass found in THIS digest** (now fixed in
> v4): (1) **D15 is partly fabricated** — there is **no** breaker/limiter at
> `resonance_integration.py:387-426` (verified: those lines are personality-overlay / HDC /
> predictive-coding gate / VoidScar `process()`); the contraction breaker is greenfield with no
> sibling to "not conflate" with. (2) The spike's "field is semantic-blind" framing is **overstated**
> — the field's pre-nudge base **has** seen the message (`HDC → ssm_input → _evolve_base`); the
> defensible claim is "the field's *fixed* transform doesn't recover the assessor's read, a trained
> core does." Also: the spike's Probe-2 win **reverses on the autocorrelated slice** (student 0.200 vs
> persistence 0.197) and Probe 2 never ran the binding field+nudge baseline — see ADR §1.4.

Companion to `v3-student-pipeline-tdd.md`. Source: a 66-agent owner review (22 findings, 2 blockers)
→ digested by an 11-agent verify/fix/cross-check/spike/completeness workflow (2026-06-25).
Raw output: `…/tasks/wa4zoyds2.output` (temp). This file is the durable v4 input.

**Verdict in one line:** the review is right on the substance; several claims were *overstated* (caught
on re-verification); and the digest surfaced two **worse, unaddressed** problems — concurrency and int8
reproducibility — plus one cheap one-file check (plugin `.engine`) that gates the whole no-split-brain story.

---

## 1. Consolidated remediation ledger

| ID | Verdict (after re-verify) | Final fix (one line) |
|---|---|---|
| **A1** proof | real bug; patch (z_{t-1} out of x_t) **correct & sufficient** for the dual path; cert half **uncertified** until load-time recheck | `J=(1-α)I+α·diag(tanh'_u)·Wrec_sn`. Cert at LOAD on **dequant int8**: exact `np.linalg.norm(Wrec_deq,2)<1-margin`, `α∈[ε,1-ε]`, else RefuseLoad. Train: spectral_norm Wrec→σ≤0.9; α via sigmoid. K3 gate = this static check, never val-MAE. |
| **A9** residual bound | **overstated as current-code bug** (Stage-C is spec-only; existing nudge already clamps); real bug for the *future* residual | Inject plastic bias **pre-tanh**: `u=tanh(z_{t-1}·Wrec_sn+h·Wout+b_res)`. tanh keeps `[-1,1]^8`, b_res invisible to A1's Jacobian. Apply inside `BroadCore.step()`, never a post-hoc `base` write (kills the `:625` alias). |
| **A3** scar-mod parity | **confirmed** — without `modulate()` (scar history) in x_t, MAE≤0.03 info-theoretically impossible | Keep scar-mod summary (8 floats, `scar_algebra.py:352-363`) in x_t[9:17]; it's a *cause*, input-side, no contract violation. Compute once before the core. **Phase-K gap → decision U1.** |
| **B2** tick-vs-call | **confirmed**; floor is **1** not "2..N"; tick-level **forced** (per-call embeds core in field's loop ⇒ Phase-K impossible) | One inference/tick; target = final post-tick base (after both `step()`s + preserved side-effects). Corpus tick-granular. Coupling-magnitude add-on → **decision U4**. Resolve **B4 first** (its target depends on B4). |
| **B4** skip-nudge drops side-effects | **confirmed** incl. ComputationSpine vacuous-test | Replace "skip nudge" with per-side-effect **REPLACE-vs-PRESERVE**: student owns ONLY ResonanceSpine continuous valence/arousal `base[0,1,2]`; PRESERVE wound-step/scar/void/撒娇·生气/expression.accumulate. Spine-specific tests. |
| **B10** should_express | **confirmed** hidden behavior change (it's bifurcation+HGT-veto+bandit, not `z[6]>thr`) | DROP the BroadCore should_express head in Ring 1; expression decision stays field-side on student base. Remove the BCE term. fix #6 → monitor-only. |
| **C6** Stage-B leakage | **real** (mechanism partly overstated: par1-as-built logs post-nudge f_*, no x_t copy) | Target must not be the same-tick a_* that's in x_t. Use divergence `d_t=a_t−base_pre_nudge`. KS→admission only; promote on held-out MAE on d_t. Manifest: assessor_version + label-drift. **→ decision U2.** |
| **C8** λ_kd ghost | **confirmed** — EmotiCore is orphan .pyc, λ_kd=0 always; cited teacher is a 128-dim text Transformer (category mismatch) | DELETE the KD term + the "λ_kd=0 / no teacher .pt" doc clauses. CI grep-gate against EmotiCore/lambda_kd reappearing. Lands with B10 (same loss line). |
| **C7** cost vs label-starvation | **confirmed** gap | Mandatory assessor-call **exploration floor** ρ_floor on gated-away ticks, stratified on (conf,surprise). Magnitude → **decision U3**. Realized savings ceiling = (1−ρ_floor)·gateable. |
| **C11** ROI/theater circular | **confirmed** — field already injects a_* every tick, so distilling post-nudge f_* shows zero increment | ROI = predict `d_t` (the correction the field wouldn't make) **before** the LLM call. Shared `base_pre_nudge` instrument. **The NTAP spike (§3) defines the previously-undefined pre-P0 pass condition.** |
| **D12** snapshot versioning | partial — gap real (bare version string, silent legacy-drop); residual claim premature | `_core_fn` runtime-only (never snapshot). Per-session `b_res` rides snapshot with a `core_version` tag. Snapshot manifest {model_version,schema_version,input_contract_hash,sha256}; unknown schema → **refuse**, not silent v1. |
| **D13** orphaned residual | partial — materializes only once Stage-C exists | On re-distill, bump `core_version`; `restore()` discards b_res on mismatch (reset to seed). Add core_version to residual to_dict/from_dict. |
| **D14** salt/deletion | confirmed both; **failure mode REVERSED** — salt='' is *stable* (cross-deploy linkable), not per-process-random as the docstring claims | Pick: implement real per-process random on empty, OR require non-empty per-deployment salt + refuse-enable on empty. Add `delete_session()`/tombstone (no erasure path today). |
| **D15** breaker vs proof | partial — **two breakers conflated** (existing `:387-426` is a wound-rate limiter, unrelated) | Scope the future ‖Δbase‖ breaker to **non-proven** modes only (corrupt/NaN/int8-edge/load-bug). A trip on the proven path = precondition-violation ALARM → rollback. State in §5.3 it does NOT contradict the proof. |
| **D5** latency | partial — conclusion right; precision: the Kuramoto/Hopfield loop is **retired prior code**, not a Ring-2 future add | Doc-only: Ring 1 keeps single-pass `resonate()` UNCHANGED → no win, no regression; Ring 2 *eliminates* resonate(). |
| **D16** plugin/corpus unverified | enumeration | Before Phase K verify in `G:\Sylanne-next`: EngineFacade forwards `.engine` (no split-brain), same spine instance, residual is a valid persistence subsystem, 1M corpus actually exists & schema-matches. **V1 below is the cheap gate.** |

**Resolution order:** B4 → B2 (target depends on B4). C8+B10 edit the same loss line — land together. `base_pre_nudge`
instrument (C6+C11) lands once. assessor_version (C6) + manifest/contract-hash (D12/D13) + sha256 land in one §9 bump.
A9 pre-tanh residual and A1 contraction are **mutually reinforcing**, not in tension.

---

## 2. Owner decisions (5 genuine forks; recommendations marked)

- **U1 — who computes scar-mod after Phase K?** A3 needs the field's `modulate()` in x_t; Phase-K K1 says no
  field call. **Rec B:** retain a scoped `ScarModulator` stub (scars + modifier cache + `modulate()`, NO seed=42
  MLP) as the deterministic producer; fold into the student in Ring 2. North star (kill the seed=42 MLP) still met;
  §8 must separate "MLP retired" from "scar bookkeeping retained". (Alt A: gate K1 to include scar-mod; risks
  indefinitely blocking Phase K if Ring 2 slips.)
- **U2 — leakage-free target: next-tick `a_{t+1}` vs divergence `d_t`?** **Rec d_t (1b):** one shared
  `base_pre_nudge` instrument de-circularizes BOTH C6 and C11; no right-censoring. (a_{t+1} needs a 2nd instrument
  for C11 anyway.) *Spike note: cheap to run BOTH — see §3.*
- **U3 — exploration-floor ρ_floor magnitude.** Cost win vs label coverage; no free lunch. Needs N_min fixed (bind
  to D-8). Accept the stated savings-ceiling reduction as an owner-visible cost.
- **U4 — coupling_wound_magnitude in x_t: proactive or reactive?** **Rec reactive (a):** ship scar-mod-only; add the
  coupling scalar to x_t[25:40] ONLY if P1 MAE≤0.03 fails. Keeps x_t minimal; the gate forces it.
- **U5 — input-only gate vs state-gated cell.** **Rec A:** ship the input-only gate (closed-form Jacobian); reopen
  only if Stage-A parity provably fails. (State-gating downgrades K3 from static proof to sampled cert.)

Only **U2 touches the pre-P0 spike**; U1/U3/U4/U5 are P1/Phase-K and can wait.

---

## 3. NTAP — the pre-P0 ROI / anti-theater spike (kill-or-continue gate)

**Why naive metrics are rigged:** the field's `_apply_assessment_to_engine` injects a_valence/a_arousal into
`base[0,1,2]` every assessed tick, so the field is NOT semantics-blind; "student vs field-with-a_t-withheld" cripples
a baseline nobody ships. The spike must isolate the only things a learned core adds: **cross-tick memory** and
**richer-than-4-scalar message content**.

**Fair metric (NTAP = Next-Tick Assessor Prediction):** from observables up to tick t, predict the **next assessed
tick's** `a_{t+1}=(valence,arousal[,wound_risk])`, joined `(session,t→t+1)`. Leakage-free (a_{t+1} was injected into
nothing at t), and it's the **same quantity Phase M needs** (predict a_{t+1} ⇒ skip the LLM call). *We also run the
C11 divergence `d_t` variant — same `base_pre_nudge` instrument, answers "can the core replace this call now".*

**Setup:** run the real field **headless** (`simulate_corpus.py`, ~150 LOC, becomes the reusable Tier-1 generator)
over **domain-randomized, temporally-autocorrelated** a_* sequences (AR(1)/regime-switching — iid would make a_{t+1}
unpredictable-by-construction and fail for the wrong reason; include near-iid controls). Log the full tick row incl.
`base_pre_nudge` (post-`_evolve_base`, pre-nudge — shared with C6/C11) and **full HDC**. Train the §5.1 recurrent cell
(f32, no int8 — learnability not serving) + a small `a_{t+1}` head, truncated BPTT, **session-split**.

**Baselines (both, on the identical held-out split):** (1) field+nudge as a *steelmanned* ridge/GBM regressor from
tick-t observables (give it its best reactive shot); (2) **persistence** `â_{t+1}=a_t` (zero-param floor under the floor).

**HDC ablation (doubles as the D-12 test):** V0 (no message) / V4 (4-float HDC) / Vfull (wider HDC). If V4≈V0 but
Vfull≫V4 ⇒ 4-float HDC insufficient, **D-12 is a HARD prerequisite, block P0 on it**. If V4≫V0, HDC sufficient.

**PASS:** student valence+arousal MAE beats BOTH baselines by ≥15% rel AND ≥0.02 abs, holds on autocorrelated +
held-out sessions, all leakage guards green (corr(â,x_t[0:4])<0.95, variance floor, session split). Report the
**skippable-fraction** (the ROI number).
**FAIL ⇒ STOP — do not enter P0.** The field's reactive nudge already extracts everything the assessor gives;
BroadCore-S would be an expensive clone. *This is the gate working.*

**Cost:** ~2-3 days (simulate_corpus is reused, not throwaway); generation minutes; a few short owner-GPU runs. Pure
offline — no serving/int8/manifest/plugin/kernel changes.

---

## 4. What the review itself MISSED (completeness critic)

**New findings (unlisted ~6):**
- **U1/V4 (CRITICAL) int8 PTQ reproducibility.** The whole contraction cert is proven on f32 (torch PTQ export) but
  served by hand-rolled numpy int8 dequant — two code paths, no pinned quant recipe, no golden-vector test. σ_max at
  load can differ from export by > margin, silently flipping contractive→not AFTER the gate passed. **Fix:** golden-vector
  CI (freeze {q,scale,zp}+inputs, assert numpy serve == f64 ref <1e-6 across numpy versions + the 2c2g box); record
  quant_scheme/per_channel/rounding/accumulator in manifest; refuse-load on mismatch.
- **U2/M2 (CRITICAL) concurrency.** 2c2g multi-session + online-mutating per-session `b_res` + a background re-distill
  loop **hot-swapping the shared core .npz mid-tick** = race hazards; zero dedicated finding. **Fix:** shared core
  read-only (assert not WRITEABLE); b_res strictly session-local; atomic core hot-swap (load new obj, swap ref under
  lock, never mutate in place); copy-on-snapshot; b_res invalidated atomically with a swap; N-session stress test asserts
  per-session trajectories are bit-identical to solo.
- **U3 (HIGH) teacher determinism.** Stage-A clones the field, but the expression policy has ε-exploration ⇒ corpus is a
  moving target. **Fix:** corpus capture uses the GREEDY policy, RNG frozen, scar iteration sorted; assert two gen runs are
  byte-identical before P0.
- **U4/M3 (HIGH) failure-mode continuity.** "Refuse-load / breaker-trip" is specified but the user-visible degraded path
  isn't: a half-killed field + rejected student = no emotion producer. **Fix:** failure matrix with a defined, tested
  outcome per cell — default "fall back to full field path, alert, never crash, never serve NaN".
- **U5/M4 (MED-HIGH) observability.** No continuous production student-vs-field divergence, b_res drift, breaker/refuse
  counters; and the offline brain loop has no health metric (silent staleness). **Fix:** add them; in Ring 1 the field is
  still there to diff against ~for free.
- **U6 (MED) dt/timestamp.** α-based carry assumes per-tick cadence, but chat dt varies and post-restore injects a big gap;
  corpus-vs-serve dt consistency unchecked. **Fix:** decide α dt-scaled vs fixed; restate the bound accordingly; test
  first-tick-after-restore.

**New risks introduced BY the fixes:** R1 `base_pre_nudge`+a_* is the richest PII surface yet (depends on the unfixed
D14 salt) → gate behind default-off sink + require salt fix first; R2 exploration-floor can cost-DoS under multi-session
bursts → global token-bucket not per-session prob; R3 spine-asymmetry (student trained on one spine, served on both) →
stratify corpus by spine, parity-gate both; R4 SVD cert can `LinAlgError` at boot → wrap in try/except→RefuseLoad; R5
dropping loss heads shifts the 0.03 MAE calibration → re-tune the gate.

**Unverified claims that matter:** **V1 (CRITICAL, cheap)** — does the plugin `EngineFacade` (`engine_adapter.py:129`)
actually forward `.engine` so the prompt sees the STUDENT, not the field? One-file read in `G:\Sylanne-next`; gates the
entire no-split-brain story. V2 the "1M corpus" is asserted, not counted/schema-checked. V3 assessor versioning has no
manifest field today. V5 sanity-check the CURRENT field is even contractive (power-iter underestimate + no load recheck).

**Whole modalities un-checked:** M1 corpus privacy lifecycle (encryption/retention/deletion/egress — plaintext JSONL
today); M2 concurrency (above); M3 failure matrix; M4 observability + brain-loop health; M5 .npz integrity
(`np.load(allow_pickle=False)` always, sha256 + atomic write — the brain loop writes cores the live runtime loads).

**Single most dangerous unaddressed:** concurrency (M2/U2) tied with int8 PTQ reproducibility (U1/V4) — every Cluster-A
proof is single-trajectory and f32; neither survives a live hot-swap race or the torch→numpy int8 boundary.

**Priority order:** V1 → U1/V4 → U2/M2 → M1 → R1 → U4/M3 → V2/V3 → U3 → U5/M4 → R2 → R3 → U6 → M5 → R4 → V5 → R5.
