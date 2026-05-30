"""Tests for sylanne_core.compute.kernel module."""

from sylanne_core.compute.kernel import AlphaKernel, AlphaKernelEvent


class TestKernelBoot:
    def test_boot_fresh(self):
        kernel = AlphaKernel.boot("test_session")
        assert kernel.session_key == "test_session"
        assert kernel.turns == 0
        assert kernel.body.pulse.beat == 0.0

    def test_boot_with_legacy_none(self):
        kernel = AlphaKernel.boot("s1", legacy=None)
        assert kernel.turns == 0


class TestKernelTick:
    def test_tick_increments_turns(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hello", now=1.0))
        assert kernel.turns == 1

    def test_tick_returns_surface(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        assert "surface" in result
        assert "decision" in result
        assert "guard" in result

    def test_tick_with_dict_event(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick({"text": "hello", "now": 1.0, "flags": ["safe"]})
        assert result["decision"]["action"] in {
            "wait", "explore", "express", "reach_out", "repair", "withdraw", "recover"
        }

    def test_tick_with_none_event(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(None)
        assert "surface" in result

    def test_multiple_ticks(self):
        kernel = AlphaKernel.boot("s1")
        for i in range(5):
            kernel.tick(AlphaKernelEvent(text=f"msg {i}", now=float(i + 1)))
        assert kernel.turns == 5

    def test_tick_exception_returns_fallback(self):
        from unittest.mock import patch

        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="setup", now=1.0))
        with patch(
            "sylanne_core.compute.computation_spine.ComputationSpine.process",
            side_effect=RuntimeError("boom"),
        ):
            result = kernel.tick(AlphaKernelEvent(text="crash", now=2.0))
        assert "surface" in result
        assert "decision" in result


class TestKernelDecision:
    def test_default_decision_is_wait(self):
        kernel = AlphaKernel.boot("s1")
        decision = kernel._decide()
        assert decision["action"] == "wait"

    def test_repair_decision(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.needs["need_repair"] = 0.5
        decision = kernel._decide()
        assert decision["action"] == "repair"

    def test_withdraw_decision(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.immunity.boundary_pressure = 0.9
        decision = kernel._decide()
        assert decision["action"] == "withdraw"

    def test_express_decision(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.needs["need_expression"] = 0.5
        decision = kernel._decide()
        assert decision["action"] == "express"


class TestKernelGuard:
    def test_guard_allows_by_default(self):
        kernel = AlphaKernel.boot("s1")
        decision = kernel._decide()
        guard = kernel._guard(decision)
        assert guard["allowed"] is True

    def test_guard_blocks_on_pause(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.immunity.paused = True
        decision = kernel._decide()
        guard = kernel._guard(decision)
        assert guard["allowed"] is False
        assert "user_pause" in guard["flags"]

    def test_guard_blocks_on_exhaustion(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.mortality.exhaustion = 0.9
        decision = kernel._decide()
        guard = kernel._guard(decision)
        assert guard["allowed"] is False
        assert "exhaustion" in guard["flags"]

    def test_guard_blocks_low_sovereignty(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.immunity.sovereignty = 0.3
        decision = {
            "action": "reach_out", "reason": "test",
            "reason_code": "test", "confidence": 0.5,
        }
        guard = kernel._guard(decision)
        assert guard["allowed"] is False


class TestKernelSnapshot:
    def test_snapshot_roundtrip(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hello", now=1.0))
        snap = kernel.snapshot()
        restored = AlphaKernel.restore(snap)
        assert restored.session_key == "s1"
        assert restored.turns == 1
        assert restored.body.pulse.beat == kernel.body.pulse.beat

    def test_restore_from_empty(self):
        kernel = AlphaKernel.restore({})
        assert kernel.session_key == "default"
        assert kernel.turns == 0

    def test_restore_preserves_personality(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        snap = kernel.snapshot()
        restored = AlphaKernel.restore(snap)
        assert restored.personality == kernel.personality


class TestKernelSurface:
    def test_surface_structure(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        surface = kernel.surface()
        assert "schema_version" in surface
        assert "body" in surface
        assert "decision" in surface
        assert "guard" in surface
        assert "workset" in surface
        assert "diagnostics" in surface

    def test_surface_session_key(self):
        kernel = AlphaKernel.boot("my_session")
        surface = kernel.surface()
        assert surface["session_key"] == "my_session"
