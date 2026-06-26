# ADR-0001 — v3 Learned Emotion Core: GO / NO-GO into P0

- **Status:** Accepted — 2026-06-25
- **Owner / decision authority:** Ayleovelle
- **Author:** Sylanne (design)
- **Relates to:** `docs/design/v3-student-pipeline-tdd.md` (TDD v4), `docs/design/v3-review-digest.md`
  §3 (the spike spec), `docs/design/v3-realdata-harness-spec.md` (the gate made concrete),
  `training/student_core/RESULTS.md` (the spike results this ADR ratifies).
- **Decision in one line:** Do **not** enter P0 on the offline spike alone. Gate the real go/no-go
  on collecting real assessor-labeled traffic (par1 / CORE2) and re-running the probes on it.
- **Honesty note (read first):** the spike is *weaker* than an early read suggested. The headline
  "a cheap core beats the field" survives, but the win over the only **trivial** baseline
  (persistence) **does not hold on the realistic, autocorrelated slice**, and the binding
  field+nudge baseline for the payoff probe was **never run**. This makes the case for "decide on
  real data, not synthetic" *stronger*, not weaker.

---

## 1. Context

### 1.1 The program

SylannEngine's runtime emotion core today is a fixed `seed=42` field: `ScarredState._evolve_base`
(defined `scar_algebra.py:276`, called inside `step()` at `scar_algebra.py:402`), a spectrally-
normalized 2-layer MLP (`base_t = tanh(W2·tanh(W1·[base_{t-1}; modulated_input]))`, each
`‖W‖₂≤0.7` so the two-layer product is `<0.49`; boundedness comes free from the final `tanh` at
`scar_algebra.py:304`). v3 proposes to replace it with **BroadCore-S**: a learned recurrent emotion
cell (~3.4K params, 8-dim emotion latent), eventually served as pure-numpy int8 in a 2 vCPU / 2 GB /
no-GPU multi-session box. BroadCore-S would absorb `_evolve_base`, the `_apply_assessment_to_engine`
nudge (`resonance_integration.py:588-647`), and the `observe()` readout, under the **I/O flip**:
par1's `f_*` emotion features become the core's *outputs*, never its inputs.

The **north star** is to retire the `seed=42` field from the **runtime** (live core, runtime
fallback, stability guarantee) under a gated two-release quarantine (TDD Phase K) — while
**demoting, not deleting, its source**. The field source is the only deterministic, infinite
generator of transition data over the *whole* state space (trauma spikes, prior base across
`[-1,1]^8`, dt extremes); real-traffic corpora only ever capture the on-distribution slice. So the
source is kept forever, frozen and version-pinned, as the offline `reference_teacher`. Deleting that
source is the one truly irreversible "white-train" event and is out of scope.[^scarmod]

[^scarmod]: "Field out of the live path" is **not literally "zero field-derived code in the live
    path."** Per the TDD ledger fork U1, a scoped `ScarModulator` (scars + `modulate()` bookkeeping,
    **no** `seed=42` MLP) is retained as the deterministic producer of the scar-modulation input
    `x_t[9:17]` until Ring 2 internalizes it. The north star (kill the `seed=42` MLP) is still met;
    a sliver of scar bookkeeping survives by design.

The full build is **P0 = a multi-phase program** (corpus → cell → distillation parity → online
residual → serving/int8 → brain re-distillation → cost-gating → kill-quarantine → plugin
verification). It is expensive and, once under way, hard to unwind. That cost is exactly why a gate
exists before it.

### 1.2 The theater risk (why a gate, and why this spike)

The field already injects the assessor's affect into `base[0,1,2]` on every assessed tick
(`resonance_integration.py:625-633`). So a naive "student vs field-with-`a_t`-withheld" comparison
cripples a baseline nobody ships and manufactures a fake win. The deeper failure mode is
**circularity / theater**: if you distill the field's own post-nudge outputs (`f_*`) from
field-generated data, the increment over the field is **zero by construction** — an expensive clone
that proves nothing (digest C11). The TDD therefore made a **pre-P0 spike a hard gate** (digest §3):
it must isolate the only things a *learned* core can add — **cross-tick memory** and
**richer-than-4-scalar message content** — and STOP the program if it cannot show them.

### 1.3 What the spike ran

A reusable headless generator (`training/student_core/simulate_corpus.py`) drove the **real field**
over a synthetic `mood → assessor → message → field` pipeline: **2000 synthetic sessions, ~62k
ticks**, with temporally-autocorrelated (AR(1) on the latent mood, `ρ=0.85` for non-control
sessions; plus near-iid control sessions) latent affect. The message tokens were **constructed to
encode the latent mood** (`simulate_corpus.py` `mood_message`), and the synthetic assessor derived
`a_*` directly from that mood — so any "the core reads the message" result is, on this data,
recovering a signal that was *planted* in the message by construction. Two probes ran on a
**session-split** held-out set:

- **Probe 1 — NTAP** (`spike_ntap.py`): predict next-tick assessor `a_{t+1}` from observables up to
  `t`. Leakage-free (`a_{t+1}` was injected into nothing at `t`) and exactly the quantity Phase M
  needs. The anti-theater cross-tick-memory test.
- **Probe 2 — Predict-assessor** (`spike_predict_assessor.py`): predict the **current** `a_t` from
  the message HDC + prior state, with **no `a_t` input** — the Phase-M call-skipping payoff test.

### 1.4 Spike results (from `RESULTS.md`, with the autocorrelated slice shown — it is load-bearing)

**Probe 1 — NTAP** (lower MAE better):

| model | MAE (full) | MAE (autocorrelated) |
|---|---|---|
| persistence (`a_t`) | 0.235 | 0.197 |
| field+nudge ridge | 0.205 | 0.180 |
| **field+nudge gbm (best baseline)** | **0.203** | **0.180** |
| student BroadCore-S Vfull | 0.215 | 0.196 |

**FAIL.** The student does not beat the steelmanned field+nudge GBM on either slice. Red-teamed: the
student is **not broken** — given `z_post` features + more epochs it ties at ~0.207. The failure is
**structural**: the synthetic mood is AR(1) (`a_{t+1}` ≈ a discounted `a_t` + noise), the field's
own reactive state already captures it, so there is **no cross-tick increment for any model to
extract**; NTAP is additionally confounded by the unknown next message. This **empirically confirms
the theater critique on field-generated data**.

**Probe 2 — Predict-assessor** (lower MAE better):

| model | MAE (full) | MAE (autocorrelated) |
|---|---|---|
| field pre-nudge base, as a guess of `a_t` | 0.533 | 0.534 |
| persistence (`a_{t-1}`) | 0.235 | **0.197** |
| student V0 (no message) | 0.250 | 0.245 |
| student V4 (8-float HDC) | 0.244 | 0.236 |
| **student Vfull (64-float HDC)** | **0.209** | **0.200** |

**MECHANISM PASS — but only partially, and only on synthetic data.** Two honest reads:

1. The student reading the WIDE HDC (0.209) far beats the field's **fixed pre-nudge transform**
   (0.533). *Correction to an earlier overstatement:* this does **not** prove "the field is
   semantic-blind." The field's pre-nudge base **has** already seen this tick's message (via
   `HDC → ssm_input → _evolve_base`, `resonance_integration.py:413-423`); what it lacks is a
   *learned* mapping from message to the assessor's affect read. The correct claim is narrower:
   **the field's fixed, untrained transform does not recover the assessor's read, and a trained core
   does.** That is real and useful — it means the core's target is learnable and not already produced
   by the field.
2. **The win over the trivial `persistence` baseline does not survive the realistic slice.** On the
   autocorrelated sessions (the closest synthetic proxy for real chat), persistence is **0.197** and
   the student Vfull is **0.200** — the student is **slightly worse**. The full-set "win" (0.209 vs
   0.235) is driven **entirely by the near-iid control sessions**, where persistence collapses
   (0.235) because `a_{t-1}` is uncorrelated with `a_t` there. On data that looks like real
   conversation, "just reuse the last assessor read" is as good as the learned core.

**D-12 confirmed *mechanically* (synthetic):** HDC width helps monotonically (V0 0.250 → V4 0.244 →
Vfull 0.209). On synthetic data a 4–8-float bottleneck loses the *injected* latent; whether it loses
*real* message affect is the open question only CORE2 can answer.

### 1.5 Honest synthesis (the load-bearing caveat)

- The genuinely positive result: a trained core reading the message decodes the assessor's read far
  better than the field's fixed transform. The capability is real and the target is learnable.
- The sobering results: (a) it does **not** beat trivial persistence on autocorrelated data — and
  for Phase M, persistence (reuse `a_{t-1}` to skip a call) is itself a legitimate cheap policy, so
  the core must beat it to justify its existence; (b) Probe 2 **never ran the steelmanned field+nudge
  regressor** that the PASS bar requires (the probe codes only field-pre-nudge and persistence) — the
  binding baseline is **unmeasured**; (c) everything is on data where the message was built to carry
  the latent, so real-message affect predictability is **unproven**; (d) the cross-tick memory
  increment (Probe 1) is not demonstrated and may be small even on real data.
- **This cannot be de-risked offline.** The field is **both the data generator and the baseline**, so
  it structurally cannot produce data showing its own replacement wins. Only real assessor-labeled
  traffic can size the Probe-2 value (against a *proper* baseline set, on a realistic slice) and the
  Probe-1 memory increment.

---

## 2. Decision Drivers

- **D1 — Anti-theater integrity.** A GO must rest on a non-circular demonstration of value. Offline
  field-distillation is circular by construction (digest C11; Probe 1 confirmed it empirically).
- **D2 — Irreversibility asymmetry.** Entering P0 is an expensive, hard-to-unwind program.
  Collecting real labeled traffic is *cheaper* and additive — **but it is not "reversible":** once
  logged, real-user affect traces are a standing liability (§5.2), so collection is gated, not free.
- **D3 — Evidence sufficiency for Phase M.** The call-skipping ROI (the cost win that pays for the
  program) depends on *real* `message → assessor` predictability **beating persistence**, which the
  spike cannot measure and on synthetic data does not show.
- **D4 — Don't discard a demonstrated capability.** Probe 2 shows a trained core decodes the message
  to the assessor's read far better than the field's fixed transform — a real, measured mechanism.
- **D5 — Statistical rigor of the gate.** The eventual GO must be powered, accounting for
  within-session autocorrelation, and must use the binding baseline the spike skipped.
- **D6 — Reuse / sunk-cost preservation.** The corpus generator, both probes, and the D-12 finding
  are reusable offline assets regardless of the verdict.

---

## 3. Considered Options

### Option A — Enter P0 now on offline field-distillation. **Rejected.**

The spike **empirically** shows offline field-distillation cannot prove value: Probe 1 FAILED
because field-generated transition data is Markovian and the field's own reactive state already
captures all cross-tick structure — a distilled student can at best *tie* the field. The field is
simultaneously generator and baseline; it cannot emit data showing its own replacement wins. P0 here
would spend an expensive program to produce, at best, a field-clone that gains nothing — the exact
theater the gate exists to prevent (D1, D2). The Phase-M payoff P0's economics depend on would
remain unmeasured (D3).

### Option B — Shelve v3. **Rejected.**

Probe 2 shows the mechanism is real: a trained core decodes the message to the assessor's read far
better than the field's fixed transform (0.209 vs 0.533). Shelving discards a demonstrated, learnable
capability (D4). The Probe-1 FAIL is an artifact of *synthetic Markovian* data, not of the
architecture. Killing the program on it would be the mirror error of Option A.

### Option C — Gate on real-data collection, then re-run the probes. **Selected.**

Do not enter P0 now. Stand up / continue the **par1 / CORE2** real-assessor-labeled stream, then
re-run the probes on the *real* corpus against a **complete** baseline set (persistence **and** the
steelmanned field+nudge regressor that Probe 2 currently lacks), on the **autocorrelated/realistic
slice**, at the PASS bar. GO into P0 iff the real-data gate passes; otherwise STOP.

**Why C resolves the impasse:** the field cannot generate data proving its own replacement, so the
gate must move onto data the field did **not** generate. It honors both true findings — the real
mechanism (don't shelve) and the real theater warning plus the autocorrelated reversal (don't build
on field data, and don't trust the synthetic win). It directly measures the Phase-M ROI against the
binding baseline. Collection is gated behind the privacy prerequisites (§5.2), not free, but it is
the only option that can actually answer the question.

---

## 4. Decision

**Adopt Option C.** Do **not** enter P0 on the spike evidence alone.

- **Collection plumbing is authorized now and is NOT P0.** Landing the CORE2 telemetry sink, the
  salt fix, the JSONL→parquet adapter, and the probe harness in the SDK (all default-off, additive)
  is **Phase-0-collection**, explicitly *not* the gated build. **P0 = the cell / distillation /
  online-residual / serving-int8 / brain re-distillation / cost-gating / kill program, and it stays
  gated** behind the real-data result. The boundary is stated identically here and in the harness
  spec §0.
- **The gate:** collect real assessor-labeled traffic; re-run the probes on it against persistence
  **and** a steelmanned field+nudge baseline (which the harness must *add* to Probe 2 — it does not
  exist in the probe today), evaluated on held-out **autocorrelated** sessions with all leakage
  guards green, at **≥15% relative AND ≥0.02 absolute** paired-MAE improvement.
- **Gating probe vs diagnostic probe (reconciled — single source of truth):** **Probe 2
  (predict-assessor) is the GO gate.** **Probe 1 (NTAP) is a report-only diagnostic** that informs
  the Ring-1-vs-Phase-M-only scoping decision but does **not** by itself block GO (the call-skipping
  value can be real even if the cross-tick memory increment is small). The harness spec uses this
  exact language.
- **Independent prerequisites** (not part of this gate): close blocker #1 (TDD §5.1 architectural
  contraction proof) and blocker #2 (TDD §6 fix-#2 tick granularity) before any P0 start.

---

## 5. Consequences

### 5.1 Positive

- The program is de-risked at its cheapest point; no expensive build is committed on circular,
  partially-reversed evidence.
- Both honest findings are preserved: the demonstrated mechanism keeps it alive; the theater +
  autocorrelated reversal keep it from building a field-clone or trusting a fragile synthetic win.
- The Phase-M ROI question is moved onto the only data that can answer it, against the binding
  baseline the spike skipped.
- The eventual GO is powered (§6) and uses a complete baseline set.

### 5.2 Negative

- **The decision now blocks on a deploy/telemetry dependency**, not an offline run: P0 cannot start
  until enough real labeled traffic is collected. Collection rate, not engineering effort, is the
  critical path.
- **Real-data risk is live.** The synthetic data already shows the student tying/losing to
  persistence on the realistic slice; it is entirely possible the real-data gate FAILS. That is the
  gate working, but the program may still be killed after collection effort is spent.
- **Collection is not reversible w.r.t. PII.** The `(session_hash, base_pre_nudge, a_*)` log is the
  richest re-identification surface in the system. It is **blocked** until the salt/deletion bug
  (digest D14 / R1) is fixed: `training_data_salt=""` today produces a *stable, cross-deploy-linkable*
  hash (`telemetry/sink.py:74`, `config.py:217`), the opposite of the docstring's claim, and there is
  no `delete_session()` path. The salt fix **and** a deletion/tombstone path are **hard preconditions
  of starting collection**, not follow-ups. Note also: tombstones cover raw logs only — **affect data
  already distilled into a shipped core cannot be un-baked**; a retention/eligibility window must gate
  rows *before* distillation, and post-distill deletion is best-effort.
- **The serving path is unproven.** "pure-numpy int8, no torch" is a *target*, not an established
  property: the spike ran f32 + torch, and the torch→numpy int8 boundary (digest U1/V4) can silently
  flip the contraction cert after the gate passes. int8 reproducibility is a P0 precondition, not a
  settled fact.

### 5.3 Neutral — what stays true offline regardless of the real-data verdict

- The corpus generator and both probes are reusable, durable assets; the real-data re-run is the
  *same harness* pointed at a real corpus (plus the one added baseline), not a rewrite.
- **D-12 is confirmed necessary on synthetic data** (V0 0.250 → V4 0.244 → Vfull 0.209): any future
  core must widen the message HDC well beyond a 4–8-float bottleneck. The *size* of the effect on
  real text is unknown.
- **The core's target is learnable and not already produced by the field** (the field's fixed
  pre-nudge transform scores 0.533 vs the trained core's 0.209). This is the precise, defensible
  version of the "semantic-blind" claim.
- An infrastructure bug was found and fixed: running the spike scripts directly put the script's own
  `student_core/` directory at `sys.path[0]`, shadowing the editable-installed package
  (`simulate_corpus.py:33-34`, `spike_predict_assessor.py:22-23` rewrite `sys.path[0]` to
  `os.getcwd()` when its basename is `student_core`). Carries forward to any future runner.

---

## 6. Power Analysis — how much real traffic the gate needs

**What this section is and is NOT.** It estimates the number of real sessions needed to **detect a
paired-MAE improvement of `δ = 0.02`** (the absolute floor of the PASS bar) at **α = 0.05 two-sided,
power 0.8**, *if such an effect exists on real data*. It does **not** predict that the effect exists:
the spike's own autocorrelated slice shows the student-vs-persistence effect is ≈ **−0.003** (no
win), so a plausible real-data outcome is **no detectable effect**, in which case the gate STOPs.
This is collection-sizing under the optimistic-but-floor hypothesis, not a forecast of success.

This is a paired comparison on the binding baseline (persistence on the autocorrelated slice): per
tick, `d_t = |b̂_t − a_t| − |â_t − a_t|`, testing `E[d_t] = δ`.

### 6.1 Effect size

We power for the PASS-bar floor `δ = 0.02`. We deliberately do **not** use the full-set spike gap
(0.235 − 0.209 = 0.026): it exists only by mixing in the easy near-iid controls and **reverses to
−0.003 on the autocorrelated slice** the PASS bar requires. There is therefore **no positive
synthetic effect to bank as buffer**; `δ = 0.02` is a hypothesized floor to be confirmed or refuted
on real data.

### 6.2 Per-tick paired-difference std `σ_d` (assumption, with sensitivity — NOT "conservative")

We have no real paired-error series, so `σ_d` is a **prior to be re-estimated on a pilot**. Per-tick
absolute affect errors live on the order of the MAEs (~0.20), so per-error std ≈ 0.20; the paired
difference of two positively-correlated error series has `σ_d² = σ_base² + σ_student² − 2ρ_be σ_base
σ_student`, but since the cross-error correlation `ρ_be` is itself unknown, we do **not** claim
variance reduction (at `ρ_be=0.5` the reduction is exactly zero). We therefore treat `σ_d` as a free
parameter and report N across a range. `N ∝ σ_d²`:

| `σ_d` | per-tick `δ/σ_d` | eff. independent tick-pairs `N_eff` |
|---|---|---|
| 0.15 | 0.133 | ≈ 442 |
| **0.20** | **0.10** | **≈ 785** |
| 0.25 | 0.08 | ≈ 1228 |

via `N_eff ≥ (z_{α/2}+z_β)² σ_d² / δ² = (1.96+0.8416)² σ_d² / (0.02)²`.

### 6.3 Cluster inflation (the real cost)

Ticks cluster by session; independence is at the **session** level. Design effect for mean cluster
size `m`: `DEFF = 1 + (m−1)·ρ_icc`. Assumptions, **each "to validate on a pilot of ≥30 sessions"**
(an ICC estimated from fewer than ~30 clusters has a CI too wide to size a budget):

- `m` = labeled (assessor-called) ticks per session. The naive "30" is **wrong** under the Phase-M
  exploration floor `ρ_floor` (digest C7/U3), which gates most calls away — labeled ticks/session may
  be far lower. `m` must be **measured at the real assessor-call rate**, and low `m` *raises* the
  session count.
- `ρ_icc` of the paired difference `d_t`. Affect is strongly autocorrelated; `d_t` is a difference of
  two models' errors that share the same hard ticks, so a non-trivial residual `ρ_icc` is plausible.

Headline (at `σ_d=0.20`, `δ=0.02` ⇒ `N_eff ≈ 785`), as a **range gated on the pilot**, never a
single number:

| `ρ_icc` | `m=15` → DEFF / sessions | `m=30` → DEFF / sessions |
|---|---|---|
| 0.05 | 1.70 / ≈ **89** | 2.45 / ≈ **64** |
| 0.10 | 2.40 / ≈ **126** | 3.90 / ≈ **102** |
| 0.20 | 3.80 / ≈ **199** | 6.80 / ≈ **178** |
| 0.30 | 5.20 / ≈ **272** | 9.70 / ≈ **254** |

> **Order of magnitude: ~65–270 real assessor-labeled sessions**, depending on `ρ_icc` and the real
> labeled-ticks-per-session `m`. **Do not treat any single cell as a budget.**

### 6.4 Mandatory pilot, and a pre-registered escalation rule

- **Pilot (≥30 sessions):** measure the empirical `σ_d`, `m` (at the real assessor-call rate), and
  the intra-session `ρ_icc` of `d_t` directly; re-derive N via §6.2–§6.3 using the **upper CI** of
  `ρ_icc`, not the point estimate.
- **Pre-registered escalation (decided now, not after sunk cost):** if the pilot-derived N exceeds
  **300 sessions**, OR the projected collection ETA at the real rate exceeds **8 weeks**, OR the
  pilot's autocorrelated student-vs-persistence effect is `≤ 0` (as the synthetic slice already
  shows), **escalate to the owner for shelve-vs-redesign** rather than collecting indefinitely.
  Collection is not an open-ended critical path.

---

## 7. Operational notes (RACI + dependencies for the GO path)

- **RACI (to be filled before collection starts):** *Responsible* — who runs/monitors the live
  collection and the pilot re-derivation; *Accountable* — Ayleovelle (this ADR + the successor
  GO/NO-GO ADR); *Consulted* — privacy/governance for the salt+deletion+disclosure gate; *Informed*
  — whoever is paged on a sink/privacy incident. The brain-loop SLO owner and the Phase-K rollback
  authority are named at P0 entry, not now.
- **Assessor as a first-class dependency.** The entire gate predicts the assessor LLM; if its
  version changes, all `a_*` labels re-base. **Freeze the assessor version for the duration of a
  collection campaign**, record `assessor_version` on every CORE2 row (digest V3), and **STOP /
  invalidate** in-flight corpora if the assessor version changes before minimum-N is reached.
- **Input modality is text-only** for this gate. Non-text / empty-text turns (stickers, images,
  voice) have a degenerate HDC and an undefined assessor read; they are **excluded from the corpus**,
  not silently zero-fed (else they poison the variance-floor guard and the labels).

---

## 8. Follow-ups (tracked for the GO path, out of scope for this ADR)

- Land the CORE2 stream (TDD §9 / harness spec §1) behind the default-off sink, **after** the salt +
  deletion fix (digest D14 / R1) and with the multi-user disclosure gate.
- Run the pilot (§6.4); re-derive N from the pilot's upper-CI ICC; then collect to target or escalate.
- **Add the missing steelmanned field+nudge baseline to `spike_predict_assessor.py`** (it ships only
  field-pre-nudge + persistence today); add a coded PASS gate evaluated on the autocorrelated slice.
- Re-run both probes on the real corpus; apply the PASS bar; record GO/NO-GO in a successor ADR.
- Close blocker #1 (§5.1 contraction proof) and blocker #2 (§6 fix-#2 granularity) before any P0.
