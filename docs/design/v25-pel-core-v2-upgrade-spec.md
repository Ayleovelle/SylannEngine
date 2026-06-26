All load-bearing claims verify against the real `W_gen` init and the recon error scales. Key confirmations: contraction holds (KAPPA·λ_max(H)@pi=5 = 0.635 ≪ 2; analytic ceiling 0.905); legacy precision pins to flat [5.0]·8 (std 0.0) while budget-divisive lands [1.33,…,2.39] (std 0.73, peak 2.39 ≪ PI_MAX); post-warm-up the dead baseline's over-time variance is genuinely 0.0 (the red team's 0.03 was the warm-up ramp); the degenerate single-dim case peaks at 7.1 (>PI_MAX → clip is load-bearing) with exactly one dim saturating (theorem holds); eta_w gain = 5.0 exactly restores the designed mean.

Here is the authoritative spec.

---

# PEL 更脑 v2 — Authoritative Upgrade Spec

> Folds into `docs/design/v25-pel-core-techspec.md` as new §3.5 (mechanisms), §3.6 (re-derived proof), and §5 test rows #13–#19. All line numbers verified against `sylanne_core/compute/pel_core.py` (376 LOC, read this session). Numeric claims marked **[verified]** were reproduced against the real `W_gen` init + recon error scales (`scratchpad/verify_pel_v2.py`).
>
> Master gate unchanged: everything below is live only when `pel_core_enabled=True` (config.py:223, default `False`). With the flag off the legacy MLP path is byte-identical. When on, the v2 mechanisms are the new on-path default, each independently ablatable.

## §0 Red-team must-fix disposition (all 11)

| # | Must-fix | Disposition |
|---|---|---|
| 1 | Resolve form conflict → budget+clip, not the prompt's N-factor form | **ADOPT.** Budget form `PI_MIN + 7.2·rᵢ/Σr` (mean 1.0 = `ones`-init). **[verified]** at-most-one-saturation theorem (5k≤8⇒k≤1); real-path peak 2.39. Prompt's literal `N·rᵢ/Σr` re-saturates the equal-error case to 5.0 — rejected. |
| 2 | Keep elementwise clip | **ADOPT.** **[verified]** degenerate single-dim target = 7.1 > PI_MAX; clip keeps runtime in `[PI_MIN,PI_MAX]` = exactly the range contraction-fuzz test #7 already samples ⇒ no test change. |
| 3 | Apply divisive to `pi_top` too | **ADOPT.** `e1f=mu−pi≈0` at init saturates `pi_top` identically; divisive applied to both. |
| 4 | Fix acceptance witness (cross-dim primary; drop warm-up for temporal) | **ADOPT + refine.** **[verified]** post-warm-up the dead baseline temporal var = 0.0 (not 0.03 — that was warm-up). So after discarding warm-up BOTH legs discriminate (legacy 0.0 vs divisive 0.0023); I keep cross-dim std as primary (0.0 vs 0.67, warm-up-insensitive) and temporal as secondary-on-steady-window. |
| 5 | Acceptance on real `ResonanceSpine` over CORPUS, not `_varying_input` | **ADOPT.** New headline test T-DIV lives in `test_pel_spine.py` driving the real spine; existing synthetic ablations stay (they only test toggle-has-effect). |
| 6 | W_gen 5× magnitude drop (raise eta_w OR path-length) | **ADOPT both.** Bake `ETA_W_DIVISIVE_GAIN = PI_MAX/(PI_BUDGET/N) = 5.0` **[verified]** into eta_w at construction, coupled to `PRECISION_DIVISIVE` (restores the *designed* mean, proof-free: eta only scales pre-clamp ΔW). AND reframe plasticity acceptance to PATH-LENGTH + cross-dim gate-spread, not net drift. |
| 7 | Surprise-gate OFF by default | **ADOPT.** Default drift = `RHO_PI` constant. `SURPRISE_GATE`/`RHO_S` kept as separate ablatable knob, default `False`. No rigged 0.5-vs-0.05 test. |
| 8 | Single schema bump v1→v2 adding {theta, pi0, s_bar} | **ADOPT.** `PEL_SCHEMA_VERSION 1→2`, one bump, back-compat fallbacks. |
| 9 | Product-spread CI guard `var(pi_obsᵢ·mᵢ) > tol` | **ADOPT.** Expose `last_m` diagnostic; test T-PROD on real path. |
| 10 | Relabel "BCM-inspired metaplastic gain", drop LTD/sign-flip | **ADOPT.** At shipped `LAMBDA_BCM=1`, `mᵢ∈[0,2]` non-negative, no sign reversal. Docstrings say "BCM-inspired sliding-threshold metaplastic gain." |
| 11 | Three independent flags, each with a real-path effect test | **ADOPT.** `PRECISION_DIVISIVE`, `LAMBDA_BCM`, `RHO_ANCHOR` are independent module knobs; one effect-test each. |

Nothing disproved/rejected. One refinement (#4): the temporal leg is *not* vacuous once warm-up is dropped — I keep it as a guarded secondary rather than discarding it.

---

## §1 Final mechanism set — exact equations + line replacements

Three mechanisms, one new helper, three new constants groups. They compose under strict timescale/role separation: **descent (instant) < Hebbian (η≈0.01) < BCM θ (ρ_θ=0.01, ~100 ticks) < allostatic π (ρ_π=1e-3 + anchor, ~200 ticks).**

### New constants — insert after pel_core.py:57

```python
# --- 更脑 v2: divisive-normalization precision (M1; Heeger 1992; Carandini & Heeger 2012)
PRECISION_DIVISIVE: bool = True            # ablation knob; False => legacy inverse-variance (byte-identical)
PI_BUDGET: float = float(N)                # conserved total precision; mean target 1.0 == ones-init
_PI_GAIN: float = PI_BUDGET - N * PI_MIN   # 7.2; affine budget share multiplier
ETA_W_DIVISIVE_GAIN: float = PI_MAX / (PI_BUDGET / N)  # 5.0; restores mean Hebbian magnitude

# --- 更脑 v2: BCM-inspired sliding-threshold metaplastic gain (M2; Bienenstock+1982; Abraham 2008)
LAMBDA_BCM: float = 1.0     # gain depth; 0.0 => exact legacy three-factor Hebbian
GAMMA_BCM: float = 0.5      # relative-surprise sensitivity inside tanh
RHO_THETA: float = 0.01     # theta EMA rate (~100-tick medium timescale)
THETA_INIT: float = 0.01    # initial sliding threshold (~ typical e0^2)
THETA_FLOOR: float = 1e-4   # ratio-denominator numerical floor

# --- 更脑 v2: anchored allostatic pi (M3; Sterling 2012; discrete OU/AR(1) mean reversion)
RHO_ANCHOR: float = 4e-3    # trait-prior restoring force; 0.0 => legacy leak-to-<z>
SURPRISE_GATE: bool = False # optional drift gate; default OFF (surprise is flat on real path)
RHO_S: float = 0.02         # slow surprise EMA rate (only used when SURPRISE_GATE)
```

### New helper — insert near pel_core.py:82 (after `_dot`)

```python
def _divisive_precision(errs: list[float]) -> list[float]:
    """Budget-conserving divisive-normalization target precision (Heeger 1992).

    Each dim gets PI_MIN plus a share of a FIXED budget proportional to its
    relative reliability r_i = 1/(e_i^2 + EPS). sum_i target == PI_BUDGET (mean
    1.0 == the ``ones`` init), so precision is a *redistribution* of attention,
    not an absolute magnitude that can all-pin. target_i in [PI_MIN, PI_MIN+_PI_GAIN].
    """
    r = [1.0 / (errs[i] ** 2 + EPS) for i in range(N)]
    s = sum(r) + 1e-12
    return [PI_MIN + _PI_GAIN * (r[i] / s) for i in range(N)]
```

### M1 — Divisive precision: REPLACES pel_core.py:289-300

Legacy at the flag-off branch is algebraically identical to the original (`RHO_P·tgt == RHO_P/(e²+EPS)`), so `PRECISION_DIVISIVE=False` reproduces the committed build byte-for-byte.

```python
        # 更脑 v2 (M1): divisive-normalization precision — competitive, budget-conserving.
        if PRECISION_DIVISIVE:
            tgt_obs = _divisive_precision(e0f)
            tgt_top = _divisive_precision(e1f)
        else:                                   # legacy absolute inverse-variance
            tgt_obs = [1.0 / (e0f[i] ** 2 + EPS) for i in range(N)]
            tgt_top = [1.0 / (e1f[i] ** 2 + EPS) for i in range(N)]
        for i in range(N):
            st.pi_obs[i] = _clip((1.0 - RHO_P) * st.pi_obs[i] + RHO_P * tgt_obs[i], PI_MIN, PI_MAX)
            st.pi_top[i] = _clip((1.0 - RHO_P) * st.pi_top[i] + RHO_P * tgt_top[i], PI_MIN, PI_MAX)
```

The RHO_P EMA and the `[PI_MIN, PI_MAX]` clip are unchanged — only the per-dim *target* changes (relative share vs raw inverse-variance).

### M2 — BCM-inspired metaplastic gain: REPLACES the Hebbian block pel_core.py:281-287

```python
        # 更脑 v2 (M2): BCM-inspired metaplastic GAIN on the three-factor F-gradient Hebbian.
        # m_i potentiates dims whose squared error exceeds their own sliding threshold
        # theta_i and pauses those below; theta_i = EMA(e0^2) self-modifies plasticity on
        # a ~100-tick timescale. m_i in [1-LAMBDA_BCM, 1+LAMBDA_BCM] = [0, 2] at default.
        m = [1.0] * N
        for i in range(N):
            a_i = e0f[i] * e0f[i]                               # PC error-unit activity^2
            g_i = math.tanh(GAMMA_BCM * (a_i - st.theta[i]) / (st.theta[i] + THETA_FLOOR))
            m_i = 1.0 + LAMBDA_BCM * g_i
            m[i] = m_i
            factor = st.eta_w * surprise * st.pi_obs[i] * e0f[i] * m_i
            row = st.w_gen[i]
            for j in range(N):
                row[j] += factor * mu[j]
            st.theta[i] = (1.0 - RHO_THETA) * st.theta[i] + RHO_THETA * a_i   # threshold lags activity
        st.w_gen = spectral_clamp(st.w_gen, W_SPECTRAL_MAX)    # UNCHANGED, unconditional
```

`theta_i` is read **before** its own EMA update (threshold reflects *past* error energy). The direction stays `+e0·mu` (free-energy descent) — M2 only gates rate, never the direction, so it does not re-introduce aimless Hebb. Add `self.last_m = m` at the step tail (after `self.last_e1 = e1f`, pel_core.py:318).

### M3 — Anchored allostatic π: REPLACES pel_core.py:309-312

```python
        # 更脑 v2 (M3): anchored allostatic pi — mean-reverts toward <z> AND back to the
        # frozen trait prior pi0 (no identity erosion). Optional surprise gate default OFF.
        drift = RHO_PI
        if SURPRISE_GATE:
            st.s_bar = (1.0 - RHO_S) * st.s_bar + RHO_S * surprise
            drift = RHO_PI * st.s_bar
        for i in range(N):
            st.z_ema[i] = (1.0 - Z_EMA_RATE) * st.z_ema[i] + Z_EMA_RATE * z[i]
            st.pi[i] = _clip(
                st.pi[i] + drift * (st.z_ema[i] - st.pi[i]) - RHO_ANCHOR * (st.pi[i] - st.pi0[i]),
                -1.0, 1.0,
            )
```

The free-energy block (302-307) and descent/readout (123-171) are untouched (F now simply reads the live varying precision).

### eta_w gain — augment from_personality pel_core.py:238

```python
        eta_w_base = 0.002 * (0.5 + openness)
        eta_w = eta_w_base * (ETA_W_DIVISIVE_GAIN if PRECISION_DIVISIVE else 1.0)
```

---

## §2 Re-derived boundedness + contraction proof (closed-form, machine-checkable)

**Admissible set** `A = { (W, Π_obs, Π_top, π) : ‖W‖₂ ≤ 0.9,  Π_obs[i],Π_top[i] ∈ [0.1, 5] ∀i,  π ∈ [−1,1]⁸ }`. Three per-tick enforcers keep state in `A` unconditionally: `spectral_clamp` (‖W‖₂≤0.9), elementwise `_clip` on both precisions, and the convex anchored-π update (below).

**2.1 Forward invariance `μ,z ∈ [−1,1]⁸`** — unchanged. Both active states are leaky-tanh convex updates `(1−γ)u_prev + γ·tanh(·)`, γ∈(0,1]; M1/M2/M3 do not touch this structure (M1/M3 act on precision/π *after* μ,z; M2 acts on W *after*). Invariance holds verbatim (techspec §3.1).

**2.2 Latent Jacobian.** descent_step is unchanged, so
```
∂g/∂μ = −H,  H = Wᵀ diag(Π_obs) W + diag(Π_top)  (symmetric PSD)
J_μ   = (1−α)I + α·D·(1−δ)·(I − κH),   D = diag(tanh'(·)), ‖D‖₂ ≤ 1
‖J_μ‖₂ ≤ (1−α) + α(1−δ)‖I − κH‖₂.
```
Since `H ⪰ 0`, `‖I−κH‖₂ ≤ 1  ⇔  κ·λ_max(H) ≤ 2` (admissible-set condition). The **key invariant under the new precision scheme**:
```
λ_max(H) ≤ ‖W‖₂²·max_i Π_obs[i] + max_i Π_top[i].
```
λ_max(H) depends on precision **only through the per-dim max**, never the sum/budget. Divisive normalization redistributes mass *within* `[PI_MIN,PI_MAX]`; the retained clip enforces each entry ≤ PI_MAX. Therefore:
```
λ_max(H) ≤ 0.81·5 + 5 = 9.05,   κ·λ_max(H) ≤ 0.905 ≤ 2.
‖J_μ‖₂ ≤ (1−α) + α(1−δ)·1 = 1 − αδ = 0.985 < 1,  every tick, ∀(W,Π)∈A.
```
**[verified]** on the real init (‖W‖₂=0.52): κ·λ_max(H)@Π=5 = **0.635**. The EMA-of-clipped-values stays ≤ PI_MAX, descent reads post-clip Π, so effective gradient precision **never exceeds PI_MAX**. The normalization/budget is irrelevant to the bound.

**2.3 Read-out Jacobian** `J_z = (1−β)I`, `‖J_z‖₂ = 0.6` — unchanged (precision/π never enter readout_step).

**2.4 New lemma — anchored-π is forward-invariant on `[−1,1]⁸`.** Write `d = drift ≥ 0`, `a = RHO_ANCHOR ≥ 0`:
```
π_i' = π_i(1 − d − a) + d·z_ema_i + a·π0_i.
```
The three coefficients are ≥ 0 and sum to 1 iff `d + a ≤ 1`. With `d ≤ RHO_PI = 1e-3`, `a = 4e-3`: `d+a = 5e-3 ≤ 1`. Since `z_ema_i ∈ [−1,1]` (EMA of tanh-bounded z), `π0_i ∈ (−1,1)` (tanh of trait raw), `π_i ∈ [−1,1]` (induction), `π_i'` is a convex combination ⇒ `π ∈ [−1,1]⁸` forward-invariant **for any rates with d+a ≤ 1** — strictly stronger than the legacy rule (a=0). π's *value* never enters the `‖J_μ‖` bound (it enters only through `tanh'`, whose magnitude ≤ 1 regardless), so M3 cannot affect contraction. **No-washout:** the slow fixed point `π_eq = (d·z_ema + a·π0)/(d+a)` is a convex blend, so `|π_eq − π0| = (d/(d+a))·|z_ema − π0| < |z_ema − π0|` strictly (legacy a=0 gave π_eq=z_ema = full washout).

**2.5 M2 / eta_w proof-safety.** M2 rescales the pre-clamp ΔW by `m_i ∈ [0,2]`; the eta_w 5× scales it further. Both leave KAPPA, PI_MAX, Π, and the unconditional `spectral_clamp` untouched, so W entering every descent_step satisfies ‖W‖₂≤0.9 — admissible set unchanged. Numerical obligation (no inf/nan): `|e0f_i| ≤ 1 + ‖W_row‖₁ ≤ ~3.5` (bounded), and the true max `η = 0.002·(0.5+1.0)·5 = 0.015` (with the ETA_W_DIVISIVE_GAIN=5 multiply — NOT the stale 0.01), so per-entry `|ΔW| ≤ η·s·Π_max·|e0|·|m|·|μ| ≤ 0.015·1·5·3.5·2·1 = 0.525`, finite; the clamp restores the norm. ✔

**Net: the admissible set, the condition `κ·λ_max(H) ≤ 2`, and the guarantees `‖J_μ‖₂ ≤ 0.985`, `‖J_z‖₂ = 0.6`, `μ,z,π ∈ [−1,1]⁸` all hold verbatim, every tick, under M1+M2+M3.** Contraction-fuzz test #7 (samples Π∈[PI_MIN,PI_MAX]) already covers the divisive runtime range with the clip retained — **no test change required**.

---

## §3 Ablation knobs + CI tests

Three independent knobs (module constants, monkeypatchable, matching the existing `RHO_P` ablation pattern). Each gets one real-path effect test. New rows #13–#19 in techspec §5; all run merge-blocking.

| Knob | Null value (= legacy) | Default |
|---|---|---|
| `PRECISION_DIVISIVE` | `False` (absolute inverse-variance) | `True` |
| `LAMBDA_BCM` | `0.0` (m≡1, exact legacy Hebbian) | `1.0` |
| `RHO_ANCHOR` | `0.0` (leak-to-⟨z⟩, erosion) | `4e-3` |
| `SURPRISE_GATE` (sub-knob) | `False` | `False` (shipped off) |

**#13 — T-DIV real-path precision-variance acceptance (the gate the current build LACKS).** Drive the real `ResonanceSpine(lite, pel_enabled=True)` over `CORPUS`, 160 ticks, sparse assessor (`t%5==0`), reading `scar._pel.state.pi_obs`/`pi_top` each tick. Discard first 30 warm-up ticks. Assert on the steady window:
- PRIMARY: `mean_t cross-dim pstd(pi_obs) > 0.15` **[verified ~0.67]** and same for `pi_top`.
- SECONDARY: `mean_i over-time var(pi_obs[i]) > 1e-3` **[verified ~0.0023]**.
- CLIP WITNESS: `max over all (t,i) pi_obs[i] ≤ PI_MAX + 1e-9` (and `pi_top`).

**#14 — T-DIV-OFF ablation.** Same real-path replay with `PRECISION_DIVISIVE=False`: assert precision collapses — `mean_t cross-dim pstd(pi_obs) < 0.05` and dims pin near PI_MAX **[verified std 0.0, pinned 5.0]**. The >13× cross-dim gap proves the toggle is no no-op.

**#15 — T-BCM ablation.** (a) `LAMBDA_BCM=0` reduces algebraically to the legacy three-factor rule ⇒ compare W_gen vs a hand-rolled legacy step, `_frobenius < 1e-12`. (b) `LAMBDA_BCM=1`: `theta` shows multi-timescale movement — `pvariance(theta) > 1e-4` across dims AND `over-time var(theta[i]) > 1e-6`; gain is load-bearing — `mean_t (max_i m_i − min_i m_i) > 1e-2`. (c) PATH-LENGTH: `Σ_t ‖ΔW_t‖_F` at λ=1 differs from λ=0 by > tol (path-length, **not** net endpoint drift).

**#16 — T-PROD BCM×divisive cancellation guard (must-fix #9).** Real path; per tick collect effective gate `gᵢ = pi_obs[i]·last_m[i]`. After warm-up assert `mean_t cross-dim pstd(g) > tol` AND `over-time var > tol` — the product cannot silently collapse to a content-independent scalar (the two mechanisms sit on orthogonal axes: cross-dim competition vs within-dim temporal).

**#17 — T-ANCHOR identity retention.** Long high-surprise session (z driven small, ~1500 ticks), run twice: assert `‖π−π0‖` with `RHO_ANCHOR=4e-3` is `< 0.5×` the `RHO_ANCHOR=0` washout. T-ANCHOR-LIVE: with anchor on, `‖π_final − π0‖ > 1e-3` (anchor is not a pin-to-π0 no-op; π MOVES). No surprise-gate test (shipped off).

**#18 — T-SCHEMA (must-fix #8).** v1 dict (no `pi0/theta/s_bar`) round-trips with fallbacks (`pi0:=pi`, `theta:=THETA_INIT`, `s_bar:=0.0`); v2 round-trips all three. Both spine paths (`ResonanceSpine` :968/994, `ComputationSpine` :1176/1199).

**#19 — proof guards (extend #6/#7).** Boundedness fuzz #6 gains a per-tick `π ∈ [−1,1]⁸` assertion. Contraction fuzz #7 unchanged; add a real-spine assertion that runtime `pi_obs/pi_top ≤ PI_MAX` every tick (clip witness). Cost #12 (real 500-tick `<10ms/tick`) stays the empirical cost gate.

**Re-validate (build note):** the PEL-ON tests #1/#2/#5/#8 and `test_pel_ablation` now exercise the v2 default path. #2/#5/#8 get healthier (5× η, live precision). #1 (F-descent) and the `rho_p`/`eta_w`/`pi_top` ablations must be re-run; #1 is the one to watch — the `−½Σlog Πᵢ` term now varies, though the dominant shrinking error term should still drive descent. Re-tolerance only if observed, do not pre-loosen.

---

## §4 Per-tick cost

Pure-Python, O(N)/O(N²) on N=8, fixed step count, no iterate-to-convergence.

| Mechanism | Added scalar ops |
|---|---|
| M1 divisive (×{Π_obs,Π_top}) | 2 inverse passes + 2 sums + 2 affine ≈ **8N = 64** |
| M2 BCM | ≈ **9N + 8 tanh = 72 + 8 tanh** (inner N×N Hebbian loop unchanged) |
| M3 anchored π | ≈ **11N = 88** |

Total **≈ +224 scalar ops + 8 tanh/tick**. Per-tick cost stays dominated by the existing single `spectral_clamp` (10 power-iters × ~2N² ≈ 1280 ops) — the addition is **<15%**, sub-microsecond on N=8, no new allocation beyond a few length-8 lists. No new `spectral_clamp` call. Comfortably under the 10ms/tick gate; the real 500-tick benchmark (#12) is the empirical guard.

---

## §5 Snapshot / schema changes

`PEL_SCHEMA_VERSION: 1 → 2` (pel_core.py:37).

**PELState** (pel_core.py:183-191) — `+3` plastic fields; defaulted so the boundedness-fuzz bare construction (test_pel_core.py:153) stays valid (production paths always set them explicitly):
```python
    pi0: list[float] = field(default_factory=lambda: [0.0] * N)        # frozen trait-prior anchor
    theta: list[float] = field(default_factory=lambda: [THETA_INIT] * N)  # BCM sliding thresholds
    s_bar: float = 0.0                                                  # slow surprise EMA (gate only)
```
(Place after the required fields to satisfy dataclass ordering; `mu…eta_w` positions unchanged.)

**PELCore** (pel_core.py:198-201) — `+1` diagnostic, NOT persisted (recomputed each tick):
```python
    last_m: list[float] = field(default_factory=lambda: [1.0] * N)
```

**to_dict** (322-341): add `"pi0"`, `"theta"`, `"s_bar"`; `"v"` now 2.
**from_dict** (343-357): `pi0=data.get("pi0", data["pi"])`, `theta=data.get("theta",[THETA_INIT]*N)`, `s_bar=float(data.get("s_bar",0.0))` — v1 back-compat.
**from_personality** (240-249): set `pi0=list(pi)`, `theta=[THETA_INIT]*N`, eta_w gain (§1).

Optional: surface `theta` in `scar_algebra.pel_diagnostics()` (:231-237) for the BCM CI + observability (cheap; `pi0` is static, skip). The CORPUS spine tests read `scar._pel.state.*` directly regardless.

---

## §6 Anti-theater statement (honest)

**What genuinely changes on the real deployment path (sparse assessor, surprise floor ~0.47, small e0):**

1. **Precision/attention: DEAD → LIVE.** `pi_obs` goes from a constant `[5.0]·8` (cross-dim std **0.0**, every dim pinned every tick) to a competitive allocation **[verified: std ~0.67, peak 2.39, steady over-time var ~0.0023]**. The Hebbian's per-dim precision gate `pi_obs[i]` was a dead flat 5× scalar; it is now a genuine per-dim attention weight. This is the headline real-path win and the #1 diagnosed pathology, fixed structurally (not by EPS/rate tuning).
2. **Plasticity: differentiated + perpetually live.** η is restored 5× so the *mean* Hebbian magnitude matches the prior designed level (precision no longer pathologically inflates it), but it is now (a) reliability-weighted across dims and (b) BCM-metaplastic with a genuinely new live ~100-tick state `theta`. The witness is PATH-LENGTH + cross-dim gate spread.
3. **Identity: erosion stopped.** π no longer drifts to the noise-dominated `⟨z⟩≈0.08`; the anchor retains ~80% of π0 asymptotically while still adapting (~0.02–0.04 allostatic move).
4. **A real four-timescale self-modifying stack**, no two mechanisms sharing a knob.

**Residual limits we explicitly DO NOT claim:**
- **Not "better learning / lower emotion MAE."** No loss, no training, no semantics — unfalsifiable here. The claim is *liveness + differentiation + multi-timescale self-modification*, not task performance.
- **Not a bigger net W_gen drift.** Net drift stays ~0.02–0.05; the honest witness is path-length and gate spread, not net displacement. M2's pause-below-threshold makes net drift a poor metric by design.
- **Liveness is data-contingent.** It requires the corpus to keep supplying cross-dim error heterogeneity (recon: 5–9×). If real traffic ever drove near-equal, static errors, cross-dim spread → 0. This is precisely why T-DIV asserts *measured* cross-dim std on the real spine, not "code runs."
- **The surprise-gate is cut from the default** (flat surprise ⇒ constant rescale = theater); kept only as an ablatable curiosity.
- **Still 8-dim, semantic-blind, pure-Python O(N²), no training.** We did not enlarge the box — we made the existing brain-shaped machinery actually express on real traffic. No resonance-field sins: every mechanism is input-driven, closed-form, single-knob ablatable, and increases (not decreases) input-sensitivity.

---

## §7 Open forks

- **E-1 Divisive form.** budget+clip (mean 1.0, peak 7.3→clip) vs N-free (mean 0.71, peak 5.0 clip-free). **Recommend budget+clip:** matches the `ones`-init mean, gives the at-most-one-saturation theorem, real-path peak 2.39 ≪ clip so the clip is a pure proof safety-net, and test #7's `[PI_MIN,PI_MAX]` fuzz already covers it. N-free would deepen the magnitude problem (mean 0.71).
- **E-2 eta_w compensation.** 5× (restore designed mean) vs none (accept 5× weaker, lean on path-length). **Recommend 5×** — don't regress the one passing plasticity number, and differentiate *around* the restored mean. Sub-fork: gain tunable 3–5×; default 5.0 = `PI_MAX/(PI_BUDGET/N)`, self-adjusting if budget changes.
- **E-3 RHO_ANCHOR.** 4e-3 (richer adaptation; slow-loop sufficient condition met on real-path pi_top~3; boundedness unconditional) vs 8e-3 (monotone slow-contraction even at worst-case pinned pi_top=5). **Recommend 4e-3** — degenerate pi_top=5 is measure-zero and only costs slow-loop monotonicity, never the bound (§2.4 is unconditional). Revisit to 8e-3 only if T-ANCHOR shows wander.
- **E-4 v2 ON by default when `pel_core_enabled=True`?** **Recommend yes** — master flag stays default-off, the upgrade *is* the on-path, each mechanism independently ablatable. Consequence: re-validate PEL-ON tests (§3). Alternative second flag `pel_v2_enabled` **rejected** — strands the upgrade, doubles flag surface, no caller benefit since pel_core_enabled isn't in stable.
- **E-5 Surprise-gate.** **Recommend ship OFF** (red-team #7); keep `SURPRISE_GATE`/`RHO_S` ablatable for the regime-transition case only.
- **E-6 BCM θ drive.** `e0f²` (PC error-unit activity) vs `μ²`/`z²`. **Recommend `e0f²`** — it is the predictive-coding postsynaptic activity, ties θ to surprise structure, verified live on the recon 5× spread.
- **E-7 Surface `theta` in diagnostics?** **Recommend yes** (cheap, aids BCM CI + observability); skip static `pi0`.

---

## §8 Citations (canonical; author/year/venue verified by red-team citation_audit, page-markers preserved; not re-fetched this session)

**M1 divisive precision / attention-as-precision:**
- Heeger, D.J. (1992). Normalization of cell responses in cat striate cortex. *Visual Neuroscience* 9(2):181–197.
- Carandini, M. & Heeger, D.J. (2012). Normalization as a canonical neural computation. *Nature Reviews Neuroscience* 13(1):51–62 [pages: verify].
- Reynolds, J.H. & Heeger, D.J. (2009). The normalization model of attention. *Neuron* 61(2):168–185 [pages: verify].
- Feldman, H. & Friston, K.J. (2010). Attention, uncertainty, and free-energy. *Frontiers in Human Neuroscience* 4:215.
- Bogacz, R. (2017). A tutorial on the free-energy framework for modelling perception and learning. *Journal of Mathematical Psychology* 76:198–211 [pages: verify] — used to show free-energy-optimal Π*=1/e² *also* saturates on small errors, motivating the relative/divisive form.

**M2 BCM-inspired metaplasticity (labeled "BCM-inspired metaplastic gain," not literal BCM82 φ — at LAMBDA_BCM=1 the gain is non-negative [0,2], no LTD/sign-flip):**
- Bienenstock, E.L., Cooper, L.N. & Munro, P.W. (1982). Theory for the development of neuron selectivity. *Journal of Neuroscience* 2(1):32–48.
- Abraham, W.C. (2008). Metaplasticity: tuning synapses and networks for plasticity. *Nature Reviews Neuroscience* 9(5):387–399 [pages: verify].
- Intrator, N. & Cooper, L.N. (1992). Objective function formulation of the BCM theory. *Neural Networks* 5(1):3–17 [pages: verify].
- Friston, K. (2005). A theory of cortical responses. *Phil. Trans. R. Soc. B* 360(1456):815–836 [pages: verify] — error-units-as-neurons grounding for `theta = EMA(e0²)`.

**M3 anchored allostatic π:**
- Sterling, P. (2012). Allostasis: a model of predictive regulation. *Physiology & Behavior* 106(1):5–15.
- Ramsay, D.S. & Woods, S.C. (2014). Clarifying the roles of homeostasis and allostasis. *Psychological Review* 121(2):225–247 — used to *not* over-claim.
- Friston, K. (2010). The free-energy principle: a unified brain theory? *Nature Reviews Neuroscience* 11(2):127–138 — π0 as identity hyperprior.
- Uhlenbeck, G.E. & Ornstein, L.S. (1930). On the theory of Brownian motion. *Physical Review* 36:823–841 — the update is a discrete OU/AR(1) mean-reversion to π0.

**Files:** spec target `G:\SylannEngine\docs\design\v25-pel-core-techspec.md`; implementation `G:\SylannEngine\sylanne_core\compute\pel_core.py`; tests `G:\SylannEngine\tests\test_pel_core.py`, `tests\test_pel_spine.py`, `tests\test_pel_ablation.py`; verification script `C:\Users\pidan\AppData\Local\Temp\claude\G--SylannEngine\edcba155-0c80-453f-a103-fc3259044627\scratchpad\verify_pel_v2.py`.