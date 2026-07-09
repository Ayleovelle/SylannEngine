"""v2.6.0 T1-completion 契约：E 律**影子**接线（Gate A）。

对照 docs/design/v26-upgrade-path.md §2 T1-COMPLETION。守护：
- flag off ⇒ 字节一致（影子从不初始化、base 与无 affect 运行逐元素相同）；
- flag on ⇒ 影子被填充且有限，但 base **绝不**被影子写动（parity：观测不变）；
- 快通道 appraisal 只动影子、返回命中意图诊断；墙钟衰减把影子拉向 Φ_eq；
- 持久化：``e_last_wall_ts`` 仅在启用时落盘，旧快照缺键回落 0.0；
- fail-closed：投影/增益异常被吞、绝不外逃主回合，base 完好（t1-audit #1）。
"""

from __future__ import annotations

import math

from sylanne_core.compute import affect_dynamics, affect_projection
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.scar_algebra import ScarredState
from sylanne_core.config import build_profile

_TSUNDERE: dict[str, float] = {
    "openness": 0.7,
    "neuroticism": 0.7,
    "extraversion": 0.4,
    "agreeableness": 0.3,
    "conscientiousness": 0.6,
    "warmth_bias": 0.6,
    "curiosity": 0.7,
    "sovereignty_guard": 0.8,
    "expression_drive_trait": 0.6,
    "perception_acuity": 0.7,
}

_EVENTS: list[list[float]] = [
    [0.3, 0.1, 0.2, -0.1, 0.2, -0.2, 0.1, 0.0],
    [-0.2, 0.4, -0.3, 0.5, 0.0, 0.3, -0.1, 0.2],
    [0.5, -0.2, 0.4, -0.3, 0.1, -0.4, 0.3, -0.1],
    [0.0, 0.2, 0.1, 0.1, -0.2, 0.0, 0.2, 0.1],
]


def _driven(state: ScarredState, base_ts: float = 100.0) -> ScarredState:
    """把同一组事件按递增墙钟喂进 state（每 300s 一步）。"""
    for i, ev in enumerate(_EVENTS):
        state.step(ev, timestamp=base_ts + i * 300.0)
    return state


class TestShadowNeverTouchesBase:
    def test_flag_off_shadow_never_initialised(self) -> None:
        off = ScarredState(n_dims=8, affect_enabled=False)
        _driven(off)
        assert off._affect_shadow_base is None
        assert off._last_affect_shadow is None
        assert off._e_last_wall_ts == 0.0   # affect clock never advanced when off

    def test_base_parity_on_vs_off(self) -> None:
        off = ScarredState(n_dims=8, affect_enabled=False)
        on = ScarredState(n_dims=8, affect_enabled=True)
        on.set_affect_params(_TSUNDERE, relationship=0.5)
        _driven(off)
        _driven(on)
        # The shadow path only reads base and writes _affect_shadow_base; base must
        # evolve identically (same seeded MLP, no shadow leak).
        assert on.base == off.base
        # ...but the shadow IS populated and finite when on.
        assert on._affect_shadow_base is not None
        assert all(math.isfinite(x) and -1.0 <= x <= 1.0 for x in on._affect_shadow_base)


class TestFastChannelAppraisalShadow:
    def test_appraisal_moves_shadow_not_base(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TSUNDERE)
        st.step(_EVENTS[0], timestamp=100.0)   # init shadow
        base_before = list(st.base)
        diag = st.apply_affect_appraisal_shadow(0.8, 0.6, 0.1, "撒娇")
        assert diag is not None
        assert diag["intent_class"] == "coax"
        assert st.base == base_before             # base untouched
        assert st._affect_shadow_base is not None
        assert diag["divergence_l2"] >= 0.0

    def test_disabled_returns_none(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=False)
        assert st.apply_affect_appraisal_shadow(0.5, 0.5, 0.0, "生气") is None

    def test_non_eight_dim_is_noop(self) -> None:
        st = ScarredState(n_dims=16, affect_enabled=True)
        st.set_affect_params(_TSUNDERE)
        st.step([0.1] * 16, timestamp=100.0)
        assert st._affect_shadow_base is None      # affect only for the 8-dim core
        assert st.apply_affect_appraisal_shadow(0.5, 0.5, 0.0, "撒娇") is None


class TestWallClockDecay:
    def test_shadow_decays_toward_equilibrium(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TSUNDERE, relationship=0.5)
        st.step(_EVENTS[0], timestamp=1000.0)          # init shadow, no decay yet
        # Push the shadow far from equilibrium, then let a huge silence gap decay it.
        st.apply_affect_appraisal_shadow(1.0, 1.0, 0.0, "分享")
        st.step([0.0] * 8, timestamp=1000.0 + 1e7)     # ~116 days of silence
        eq_native = affect_dynamics.from_unit_interval(
            affect_dynamics.equilibrium(_TSUNDERE, 0.5)
        )
        assert st._affect_shadow_base is not None
        for i in range(8):
            assert abs(st._affect_shadow_base[i] - eq_native[i]) < 1e-3, i

    def test_clock_advances_only_on_real_timestamp(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TSUNDERE)
        st.step(_EVENTS[0], timestamp=0.0)             # feedback-style, no clock
        assert st._e_last_wall_ts == 0.0
        st.step(_EVENTS[0], timestamp=500.0)
        assert st._e_last_wall_ts == 500.0


class TestPersistence:
    def test_wall_ts_persisted_only_when_enabled(self) -> None:
        on = ScarredState(n_dims=8, affect_enabled=True)
        on.set_affect_params(_TSUNDERE)
        on.step(_EVENTS[0], timestamp=777.0)
        assert on.to_dict()["e_last_wall_ts"] == 777.0

        off = ScarredState(n_dims=8, affect_enabled=False)
        off.step(_EVENTS[0], timestamp=777.0)
        assert "e_last_wall_ts" not in off.to_dict()   # byte-identical legacy snapshot

    def test_roundtrip_and_legacy_default(self) -> None:
        on = ScarredState(n_dims=8, affect_enabled=True)
        on.set_affect_params(_TSUNDERE)
        on.step(_EVENTS[0], timestamp=888.0)
        restored = ScarredState.from_dict(on.to_dict(), affect_enabled=True)
        assert restored._e_last_wall_ts == 888.0
        # Legacy snapshot (no key) → default 0.0, no crash.
        legacy = on.to_dict()
        del legacy["e_last_wall_ts"]
        assert ScarredState.from_dict(legacy, affect_enabled=True)._e_last_wall_ts == 0.0


class TestFailClosed:
    def test_projection_exception_swallowed_base_intact(self, monkeypatch) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TSUNDERE)
        st.step(_EVENTS[0], timestamp=100.0)
        base_before = list(st.base)

        def boom(*_a: object, **_k: object) -> object:
            raise RuntimeError("assessor projection blew up")

        monkeypatch.setattr(affect_projection, "project_appraisal", boom)
        # Must NOT raise; returns None; base untouched.
        assert st.apply_affect_appraisal_shadow(0.5, 0.5, 0.0, "撒娇") is None
        assert st.base == base_before

    def test_decay_exception_swallowed_in_step(self, monkeypatch) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TSUNDERE)
        st.step(_EVENTS[0], timestamp=100.0)
        base_before = list(st.base)

        def boom(*_a: object, **_k: object) -> object:
            raise RuntimeError("equilibrium blew up")

        monkeypatch.setattr(affect_dynamics, "equilibrium", boom)
        # step() must not propagate the shadow exception; base evolves normally.
        st.step(_EVENTS[1], timestamp=1000.0)
        assert st.base != base_before          # base still evolved (event applied)
        assert all(math.isfinite(x) for x in st.base)


class TestSpineIntegration:
    def _drive(self, spine: ResonanceSpine) -> ResonanceSpine:
        spine.apply_personality(_TSUNDERE)
        for t in range(12):
            assessment = None
            if t % 3 == 0:
                assessment = {
                    "valence": 0.3,
                    "arousal": 0.5,
                    "wound_risk": 0.1,
                    "intent": "撒娇",
                    "confidence": 0.7,
                }
            spine.process("你今天怎么样？", timestamp=float(t + 1), assessment=assessment)
        return spine

    def test_observe_parity_on_vs_off(self) -> None:
        off = self._drive(ResonanceSpine(profile=build_profile("lite"), affect_enabled=False))
        on = self._drive(ResonanceSpine(profile=build_profile("lite"), affect_enabled=True))
        obs_off = off._engine.scar_state.observe()
        obs_on = on._engine.scar_state.observe()
        for k in obs_off:
            assert obs_on[k] == obs_off[k], k    # base/sensitivity byte-identical
        # The live (Resonance) spine actually populated the shadow diagnostic.
        assert on._engine.scar_state._last_affect_shadow is not None
        assert on._engine.scar_state._affect_shadow_base is not None


class TestConfigThreading:
    """Lock the full config -> host -> runtime -> kernel -> spine -> scar_state path."""

    def test_flag_reaches_scar_state(self, tmp_path) -> None:
        from sylanne_core.compute.host import SylanneAlphaHost

        on = SylanneAlphaHost(
            root=str(tmp_path), session_key="on", profile=build_profile("lite"), affect_enabled=True
        )
        assert on.kernel.computation._engine.scar_state._affect_enabled is True
        off = SylanneAlphaHost(
            root=str(tmp_path), session_key="off", profile=build_profile("lite")
        )
        assert off.kernel.computation._engine.scar_state._affect_enabled is False
