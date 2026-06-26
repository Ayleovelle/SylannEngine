Confirmed numerically. Key new findings: contraction holds (κ·λ_max(H)@π=5 = 0.635); divisive de-saturates (std 0.73, peak 2.39); BCM m-spread is robustly live (0.58 ≫ 1e-2) — but the **θ-movement thresholds in test #15(b) FAIL numerically** on the real error scale.

---

# Completeness critique — PEL 更脑 v2 spec

## Punch-list

### (a) Mechanism dismissed without a fair hearing
- **Gamma/conjugate-hyperprior precision (the canonical bounded free-energy form) is used one-sidedly.** §8 cites Bogacz 2017 only to argue Π\*=1/e² saturates → motivate divisive. But Bogacz's *own* prior-regularized update Π = (1+2a)/(e²+2b) is bounded above by (1+2a)/(2b) with **no clip and no normalization sum** — strictly cheaper than divisive (fully local O(N), no Σr pass). The honest reason to still pick divisive is that the Gamma form gives bounded-but-*independent* precision, NOT cross-dim competition, and the headline witness is cross-dim spread. Add one sentence saying that explicitly; right now the dismissal reads as if Bogacz only supports the saturation point. Not fatal, but it is the one real "cheaper alternative" the spec half-buried.
- No cheaper *competitive* form was missed: divisive (rᵢ/Σr) is already the L1 (exp-free) version of softmax-attention. Good.

### (b) Proof gaps under combined mechanisms
- **Contraction proof is sound** — the bound depends on precision only via `max_i Πᵢ ≤ PI_MAX` (per-dim clip), and divisive's budget/sum is irrelevant to it. Verified κ·λ_max(H)=0.635. M3's convex π-update (d+a=5e-3≤1) is forward-invariant and value-of-π never enters ‖J_μ‖. M2 only rescales pre-clamp ΔW, spectral_clamp is unconditional and last. **No contraction gap.**
- **One numeric honesty slip in §2.5:** it bounds |ΔW| with "η≈0.01", but real max η = 0.002·(0.5+1.0)·5 = **0.015**, not 0.01. Bound stays finite (0.525) so boundedness is fine, but state the true 0.015.
- **Ordering is safe** (descent reads previous-tick clamped W; Hebbian→clamp at tail) — M2 does not perturb it. Worth one explicit line, since it's load-bearing.

### (c) Does the real-path test actually catch regression to saturation?
- Primary (cross-dim pstd > 0.15) **does** discriminate (0.67 vs 0.0) and is warm-up-insensitive. Good.
- **Two sub-thresholds are mis-scaled and would FAIL a correctly-working build** (concrete CI bug, NOT [verified] in the spec):
  - #15(b) `pvariance(theta) > 1e-4 across dims` — measured **1.8e-5** (fails 5.5×). θ≈EMA(e0²)∈[1e-4,1e-2], so cross-dim θ variance is intrinsically O(1e-5).
  - #15(b) `over-time var(theta[i]) > 1e-6` — measured **3.4e-7** (fails ~3×).
  - Fix: drop both θ-variance thresholds (or rescale to ~1e-6 / ~1e-7, or normalize by mean θ²). The robust BCM witnesses are **m-spread (0.58)** and **path-length**; lean on those, not raw θ variance.
- **Temporal secondary margin is thin:** over-time var 0.0023 vs tol 1e-3 = only 2.3×. A modest regime shift drops it under tol → flaky. Either lower tol with a comment or demote to a soft/observability assert.

### (d) Snapshot migration safety
- Dataclass ordering OK (all new fields defaulted, placed after `free_energy`; the only positional/bare construction is test_pel_core.py:153). from_dict uses kwargs (scar_algebra.py:707 `PELCore.from_dict`). Safe.
- **Real semantic gap: v1 fallback `pi0 := data["pi"]` anchors to the already-drifted π, not the true trait-prior.** A long-running v1 session that eroded under the old leak-to-⟨z⟩ rule will, post-migration, "anchor" to its eroded identity — the no-washout guarantee does NOT retroactively restore identity, it freezes the loss. Unavoidable without personality at the snapshot path, but it must be documented in §5, and ideally the host re-calls `set_pel_priors` (which has personality) to recover true π0 on first load rather than trusting the fallback.
- Pre-existing, tangential: scar_algebra.py:708 force-sets `_pel_enabled=True` whenever a "pel" key is present — a snapshot can re-enable PEL with the config flag off, nicking the "flag-off ⇒ byte-identical" claim. Not introduced by v2, but the v2 default-on makes it more consequential; flag it.

### (e) Over-claim / theater re-opening
- §6 is mostly honest. M2 is **not** a steady-state no-op (refuted: steady mean m per dim spans 0.72–1.01, persistent cross-dim depression — genuine differentiation, not zero-mean jitter). Good.
- Trim/soften: "**a real four-timescale self-modifying stack**" — θ self-modifies the *rate envelope* but its operating point tracks its own input (m→differentiated-but-input-slaved), and π's allostatic move is 0.02–0.04. Call it "multi-timescale, input-driven modulation," not "self-modifying" without qualification, to avoid the resonance-field's "aimless autonomy" framing.
- "~80% of π0 retained" is exact (a/(d+a)=0.8) and fine.

### (f) Citation truth
- Spot-checked the load-bearing refs: Bienenstock/Cooper/Munro 1982 *J Neurosci* 2(1):32–48 ✓, Heeger 1992 *Vis Neurosci* 9(2):181–197 ✓, Reynolds & Heeger 2009 *Neuron* 61(2):168–185 ✓, Feldman & Friston 2010 *Front Hum Neurosci* 4:215 ✓, Sterling 2012 *Physiol Behav* 106(1):5–15 ✓, Uhlenbeck & Ornstein 1930 *Phys Rev* 36:823–841 ✓. No fabrication, no 拉大旗; [pages: verify] markers are correctly placed on the ones not re-fetched. The "BCM-inspired metaplastic gain" relabel (not literal BCM82 φ) is the honest call. Clean — but none were re-fetched this session, so keep the markers.

---

## THE single most dangerous unaddressed risk

**The entire "DEAD→LIVE" proof is executed against a fixed CORPUS fixture, and there is NO production-side witness that precision spread stays alive on real deployment traffic.** Divisive precision's liveness is, by the spec's own admission, data-contingent on cross-dim error heterogeneity (recon 5–9×). The test #8 corpus was selected/known to have that spread, so T-DIV passes by construction. But if real production traffic carries flatter, more uniform errors, divisive collapses to a uniform ≈1.0 vector (cross-dim std→0) — i.e. precision goes dead again — and **every CI gate stays green**, because they all read the curated corpus, not live traffic. This is structurally the same sin the north star warns against ("success measured on a rigged synthetic session"), only with a more realistic-looking rig: the gate proves liveness on a chosen fixture, not on the regime that actually ships.

Mitigation (do before merge): add a lightweight runtime/telemetry assertion — surface `cross-dim pstd(pi_obs)` (and the §1 product-spread `var(pi_obs·m)`) in `pel_diagnostics()` and emit it on real traffic, with an alert if the steady-window spread falls below the T-DIV tol. That converts "live on our corpus" into "we will notice if it goes dead in production," which is the only thing that makes the headline claim falsifiable post-deploy.

**Immediate must-fix before the build is green:** the test #15(b) θ-variance thresholds (1e-4 / 1e-6) reject a correctly-functioning BCM (measured 1.8e-5 / 3.4e-7) — drop them and gate M2 on m-spread + path-length, which are the robust, verified witnesses.

Relevant files: `G:\SylannEngine\sylanne_core\compute\pel_core.py`, `G:\SylannEngine\sylanne_core\compute\scar_algebra.py` (PEL wiring :471-476, snapshot :703-708, diagnostics :227-236), spec target `G:\SylannEngine\docs\design\v25-pel-core-techspec.md`.