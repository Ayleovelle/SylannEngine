"""Tests for sylanne_core.compute.body module."""

import time

from sylanne_core.compute.body import AlphaBodyState


class TestBodyInit:
    def test_default_state(self):
        body = AlphaBodyState()
        assert body.pulse.beat == 0.0
        assert body.pulse.rhythm == 0.5
        assert body.immunity.sovereignty == 1.0
        assert body.immunity.paused is False
        assert body.needs["need_contact"] == 0.0

    def test_state_vector_dimensions(self):
        body = AlphaBodyState()
        vec = body.state_vector()
        assert len(vec) == 29

    def test_raw_state_vector_matches(self):
        body = AlphaBodyState()
        raw = body._raw_state_vector()
        rounded = body.state_vector()
        for key in raw:
            assert key in rounded


class TestBodyApply:
    def test_apply_increments_beat(self):
        body = AlphaBodyState()
        body.apply(text="hello", now=1.0)
        assert body.pulse.beat > 0.0

    def test_apply_with_hurt_flag(self):
        body = AlphaBodyState()
        body.apply(text="ouch", flags=["hurt"], now=1.0)
        assert body.wound.open > 0.0
        assert body.needs["need_repair"] > 0.0

    def test_apply_with_safe_flag(self):
        body = AlphaBodyState()
        body.apply(text="hi", flags=["safe"], now=1.0)
        assert body.bloodflow.warmth >= 0.4

    def test_apply_tracks_repetition(self):
        body = AlphaBodyState()
        body.apply(text="repeat", now=1.0)
        body.apply(text="repeat", now=2.0)
        assert body.nerve.repetition == 2

    def test_apply_stores_trace(self):
        body = AlphaBodyState()
        body.apply(text="hello world", now=1.0)
        assert len(body.memory["traces"]) == 1
        assert body.memory["traces"][0]["text"] == "hello world"

    def test_apply_pause_flag(self):
        body = AlphaBodyState()
        body.apply(text="", flags=["pause"], now=1.0)
        assert body.immunity.paused is True

    def test_apply_resume_flag(self):
        body = AlphaBodyState()
        body.immunity.paused = True
        body.apply(text="", flags=["resume"], now=2.0)
        assert body.immunity.paused is False

    def test_values_clamped(self):
        body = AlphaBodyState()
        for _ in range(50):
            body.apply(text="hurt", flags=["hurt"], now=time.time())
        assert body.wound.open <= 1.0
        assert body.pulse.strain <= 1.0


class TestPassiveDecay:
    def test_no_decay_for_tiny_elapsed(self):
        body = AlphaBodyState()
        body.immunity.cooldown = 0.5
        body._passive_decay(0.1)
        assert body.immunity.cooldown == 0.5

    def test_cooldown_decays_over_time(self):
        body = AlphaBodyState()
        body.immunity.cooldown = 0.8
        body._passive_decay(3600.0)
        assert body.immunity.cooldown < 0.8

    def test_fatigue_decays(self):
        body = AlphaBodyState()
        body.muscle.fatigue = 0.6
        body._passive_decay(3600.0)
        assert body.muscle.fatigue < 0.6

    def test_wound_heals(self):
        body = AlphaBodyState()
        body.wound.open = 0.5
        body._passive_decay(3600.0)
        assert body.wound.open < 0.5

    def test_budget_recovers(self):
        body = AlphaBodyState()
        body.immunity.interruption_budget = 0.3
        body._passive_decay(3600.0)
        assert body.immunity.interruption_budget > 0.3

    def test_decay_capped_at_4_hours(self):
        body = AlphaBodyState()
        body.immunity.cooldown = 1.0
        body._passive_decay(3600.0 * 4)
        val_4h = body.immunity.cooldown
        body.immunity.cooldown = 1.0
        body._passive_decay(3600.0 * 100)
        val_100h = body.immunity.cooldown
        assert val_4h == val_100h


class TestFromDict:
    def test_roundtrip(self):
        body = AlphaBodyState()
        body.apply(text="test", flags=["safe"], now=1.0)
        data = body.to_dict()
        restored = AlphaBodyState.from_dict(data)
        assert restored.pulse.beat == body.pulse.beat
        assert restored.bloodflow.warmth == body.bloodflow.warmth

    def test_ignores_extra_keys(self):
        data = {
            "pulse": {
                "beat": 5.0,
                "unknown_field": 99.0,
                "rhythm": 0.8,
                "strain": 0.1,
                "last_tick": 0.0,
            }
        }
        body = AlphaBodyState.from_dict(data)
        assert body.pulse.beat == 5.0

    def test_type_coercion(self):
        data = {"pulse": {"beat": "3.5", "rhythm": "0.7", "strain": "0.2", "last_tick": "1.0"}}
        body = AlphaBodyState.from_dict(data)
        assert body.pulse.beat == 3.5
        assert isinstance(body.pulse.beat, float)

    def test_invalid_subsystem_isolated(self):
        data = {
            "pulse": "not_a_dict",
            "bloodflow": {"warmth": 0.9, "circulation": 0.5, "memory_flow": 0.3},
        }
        body = AlphaBodyState.from_dict(data)
        assert body.pulse.beat == 0.0  # default
        assert body.bloodflow.warmth == 0.9

    def test_bool_coercion(self):
        data = {
            "immunity": {
                "boundary_pressure": 0.0,
                "sovereignty": 1.0,
                "interruption_budget": 1.0,
                "cooldown": 0.0,
                "paused": 1,
            }
        }
        body = AlphaBodyState.from_dict(data)
        assert body.immunity.paused is True

    def test_empty_dict(self):
        body = AlphaBodyState.from_dict({})
        assert body.pulse.rhythm == 0.5


class TestEventVector:
    def test_idle_event(self):
        body = AlphaBodyState()
        vec = body.event_vector(flags=["idle"])
        assert vec["idle"] == 1.0
        assert vec["has_text"] == 0.0

    def test_text_event(self):
        body = AlphaBodyState()
        vec = body.event_vector(text="hello", confidence=0.8)
        assert vec["has_text"] == 1.0
        assert vec["confidence"] == 0.8

    def test_elapsed_clamped(self):
        body = AlphaBodyState()
        vec = body.event_vector(elapsed=0.1)
        assert vec["elapsed"] == 1.0
        vec = body.event_vector(elapsed=100.0)
        assert vec["elapsed"] == 12.0


class TestMemory:
    def test_recall_empty(self):
        body = AlphaBodyState()
        assert body.recall_memory("anything") == []

    def test_recall_matches(self):
        body = AlphaBodyState()
        body.apply(text="python programming", now=1.0)
        body.apply(text="rust language", now=2.0)
        results = body.recall_memory("python")
        assert len(results) >= 1
        assert "python" in results[0]["text"]

    def test_trace_limit(self):
        body = AlphaBodyState()
        for i in range(60):
            body.apply(text=f"msg {i}", now=float(i + 1))
        assert len(body.memory["traces"]) <= 50
