"""v2.6.0 T3-silence 契约：真墙钟沉默 + 接入**活跃** ResonanceSpine 表达路径。

对照 docs/design/v26-upgrade-path.md §2 T3-SILENCE。守护：
- 纯方法：wall_silence_seconds 不封顶 / 未播种→0 / read-then-mark 序；classify 激活死代码；
- 接线必须触达 **live** ResonanceSpine._update_expression（只改 phase_transition 触达 0% 生产）：
  takeover on ⇒ 长墙钟沉默抬升 reach-out 驱动；takeover off ⇒ 沉默对驱动**零影响**（字节一致）。
"""

from __future__ import annotations

from sylanne_core.compute.phase_transition import PhaseTransitionExpression
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.void_calculus import SilenceTexture
from sylanne_core.config import build_profile

_TRAITS = {"extraversion": 0.5, "neuroticism": 0.5, "warmth_bias": 0.6}


class TestWallSilencePure:
    def test_unseeded_is_zero(self) -> None:
        pt = PhaseTransitionExpression()
        assert pt.wall_silence_seconds(5000.0) == 0.0     # never marked

    def test_uncapped_seconds(self) -> None:
        pt = PhaseTransitionExpression()
        pt.mark_activity(1000.0)
        assert pt.wall_silence_seconds(1000.0 + 7200.0) == 7200.0   # 2h, uncapped

    def test_backwards_clock_is_zero(self) -> None:
        pt = PhaseTransitionExpression()
        pt.mark_activity(1000.0)
        assert pt.wall_silence_seconds(900.0) == 0.0      # clock rewind -> 0

    def test_read_then_mark_ordering(self) -> None:
        pt = PhaseTransitionExpression()
        pt.mark_activity(100.0)
        silence = pt.wall_silence_seconds(400.0)          # read BEFORE mark
        pt.mark_activity(400.0)
        assert silence == 300.0
        assert pt.wall_silence_seconds(400.0) == 0.0      # after mark, same-now -> 0


class TestSilenceTextureActivated:
    def test_classify_returns_valid_textures(self) -> None:
        pt = PhaseTransitionExpression()
        pt.mark_activity(0.0)   # no-op (now<=0), stays unseeded
        pt.mark_activity(1000.0)
        # short + positive -> content; long + cold -> distant
        assert pt.classify_silence_texture(1000.0 + 60, last_valence=0.5) == SilenceTexture.CONTENT
        distant = pt.classify_silence_texture(
            1000.0 + 8000, last_valence=0.0, relationship_warmth=0.1
        )
        assert distant == SilenceTexture.DISTANT


class TestLiveSpineWiring:
    def _drive_after_gap(self, *, takeover: bool, gap: float) -> float:
        sp = ResonanceSpine(
            profile=build_profile("lite"), affect_enabled=True, affect_takeover=takeover
        )
        sp.apply_personality(_TRAITS)
        sp.process("在吗", timestamp=100.0)
        sp.process("在吗", timestamp=100.0 + gap)
        return sp._expression_drive

    def test_long_silence_raises_reachout_drive_when_takeover(self) -> None:
        long_gap = self._drive_after_gap(takeover=True, gap=7200.0)   # 2h silence
        short_gap = self._drive_after_gap(takeover=True, gap=1.0)     # 1s
        # More real-time silence must never REDUCE the reach-out drive, and here it
        # strictly raises it (the wall-clock trigger reaches the live bifurcation).
        assert long_gap >= short_gap
        assert long_gap > short_gap

    def test_silence_has_no_effect_when_off(self) -> None:
        # Byte-identical off: the drive must not depend on the silence gap at all
        # (proves the wall-clock trigger is fully gated).
        long_gap = self._drive_after_gap(takeover=False, gap=7200.0)
        short_gap = self._drive_after_gap(takeover=False, gap=1.0)
        assert long_gap == short_gap

    def test_silence_gated_off_when_affect_disabled(self) -> None:
        # red-team #2: takeover flag set but affect_dynamics_enabled False -> silence
        # must NOT fire (gate on the full predicate takeover AND affect_active, not
        # takeover alone). Construct the spine directly to bypass config validation.
        def drive(gap: float) -> float:
            sp = ResonanceSpine(
                profile=build_profile("lite"), affect_enabled=False, affect_takeover=True
            )
            sp.apply_personality(_TRAITS)
            sp.process("在吗", timestamp=100.0)
            sp.process("在吗", timestamp=100.0 + gap)
            return sp._expression_drive

        assert drive(7200.0) == drive(1.0)   # silence has zero effect (gated off)
