"""v2.6.0 T3 契约：E 律**夺权**（Gate B，behind affect_takeover，默认关）。

对照 docs/design/v26-upgrade-path.md §2 T3。守护：
- takeover off ⇒ 影子语义不变、``apply_affect_takeover`` 返回 False、base 不被 E 律写；
- takeover on ⇒ decay 在 step 顶部写**权威 base**（settle 先于事件，e-core #2）、快通道
  ``apply_affect_takeover`` 写 base 并返回 True（替代手写意图规则）；
- fail-closed（assessor #2）：增益越界/投影异常 ⇒ 夺权返回 False，回落遗留手写规则，base 不崩；
- 迁移：夺权 on vs off 的 observe() **不同**（这是**有意的行为变更**，非零变更）；
- 配置贯通：SylanneConfig(affect_takeover=True) → scar_state._affect_takeover。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sylanne_core.compute import affect_dynamics
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.scar_algebra import ScarredState
from sylanne_core.config import SylanneConfig, build_profile

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
        st.base = [0.9] * 8  # far from equilibrium
        st._e_last_wall_ts = 100.0
        st._affect_decay(100.0 + 1e7)  # huge silence gap
        eq_native = affect_dynamics.from_unit_interval(affect_dynamics.equilibrium(_TRAITS, 0.5))
        for i in range(8):
            assert abs(st.base[i] - eq_native[i]) < 1e-3, i

    def test_shadow_mode_decay_leaves_base_untouched(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=False)
        st.base = [0.9] * 8
        st._e_last_wall_ts = 100.0
        st._affect_decay(100.0 + 1e7)
        assert st.base == [0.9] * 8  # base never touched in shadow mode
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
        st.set_affect_params(_TRAITS, takeover=False)  # shadow mode
        st.step([0.1] * 8, timestamp=100.0)
        before = list(st.base)
        assert st.apply_affect_takeover(0.9, 0.7, 0.1, "撒娇") is False
        assert st.base == before  # E-law did NOT write base

    def test_fail_closed_on_bad_gain(self, monkeypatch) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True)
        st.step([0.1] * 8, timestamp=100.0)
        before = list(st.base)
        # Force an out-of-range gain so validate_gain raises inside the takeover.
        monkeypatch.setattr(affect_dynamics, "gain_vector", lambda _t: [2.0] * 8)
        assert st.apply_affect_takeover(0.9, 0.7, 0.1, "撒娇") is False  # fail-closed
        assert st.base == before  # base untouched


class TestDecayAtTopOrdering:
    def test_event_survives_long_silence(self) -> None:
        # e-core #2: decay is applied at the TOP of step(), BEFORE event evolution.
        # After a huge silence gap the prior base has fully decayed toward equilibrium,
        # so the resulting base must still be SHAPED BY THE EVENT (different events ->
        # different base). If decay ran AFTER event evolution (the forbidden order), the
        # event response would be pulled back to ~equilibrium and both would collapse
        # to the same value — this test would then fail, catching the reintroduced bug.
        def run(event: list[float]) -> list[float]:
            st = ScarredState(n_dims=8, affect_enabled=True)
            st.set_affect_params(_TRAITS, takeover=True)
            st.step([0.0] * 8, timestamp=1000.0)  # seed the affect clock
            st.step(event, timestamp=1000.0 + 1e7)  # ~116 days later + an event
            return list(st.base)

        b_pos = run([0.9] * 8)
        b_neg = run([-0.9] * 8)
        assert any(abs(a - b) > 1e-3 for a, b in zip(b_pos, b_neg, strict=True)), (
            "event erased by silence -> decay ran after event evolution (wrong order)"
        )


class TestSpineTakeover:
    def _spine(self, *, takeover: bool) -> ResonanceSpine:
        sp = ResonanceSpine(
            profile=build_profile("lite"), affect_enabled=True, affect_takeover=takeover
        )
        sp.apply_personality(_TRAITS)
        return sp

    def _drive(self, sp: ResonanceSpine) -> None:
        for t in range(8):
            a = {
                "valence": 0.6,
                "arousal": 0.6,
                "wound_risk": 0.1,
                "intent": "撒娇",
                "confidence": 0.8,
            }
            sp.process("抱抱我嘛", timestamp=float(t + 1), assessment=a)

    def test_takeover_path_runs_at_spine(self) -> None:
        sp = self._spine(takeover=True)
        self._drive(sp)
        # The takeover branch actually wrote base (its diagnostic stamp is "takeover").
        assert sp._engine.scar_state._last_affect_shadow is not None
        assert sp._engine.scar_state._last_affect_shadow["source"] == "takeover"

    def test_spine_fail_closed_falls_to_handrules(self, monkeypatch) -> None:
        # assessor #2: when the E-law takeover errors mid-turn (bad gain), the spine's
        # `if not took_over:` guard must fall through to the LEGACY path for that turn —
        # exercised end-to-end through process(), not just the isolated ScarredState unit.
        sp = self._spine(takeover=True)
        monkeypatch.setattr(affect_dynamics, "gain_vector", lambda _t: [2.0] * 8)  # invalid
        self._drive(sp)
        scar = sp._engine.scar_state
        # Takeover never completed (its diagnostic stamp would be "takeover"); legacy ran.
        last = scar._last_affect_shadow
        assert last is None or last.get("source") != "takeover"
        assert all(-1.0 <= x <= 1.0 for x in scar.base)  # no crash, base still valid

    def test_takeover_changes_observed_emotion_vs_legacy(self) -> None:
        # Intended behaviour change (NOT byte-identical): same drive, on vs off,
        # must diverge in the observed base (documents the migration delta).
        on = self._spine(takeover=True)
        off = self._spine(takeover=False)
        self._drive(on)
        self._drive(off)
        obs_on = on._engine.scar_state.observe()
        obs_off = off._engine.scar_state.observe()
        assert any(abs(obs_on[f"dim_{d}"] - obs_off[f"dim_{d}"]) > 1e-6 for d in range(8)), (
            "takeover produced no observable delta vs legacy"
        )


class TestPelExclusion:
    def test_takeover_inert_under_pel(self) -> None:
        # red-team #1: PEL owns base evolution (its readout overwrites base each tick),
        # so the E-law takeover must be INERT under PEL — else decay is dead on arrival.
        st = ScarredState(n_dims=8, pel_enabled=True, affect_enabled=True)
        st.set_pel_priors({"openness": 0.6, "neuroticism": 0.6, "extraversion": 0.5})
        st.set_affect_params(_TRAITS, takeover=True)
        assert st.pel_active()
        st.step([0.1] * 8, timestamp=100.0)
        before = list(st.base)
        assert st.apply_affect_takeover(0.9, 0.7, 0.1, "撒娇") is False  # inert under PEL
        assert st.base == before


class TestConfigValidation:
    def test_takeover_requires_affect_enabled(self) -> None:
        with pytest.raises(ValueError):
            SylanneConfig(affect_takeover=True)  # affect_dynamics_enabled defaults False

    def test_takeover_incompatible_with_pel(self) -> None:
        with pytest.raises(ValueError):
            SylanneConfig(affect_takeover=True, affect_dynamics_enabled=True, pel_core_enabled=True)

    def test_valid_takeover_config_accepted(self) -> None:
        SylanneConfig(affect_takeover=True, affect_dynamics_enabled=True)  # no raise


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
