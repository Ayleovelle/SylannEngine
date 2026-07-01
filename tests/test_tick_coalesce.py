"""Tests for SylanneEngine.tick()'s absolute-minimum-interval coalescer.

KS1 fix: several co-resident plugins each running their own independent
~60s heartbeat loop against the same shared engine must collapse to roughly
one real tick per ``tick_min_interval_seconds`` instead of N.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core.config import SylanneConfig


def _llm() -> AsyncMock:
    return AsyncMock(return_value="ok")


class TestTickCoalescer:
    @pytest.mark.asyncio
    async def test_first_tick_always_advances(self, tmp_path: Path):
        cfg = SylanneConfig(tick_min_interval_seconds=60.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        surface = await engine.tick("s1")
        assert surface["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_within_interval_returns_cached_without_advancing(self, tmp_path: Path):
        cfg = SylanneConfig(tick_min_interval_seconds=60.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        s1 = await engine.tick("s1")
        s2 = await engine.tick("s1")
        assert s2 is s1  # cached, no new snapshot — state was NOT advanced

    @pytest.mark.asyncio
    async def test_three_offset_heartbeat_loops_converge_to_one_real_tick(
        self, tmp_path: Path, monkeypatch
    ):
        # Simulate 3 co-resident plugins each running their own 60s heartbeat
        # loop at phases 0s/20s/40s, for 3 cycles (9 calls, 180s of wall time).
        # A naive per-call tick would be 9x real advances; the absolute
        # tick_min_interval_seconds=45.0 coalescer must collapse that close to
        # 180/45 = 4 real advances, nowhere near the naive 9x.
        cfg = SylanneConfig(tick_min_interval_seconds=45.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()

        clock = {"t": 1_000_000.0}
        monkeypatch.setattr(time, "time", lambda: clock["t"])

        surfaces = []
        for cycle in range(3):
            for phase in (0, 20, 40):
                clock["t"] = 1_000_000.0 + cycle * 60 + phase
                surfaces.append(await engine.tick("s1"))

        distinct_advances = len({id(s) for s in surfaces})
        assert distinct_advances <= 5  # well under the naive 9x
        assert distinct_advances >= 1

    @pytest.mark.asyncio
    async def test_force_bypasses_coalescer(self, tmp_path: Path):
        cfg = SylanneConfig(tick_min_interval_seconds=60.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        s1 = await engine.tick("s1")
        s2 = await engine.tick("s1", force=True)
        assert s2 is not s1  # force= always advances, regardless of interval

    @pytest.mark.asyncio
    async def test_per_session_independence(self, tmp_path: Path):
        cfg = SylanneConfig(tick_min_interval_seconds=60.0)
        engine = SylanneEngine(tmp_path, llm=_llm(), config=cfg)
        await engine.start()
        await engine.tick("s1")
        # A DIFFERENT session has its own independent coalescer window and
        # must still advance on its own first call.
        s2 = await engine.tick("s2")
        assert s2["session_id"] == "s2"
        assert "s1" in engine._last_tick and "s2" in engine._last_tick

    @pytest.mark.asyncio
    async def test_rebind_clears_last_tick(self, tmp_path: Path):
        m = _llm()

        def first_loop() -> None:
            async def run() -> None:
                engine = await SylanneEngine.shared(tmp_path, llm=m)
                await engine.tick("s1")

            asyncio.run(run())

        t = threading.Thread(target=first_loop)
        t.start()
        t.join()

        # Re-acquire on the current loop: triggers the rebind branch, which
        # must also clear _last_tick (KS1-adjacent fix alongside _submissions).
        engine = await SylanneEngine.shared(tmp_path, llm=m)
        assert engine._last_tick == {}

        # A tick right after rebind must actually advance (no stale cache).
        surface = await engine.tick("s1")
        assert surface["session_id"] == "s1"
