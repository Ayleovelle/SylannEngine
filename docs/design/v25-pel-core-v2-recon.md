Diagnosis confirmed. Here are the numbers:

---

**[1] Pi_obs (Precision/Attention) — FULLY SATURATED**

All 8 dims hit PI_MAX=5.0 on tick 1 and stay there for all 150 ticks:

```
Ticks pinned at PI_MAX (out of 150): [150, 149, 150, 150, 149, 149, 150, 148]
```

Final Pi_obs: `[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]`

Cross-dim std mean = **0.008915** (practically zero — a flat constant). Over-time variance per dim is essentially zero for 5 of 8 dims; only dims 1/5/7 show any variance at all, and that variance is from rare transient ticks falling to ~4.5 before snapping back. Pi_obs[dim0] for all 20 first ticks: `[5.0, 5.0, …, 5.0]` — it pins immediately from tick 1.

**Why**: e0 magnitudes on the real path are tiny (mean |e0| = 0.039–0.097 per dim). The raw 1/(e0^2+eps) evaluates to **83–685 across dims** — all between 16x and 137x above PI_MAX=5. Fraction of (dim, tick) pairs where the unclipped value exceeds PI_MAX: **100/100 = 100.0%**. The clip does all the work, every tick, every dim. The EMA is irrelevant because the new value always equals PI_MAX before blending.

---

**[2] W_gen Frobenius Drift**

```
||W_gen||_F init  = 1.428846
||W_gen||_F final = 1.405557
Absolute drift    = 0.023289  (1.63% relative)
Max per-entry |ΔW| = 0.019748
```

Drift is weak. The Hebbian update is `eta_w * surprise * Pi_obs[i] * e0f[i] * mu[j]`, and since Pi_obs[i] is a fixed constant 5.0, the precision gating does nothing — it just contributes a fixed 5x scale that doesn't differentiate attention across dims. The net per-update push is small (eta_w ~0.002, e0f ~0.05-0.10), and spectral clamping to 0.9 then further shrinks entries. Real plasticity magnitude: ~0.02 total Frobenius change over 150 ticks.

---

**[3] pi (Allostatic Personality Setpoint) Drift**

```
pi_init:  [0.09372, 0.29131, -0.03998, 0.21652, 0.28029, 0.10956, 0.07088, 0.30044]
pi_final: [0.08443, 0.26128, -0.03604, 0.19784, 0.25213, 0.09504, 0.06529, 0.27023]
||Δpi||   = 0.0574512
max |Δpi| = 0.030207  (dims 1 and 7)
z_ema final: [0.026, 0.080, -0.012, 0.093, 0.079, 0.008, 0.035, 0.082]
```

pi is being pulled toward z_ema (which reflects the sparse, noise-dominated emotion signal). z_ema values are consistently smaller in magnitude than pi_init, so ALL dimensions are drifting toward zero — **personality erosion confirmed**. No anchor pulls back to the trait prior pi_0. Over a long session this washes out the identity.

---

**[4] e0 Magnitude Range — The Root Cause of Saturation**

```
Per-tick mean |e0|: min=0.0388, max=0.0973, mean=0.0654
Per-dim mean |e0| (50-tick re-run):
  dim 0: 0.041  => 1/(e0^2+eps) = 370
  dim 1: 0.105  => 1/(e0^2+eps) =  83
  dim 2: 0.021  => 1/(e0^2+eps) = 685
  dim 3: 0.079  => 1/(e0^2+eps) = 139
  dim 4: 0.104  => 1/(e0^2+eps) =  84
  dim 5: 0.065  => 1/(e0^2+eps) = 191
  dim 6: 0.029  => 1/(e0^2+eps) = 550
  dim 7: 0.109  => 1/(e0^2+eps) =  77
```

The smallest per-dim inverse variance seen (dim 7, least bad) is still **77x PI_MAX**. There is no regime — even the "worst" dim with the largest errors — where the raw precision signal falls below PI_MAX. The floor is 1/(0.11^2 + 0.001) ≈ 77; to clear PI_MAX=5 you'd need |e0| > sqrt(1/5 - 0.001) ≈ 0.447, but real spine errors are 4–20x smaller than that threshold. The problem is structural, not a tuning issue.

---

**Summary of confirmed pathologies:**

1. **Precision: completely dead.** Pi_obs = constant [5.0]*8 on every real-path tick. The "attention" gating mechanism contributes no differentiation whatsoever. 100% of update pairs saturate. Requires architectural fix (divisive normalization), not EPS/rate tuning.

2. **Plasticity: weak but non-zero.** W_gen Frob drift = 0.023 over 150 ticks. The precision gating degrades to a fixed 5x constant multiplier. Only surprise (scalar) and e0 (small) differentiate Hebbian updates across ticks; no dim-selective attention. Max per-entry change 0.0198.

3. **pi: drifting toward zero with no anchor.** ||Δpi|| = 0.057 in 150 ticks, consistently eroding toward the small-magnitude z_ema signal. No pi_0 restoring force. At this rate over thousands of ticks the personality setpoint would be washed out.

4. **No metaplasticity:** eta_w is a fixed scalar per session. The learning rate never self-modifies.

Script at: `C:\Users\pidan\AppData\Local\Temp\claude\G--SylannEngine\edcba155-0c80-453f-a103-fc3259044627\scratchpad\recon_pel_saturation.py`