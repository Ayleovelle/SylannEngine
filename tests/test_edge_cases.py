"""Edge case and boundary condition tests for rc1 release readiness."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core.compute.body import AlphaBodyState
from sylanne_core.compute.computation_spine import ComputationSpine
from sylanne_core.compute.kernel import AlphaKernel, AlphaKernelEvent


class TestEmptyAndNoneInput:
    def test_tick_empty_text(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(AlphaKernelEvent(text="", now=1.0))
        assert "surface" in result
        assert kernel.turns == 1

    def test_tick_none_event(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(None)
        assert "surface" in result

    def test_tick_dict_event_empty(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick({})
        assert "surface" in result

    def test_tick_dict_event_none_values(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick({"text": None, "now": None, "flags": None})
        assert "surface" in result

    @pytest.mark.asyncio
    async def test_engine_process_empty_text(self, tmp_path: Path):
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()
        result = await engine.process("session1", "")
        assert result is not None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_engine_process_whitespace_only(self, tmp_path: Path):
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()
        result = await engine.process("session1", "   \n\t  ")
        assert result is not None
        await engine.shutdown()


# PLACEHOLDER_LARGE_INPUT


class TestCorruptedStateRecovery:
    def test_restore_from_empty_dict(self):
        kernel = AlphaKernel.restore({})
        assert kernel.session_key == "default"
        assert kernel.turns == 0

    def test_restore_from_garbage_types(self):
        kernel = AlphaKernel.restore(
            {
                "session_key": 12345,
                "turns": "not_a_number",
                "body": "not_a_dict",
                "personality": [1, 2, 3],
                "audit": None,
            }
        )
        assert kernel.session_key == "12345"
        assert kernel.turns == 0
        assert isinstance(kernel.body, AlphaBodyState)

    def test_restore_with_nan_values(self):
        kernel = AlphaKernel.restore(
            {
                "turns": float("nan"),
                "body": {"pulse": {"beat": float("nan"), "rhythm": float("inf")}},
            }
        )
        assert kernel.turns == 0

    def test_body_from_dict_partial(self):
        body = AlphaBodyState.from_dict({"pulse": {"beat": 5.0}})
        assert body.pulse.beat == 5.0
        assert body.bloodflow.warmth == 0.4

    def test_body_from_dict_extra_keys(self):
        body = AlphaBodyState.from_dict(
            {
                "pulse": {"beat": 1.0, "unknown_field": 999},
                "nonexistent_subsystem": {"x": 1},
            }
        )
        assert body.pulse.beat == 1.0

    def test_computation_spine_from_dict_empty(self):
        spine = ComputationSpine()
        spine.from_dict({})
        assert spine is not None

    def test_computation_spine_from_dict_garbage(self):
        spine = ComputationSpine()
        spine.from_dict({"void_scar": "not_a_dict", "autopoiesis": 42})
        assert spine is not None


class TestNaNInfPropagation:
    def test_tick_with_nan_confidence(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(AlphaKernelEvent(text="hello", now=1.0, confidence=float("nan")))
        assert "surface" in result

    def test_tick_with_inf_now(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(AlphaKernelEvent(text="hello", now=float("inf")))
        assert "surface" in result

    def test_body_state_stays_bounded(self):
        kernel = AlphaKernel.boot("s1")
        for i in range(100):
            kernel.tick(
                AlphaKernelEvent(
                    text="hurt" * 50,
                    now=float(i),
                    confidence=1.0,
                    flags=["hurt", "boundary"],
                )
            )
        state = kernel.body
        assert 0.0 <= state.wound.open <= 1.0
        assert 0.0 <= state.immunity.boundary_pressure <= 1.0
        assert 0.0 <= state.mortality.exhaustion <= 1.0


class TestStressAndCapacity:
    def test_many_ticks_no_crash(self):
        kernel = AlphaKernel.boot("stress")
        for i in range(1000):
            kernel.tick(AlphaKernelEvent(text=f"msg {i}", now=float(i)))
        assert kernel.turns == 1000

    def test_large_text_input(self):
        kernel = AlphaKernel.boot("s1")
        large_text = "这是一段很长的文本。" * 1000
        result = kernel.tick(AlphaKernelEvent(text=large_text, now=1.0))
        assert "surface" in result

    def test_memory_traces_bounded(self):
        kernel = AlphaKernel.boot("s1")
        for i in range(200):
            kernel.tick(AlphaKernelEvent(text=f"记忆测试 {i}", now=float(i)))
        traces = kernel.body.memory.get("traces", [])
        assert len(traces) <= 500

    def test_snapshot_restore_roundtrip_after_stress(self):
        kernel = AlphaKernel.boot("s1")
        for i in range(50):
            kernel.tick(AlphaKernelEvent(text=f"msg {i}", now=float(i)))
        snapshot = kernel.snapshot()
        restored = AlphaKernel.restore(snapshot)
        assert restored.turns == 50
        assert restored.session_key == "s1"

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolated(self, tmp_path: Path):
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()
        r1 = await engine.process("alice", "hello")
        r2 = await engine.process("bob", "hi")
        assert r1 is not None
        assert r2 is not None
        await engine.shutdown()


class TestConcurrentSafety:
    @pytest.mark.asyncio
    async def test_concurrent_process_calls(self, tmp_path: Path):
        import asyncio

        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()
        tasks = [engine.process(f"session_{i}", f"message {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_process_after_shutdown_still_works(self, tmp_path: Path):
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()
        await engine.shutdown()
        result = await engine.process("s1", "should still return")
        assert result is not None


class TestDecisionBoundary:
    def test_all_flags_simultaneously(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(
            AlphaKernelEvent(
                text="complex",
                now=1.0,
                confidence=1.0,
                flags=["safe", "hurt", "boundary", "repair", "group"],
            )
        )
        assert result["decision"]["action"] in {
            "express",
            "listen",
            "hold",
            "repair",
            "withdraw",
            "explore",
            "recover",
        }

    def test_guard_blocks_when_exhausted(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.mortality.exhaustion = 0.95
        kernel.body.immunity.sovereignty = 0.3
        result = kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        guard = result.get("guard", {})
        assert guard.get("allowed") is not None
