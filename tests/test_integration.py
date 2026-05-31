"""Integration smoke test: simulates AstrBot plugin lifecycle end-to-end."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core.config import SylanneConfig


class TestPluginLifecycle:
    """Simulates the full AstrBot plugin flow without AstrBot dependency."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, tmp_path: Path):
        """Plugin init → start → process messages → tick → snapshot → shutdown."""
        llm = AsyncMock(return_value='{"sentiment": "positive", "confidence": 0.8}')
        config = SylanneConfig()
        engine = SylanneEngine(data_dir=tmp_path, llm=llm, config=config)

        # Phase 1: Start (plugin.initialize)
        await engine.start()
        assert engine.status == "running"
        health = engine.health()
        assert health["status"] in ("running", "degraded")

        # Phase 2: Process messages (on_message handler)
        surface1 = await engine.process("user_001", "你好呀")
        assert surface1 is not None
        assert "state" in surface1
        assert "decision" in surface1
        assert "guard" in surface1
        assert surface1["session_id"] == "user_001"

        # Phase 3: Multiple turns build relationship
        surface2 = await engine.process("user_001", "今天心情怎么样？")
        assert surface2["turns"] == 2

        surface3 = await engine.process("user_001", "我觉得有点难过")
        assert surface3["turns"] == 3

        # Phase 4: Tick (periodic background tick)
        await engine.tick("user_001")

        # Phase 5: State query (sync)
        state = engine.state("user_001")
        assert state is not None

        # Phase 6: Second session is isolated
        surface_b = await engine.process("user_002", "hello")
        assert surface_b["session_id"] == "user_002"
        assert surface_b["turns"] == 1

        # Phase 7: Shutdown (plugin cleanup)
        await engine.shutdown()
        assert engine.status == "closed"

    @pytest.mark.asyncio
    async def test_persistence_across_restarts(self, tmp_path: Path):
        """State survives engine restart (simulates bot restart)."""
        llm = AsyncMock(return_value="ok")

        # First boot
        engine1 = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine1.start()
        await engine1.process("user_001", "第一次对话")
        await engine1.process("user_001", "第二次对话")
        await engine1.shutdown()

        # Second boot (same data_dir)
        engine2 = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine2.start()
        state = engine2.state("user_001")
        assert state is not None
        surface = await engine2.process("user_001", "重启后继续")
        assert surface["turns"] >= 3
        await engine2.shutdown()

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self, tmp_path: Path):
        """Engine degrades gracefully when LLM is unavailable."""
        llm = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()

        surface = await engine.process("user_001", "hello")
        assert surface is not None
        assert "decision" in surface
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_config_assessor_disabled(self, tmp_path: Path):
        """With assessor disabled, LLM is not called."""
        llm = AsyncMock(return_value="ok")
        config = SylanneConfig(assessor_enabled=False)
        engine = SylanneEngine(data_dir=tmp_path, llm=llm, config=config)
        await engine.start()

        surface = await engine.process("user_001", "test")
        assert surface is not None
        llm.assert_not_called()
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_reset_clears_session(self, tmp_path: Path):
        """Reset removes session state."""
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()

        await engine.process("user_001", "hello")
        await engine.process("user_001", "world")
        engine.reset("user_001")

        surface = await engine.process("user_001", "fresh start")
        assert surface["turns"] == 1
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_destroy_session(self, tmp_path: Path):
        """Destroy resets session to fresh state."""
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()

        await engine.process("user_001", "hello")
        await engine.process("user_001", "world")
        engine.destroy("user_001")

        surface = await engine.process("user_001", "after destroy")
        assert surface["turns"] == 1
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_listener_receives_events(self, tmp_path: Path):
        """Event listeners are called on process."""
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()

        events_received: list = []
        engine.on(lambda session_id, surface: events_received.append((session_id, surface)))

        await engine.process("user_001", "trigger event")
        assert len(events_received) >= 1
        assert events_received[0][0] == "user_001"
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_health_check(self, tmp_path: Path):
        """Health endpoint returns structured status."""
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)
        await engine.start()

        health = engine.health()
        assert "status" in health
        assert "active_sessions" in health
        assert "llm_configured" in health
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_emotional_trajectory(self, tmp_path: Path):
        """Verify emotional state evolves meaningfully over conversation."""
        llm = AsyncMock(return_value="ok")
        engine = SylanneEngine(
            data_dir=tmp_path, llm=llm, config=SylanneConfig(assessor_enabled=False)
        )
        await engine.start()

        # Warm conversation
        for msg in ["你好", "今天天气真好", "和你聊天很开心", "谢谢你的陪伴"]:
            surface = await engine.process("user_001", msg)

        warmth = surface["state"]["connection"]["warmth"]
        assert warmth > 0.4, f"Expected warmth to increase, got {warmth}"

        # Hurtful turn
        surface_hurt = await engine.process("user_001", "你真没用", flags=["hurt"])
        damage = surface_hurt["state"]["damage"]["open"]
        assert damage > 0.0, "Expected damage after hurt event"

        await engine.shutdown()
