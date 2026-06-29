"""Tests for the process-shared engine registry (SylanneEngine.shared)."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SharedEngineConflictError, SylanneEngine
from sylanne_core.config import SylanneConfig


def _llm() -> AsyncMock:
    return AsyncMock(return_value="ok")


class TestSharedDedup:
    @pytest.mark.asyncio
    async def test_returns_same_instance(self, tmp_path: Path):
        m = _llm()
        a = await SylanneEngine.shared(tmp_path, llm=m)
        b = await SylanneEngine.shared(tmp_path, llm=m)
        assert a is b

    @pytest.mark.asyncio
    async def test_path_normalization(self, tmp_path: Path):
        m = _llm()
        a = await SylanneEngine.shared(tmp_path, llm=m)
        b = await SylanneEngine.shared(str(tmp_path), llm=m)
        assert a is b

    @pytest.mark.asyncio
    async def test_dot_segment_normalized(self, tmp_path: Path):
        m = _llm()
        sub = tmp_path / "sub"
        sub.mkdir()
        a = await SylanneEngine.shared(sub, llm=m)
        b = await SylanneEngine.shared(tmp_path / "sub" / "." / "..", llm=m)
        # tmp_path/sub/./.. resolves to tmp_path, distinct from sub
        assert a is not b
        again = await SylanneEngine.shared(sub / "..", llm=m)
        assert again is b

    @pytest.mark.asyncio
    async def test_started(self, tmp_path: Path):
        engine = await SylanneEngine.shared(tmp_path, llm=_llm())
        assert engine.status == "running"


class TestSharedConflict:
    @pytest.mark.asyncio
    async def test_config_conflict_raises(self, tmp_path: Path):
        m = _llm()
        await SylanneEngine.shared(tmp_path, llm=m, config=SylanneConfig(mode="lite"))
        with pytest.raises(SharedEngineConflictError):
            await SylanneEngine.shared(tmp_path, llm=m, config=SylanneConfig(mode="pro"))

    @pytest.mark.asyncio
    async def test_llm_mismatch_warns_not_raises(self, tmp_path: Path, caplog):
        first = await SylanneEngine.shared(tmp_path, llm=_llm())
        with caplog.at_level("WARNING", logger="sylanne_core"):
            second = await SylanneEngine.shared(tmp_path, llm=_llm())
        assert second is first
        assert any("different llm" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_config_copy_immutability(self, tmp_path: Path):
        m = _llm()
        cfg = SylanneConfig(mode="lite")
        await SylanneEngine.shared(tmp_path, llm=m, config=cfg)
        # Mutating the caller's config object must not shift the stored baseline.
        cfg.mode = "pro"
        # A second call with an equivalent original config must not conflict.
        again = await SylanneEngine.shared(tmp_path, llm=m, config=SylanneConfig(mode="lite"))
        assert again.status == "running"


class TestDirectConstructionUnaffected:
    @pytest.mark.asyncio
    async def test_direct_not_in_registry(self, tmp_path: Path):
        m = _llm()
        direct = SylanneEngine(tmp_path, llm=m)
        await direct.start()
        shared = await SylanneEngine.shared(tmp_path, llm=m)
        # Direct construction must be independent of the shared instance.
        assert direct is not shared
        await direct.shutdown()


class TestRelease:
    @pytest.mark.asyncio
    async def test_release_shuts_down_and_frees(self, tmp_path: Path):
        m = _llm()
        first = await SylanneEngine.shared(tmp_path, llm=m)
        await SylanneEngine.release_shared(tmp_path)
        assert first.status == "closed"
        second = await SylanneEngine.shared(tmp_path, llm=m)
        assert second is not first
        assert second.status == "running"

    @pytest.mark.asyncio
    async def test_release_unknown_is_noop(self, tmp_path: Path):
        # Releasing a path that was never shared must not raise.
        await SylanneEngine.release_shared(tmp_path / "never")

    @pytest.mark.asyncio
    async def test_concurrent_acquire_during_release(self, tmp_path: Path):
        m = _llm()
        first = await SylanneEngine.shared(tmp_path, llm=m)
        # Fire release and a re-acquire concurrently; the acquire must either
        # see the tombstone and build fresh, or complete after release.
        release = asyncio.create_task(SylanneEngine.release_shared(tmp_path))
        acquire = asyncio.create_task(SylanneEngine.shared(tmp_path, llm=m))
        await release
        rebuilt = await acquire
        assert rebuilt.status == "running"
        assert first.status == "closed"
        # And the registry now holds exactly that rebuilt instance.
        again = await SylanneEngine.shared(tmp_path, llm=m)
        assert again is rebuilt


class TestRegistryReset:
    def test_clear_registry_sync(self, tmp_path: Path):
        # Must work without a running event loop.
        SylanneEngine.clear_shared_registry()


class TestIntrospection:
    @pytest.mark.asyncio
    async def test_is_shared(self, tmp_path: Path):
        assert SylanneEngine.is_shared(tmp_path) is False
        await SylanneEngine.shared(tmp_path, llm=_llm())
        assert SylanneEngine.is_shared(tmp_path) is True
        await SylanneEngine.release_shared(tmp_path)
        assert SylanneEngine.is_shared(tmp_path) is False

    @pytest.mark.asyncio
    async def test_list_shared(self, tmp_path: Path):
        assert SylanneEngine.list_shared() == []
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        await SylanneEngine.shared(a, llm=_llm())
        await SylanneEngine.shared(b, llm=_llm())
        listing = SylanneEngine.list_shared()
        assert len(listing) == 2
        assert all(item["status"] == "running" for item in listing)
        dirs = {item["data_dir"] for item in listing}
        assert os.path.normcase(str(a.resolve())) in dirs
        assert os.path.normcase(str(b.resolve())) in dirs

    @pytest.mark.asyncio
    async def test_direct_not_in_listing(self, tmp_path: Path):
        direct = SylanneEngine(tmp_path, llm=_llm())
        await direct.start()
        # Direct construction does not register, so introspection ignores it.
        assert SylanneEngine.is_shared(tmp_path) is False
        assert SylanneEngine.list_shared() == []
        await direct.shutdown()


class TestRedundancyGuard:
    @pytest.mark.asyncio
    async def test_direct_construction_warns_when_shared_exists(self, tmp_path: Path, caplog):
        await SylanneEngine.shared(tmp_path, llm=_llm())
        with caplog.at_level("WARNING", logger="sylanne_core"):
            redundant = SylanneEngine(tmp_path, llm=_llm())
        assert any("constructed directly" in r.message for r in caplog.records)
        # The warning does not block construction.
        assert redundant.status == "init"

    @pytest.mark.asyncio
    async def test_shared_creation_does_not_self_warn(self, tmp_path: Path, caplog):
        with caplog.at_level("WARNING", logger="sylanne_core"):
            await SylanneEngine.shared(tmp_path, llm=_llm())
        assert not any("constructed directly" in r.message for r in caplog.records)

    def test_direct_construction_no_warning_when_unshared(self, tmp_path: Path, caplog):
        with caplog.at_level("WARNING", logger="sylanne_core"):
            SylanneEngine(tmp_path, llm=_llm())
        assert not any("constructed directly" in r.message for r in caplog.records)


class TestStartFailure:
    @pytest.mark.asyncio
    async def test_start_failure_does_not_leak_entry(self, tmp_path: Path, monkeypatch):
        m = _llm()

        async def boom(self) -> None:
            raise RuntimeError("start failed")

        monkeypatch.setattr(SylanneEngine, "start", boom)
        with pytest.raises(RuntimeError, match="start failed"):
            await SylanneEngine.shared(tmp_path, llm=m)
        # Restore start; the slot must be free so a fresh acquire works.
        monkeypatch.undo()
        engine = await SylanneEngine.shared(tmp_path, llm=m)
        assert engine.status == "running"


class TestLoopAffinity:
    @pytest.mark.asyncio
    async def test_cross_loop_raises(self, tmp_path: Path):
        m = _llm()
        await SylanneEngine.shared(tmp_path, llm=m)

        result: dict[str, object] = {}

        def worker() -> None:
            async def acquire() -> None:
                try:
                    await SylanneEngine.shared(tmp_path, llm=m)
                except RuntimeError as exc:  # expected: cross-loop
                    result["error"] = exc

            asyncio.run(acquire())

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert isinstance(result.get("error"), RuntimeError)
        assert "different event loop" in str(result["error"])

    @pytest.mark.asyncio
    async def test_release_from_foreign_loop_raises(self, tmp_path: Path):
        m = _llm()
        await SylanneEngine.shared(tmp_path, llm=m)

        result: dict[str, object] = {}

        def worker() -> None:
            async def release() -> None:
                try:
                    await SylanneEngine.release_shared(tmp_path)
                except RuntimeError as exc:  # expected: cross-loop release
                    result["error"] = exc

            asyncio.run(release())

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert isinstance(result.get("error"), RuntimeError)
        assert "different event loop" in str(result["error"])

    @pytest.mark.asyncio
    async def test_closed_loop_rebind_preserves_state(self, tmp_path: Path):
        m = _llm()

        # Acquire and put a session on the engine in loop L1, then let L1 close.
        def first_loop() -> None:
            async def run() -> None:
                engine = await SylanneEngine.shared(tmp_path, llm=m)
                await engine.process("s1", "hello")

            asyncio.run(run())

        t = threading.Thread(target=first_loop)
        t.start()
        t.join()

        # Now on the current loop (L1 is closed): re-acquire must rebind without
        # raising, drop the stale per-session locks, and preserve session state.
        engine = await SylanneEngine.shared(tmp_path, llm=m)
        assert engine.status == "running"
        assert engine.exists("s1")  # session state survived the rebind
        assert engine._locks == {}  # stale loop-bound locks were cleared
        surface = await engine.process("s1", "again")  # usable on the new loop
        assert surface["turns"] >= 2


class TestConcurrentInit:
    @pytest.mark.asyncio
    async def test_concurrent_first_acquire_builds_one_engine(self, tmp_path: Path):
        m = _llm()
        # Many tasks race on the very first acquire; exactly one engine must be
        # built and all callers must receive that same instance.
        results = await asyncio.gather(*(SylanneEngine.shared(tmp_path, llm=m) for _ in range(20)))
        assert all(e is results[0] for e in results)
        assert results[0].status == "running"
        assert len(SylanneEngine.list_shared()) == 1

    @pytest.mark.asyncio
    async def test_cancelled_init_does_not_leak_slot(self, tmp_path: Path, monkeypatch):
        m = _llm()
        started = asyncio.Event()

        async def slow_start(self) -> None:
            started.set()
            await asyncio.sleep(10)  # long enough to be cancelled mid-flight

        monkeypatch.setattr(SylanneEngine, "start", slow_start)
        task = asyncio.create_task(SylanneEngine.shared(tmp_path, llm=m))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # The cancelled init must have rolled back its placeholder, leaving the
        # slot free for a fresh, successful acquire.
        monkeypatch.undo()
        engine = await SylanneEngine.shared(tmp_path, llm=m)
        assert engine.status == "running"
        assert len(SylanneEngine.list_shared()) == 1


class TestResurrectionGuard:
    @pytest.mark.asyncio
    async def test_released_shared_engine_refuses_to_resurrect(self, tmp_path: Path):
        engine = await SylanneEngine.shared(tmp_path, llm=_llm())
        await SylanneEngine.release_shared(tmp_path)
        assert engine.status == "closed"
        # A stale holder using the released engine must NOT silently revive it
        # (that would let the next shared() build a duplicate and double-flush).
        with pytest.raises(RuntimeError, match="released"):
            await engine.process("s1", "hi")

    @pytest.mark.asyncio
    async def test_direct_engine_still_restarts_after_close(self, tmp_path: Path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        await engine.shutdown()
        assert engine.status == "closed"
        await engine.process("s1", "hi")  # a DIRECT engine auto-restarts on use
        assert engine.status in ("running", "degraded")


class TestSelfReadConfigDiff:
    @pytest.mark.asyncio
    async def test_self_read_change_reuses_not_raises(self, tmp_path: Path, caplog):
        import json

        m = _llm()
        a = await SylanneEngine.shared(tmp_path, llm=m)  # file absent -> lite default
        # The user edits the file (the template literally says "edit and restart").
        (tmp_path / "sylanne.config.json").write_text(json.dumps({"mode": "pro"}), encoding="utf-8")
        with caplog.at_level("WARNING", logger="sylanne_core"):
            b = await SylanneEngine.shared(tmp_path, llm=m)
        assert b is a  # reused, no crash
        assert a._config.mode == "lite"  # running config unchanged
        assert any("on-disk config differs" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_explicit_conflicting_config_still_raises(self, tmp_path: Path):
        m = _llm()
        await SylanneEngine.shared(tmp_path, llm=m, config=SylanneConfig(mode="lite"))
        with pytest.raises(SharedEngineConflictError):
            await SylanneEngine.shared(tmp_path, llm=m, config=SylanneConfig(mode="pro"))


class TestShutdownFlushError:
    @pytest.mark.asyncio
    async def test_flush_failure_is_logged_and_marks_degraded(
        self, tmp_path: Path, caplog, monkeypatch
    ):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        await engine.process("s1", "hi")  # create a host

        def boom(self: object) -> None:
            raise OSError("disk full")

        # The host class has __slots__, so patch the method on the class.
        monkeypatch.setattr(type(engine._hosts["s1"]), "flush", boom)
        with caplog.at_level("WARNING", logger="sylanne_core"):
            await engine.shutdown()
        assert engine.status == "degraded"  # flush failure not masked as clean 'closed'
        assert any("flush failed" in r.message for r in caplog.records)
