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
