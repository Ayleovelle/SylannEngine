"""v2.6.0 T4 记忆-情感耦合原语契约（纯函数、零调用点）。

对照 docs/design/v26-upgrade-path.md §2 T4。守护：
- 余弦相似度性质（自匹配=1、正交=0、零范数→0、长度不一致抛）；
- 传染凸混合保界 [0,1] + κ=0/1 端点语义 + 长度不一致抛；
- κ 是人格函数（红队 memory #1）：值域 (0,1]、随共情单调、过良定域断言。
"""

from __future__ import annotations

import math

import pytest

from sylanne_core.compute.memory_coupling import (
    N_DIMS,
    contagion_blend,
    contagion_kappa,
    emotion_match,
)


class TestEmotionMatch:
    def test_self_match_is_one(self) -> None:
        e = [0.1, 0.5, 0.9, 0.3, 0.2, 0.7, 0.4, 0.6]
        assert abs(emotion_match(e, e) - 1.0) < 1e-12

    def test_orthogonal_is_zero(self) -> None:
        a = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        assert abs(emotion_match(a, b)) < 1e-12

    def test_zero_norm_returns_zero(self) -> None:
        assert emotion_match([0.0] * N_DIMS, [0.5] * N_DIMS) == 0.0

    def test_nonfinite_sanitised(self) -> None:
        a = [float("nan"), 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        assert math.isfinite(emotion_match(a, [0.5] * N_DIMS))

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            emotion_match([0.1, 0.2], [0.1, 0.2, 0.3])


class TestContagionBlend:
    def test_convex_bounds(self) -> None:
        e = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 0.5, 0.3]
        m = [1.0, 0.8, 0.6, 0.4, 0.2, 0.0, 0.5, 0.7]
        for k in (0.0, 0.25, 0.5, 0.75, 1.0):
            out = contagion_blend(e, m, k)
            assert all(0.0 <= x <= 1.0 for x in out), (k, out)

    def test_endpoints(self) -> None:
        e = [0.2] * N_DIMS
        m = [0.9] * N_DIMS
        assert contagion_blend(e, m, 0.0) == pytest.approx(e)   # ignore memory
        assert contagion_blend(e, m, 1.0) == pytest.approx(m)   # fully adopt

    def test_out_of_range_kappa_clamped(self) -> None:
        e, m = [0.3] * N_DIMS, [0.7] * N_DIMS
        assert contagion_blend(e, m, 5.0) == pytest.approx(m)     # k>1 -> 1
        assert contagion_blend(e, m, -2.0) == pytest.approx(e)    # k<0 -> 0

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            contagion_blend([0.1, 0.2], [0.1, 0.2, 0.3], 0.5)


class TestContagionKappa:
    def test_within_domain(self) -> None:
        for rg in (0.0, 0.5, 1.0):
            for ag in (0.0, 0.5, 1.0):
                k = contagion_kappa({"relational_gravity": rg, "agreeableness": ag})
                assert 0.0 < k <= 1.0

    def test_monotone_in_empathy(self) -> None:
        lo = contagion_kappa({"relational_gravity": 0.1, "agreeableness": 0.1})
        hi = contagion_kappa({"relational_gravity": 0.9, "agreeableness": 0.9})
        assert hi > lo

    def test_empty_traits_neutral(self) -> None:
        assert 0.0 < contagion_kappa(None) <= 1.0
