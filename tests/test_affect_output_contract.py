"""v2.6.0 T2 契约：情感输出契约（E→标签）纯函数 + 迟滞 + kernel 诊断接线（Gate A）。

对照 docs/design/v26-upgrade-path.md §2 T2。守护：
- circumplex 量化 + LUT 映射（效价/唤醒两轴 9 词）；
- 逐维 Schmitt 迟滞：边界抖动 hold、决然跨越才切换、未知键→缺省；
- kernel：启用时 diagnostics 多出 ``affect_label_shadow`` 键、每 tick 至多推进一次；
  关闭时该键**不出现**（诊断字节一致）；标签只诊断、绝不进 prompt_fragment。
"""

from __future__ import annotations

from sylanne_core.compute.affect_output_contract import (
    EMOTION_LUT,
    HysteresisState,
    quantize,
    resolve_label,
)
from sylanne_core.compute.kernel import AlphaKernel, AlphaKernelEvent
from sylanne_core.config import build_profile


# 8 维单位区间向量构造器（维序：warmth0 arousal1 valence2 tension3 ...）。
def _e(valence: float, arousal: float) -> list[float]:
    v = [0.5] * 8
    v[2] = valence
    v[1] = arousal
    return v


class TestQuantizeLUT:
    def test_corners(self) -> None:
        assert resolve_label(_e(0.9, 0.9), None)[0] == "雀跃"  # +val +arousal
        assert resolve_label(_e(0.1, 0.1), None)[0] == "低落"  # -val -arousal
        assert resolve_label(_e(0.5, 0.5), None)[0] == "中性"
        assert resolve_label(_e(0.9, 0.1), None)[0] == "安然"  # +val -arousal

    def test_quantize_levels(self) -> None:
        assert quantize(_e(0.1, 0.1)) == (0, 0)
        assert quantize(_e(0.5, 0.5)) == (1, 1)
        assert quantize(_e(0.9, 0.9)) == (2, 2)

    def test_lut_covers_all_nine_cells(self) -> None:
        assert len(EMOTION_LUT) == 9
        assert all(isinstance(v, str) and v for v in EMOTION_LUT.values())


class TestHysteresis:
    def test_holds_near_boundary(self) -> None:
        prev = HysteresisState(key=(1, 1), label="中性")
        # valence 0.30: raw level 0 but margin |0.30-0.333|=0.033 < theta_h(0.08) -> HOLD at 1.
        label, state = resolve_label(_e(0.30, 0.5), prev)
        assert state.key == (1, 1)
        assert label == "中性"

    def test_switches_when_decisive(self) -> None:
        prev = HysteresisState(key=(1, 1), label="中性")
        # valence 0.20: margin |0.20-0.333|=0.133 >= theta_h -> switch valence level to 0.
        label, state = resolve_label(_e(0.20, 0.5), prev)
        assert state.key == (0, 1)
        assert label == "郁闷"

    def test_first_resolution_adopts_raw(self) -> None:
        label, state = resolve_label(_e(0.05, 0.95), None)
        assert state.key == (0, 2)
        assert label == "焦躁"


class TestKernelWiring:
    def _ticked(self, *, affect: bool) -> AlphaKernel:
        kw = {"profile": build_profile("lite")}
        if affect:
            kw["affect_enabled"] = True
        kernel = AlphaKernel.boot("t2", **kw)
        for i in range(4):
            kernel.tick(AlphaKernelEvent(text="你好呀", now=float(i + 1), confidence=0.6))
        return kernel

    def test_label_present_when_enabled(self) -> None:
        kernel = self._ticked(affect=True)
        assert kernel.affect_label_shadow() is not None
        diag = kernel.surface()["diagnostics"]
        assert "affect_label_shadow" in diag
        assert diag["affect_label_shadow"] == kernel.affect_label_shadow()

    def test_label_absent_when_disabled(self) -> None:
        kernel = self._ticked(affect=False)
        assert kernel.affect_label_shadow() is None
        assert "affect_label_shadow" not in kernel.surface()["diagnostics"]

    def test_label_never_reaches_prompt_fragment(self) -> None:
        kernel = self._ticked(affect=True)
        surface = kernel.surface()
        label = kernel.affect_label_shadow()
        assert label is not None
        # The label is diagnostic-only; it must not leak into the prompt fragment.
        fragment = surface["host_payload"].get("prompt_fragment", "")
        assert label not in fragment
