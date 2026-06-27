"""Tests for sylanne_core.compute.computation_spine module."""

import time

from sylanne_core.compute.computation_spine import CircuitBreaker, ComputationSpine


class TestCircuitBreaker:
    def test_initially_closed(self):
        cb = CircuitBreaker(threshold=3)
        assert cb.is_open() is False

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(threshold=3, cooldown=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is True

    def test_fallback_returns_last_good(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_success({"result": "ok"})
        cb.record_failure()
        cb.record_failure()
        assert cb.fallback() == {"result": "ok"}

    def test_success_resets(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure()
        cb.record_success("ok")
        cb.record_failure()
        assert cb.is_open() is False


class TestComputationSpine:
    def test_init(self):
        spine = ComputationSpine()
        assert spine._tick_count == 0

    def test_process_basic(self):
        spine = ComputationSpine()
        result = spine.process("hello", time.time())
        assert isinstance(result, dict)
        assert "emotion" in result or "route" in result or result == {}

    def test_process_empty_text(self):
        spine = ComputationSpine()
        result = spine.process("", time.time())
        assert isinstance(result, dict)

    def test_process_tolerates_non_dict_assessment(self):
        # A non-dict assessment must not crash — it would AttributeError early at the
        # cache-signature `assessment.items()` (before the apply_assessment guard).
        spine = ComputationSpine()
        for bad in (["hurt"], "angry", 42):
            result = spine.process("在吗", time.time(), assessment=bad)
            assert isinstance(result, dict)

    def test_apply_personality(self):
        spine = ComputationSpine()
        traits = {
            "expression_drive_trait": 0.6,
            "perception_acuity": 0.5,
            "boundary_permeability": 0.5,
            "inner_order": 0.5,
            "relational_gravity": 0.5,
        }
        spine.apply_personality(traits)
        assert spine._personality["expression_drive_trait"] == 0.6

    def test_to_dict_from_dict(self):
        spine = ComputationSpine()
        spine.process("test", time.time())
        data = spine.to_dict()
        assert isinstance(data, dict)
        spine2 = ComputationSpine()
        spine2.from_dict(data)
        assert spine2._tick_count == spine._tick_count

    def test_multiple_process(self):
        spine = ComputationSpine()
        now = time.time()
        for i in range(5):
            spine.process(f"message {i}", now + i)
        assert spine._tick_count == 5

    def test_express(self):
        spine = ComputationSpine()
        spine.process("hello", time.time())
        result = spine.express()
        assert isinstance(result, dict)
