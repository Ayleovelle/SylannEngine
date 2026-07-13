"""v2.6.0 T5 契约：慢通道（poignancy→反思→锚回弹 macro 漂移，Gate C，默认关）。

对照 docs/design/v26-upgrade-path.md §2 T5。守护：
- 纯函数：漏桶泄漏 / 反思触发（阈+墙钟冷却）/ 锚回弹漂移 / scarload 自愈 / 良定域；
- SlowChannel：累积→越阈触发→有界锚回弹漂移；**原子性**（提交异常从环回滚，无半变异）；
- 接活跃 ResonanceSpine：开 vs 关 同一驱动 → 特质因反思**发散**；关时反思计数 0；
- TraitMemory.anchor 不可变、macro 漂移朝它回弹。
"""

from __future__ import annotations

import math

import pytest

from sylanne_core.compute import affect_dynamics as ad
from sylanne_core.compute import personality as personality_mod
from sylanne_core.compute.personality import EMBODIMENT_TRAITS, TraitMemory
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.slow_channel import SlowChannel
from sylanne_core.config import build_profile

_TRAITS = {"warmth_bias": 0.6, "expression_drive_trait": 0.6, "perception_acuity": 0.6}


def _fresh_traits() -> dict[str, TraitMemory]:
    return {n: TraitMemory(0.5) for n in EMBODIMENT_TRAITS}


class TestPureFunctions:
    def test_poignancy_leaky_bucket(self) -> None:
        assert ad.poignancy_update(10.0, 0.0, 0.1) == pytest.approx(9.0)  # pure leak
        assert ad.poignancy_update(0.0, 5.0, 0.1) == pytest.approx(5.0)  # pure inflow
        assert ad.poignancy_update(-3.0, -1.0, 0.1) == 0.0  # floored at 0

    def test_reflection_ready(self) -> None:
        assert ad.reflection_ready(3.5, 3.0, 1000.0, 0.0, 1800.0) is True  # first (no cooldown)
        assert ad.reflection_ready(3.5, 3.0, 1000.0, 900.0, 1800.0) is False  # in cooldown
        assert ad.reflection_ready(3.5, 3.0, 3000.0, 900.0, 1800.0) is True  # cooldown passed
        assert ad.reflection_ready(2.0, 3.0, 3000.0, 0.0, 1800.0) is False  # below threshold

    def test_drift_step_anchor_rebound(self) -> None:
        # No drive, value above anchor -> pulled back toward anchor (negative).
        assert ad.drift_step(0.5, 0.9, 0.0, 0.3, 0.2) == pytest.approx(-0.08)
        # Value at anchor, positive direction -> pure drift.
        assert ad.drift_step(0.5, 0.5, 1.0, 0.3, 0.2) == pytest.approx(0.3)

    def test_scarload_decay(self) -> None:
        assert ad.scarload_decay([1.0] * 8, 0.1) == pytest.approx([0.9] * 8)

    def test_q_dc(self) -> None:
        assert ad.q_dc(0.8) == pytest.approx(0.8)
        assert ad.q_dc(float("nan")) == pytest.approx(0.5)

    def test_poignancy_magnitude_nonneg(self) -> None:
        assert ad.poignancy_magnitude([0.0] * 8) == 0.0
        assert ad.poignancy_magnitude([0.5] * 8) > 0.0
        assert math.isfinite(ad.poignancy_magnitude([float("nan")] * 8))

    def test_validate_slowchannel_params(self) -> None:
        ad.validate_slowchannel_params(3.0, 0.1, 0.3, 0.2, 1800.0)
        for bad in [
            (-1.0, 0.1, 0.3, 0.2, 60.0),
            (3.0, 1.0, 0.3, 0.2, 60.0),
            (3.0, 0.1, 0.0, 0.2, 60.0),
            (3.0, 0.1, 0.3, 0.2, -1.0),
        ]:
            with pytest.raises(ValueError):
                ad.validate_slowchannel_params(*bad)


class TestSlowChannel:
    def test_reflection_fires_and_drifts_within_cap(self) -> None:
        sc = SlowChannel(active=True)
        traits = _fresh_traits()
        for _ in range(60):
            sc.observe([0.8, 0.6, 0.7, 0.2, 0.3, 0.1, 0.9, 0.1])
        assert sc.ready(5000.0)
        assert sc.maybe_reflect(traits, now=5000.0, drift_tick=100) is True
        moved = [n for n, tm in traits.items() if abs(tm.value - 0.5) > 1e-9]
        assert moved, "no trait drifted on reflection"
        # Bounded by the drift cap; anchors stay put (immutable origin).
        total = sum(abs(tm.value - 0.5) for tm in traits.values())
        assert total <= 0.05 + 1e-9
        assert all(tm.anchor == 0.5 for tm in traits.values())
        assert sc.status()["reflection_count"] == 1

    def test_inactive_is_noop(self) -> None:
        sc = SlowChannel(active=False)
        traits = _fresh_traits()
        for _ in range(60):
            sc.observe([0.9] * 8)
        assert sc.maybe_reflect(traits, now=5000.0, drift_tick=1) is False
        assert all(tm.value == 0.5 for tm in traits.values())

    def test_atomic_rollback_on_commit_failure(self, monkeypatch) -> None:
        sc = SlowChannel(active=True)
        traits = _fresh_traits()
        for _ in range(60):
            sc.observe([0.8, 0.6, 0.7, 0.2, 0.3, 0.1, 0.9, 0.1])

        def boom(*_a: object, **_k: object) -> None:
            # mutate one trait THEN raise, to prove the rollback restores it
            traits["inner_order"].value = 0.123
            raise RuntimeError("drift commit blew up")

        monkeypatch.setattr(personality_mod, "compute_embodiment_drift", boom)
        assert sc.maybe_reflect(traits, now=5000.0, drift_tick=1) is False  # fail-closed
        # Half-mutation must be rolled back from the ring snapshot.
        assert all(tm.value == 0.5 for tm in traits.values())
        # Poignancy/pending retained for retry (not cleared on failure).
        assert sc.status()["poignancy"] > 0.0

    def test_rollback_last_undoes_committed_reflection(self) -> None:
        sc = SlowChannel(active=True)
        traits = _fresh_traits()
        for _ in range(60):
            sc.observe([0.8, 0.6, 0.7, 0.2, 0.3, 0.1, 0.9, 0.1])
        sc.maybe_reflect(traits, now=5000.0, drift_tick=1)
        assert any(tm.value != 0.5 for tm in traits.values())
        assert sc.rollback_last(traits) is True
        assert all(tm.value == pytest.approx(0.5) for tm in traits.values())


class TestAnchorPersistenceGating:
    def test_anchor_absent_by_default(self) -> None:
        # Byte-identical legacy snapshot: no 'anchor' key when the slow channel is off.
        tm = TraitMemory(0.5)
        assert "anchor" not in tm.to_dict()

    def test_anchor_present_when_persisting(self) -> None:
        tm = TraitMemory(0.5, persist_anchor=True)
        tm.value = 0.7  # drift value; anchor stays at origin
        d = tm.to_dict()
        assert d["anchor"] == pytest.approx(0.5)
        rt = TraitMemory.from_dict(d)
        assert rt.anchor == pytest.approx(0.5) and rt._persist_anchor is True

    def test_spine_embodiment_dicts_byte_identical_off(self) -> None:
        # A spine with the slow channel OFF must serialize embodiment traits with no
        # 'anchor' key (the whole point of gating it — red-team #4).
        off = ResonanceSpine(profile=build_profile("lite"), affect_slowchannel=False)
        for tm in off._embodiment_traits.values():
            assert "anchor" not in tm.to_dict()
        on = ResonanceSpine(profile=build_profile("lite"), affect_slowchannel=True)
        for tm in on._embodiment_traits.values():
            assert "anchor" in tm.to_dict()


class TestSpineIntegration:
    def _run(self, *, slowchannel: bool) -> ResonanceSpine:
        sp = ResonanceSpine(profile=build_profile("lite"), affect_slowchannel=slowchannel)
        sp.apply_personality(_TRAITS)
        for t in range(12):
            a = {
                "valence": 0.7,
                "arousal": 0.7,
                "wound_risk": 0.6,
                "intent": "生气",
                "confidence": 0.9,
            }
            sp.process("你这样让我好难过", timestamp=float((t + 1) * 200), assessment=a)
        return sp

    def test_slowchannel_reflection_fires_at_spine(self) -> None:
        sp = self._run(slowchannel=True)
        assert sp._slow_channel.status()["reflection_count"] >= 1

    def test_slowchannel_diverges_from_off(self) -> None:
        on = self._run(slowchannel=True)
        off = self._run(slowchannel=False)
        assert off._slow_channel.status()["reflection_count"] == 0
        on_vals = {n: tm.value for n, tm in on._embodiment_traits.items()}
        off_vals = {n: tm.value for n, tm in off._embodiment_traits.items()}
        # Same drive; only the slow channel's macro reflection differs -> traits diverge.
        assert any(abs(on_vals[n] - off_vals[n]) > 1e-6 for n in on_vals)
