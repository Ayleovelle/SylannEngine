# Pre-P0 spike results — BroadCore-S (learned emotion core)

Date: 2026-06-25. Branch: `feat/v3-core`. Data: `spike_corpus.parquet` (2000 synthetic sessions,
~62k ticks, the REAL field driven headless over a synthetic message→assessor→field pipeline).

**Bottom line:** the spike neither cleanly kills nor greenlights the program. It proves the
*mechanism* works but shows the go/no-go **cannot be settled offline** — it requires REAL
assessor-labeled data. Do **not** enter P0 (the 8-phase build) on this evidence alone.

## Probe 1 — NTAP (predict next-tick a_{t+1}); the "is it theater" memory test
`spike_ntap.py`. Lower MAE better.

| model | MAE | on autocorrelated |
|---|---|---|
| persistence (a_t) | 0.235 | 0.197 |
| field+nudge ridge | 0.205 | 0.180 |
| field+nudge gbm | **0.203** | **0.180** |
| student V0 / V4 / Vfull | 0.221 / 0.220 / 0.215 | 0.204 / 0.204 / 0.196 |

**FAIL** (student does not beat field+nudge). Red-teamed: the student is **not broken** — given the
same info (z_post) + more epochs it converges to ~0.207, i.e. it *ties* the baseline. The fail is
structural: the synthetic field data is **Markovian** (a_{t+1} ≈ 0.85·a_t + noise), the field's own
reactive state already captures it, so there is **no cross-tick increment for any model to extract**.
NTAP is also confounded — a_{t+1} depends on the *next message*, unknown at t. This **empirically
confirms the theater critique on field-generated data**: the field cannot generate data that proves
its own replacement is better.

## Probe 2 — Predict-assessor (a_t from the message, NO a_t input); the Phase-M payoff test
`spike_predict_assessor.py`. Can a cheap core predict the assessor's read from the message, to skip
the LLM call? Lower MAE better.

| model | MAE | on autocorrelated |
|---|---|---|
| field-blind (pre-nudge base) | 0.533 | 0.534 |
| persistence (a_{t-1}) | 0.235 | 0.197 |
| student V0 (no message) | 0.250 | 0.245 |
| student V4 (8-float HDC) | 0.244 | 0.236 |
| student Vfull (64-float HDC) | **0.209** | **0.200** |

**Mechanism PASS (synthetic).** A learned core reading the message HDC predicts the assessor's read
(0.209) far better than the semantic-blind field (0.533) and beats persistence. The field is
**confirmed semantic-blind** — it genuinely needs the assessor; the core's job (predict it cheaply)
is well-defined and non-trivial.

**D-12 confirmed (mechanically):** message bandwidth matters a lot — V0 0.250 → V4 0.244 → Vfull
0.209. A 4–8-float HDC bottleneck demonstrably **loses message signal**; widen it (D-12 / D-7).

## Honest synthesis & recommendation
- The learned-core **mechanism is sound** (Probe 2) — a cheap core can extract message→affect the
  field cannot. That is the real Phase-M value.
- BUT both wins are on **synthetic data where the message was constructed to encode the latent**.
  Whether a cheap HDC of a **real** message carries enough of the assessor's affect is **unproven**
  and only answerable on real labeled traffic. The cross-tick memory increment (Probe 1) is not
  demonstrated and may be small even on real data.
- **You cannot de-risk this offline.** The field is both the generator and the baseline; it can't
  produce data showing its own replacement wins. **The real gate = collect real assessor-labeled
  traffic (par1 / CORE2) and re-run BOTH probes on it.** Only real data sizes the value (Probe 2)
  and the memory increment (Probe 1).
- Proven-offline carry-forwards: the corpus generator + probes are reusable; **D-12 (widen message
  bandwidth beyond 4–8 numeric dims) is necessary**; the field is semantic-blind (the core's target
  is well-posed). A real-data NTAP+predict-assessor harness is the next concrete artifact — but it
  is gated on collection, which is the deploy/telemetry track, not an offline build.

## Reproduce
```
python training/student_core/simulate_corpus.py --sessions 2000 --seed 42 \
    --out training/student_core/spike_corpus.parquet
python training/student_core/spike_ntap.py            # Probe 1 (NTAP)
python training/student_core/spike_predict_assessor.py # Probe 2 (Phase-M payoff)
```
