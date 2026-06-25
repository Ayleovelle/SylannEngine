"""PEL-Core — Predictive-Encoding Latent core (v2.5).

A two-layer predictive-coding micro-circuit that evolves an 8-dim latent belief
``mu`` and an observed emotion read-out ``z`` (which downstream writes into
``scar_state.base``). This module is **pure Python** (``math`` + list-of-lists,
no numpy) so it can live in the lite tier, and is **fully mypy-strict typed**.

It is intentionally *standalone* at P0: nothing here couples to the rest of the
SDK yet. The maths implemented are the techspec (``v25-pel-core-techspec.md``):

* §2  — K=2 free-energy descent (``e0``, ``e1``, gradient ``g``, ``mu`` update;
        bounded read-out ``z``).
* §4  — online three-factor surprise-gated ``W_gen`` Hebbian plasticity + a
        10-iteration power-method spectral clamp to ``rho=0.9``; online
        precision updates; free energy ``F``.
* §4.3 — personality init: ``pi`` from Big-Five, ``W_gen = 0.5*I + structured
        off-diagonal`` (spectral-clamped <= 0.9), ``Pi = ones``, ``mu0 = pi``;
        plus the D-8 slow allostatic ``pi`` drift.

Boundedness & contraction are structural (techspec §3): both active states are
leaky ``tanh`` convex updates so ``mu, z in [-1, 1]^8`` is forward-invariant, and
the latent Jacobian obeys ``||J_mu||_2 <= 1 - alpha*delta`` while
``||J_z||_2 = 1 - beta`` for every admissible weight/precision/input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# --- dimensionality -----------------------------------------------------------
N: int = 8  # emotion / latent dimensionality (frozen dim order, see design §2)

# --- working point (D-4 / D-5, techspec §1) -----------------------------------
ALPHA: float = 0.3  # latent leak / descent step mix
BETA: float = 0.4  # read-out leak mix
K: int = 2  # inner free-energy descent iterations (fixed, ignores _mlp_passes)
KAPPA: float = 0.1  # gradient step size inside tanh
PI_MAX: float = 5.0  # precision ceiling
PI_MIN: float = 0.1  # precision floor
DELTA: float = 0.05  # strict-contraction leak on the descent branch
RHO_P: float = 0.05  # online precision EMA rate
EPS: float = 1e-3  # precision update numerical floor
W_IN: float = 0.6  # input pass-through gain, W_in = diag(0.6)

# --- D-8 slow allostatic pi drift ---------------------------------------------
RHO_PI: float = 1e-3  # pi drift rate (very small, bounded; in snapshot)
Z_EMA_RATE: float = 0.05  # EMA rate for <z> feeding the pi drift

# --- plasticity & spectral clamp ----------------------------------------------
W_SPECTRAL_MAX: float = 0.9  # ||W_gen||_2 ceiling (must keep kappa*Pi_max <= 0.5)
_POWER_ITERS: int = 10  # power-iteration count for the spectral clamp

# Big-Five canonical keys with their legacy Embodiment-Five aliases. P0 reads
# personality robustly from whichever naming the caller supplies.
_TRAIT_ALIASES: dict[str, str] = {
    "openness": "boundary_permeability",
    "neuroticism": "perception_acuity",
    "extraversion": "expression_drive_trait",
    "agreeableness": "relational_gravity",
    "conscientiousness": "inner_order",
}


def _trait(personality: dict[str, float], name: str, default: float = 0.5) -> float:
    """Read a Big-Five trait, falling back to its legacy alias then a default."""
    if name in personality:
        return float(personality[name])
    alias = _TRAIT_ALIASES.get(name)
    if alias is not None and alias in personality:
        return float(personality[alias])
    return default


def _dot(row: list[float], vec: list[float]) -> float:
    """Plain dot product of two equal-length vectors."""
    return sum(row[i] * vec[i] for i in range(len(vec)))


def spectral_clamp(
    weight: list[list[float]], rho: float = W_SPECTRAL_MAX
) -> list[list[float]]:
    """Return a copy of ``weight`` scaled so its spectral norm is ``<= rho``.

    Uses the same 10-iteration power method as the legacy MLP weights
    (``scar_algebra._spectral_normalize``), replicated numpy-free. A single
    power iteration only yields a *lower* bound on sigma and could silently let
    ``||W|| > rho`` slip through and break the contraction guarantee, so the
    full 10-iteration estimate is used deliberately (techspec §4 must-fix).
    """
    rows = len(weight)
    cols = len(weight[0]) if rows > 0 else 0
    if rows == 0 or cols == 0:
        return [list(r) for r in weight]

    u = [1.0 / math.sqrt(rows)] * rows
    v = [0.0] * cols
    for _ in range(_POWER_ITERS):
        for j in range(cols):
            v[j] = sum(weight[i][j] * u[i] for i in range(rows))
        v_norm = math.sqrt(sum(x * x for x in v)) + 1e-12
        v = [x / v_norm for x in v]
        for i in range(rows):
            u[i] = sum(weight[i][j] * v[j] for j in range(cols))
        u_norm = math.sqrt(sum(x * x for x in u)) + 1e-12
        u = [x / u_norm for x in u]

    sigma = 0.0
    for i in range(rows):
        sigma += u[i] * sum(weight[i][j] * v[j] for j in range(cols))

    if sigma > rho:
        scale = rho / sigma
        return [[weight[i][j] * scale for j in range(cols)] for i in range(rows)]
    return [list(r) for r in weight]


def descent_step(
    mu: list[float],
    x_t: list[float],
    w_gen: list[list[float]],
    pi_obs: list[float],
    pi_top: list[float],
    pi: list[float],
) -> list[float]:
    """One inner free-energy descent step on the latent belief ``mu``.

    ``e0 = x_t - W_gen mu`` (bottom-up), ``e1 = mu - pi`` (top-down to the
    personality prior). The gradient of ``-F`` w.r.t. ``mu`` is
    ``g = W_genᵀ (Pi_obs ⊙ e0) - Pi_top ⊙ e1``; the update is the leaky,
    bounded convex step

        mu <- (1 - alpha) mu + alpha * tanh( (1 - delta) * (mu + kappa * g) ).

    The ``(1 - delta)`` leak on the descent branch is what makes the latent
    Jacobian uniformly strictly contractive (``||J_mu|| <= 1 - alpha*delta``)
    even at ``tanh' = 1``; see techspec §3.2. Exposed at module scope so tests
    can finite-difference the *real* recursion (including the ``kappa*H`` term).
    """
    e0 = [x_t[i] - _dot(w_gen[i], mu) for i in range(N)]
    e1 = [mu[i] - pi[i] for i in range(N)]
    pe0 = [pi_obs[i] * e0[i] for i in range(N)]
    g = [
        sum(w_gen[j][i] * pe0[j] for j in range(N)) - pi_top[i] * e1[i]
        for i in range(N)
    ]
    return [
        (1.0 - ALPHA) * mu[i]
        + ALPHA * math.tanh((1.0 - DELTA) * (mu[i] + KAPPA * g[i]))
        for i in range(N)
    ]


def readout_step(
    z_prev: list[float], mu: list[float], x_t: list[float], w_gen: list[list[float]]
) -> list[float]:
    """Bounded emotion read-out: ``z <- (1-beta) z + beta tanh(W_gen mu + W_in x)``.

    The recursion in ``z_{t-1}`` is a pure leak (``z_hat`` depends on ``mu`` not
    ``z_{t-1}``), so ``J_z = (1 - beta) I`` with spectral norm ``1 - beta``.
    """
    z_hat = [_dot(w_gen[i], mu) for i in range(N)]
    return [
        (1.0 - BETA) * z_prev[i] + BETA * math.tanh(z_hat[i] + W_IN * x_t[i])
        for i in range(N)
    ]


@dataclass
class PELState:
    """Mutable plastic state of one PEL-Core (one session/host).

    All matrices are plain list-of-lists; the whole live state is < 1 KB and is
    snapshot-serialisable (P1). ``z_ema`` and the (drifting) ``pi`` participate
    in the D-8 slow allostatic update and therefore belong in the snapshot.
    """

    mu: list[float]
    z: list[float]
    w_gen: list[list[float]]
    pi_obs: list[float]
    pi_top: list[float]
    pi: list[float]
    z_ema: list[float]
    eta_w: float
    free_energy: float = 0.0


@dataclass
class PELCore:
    """Owns a :class:`PELState` and runs the per-tick PEL update."""

    state: PELState
    # last per-dim diagnostics (bottom-up / top-down errors), for observability.
    last_e0: list[float] = field(default_factory=lambda: [0.0] * N)
    last_e1: list[float] = field(default_factory=lambda: [0.0] * N)

    # -- construction ----------------------------------------------------------
    @classmethod
    def from_personality(
        cls, personality: dict[str, float], base: list[float] | None = None
    ) -> PELCore:
        """Initialise from Big-Five traits (techspec §4.3).

        ``pi`` is the personality attractor centre; ``W_gen = 0.5*I +`` a small
        deterministic structured off-diagonal band (spectral-clamped <= 0.9);
        ``Pi_obs = Pi_top = ones``; ``mu0 = pi``; ``z0 = base`` (or zeros).
        ``eta_W = 0.002*(0.5 + openness)``.
        """
        openness = _trait(personality, "openness")
        neuroticism = _trait(personality, "neuroticism")
        extraversion = _trait(personality, "extraversion")
        agreeableness = _trait(personality, "agreeableness")
        sovereignty = _trait(personality, "sovereignty_guard", default=0.5)

        pi_raw = [
            0.30 * agreeableness - 0.20 * neuroticism,  # 0 warmth
            0.10 + 0.20 * extraversion + 0.20 * neuroticism,  # 1 arousal
            0.40 * (extraversion - neuroticism),  # 2 valence
            0.40 * neuroticism,  # 3 tension
            0.40 * openness,  # 4 curiosity
            0.20 * neuroticism,  # 5 repair_pressure
            0.30 * extraversion - 0.20 * (1.0 - agreeableness),  # 6 expression_drive
            0.50 * (1.0 - agreeableness) + 0.30 * sovereignty,  # 7 boundary_firmness
        ]
        pi = [math.tanh(v) for v in pi_raw]

        w_gen = cls._init_w_gen()
        pi_obs = [1.0] * N
        pi_top = [1.0] * N
        mu = list(pi)
        z = list(base) if base is not None else [0.0] * N
        eta_w = 0.002 * (0.5 + openness)

        state = PELState(
            mu=mu,
            z=z,
            w_gen=w_gen,
            pi_obs=pi_obs,
            pi_top=pi_top,
            pi=pi,
            z_ema=list(z),
            eta_w=eta_w,
        )
        return cls(state=state)

    @staticmethod
    def _init_w_gen() -> list[list[float]]:
        """``0.5*I`` plus a small deterministic structured off-diagonal band."""
        w = [[0.0] * N for _ in range(N)]
        for i in range(N):
            w[i][i] = 0.5
            w[i][(i + 1) % N] = 0.06
            w[i][(i - 1) % N] = -0.04
        return spectral_clamp(w, W_SPECTRAL_MAX)

    # -- per-tick update -------------------------------------------------------
    def step(self, x_t: list[float], surprise: float) -> tuple[list[float], float]:
        """Advance one main tick: K-step latent descent, read-out, plasticity.

        Returns ``(z, F)`` where ``z`` is the new bounded emotion read-out and
        ``F`` is the (diagnostic) free energy. ``surprise`` in ``[0, 1]`` gates
        the three-factor ``W_gen`` Hebbian update.
        """
        st = self.state
        mu = list(st.mu)
        for _k in range(K):
            mu = descent_step(mu, x_t, st.w_gen, st.pi_obs, st.pi_top, st.pi)

        z = readout_step(st.z, mu, x_t, st.w_gen)

        # final per-dim errors (used by plasticity, precisions, and F)
        e0f = [x_t[i] - _dot(st.w_gen[i], mu) for i in range(N)]
        e1f = [mu[i] - st.pi[i] for i in range(N)]

        # three-factor surprise-gated Hebbian on the generative matrix
        for i in range(N):
            factor = st.eta_w * surprise * st.pi_obs[i] * e0f[i]
            row = st.w_gen[i]
            for j in range(N):
                row[j] += factor * mu[j]
        st.w_gen = spectral_clamp(st.w_gen, W_SPECTRAL_MAX)

        # online precision (inverse-variance) updates, clipped to [PI_MIN, PI_MAX]
        for i in range(N):
            st.pi_obs[i] = _clip(
                (1.0 - RHO_P) * st.pi_obs[i] + RHO_P / (e0f[i] ** 2 + EPS),
                PI_MIN,
                PI_MAX,
            )
            st.pi_top[i] = _clip(
                (1.0 - RHO_P) * st.pi_top[i] + RHO_P / (e1f[i] ** 2 + EPS),
                PI_MIN,
                PI_MAX,
            )

        # free energy (diagnostic / D-1 surfaceable)
        free_energy = (
            0.5 * sum(st.pi_obs[i] * e0f[i] ** 2 for i in range(N))
            + 0.5 * sum(st.pi_top[i] * e1f[i] ** 2 for i in range(N))
            - 0.5 * sum(math.log(st.pi_obs[i]) + math.log(st.pi_top[i]) for i in range(N))
        )

        # D-8: slow, bounded allostatic pi drift toward the EMA of z.
        for i in range(N):
            st.z_ema[i] = (1.0 - Z_EMA_RATE) * st.z_ema[i] + Z_EMA_RATE * z[i]
            st.pi[i] = (1.0 - RHO_PI) * st.pi[i] + RHO_PI * st.z_ema[i]

        st.mu = mu
        st.z = z
        st.free_energy = free_energy
        self.last_e0 = e0f
        self.last_e1 = e1f
        return z, free_energy

    # -- observability ---------------------------------------------------------
    def diagnostics(self) -> dict[str, float]:
        """Lightweight scalar diagnostics (no contract coupling at P0)."""
        return {
            "free_energy": self.state.free_energy,
            "mean_abs_e0": sum(abs(v) for v in self.last_e0) / N,
            "mean_abs_e1": sum(abs(v) for v in self.last_e1) / N,
        }


def _clip(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    if value < low:
        return low
    if value > high:
        return high
    return value
