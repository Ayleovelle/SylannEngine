"""v2.6.0 T6 契约：情绪标签影子拼入 prompt fragment（Gate B，behind takeover）。

对照 docs/design/v26-upgrade-path.md §2 T6。守护：
- takeover on ⇒ fragment 追加 ``[sylanne_affect_label] emotion=<label>`` 段（append-only，
  canonical 无预算/无驱逐，§6.2 作废）；
- takeover off ⇒ fragment 不含该段（字节一致）；
- 与既有 ``[sylanne_computation_emotion]``（pad.label 侧）**共存**，不替换。
"""

from __future__ import annotations

from sylanne_core.compute.kernel import AlphaKernel, AlphaKernelEvent
from sylanne_core.config import build_profile

_TRAITS = {"warmth_bias": 0.7, "expression_drive_trait": 0.6, "curiosity": 0.6}


def _fragment(*, affect: bool, takeover: bool) -> tuple[str, str | None]:
    kw: dict[str, object] = {"profile": build_profile("lite")}
    if affect:
        kw["affect_enabled"] = True
    if takeover:
        kw["affect_takeover"] = True
    kernel = AlphaKernel.boot("t6", **kw)
    kernel.computation.apply_personality(_TRAITS)
    for i in range(4):
        kernel.tick(AlphaKernelEvent(text="你好呀好开心", now=float(i + 1), confidence=0.7))
    frag = kernel.surface()["host_payload"].get("prompt_fragment", "")
    return frag, kernel.affect_label_shadow()


class TestFragmentSplice:
    def test_label_in_fragment_when_takeover(self) -> None:
        frag, label = _fragment(affect=True, takeover=True)
        assert label is not None
        assert "[sylanne_affect_label]" in frag
        assert f"emotion={label}" in frag

    def test_label_absent_when_takeover_off(self) -> None:
        # affect shadow on but takeover off -> fragment byte-identical (no label seg).
        frag, _ = _fragment(affect=True, takeover=False)
        assert "[sylanne_affect_label]" not in frag

    def test_label_absent_when_affect_off(self) -> None:
        frag, label = _fragment(affect=False, takeover=False)
        assert label is None
        assert "[sylanne_affect_label]" not in frag

    def test_coexists_with_existing_emotion_fragment(self) -> None:
        # The new label segment does not replace the pre-existing emotion fragment.
        frag, _ = _fragment(affect=True, takeover=True)
        assert "[sylanne_computation_emotion]" in frag
        assert "[sylanne_affect_label]" in frag
