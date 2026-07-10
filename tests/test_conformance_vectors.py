"""AD-L1 一致性黄金向量锁（theoretical_spec.md §13.4，v0.2 版钉）。

这是标准的可证伪性所在：任何触碰 E 律纯函数常数/公式的改动都会打红此文件——
**这是特性**。要改常数：改动 + 本文件同步重钉 + spec §12 changelog 一条，三件同 commit
（"a future revision may re-pin them with a changelog entry, never silently"）。
容差 1e-9/分量（AD-L1 规定）。
"""

from __future__ import annotations

from sylanne_core.compute import affect_dynamics as ad
from sylanne_core.compute.affect_projection import project_appraisal

_T_STAR: dict[str, float] = {
    "warmth_bias": 0.6,
    "perception_acuity": 0.7,
    "curiosity": 0.7,
    "expression_drive_trait": 0.6,
    "relational_gravity": 0.7,
    "sovereignty_guard": 0.8,
    "inner_order": 0.6,
}
_E0_STAR = [0.20, 0.80, 0.55, 0.30, 0.45, 0.25, 0.50, 0.60]
_PHI_STAR = [1.0, 0.5, 0.0, 0.25, 1.0, 0.0, 0.75, 0.1]
_TOL = 1e-9


def _close(got: list[float], want: list[float]) -> None:
    assert len(got) == len(want)
    for i, (g, w) in enumerate(zip(got, want, strict=True)):
        assert abs(g - w) <= _TOL, f"dim{i}: got {g!r}, spec pins {w!r}"


class TestGoldenVectors:
    def test_equilibrium(self) -> None:
        _close(ad.equilibrium(_T_STAR, 0.5),
               [0.52, 0.40, 0.55, 0.35, 0.50, 0.28, 0.48, 0.52])
        _close(ad.equilibrium(_T_STAR, 0.9),
               [0.64, 0.40, 0.55, 0.35, 0.50, 0.28, 0.48, 0.52])

    def test_half_lives(self) -> None:
        base = [5400.0, 1800.0, 3600.0, 3780.0, 2400.0, 3000.0, 1500.0, 7200.0]
        _close(ad.half_lives(_T_STAR, [0.0] * 8), base)
        _close(ad.half_lives(_T_STAR, [2.0] * 8), [3.0 * h for h in base])  # 粘滞封顶

    def test_gain_vector(self) -> None:
        _close(ad.gain_vector(_T_STAR),
               [0.50, 0.50, 0.50, 0.61, 0.50, 0.50, 0.58, 0.50])

    def test_decay(self) -> None:
        eq = ad.equilibrium(_T_STAR, 0.5)
        h = ad.half_lives(_T_STAR, [0.0] * 8)
        _close(ad.decay(_E0_STAR, eq, h, 1800.0),
               [0.266015831685, 0.6, 0.55, 0.314056332564,
                0.470269822125, 0.260207381338, 0.488705505633, 0.587271713220])

    def test_project_appraisal(self) -> None:
        a_k, matched = project_appraisal(0.6, 0.7, 0.2, "撒娇")
        assert matched == "coax"
        _close(a_k, [0.54, 0.40, 0.60, -0.156, 0.084, 0.0, 0.38, 0.024])

    def test_saturating_update(self) -> None:
        a_k, _ = project_appraisal(0.6, 0.7, 0.2, "撒娇")
        _close(ad.saturating_update(_E0_STAR, a_k, ad.gain_vector(_T_STAR)),
               [0.416, 0.84, 0.685, 0.271452, 0.4731, 0.25, 0.6102, 0.6048])

    def test_plasticity_step(self) -> None:
        _close(ad.plasticity_step([0.5] * 8, 0.9, 0.5, _PHI_STAR),
               [0.5002, 0.5001, 0.5, 0.50005, 0.5002, 0.5, 0.50015, 0.50002])

    def test_pinned_constants(self) -> None:
        # 常数本体也钉住（spec §13.4：本版重钉须走 changelog）。
        assert ad._PLASTICITY_ALPHA == 0.0005
        assert ad._PHI_GAMMA == 0.6
        assert ad._Q_EMA_BETA == 0.1
        assert ad._GAIN_FLOOR == 0.05
        assert ad._SIGMA == 1.0 and ad._STICKY_CAP == 3.0
        assert ad._EQ_LO == 0.15 and ad._EQ_HI == 0.85
        assert ad._H_BASE_MIN == (90.0, 30.0, 60.0, 45.0, 40.0, 50.0, 25.0, 120.0)
