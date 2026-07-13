"""v2.6.0 T1 情感核 E 律纯函数行为契约（additive，不碰现有引擎状态）。

对照 docs/design/v26-affect-dynamics-design.md §2.2 / §3.3 / §8。守护：
- 饱和更新有界性（G∈(0,1]∧|a|≤1 ⇒ E∈[0,1]）+ 边界降幅消失；
- 墙钟衰减半衰期正确 + dt/NaN 守卫；
- 均衡值域内收 [0.15,0.85] + canonical trait 单调；
- 参数良定域断言（G/κ/μ/ρ）；
- 非有限输入消毒（F1/F4）。
"""

from __future__ import annotations

import math

from sylanne_core.compute.affect_dynamics import (
    N_DIMS,
    decay,
    equilibrium,
    gain_vector,
    half_lives,
    saturating_update,
    validate_gain,
    validate_scalar_params,
)

_I_WARMTH, _I_TENSION, _I_CURIOSITY, _I_EXPR = 0, 3, 4, 6


class TestSaturatingUpdate:
    def test_positive_raises_negative_lowers(self) -> None:
        e = [0.5] * N_DIMS
        up = saturating_update(e, [0.5] * N_DIMS, [1.0] * N_DIMS)
        assert all(u > 0.5 for u in up)
        down = saturating_update(e, [-0.5] * N_DIMS, [1.0] * N_DIMS)
        assert all(d < 0.5 for d in down)

    def test_increment_vanishes_at_bounds(self) -> None:
        top = saturating_update([1.0] * N_DIMS, [1.0] * N_DIMS, [1.0] * N_DIMS)
        assert all(abs(t - 1.0) < 1e-12 for t in top)
        bot = saturating_update([0.0] * N_DIMS, [-1.0] * N_DIMS, [1.0] * N_DIMS)
        assert all(abs(b) < 1e-12 for b in bot)

    def test_bounded_given_gain_le_1(self) -> None:
        es = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0, 0.2]
        for a_val in (-1.0, -0.3, 0.0, 0.7, 1.0):
            out = saturating_update(es, [a_val] * N_DIMS, [1.0] * N_DIMS)
            assert all(0.0 <= o <= 1.0 for o in out), (a_val, out)

    def test_nan_appraisal_neutralized(self) -> None:
        out = saturating_update([0.5] * N_DIMS, [float("nan")] * N_DIMS, [1.0] * N_DIMS)
        assert all(math.isfinite(o) for o in out)
        assert all(abs(o - 0.5) < 1e-12 for o in out)   # NaN → 0 幅度 → 不变


class TestDecay:
    def test_zero_and_negative_and_nan_dt_unchanged(self) -> None:
        e0, eq, h = [0.8] * N_DIMS, [0.3] * N_DIMS, [100.0] * N_DIMS
        assert decay(e0, eq, h, 0.0) == e0
        assert decay(e0, eq, h, -50.0) == e0
        assert decay(e0, eq, h, float("nan")) == e0     # F4：NaN 墙钟守卫

    def test_halfway_at_one_half_life(self) -> None:
        mid = decay([1.0] * N_DIMS, [0.0] * N_DIMS, [100.0] * N_DIMS, 100.0)
        assert all(abs(m - 0.5) < 1e-12 for m in mid)

    def test_converges_to_equilibrium(self) -> None:
        far = decay([1.0] * N_DIMS, [0.3] * N_DIMS, [10.0] * N_DIMS, 10000.0)
        assert all(abs(f - 0.3) < 1e-6 for f in far)


class TestParamDomain:
    def test_validate_gain(self) -> None:
        validate_gain([0.5] * N_DIMS)
        validate_gain([1.0] * N_DIMS)
        for bad in ([1.4] + [0.5] * 7, [0.0] + [0.5] * 7):
            try:
                validate_gain(bad)
            except ValueError:
                continue
            raise AssertionError(f"应对 {bad[0]} 抛 ValueError")

    def test_validate_scalar_params(self) -> None:
        validate_scalar_params(1.0, 0.5, 0.9)
        for k, m, r in ((1.5, 0.5, 0.5), (0.5, 1.0, 0.5), (0.5, 0.0, 0.5), (0.5, 0.5, 1.0)):
            try:
                validate_scalar_params(k, m, r)
            except ValueError:
                continue
            raise AssertionError(f"应对 ({k},{m},{r}) 抛 ValueError")

    def test_gain_vector_within_domain(self) -> None:
        for pa in (0.0, 0.5, 1.0):
            for ed in (0.0, 0.5, 1.0):
                validate_gain(gain_vector({"perception_acuity": pa, "expression_drive_trait": ed}))


class TestEquilibrium:
    def test_range_clamped(self) -> None:
        for t in ({}, {"warmth_bias": 1.0, "perception_acuity": 1.0}, {"warmth_bias": 0.0}):
            for rel in (0.0, 0.5, 1.0):
                assert all(0.15 <= x <= 0.85 for x in equilibrium(t, rel))

    def test_monotone_canonical_traits(self) -> None:
        warm_hi = equilibrium({"warmth_bias": 0.9}, 0.5)[_I_WARMTH]
        warm_lo = equilibrium({"warmth_bias": 0.1}, 0.5)[_I_WARMTH]
        assert warm_hi > warm_lo                        # warmth_bias↑ → warmth 基线↑
        tens_hi = equilibrium({"perception_acuity": 0.9}, 0.5)[_I_TENSION]
        tens_lo = equilibrium({"perception_acuity": 0.1}, 0.5)[_I_TENSION]
        assert tens_hi > tens_lo                        # perception_acuity↑ → tension 基线↑
        cur_hi = equilibrium({"curiosity": 0.9}, 0.5)[_I_CURIOSITY]
        cur_lo = equilibrium({"curiosity": 0.1}, 0.5)[_I_CURIOSITY]
        assert cur_hi > cur_lo                          # curiosity↑ → curiosity 基线↑

    def test_relationship_raises_warmth(self) -> None:
        assert equilibrium({}, 0.9)[_I_WARMTH] > equilibrium({}, 0.1)[_I_WARMTH]


class TestHalfLives:
    def test_positive_and_perception_lengthens_tension(self) -> None:
        low = half_lives({"perception_acuity": 0.0})
        high = half_lives({"perception_acuity": 1.0})
        assert all(h > 0 for h in low) and all(h > 0 for h in high)
        assert high[_I_TENSION] > low[_I_TENSION]

    def test_scarload_stickiness_capped(self) -> None:
        base = half_lives(None, scarload=[0.0] * N_DIMS)
        huge = half_lives(None, scarload=[100.0] * N_DIMS)
        for i in range(N_DIMS):
            assert abs(huge[i] - base[i] * 3.0) < 1e-6   # 封顶 ×3
