"""P3 ablation-sweep tests for PEL-Core (techspec §P3 hardening).

Each core mechanism is toggled to its null value and shown to produce a
MEASURABLE change in the core's trajectory, proving no mechanism is a silent
no-op (anti-theater hardening):

* ``Pi_top -> 0`` — nulling the top-down precision term changes the latent
  descent (and therefore the read-out trajectory).
* ``eta_W -> 0`` — disabling the three-factor Hebbian rule freezes ``W_gen``
  (zero Frobenius drift) where the live rule drifts it non-trivially.
* ``rho_p -> 0`` — freezing the online precision EMA pins ``Pi_obs`` at its
  initial ``ones`` (zero variance) where the live rule spreads it across dims.

These run the real :class:`PELCore` (no SDK coupling needed) so they stay fast
and deterministic.
"""

from __future__ import annotations

import copy
import math
import statistics
from typing import TYPE_CHECKING

from sylanne_core.compute import pel_core
from sylanne_core.compute.pel_core import N, PELCore, descent_step

if TYPE_CHECKING:
    from pytest import MonkeyPatch

TSUNDERE: dict[str, float] = {
    "openness": 0.7,
    "neuroticism": 0.7,
    "extraversion": 0.4,
    "agreeableness": 0.3,
    "conscientiousness": 0.6,
    "sovereignty_guard": 0.8,
}


def _frobenius(a: list[list[float]], b: list[list[float]]) -> float:
    return sum(
        (a[i][j] - b[i][j]) ** 2 for i in range(len(a)) for j in range(len(a[0]))
    ) ** 0.5


def _varying_input(t: int) -> list[float]:
    """A non-trivial, dimension-asymmetric drive (mirrors the §5 #2 session).

    A couple of dims swing hard and unpredictably (large persistent ``e0`` =>
    low learned precision) while others stay near-zero (precision saturates),
    so the live precision rule genuinely spreads ``Pi_obs`` across dims.
    """
    hard = 0.95 * (1.0 if t % 2 == 0 else -1.0)
    return [
        hard,
        0.02,
        0.9 * ((t % 4) - 1.5) / 1.5,
        0.0,
        0.03,
        0.85 * (1.0 if t % 3 else -1.0),
        0.01,
        0.8 * ((t % 2) * 2 - 1),
    ]


# --------------------------------------------------------------------------- #
# Ablation A — top-down precision Pi_top is load-bearing                       #
# --------------------------------------------------------------------------- #
def test_ablation_pi_top_changes_trajectory() -> None:
    base = PELCore.from_personality(TSUNDERE)
    abl = copy.deepcopy(base)
    z_base: list[float] = [0.0] * N
    z_abl: list[float] = [0.0] * N
    for t in range(40):
        x = _varying_input(t)
        z_base, _ = base.step(x, 0.5)
        # Null the top-down precision EVERY tick (the online rule would otherwise
        # rebuild it), so the descent's ``- Pi_top ⊙ e1`` term is dead throughout.
        abl.state.pi_top = [0.0] * N
        z_abl, _ = abl.step(x, 0.5)
    diff = sum((z_base[i] - z_abl[i]) ** 2 for i in range(N)) ** 0.5
    assert diff > 1e-3, (diff, z_base, z_abl)


def test_ablation_pi_top_changes_single_descent() -> None:
    # Same fact at the pure-function level: with mu != pi (so e1 != 0), zeroing
    # Pi_top measurably moves one real ``descent_step``.
    core = PELCore.from_personality(TSUNDERE)
    w_gen = core.state.w_gen
    pi = core.state.pi
    mu = [pi[i] + 0.3 for i in range(N)]  # ensure e1 = mu - pi is non-zero
    x = [0.2, -0.3, 0.4, 0.1, -0.2, 0.3, -0.1, 0.2]
    pi_obs = [1.0] * N
    on = descent_step(mu, x, w_gen, pi_obs, [1.0] * N, pi)
    off = descent_step(mu, x, w_gen, pi_obs, [0.0] * N, pi)
    diff = max(abs(on[i] - off[i]) for i in range(N))
    assert diff > 1e-4, diff


# --------------------------------------------------------------------------- #
# Ablation B — eta_W (Hebbian rate) is load-bearing                            #
# --------------------------------------------------------------------------- #
def test_ablation_eta_w_freezes_w_gen() -> None:
    base = PELCore.from_personality(TSUNDERE)
    abl = copy.deepcopy(base)
    abl.state.eta_w = 0.0  # disable the three-factor Hebbian plasticity
    w0 = [list(row) for row in base.state.w_gen]
    for t in range(60):
        x = _varying_input(t)
        base.step(x, 0.6)
        abl.step(x, 0.6)
    drift_base = _frobenius(w0, base.state.w_gen)
    drift_abl = _frobenius(w0, abl.state.w_gen)
    # Live rule drifts the generative matrix non-trivially; ablated rule cannot
    # move it at all (the spectral clamp is idempotent on an unchanged matrix).
    assert drift_base > 1e-3, drift_base
    assert drift_abl < 1e-12, drift_abl
    assert drift_base > drift_abl


# --------------------------------------------------------------------------- #
# Ablation C — rho_p (online precision EMA rate) is load-bearing               #
# --------------------------------------------------------------------------- #
def test_ablation_rho_p_freezes_precisions(monkeypatch: MonkeyPatch) -> None:
    # Live run first: the online precision rule spreads Pi_obs across dims.
    live = PELCore.from_personality(TSUNDERE)
    for t in range(60):
        live.step(_varying_input(t), 0.6)
    var_live = statistics.pvariance(live.state.pi_obs)

    # Ablated run: rho_p = 0 => Pi <- (1-0)*Pi + 0 = Pi, pinned at its ones init.
    monkeypatch.setattr(pel_core, "RHO_P", 0.0)
    abl = PELCore.from_personality(TSUNDERE)
    for t in range(60):
        abl.step(_varying_input(t), 0.6)
    var_abl = statistics.pvariance(abl.state.pi_obs)

    assert var_live > 1e-3, (var_live, live.state.pi_obs)
    assert var_abl < 1e-12, (var_abl, abl.state.pi_obs)
    assert all(p == 1.0 for p in abl.state.pi_obs), abl.state.pi_obs


# --------------------------------------------------------------------------- #
# Test #15 — T-BCM: the metaplastic gain m is load-bearing (更脑 v2 / M2)       #
# --------------------------------------------------------------------------- #
def test_bcm_lambda_zero_is_identity_gain(monkeypatch: MonkeyPatch) -> None:
    # (a) LAMBDA_BCM=0 => m_i == 1 exactly, so the three-factor Hebbian reduces
    # ALGEBRAICALLY to the legacy rule (the factor is identical). To prove this is a
    # COMPUTED identity (1 + 0*g) and not merely last_m reading its [1.0]*N default,
    # the SAME driving at LAMBDA_BCM=1 must yield a non-identity gain — i.e. the BCM
    # machinery genuinely runs and LAMBDA_BCM gates it.
    def last_m_history(lam: float) -> list[list[float]]:
        monkeypatch.setattr(pel_core, "LAMBDA_BCM", lam)
        core = PELCore.from_personality(TSUNDERE)
        history: list[list[float]] = []
        for t in range(40):
            core.step(_varying_input(t), 0.6)
            history.append(list(core.last_m))
        return history

    zero = last_m_history(0.0)
    one = last_m_history(1.0)
    # λ=0: m is exactly the identity gain on every tick (legacy reduction).
    assert all(abs(mi - 1.0) < 1e-12 for tick in zero for mi in tick), zero[-1]
    # λ=1 on identical driving: m departs from 1.0 — the λ=0 result is a computed
    # identity, not a stuck default (the BCM gain machinery actually executes).
    assert any(abs(mi - 1.0) > 1e-3 for tick in one for mi in tick), one[-1]


def test_bcm_gain_is_live_and_differentiated(monkeypatch: MonkeyPatch) -> None:
    # (b) LAMBDA_BCM=1 => m differentiates across dims (a genuine per-dim rate gate,
    # not a content-blind scalar). The robust witness is m-SPREAD, NOT raw theta
    # variance: per critic must-fix #1, theta ~ EMA(e0^2) ~ O(1e-2) so cross-dim
    # theta variance is intrinsically O(1e-5) and the spec's draft >1e-4 / >1e-6
    # theta thresholds would FALSELY REJECT a correctly-working BCM (measured
    # 6.1e-6 / 1.8e-6). m-spread carries ~100x margin instead.
    monkeypatch.setattr(pel_core, "LAMBDA_BCM", 1.0)
    core = PELCore.from_personality(TSUNDERE)
    spreads = [0.0] * 60
    for t in range(60):
        core.step(_varying_input(t), 0.6)
        spreads[t] = max(core.last_m) - min(core.last_m)
    assert statistics.mean(spreads) > 1e-2, statistics.mean(spreads)


def test_bcm_changes_plasticity_path_length(monkeypatch: MonkeyPatch) -> None:
    # (c) PATH-LENGTH witness: the integrated plasticity path sum_t ||dW_t||_F at
    # lambda=1 differs materially from lambda=0. M2's pause-below-threshold makes net
    # endpoint drift a poor metric by design, so path-length (not net drift) is the
    # honest plasticity witness.
    def path_length(lam: float) -> float:
        monkeypatch.setattr(pel_core, "LAMBDA_BCM", lam)
        core = PELCore.from_personality(TSUNDERE)
        prev = [list(r) for r in core.state.w_gen]
        pl = 0.0
        for t in range(80):
            core.step(_varying_input(t), 0.6)
            pl += _frobenius(prev, core.state.w_gen)
            prev = [list(r) for r in core.state.w_gen]
        return pl

    pl0 = path_length(0.0)
    pl1 = path_length(1.0)
    assert abs(pl1 - pl0) / max(pl0, 1e-9) > 0.05, (pl0, pl1)


# --------------------------------------------------------------------------- #
# Test #17 — T-ANCHOR: anchored allostatic pi retains identity (更脑 v2 / M3)   #
# --------------------------------------------------------------------------- #
def test_anchor_retains_identity_vs_washout(monkeypatch: MonkeyPatch) -> None:
    def final_drift(rho_anchor: float) -> float:
        monkeypatch.setattr(pel_core, "RHO_ANCHOR", rho_anchor)
        core = PELCore.from_personality(TSUNDERE)
        pi0 = list(core.state.pi0)
        x = [0.0] * N  # drive z small => z_ema -> ~0 = maximum erosion pressure
        for _ in range(1500):
            core.step(x, 0.5)
        return math.sqrt(sum((core.state.pi[i] - pi0[i]) ** 2 for i in range(N)))

    d_anchor = final_drift(4e-3)
    d_wash = final_drift(0.0)
    # The anchor retains identity: long-session drift is < half the unanchored
    # leak-to-<z> washout (theory: retain a/(d+a) ~ 80% of pi0).
    assert d_anchor < 0.5 * d_wash, (d_anchor, d_wash)
    # But it is NOT a pin-to-pi0 no-op: pi genuinely MOVES (allostatic adaptation).
    assert d_anchor > 1e-3, d_anchor


# --------------------------------------------------------------------------- #
# Test #17b — T-GATE: the M3 surprise-gate sub-knob (shipped OFF, E-5)         #
# --------------------------------------------------------------------------- #
def test_surprise_gate_scales_drift_and_stays_bounded(monkeypatch: MonkeyPatch) -> None:
    # The surprise-gate is shipped OFF but is a live, persisted, ablatable knob, so
    # it needs coverage too (else its branch, RHO_S, and s_bar persistence are dead).
    # With it ON the pi drift rate scales with the slow surprise EMA s_bar. Assert
    # (a) s_bar tracks surprise, (b) pi stays in [-1,1]^8 under the VARIABLE drift
    # (the boundedness proof case drift+RHO_ANCHOR<=1 for surprise<=1), (c) a
    # non-zero s_bar round-trips through to_dict/from_dict.
    monkeypatch.setattr(pel_core, "SURPRISE_GATE", True)
    core = PELCore.from_personality(TSUNDERE)
    x = [0.4, -0.3, 0.5, 0.1, -0.2, 0.3, 0.0, -0.1]
    for _ in range(200):
        core.step(x, 0.8)  # high, steady surprise drives s_bar up
        for v in core.state.pi:
            assert -1.0 <= v <= 1.0, v
    # s_bar is the slow EMA of surprise; pinned at 0.8 it climbs toward 0.8 (~0.78
    # after 200 ticks at RHO_S=0.02), proving the gate branch genuinely executed.
    assert 0.1 < core.state.s_bar <= 0.8 + 1e-9, core.state.s_bar
    # a non-zero s_bar must round-trip (schema v2 persists it).
    back = PELCore.from_dict(core.to_dict())
    assert back.state.s_bar == core.state.s_bar


def test_surprise_gate_off_keeps_s_bar_zero() -> None:
    # Default (gate OFF): s_bar is never touched, so it stays at its 0.0 init — the
    # drift uses the constant RHO_PI. This pins the shipped default behaviour.
    core = PELCore.from_personality(TSUNDERE)
    for _ in range(50):
        core.step([0.4, -0.3, 0.5, 0.1, -0.2, 0.3, 0.0, -0.1], 0.8)
    assert core.state.s_bar == 0.0
