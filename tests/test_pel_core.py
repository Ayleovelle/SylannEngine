"""P0 maths-locking tests for :mod:`sylanne_core.compute.pel_core`.

These cover the zero-real-data techspec gates (§5): #1 F-descent, #3 personality
separability, #4 input sensitivity, #6 boundedness fuzz, #7 contraction fuzz.
They lock the brain maths before any SDK coupling exists.
"""

from __future__ import annotations

import copy
import math
import random

from sylanne_core.compute.pel_core import (
    ALPHA,
    BETA,
    DELTA,
    PEL_SCHEMA_VERSION,
    PI_MAX,
    PI_MIN,
    THETA_INIT,
    N,
    PELCore,
    PELState,
    descent_step,
    readout_step,
    spectral_clamp,
)

# A tsundere-ish Big-Five profile (Sylanne) and a contrasting warm one.
TSUNDERE = {
    "openness": 0.7,
    "neuroticism": 0.7,
    "extraversion": 0.4,
    "agreeableness": 0.3,
    "conscientiousness": 0.6,
    "sovereignty_guard": 0.8,
}
WARM = {
    "openness": 0.4,
    "neuroticism": 0.2,
    "extraversion": 0.8,
    "agreeableness": 0.85,
    "conscientiousness": 0.5,
    "sovereignty_guard": 0.2,
}


def _spectral_norm(mat: list[list[float]], iters: int = 200) -> float:
    """Largest singular value of a square matrix via power iteration on MᵀM."""
    n = len(mat)
    v = [1.0 / math.sqrt(n)] * n
    sigma = 0.0
    for _ in range(iters):
        # w = M v
        w = [sum(mat[i][j] * v[j] for j in range(n)) for i in range(n)]
        # u = Mᵀ w  == (MᵀM) v
        u = [sum(mat[i][k] * w[i] for i in range(n)) for k in range(n)]
        norm = math.sqrt(sum(x * x for x in u))
        if norm < 1e-18:
            return 0.0
        v = [x / norm for x in u]
        sigma = math.sqrt(norm)
    return sigma


def _finite_diff_jacobian_mu(
    mu: list[float],
    x_t: list[float],
    w_gen: list[list[float]],
    pi_obs: list[float],
    pi_top: list[float],
    pi: list[float],
    h: float = 1e-6,
) -> list[list[float]]:
    """Central-difference Jacobian of one real ``descent_step`` w.r.t. ``mu``."""
    jac = [[0.0] * N for _ in range(N)]
    for j in range(N):
        mp = list(mu)
        mm = list(mu)
        mp[j] += h
        mm[j] -= h
        fp = descent_step(mp, x_t, w_gen, pi_obs, pi_top, pi)
        fm = descent_step(mm, x_t, w_gen, pi_obs, pi_top, pi)
        for i in range(N):
            jac[i][j] = (fp[i] - fm[i]) / (2.0 * h)
    return jac


# --------------------------------------------------------------------------- #
# Test #1 — free-energy descent                                               #
# --------------------------------------------------------------------------- #
def test_free_energy_descends_on_repeated_input() -> None:
    """On a repeated input the predictive-coding loop settles to predict it, so the
    bottom-up error ENERGY ``||e0||^2`` descends; AND online plasticity (the W_gen
    Hebbian) makes it descend strictly MORE than pure inference, witnessing genuine
    generative learning — not merely the inference loop settling.

    NB (更脑 v2): the assertion is on the *error energy*, not the full textbook
    free energy ``F = 1/2 Σ Π e^2 - 1/2 Σ log Π``. Under v2's divisive precision
    ``F`` is no longer monotone — competitive normalization deliberately assigns
    LOW precision (= high entropy, large ``-1/2 log Π``) to high-relative-error
    dims, so the entropy term rises. Critically, the *legacy* full-``F`` descent
    was itself an artifact of precision SATURATION: as Π pinned at PI_MAX the
    ``-1/2 Σ log Π`` term plummeted while the precision-weighted error actually
    *rose*. So full-``F`` monotonicity measured the dead-precision pathology v2
    removes, not learning. ``||e0||^2`` descends monotonically under BOTH paths
    (legacy 0.93→0.65, v2 0.93→0.63), so this is the honest, path-independent gate;
    ``F`` is asserted finite. The eta_w-live-vs-frozen differential keeps this test
    distinct from #5 (a bare error-drop check) by exercising the GENERATIVE weights.
    """

    def err_endpoints(freeze_plasticity: bool) -> tuple[float, float]:
        core = PELCore.from_personality(TSUNDERE)
        if freeze_plasticity:
            core.state.eta_w = 0.0  # inference only — no generative W_gen learning
        x = [0.3, -0.2, 0.5, 0.1, -0.4, 0.2, 0.0, -0.1]
        energies: list[float] = []
        for _ in range(20):
            _z, f = core.step(x, 0.5)
            assert math.isfinite(f), f
            energies.append(sum(v * v for v in core.last_e0))
        return energies[0], energies[-1]

    first_live, last_live = err_endpoints(freeze_plasticity=False)
    first_frozen, last_frozen = err_endpoints(freeze_plasticity=True)
    # (1) the error energy descends as the loop settles to predict the repeated input.
    assert last_live < first_live - 1e-3, (first_live, last_live)
    # (2) generative LEARNING contributes: the drop with plasticity on strictly
    # exceeds the inference-only (eta_w=0) drop (measured live 0.299 vs frozen 0.267 —
    # W_gen plasticity adds ~0.03 of error reduction beyond inference settling).
    assert (first_live - last_live) - (first_frozen - last_frozen) > 1e-2, (
        first_live - last_live,
        first_frozen - last_frozen,
    )


# --------------------------------------------------------------------------- #
# Test #3 — personality separability                                          #
# --------------------------------------------------------------------------- #
def test_personality_separability() -> None:
    core_a = PELCore.from_personality(TSUNDERE)
    core_b = PELCore.from_personality(WARM)
    x = [0.2, 0.1, -0.3, 0.0, 0.4, -0.1, 0.2, 0.1]
    za: list[float] = [0.0] * N
    zb: list[float] = [0.0] * N
    for _ in range(15):
        za, _fa = core_a.step(x, 0.3)
        zb, _fb = core_b.step(x, 0.3)
    diffs = [abs(za[i] - zb[i]) for i in range(N)]
    separated_dims = sum(1 for d in diffs if d > 1e-3)
    assert separated_dims >= 2, diffs
    assert math.sqrt(sum(d * d for d in diffs)) > 1e-2, diffs


# --------------------------------------------------------------------------- #
# Test #4 — input sensitivity (no saturation / content-blind collapse)        #
# --------------------------------------------------------------------------- #
def test_input_sensitivity_per_dimension() -> None:
    core = PELCore.from_personality(TSUNDERE)
    x = [0.1, -0.1, 0.2, 0.0, 0.3, -0.2, 0.1, 0.0]
    # warm up to a non-trivial interior state.
    for _ in range(5):
        core.step(x, 0.4)

    delta = 0.05
    for i in range(N):
        base_core = copy.deepcopy(core)
        pert_core = copy.deepcopy(core)
        x_pert = list(x)
        x_pert[i] += delta
        z_base, _ = base_core.step(x, 0.4)
        z_pert, _ = pert_core.step(x_pert, 0.4)
        # the perturbed dimension must move the read-out for that dimension.
        assert abs(z_pert[i] - z_base[i]) > 1e-6, (i, z_base[i], z_pert[i])


# --------------------------------------------------------------------------- #
# Test #6 — boundedness fuzz (1000 trials)                                     #
# --------------------------------------------------------------------------- #
def _random_admissible_state(rng: random.Random) -> PELState:
    raw = [[rng.uniform(-1.0, 1.0) for _ in range(N)] for _ in range(N)]
    w_gen = spectral_clamp(raw, 0.9)
    pi_obs = [rng.uniform(PI_MIN, PI_MAX) for _ in range(N)]
    pi_top = [rng.uniform(PI_MIN, PI_MAX) for _ in range(N)]
    pi = [rng.uniform(-0.999, 0.999) for _ in range(N)]
    mu = [rng.uniform(-1.0, 1.0) for _ in range(N)]
    z = [rng.uniform(-1.0, 1.0) for _ in range(N)]
    return PELState(
        mu=mu,
        z=z,
        w_gen=w_gen,
        pi_obs=pi_obs,
        pi_top=pi_top,
        pi=pi,
        z_ema=list(z),
        eta_w=0.002,
    )


def test_boundedness_fuzz() -> None:
    rng = random.Random(20250626)
    for _ in range(1000):
        core = PELCore(state=_random_admissible_state(rng))
        x = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        surprise = rng.uniform(0.0, 1.0)
        for _step in range(3):
            z, _f = core.step(x, surprise)
            for v in core.state.mu:
                assert -1.0 <= v <= 1.0, v
            for v in z:
                assert -1.0 <= v <= 1.0, v
            # 更脑 v2 (#19): the anchored allostatic pi is a convex update
            # (drift + RHO_ANCHOR <= 1), so pi is forward-invariant on [-1,1]^8.
            for v in core.state.pi:
                assert -1.0 <= v <= 1.0, v


# --------------------------------------------------------------------------- #
# Test #7 — contraction fuzz: ||J_mu|| <= 1 - alpha*delta (incl. kappa*H),     #
#           and ||J_z|| == 1 - beta                                            #
# --------------------------------------------------------------------------- #
def test_latent_jacobian_is_strictly_contractive() -> None:
    rng = random.Random(424242)
    bound = 1.0 - ALPHA * DELTA  # 0.985
    worst = 0.0
    for _ in range(400):
        raw = [[rng.uniform(-1.0, 1.0) for _ in range(N)] for _ in range(N)]
        w_gen = spectral_clamp(raw, 0.9)
        pi_obs = [rng.uniform(PI_MIN, PI_MAX) for _ in range(N)]
        pi_top = [rng.uniform(PI_MIN, PI_MAX) for _ in range(N)]
        pi = [rng.uniform(-0.999, 0.999) for _ in range(N)]
        mu = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        x = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        jac = _finite_diff_jacobian_mu(mu, x, w_gen, pi_obs, pi_top, pi)
        sigma = _spectral_norm(jac)
        worst = max(worst, sigma)
        assert sigma <= bound + 1e-6, (sigma, bound)
    # the bound should be genuinely exercised, not vacuous.
    assert worst > 0.5, worst


def test_readout_jacobian_is_pure_leak() -> None:
    rng = random.Random(13)
    for _ in range(50):
        w_gen = spectral_clamp([[rng.uniform(-1.0, 1.0) for _ in range(N)] for _ in range(N)], 0.9)
        mu = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        x = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        z0 = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        h = 1e-6
        jac = [[0.0] * N for _ in range(N)]
        for j in range(N):
            zp = list(z0)
            zm = list(z0)
            zp[j] += h
            zm[j] -= h
            fp = readout_step(zp, mu, x, w_gen)
            fm = readout_step(zm, mu, x, w_gen)
            for i in range(N):
                jac[i][j] = (fp[i] - fm[i]) / (2.0 * h)
        # J_z must equal (1 - beta) * I exactly (up to FD noise).
        for i in range(N):
            for j in range(N):
                expected = (1.0 - BETA) if i == j else 0.0
                assert abs(jac[i][j] - expected) < 1e-6, (i, j, jac[i][j])
        assert abs(_spectral_norm(jac) - (1.0 - BETA)) < 1e-6


# --------------------------------------------------------------------------- #
# Test #18 — schema v1->v2 round-trip with back-compat fallbacks               #
# --------------------------------------------------------------------------- #
def test_schema_v2_roundtrips_all_plastic_state() -> None:
    core = PELCore.from_personality(TSUNDERE)
    # evolve so pi0 != pi and theta != THETA_INIT (genuinely distinct state).
    x = [0.4, -0.3, 0.5, 0.1, -0.2, 0.3, 0.0, -0.1]
    for _ in range(30):
        core.step(x, 0.6)
    d = core.to_dict()
    assert d["v"] == PEL_SCHEMA_VERSION == 2
    assert "pi0" in d and "theta" in d and "s_bar" in d
    back = PELCore.from_dict(d)
    assert back.state.pi0 == core.state.pi0
    assert back.state.theta == core.state.theta
    assert back.state.s_bar == core.state.s_bar
    # the frozen trait anchor must NOT equal the drifted pi (proves it is real state).
    assert any(abs(core.state.pi0[i] - core.state.pi[i]) > 1e-4 for i in range(N))


def test_schema_v1_dict_migrates_with_fallbacks() -> None:
    # An old v1 snapshot has no pi0/theta/s_bar. Migration must apply the documented
    # fallbacks (pi0 := pi, theta := THETA_INIT, s_bar := 0.0) rather than KeyError.
    core = PELCore.from_personality(TSUNDERE)
    for _ in range(10):
        core.step([0.2, -0.1, 0.3, 0.0, 0.1, -0.2, 0.1, 0.0], 0.5)
    v1 = core.to_dict()
    del v1["pi0"], v1["theta"], v1["s_bar"]
    v1["v"] = 1
    back = PELCore.from_dict(v1)
    assert back.state.pi0 == core.state.pi  # must-fix #2: anchors to (drifted) pi
    assert back.state.theta == [THETA_INIT] * N
    assert back.state.s_bar == 0.0


# --------------------------------------------------------------------------- #
# v2.5 (B) — the e2 semantic prior keeps the descent strictly contractive      #
# (the term adds only diag(pi_a) to H; shipped OFF but must be bounded if on)   #
# --------------------------------------------------------------------------- #
def test_semantic_prior_descent_stays_contractive() -> None:
    rng = random.Random(99)
    bound = 1.0 - ALPHA * DELTA  # 0.985
    worst = 0.0
    for _ in range(300):
        w_gen = spectral_clamp([[rng.uniform(-1.0, 1.0) for _ in range(N)] for _ in range(N)], 0.9)
        pi_obs = [rng.uniform(PI_MIN, PI_MAX) for _ in range(N)]
        pi_top = [rng.uniform(PI_MIN, PI_MAX) for _ in range(N)]
        pi = [rng.uniform(-0.999, 0.999) for _ in range(N)]
        pi_a = [rng.uniform(0.0, PI_MAX) for _ in range(N)]  # assessor precision channel
        a_vec = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        mu = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        x = [rng.uniform(-1.0, 1.0) for _ in range(N)]
        h = 1e-6
        jac = [[0.0] * N for _ in range(N)]
        for j in range(N):
            mp, mm = list(mu), list(mu)
            mp[j] += h
            mm[j] -= h
            fp = descent_step(mp, x, w_gen, pi_obs, pi_top, pi, a_vec, pi_a)
            fm = descent_step(mm, x, w_gen, pi_obs, pi_top, pi, a_vec, pi_a)
            for i in range(N):
                jac[i][j] = (fp[i] - fm[i]) / (2.0 * h)
        sigma = _spectral_norm(jac)
        worst = max(worst, sigma)
        assert sigma <= bound + 1e-6, (sigma, bound)
    assert worst > 0.5, worst  # the bound is genuinely exercised
