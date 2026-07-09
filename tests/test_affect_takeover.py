"""v2.6.0 T3 契约：E 律**夺权**（Gate B，behind affect_v26_takeover，默认关）。

对照 docs/design/v26-upgrade-path.md §2 T3。守护：
- takeover off ⇒ 影子语义不变、``apply_affect_takeover`` 返回 False、base 不被 E 律写；
- takeover on ⇒ decay 在 step 顶部写**权威 base**（settle 先于事件，e-core #2）、快通道
  ``apply_affect_takeover`` 写 base 并返回 True（替代手写意图规则）；
- fail-closed（assessor #2）：增益越界/投影异常 ⇒ 夺权返回 False，回落遗留手写规则，base 不崩；
- 迁移：夺权 on vs off 的 observe() **不同**（这是**有意的行为变更**，非零变更）；
- 配置贯通：SylanneConfig(affect_v26_takeover=True) → scar_state._affect_takeover。
"""

from __future__ import annotations

from pathlib import Path

from sylanne_core.compute import affect_dynamics
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.scar_algebra import ScarredState
from sylanne_core.config import build_profile

_TRAITS: dict[str, float] = {
    "warmth_bias": 0.6,
    "expression_drive_trait": 0.6,
    "perception_acuity": 0.7,
    "curiosity": 0.7,
    "sovereignty_guard": 0.8,
    "neuroticism": 0.6,
    "extraversion": 0.4,
}


class TestDecayWritesBaseUnderTakeover:
    def test_takeover_decay_pulls_base_to_equilibrium(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True)
        st.base = [0.9] * 8                      # far from equilibrium
        st._e_last_wall_ts = 100.0
        st._affect_decay(100.0 + 1e7)            # huge silence gap
        eq_native = affect_dynamics.from_unit_interval(
            affect_dynamics.equilibrium(_TRAITS, 0.5)
        )
        for i in range(8):
            assert abs(st.base[i] - eq_native[i]) < 1e-3, i

    def test_shadow_mode_decay_leaves_base_untouched(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=False)
        st.base = [0.9] * 8
        st._e_last_wall_ts = 100.0
        st._affect_decay(100.0 + 1e7)
        assert st.base == [0.9] * 8              # base never touched in shadow mode
        assert st._affect_shadow_base is not None


class TestAppraisalTakeover:
    def test_takeover_writes_base_returns_true(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True)
        st.step([0.1] * 8, timestamp=100.0)
        before = list(st.base)
        assert st.apply_affect_takeover(0.9, 0.7, 0.1, "撒娇") is True
        assert st.base != before
        assert all(-1.0 <= x <= 1.0 for x in st.base)
        assert st._last_affect_shadow is not None
        assert st._last_affect_shadow["source"] == "takeover"

    def test_disabled_returns_false_and_leaves_base(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=False)   # shadow mode
        st.step([0.1] * 8, timestamp=100.0)
        before = list(st.base)
        assert st.apply_affect_takeover(0.9, 0.7, 0.1, "撒娇") is False
        assert st.base == before                        # E-law did NOT write base

    def test_fail_closed_on_bad_gain(self, monkeypatch) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True)
        st.step([0.1] * 8, timestamp=100.0)
        before = list(st.base)
        # Force an out-of-range gain so validate_gain raises inside the takeover.
        monkeypatch.setattr(affect_dynamics, "gain_vector", lambda _t: [2.0] * 8)
        assert st.apply_affect_takeover(0.9, 0.7, 0.1, "撒娇") is False   # fail-closed
        assert st.base == before                                          # base untouched


class TestSpineTakeover:
    def _spine(self, *, takeover: bool) -> ResonanceSpine:
        sp = ResonanceSpine(
            profile=build_profile("lite"), affect_enabled=True, affect_takeover=takeover
        )
        sp.apply_personality(_TRAITS)
        return sp

    def _drive(self, sp: ResonanceSpine) -> None:
        for t in range(8):
            a = {"valence": 0.6, "arousal": 0.6, "wound_risk": 0.1, "intent": "撒娇", "confidence": 0.8}
            sp.process("抱抱我嘛", timestamp=float(t + 1), assessment=a)

    def test_takeover_path_runs_at_spine(self) -> None:
        sp = self._spine(takeover=True)
        self._drive(sp)
        # The takeover branch actually wrote base (its diagnostic stamp is "takeover").
        assert sp._engine.scar_state._last_affect_shadow is not None
        assert sp._engine.scar_state._last_affect_shadow["source"] == "takeover"

    def test_takeover_changes_observed_emotion_vs_legacy(self) -> None:
        # Intended behaviour change (NOT byte-identical): same drive, on vs off,
        # must diverge in the observed base (documents the migration delta).
        on = self._spine(takeover=True)
        off = self._spine(takeover=False)
        self._drive(on)
        self._drive(off)
        obs_on = on._engine.scar_state.observe()
        obs_off = off._engine.scar_state.observe()
        assert any(
            abs(obs_on[f"dim_{d}"] - obs_off[f"dim_{d}"]) > 1e-6 for d in range(8)
        ), "takeover produced no observable delta vs legacy"


class TestConfigThreading:
    def test_takeover_flag_reaches_scar_state(self, tmp_path: Path) -> None:
        from sylanne_core.compute.host import SylanneAlphaHost

        host = SylanneAlphaHost(
            root=str(tmp_path),
            session_key="tk",
            profile=build_profile("lite"),
            affect_enabled=True,
            affect_takeover=True,
        )
        host.kernel.computation.apply_personality(_TRAITS)
        assert host.kernel.computation._engine.scar_state._affect_takeover is True
