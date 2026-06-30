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


class TestRole:
    @pytest.mark.asyncio
    async def test_unowned_before_any_build(self, tmp_path: Path):
        assert SylanneEngine.role(tmp_path) == "unowned"

    @pytest.mark.asyncio
    async def test_builder_is_driver(self, tmp_path: Path):
        await SylanneEngine.shared(tmp_path, llm=_llm())
        # The copy that built the engine is the driver.
        assert SylanneEngine.role(tmp_path) == "driver"

    @pytest.mark.asyncio
    async def test_reacquire_same_copy_stays_driver(self, tmp_path: Path):
        # A single installed copy acquiring twice is still the driver — there is
        # only one plugin, so it drives. Observer-ness needs a *different* copy.
        await SylanneEngine.shared(tmp_path, llm=_llm())
        await SylanneEngine.shared(tmp_path, llm=_llm())
        assert SylanneEngine.role(tmp_path) == "driver"

    @pytest.mark.asyncio
    async def test_foreign_builder_is_observer(self, tmp_path: Path):
        from sylanne_core._sharing import _cell, _make_key, _self_identity

        await SylanneEngine.shared(tmp_path, llm=_llm())
        key = _make_key(tmp_path)
        real_id = _self_identity()["copy_id"]
        # Simulate the engine having been built by a different co-resident copy
        # (a second vendored plugin). This copy must then read as an observer.
        _cell.builders[key] = "foreign-copy-deadbeef"
        try:
            assert SylanneEngine.role(tmp_path) == "observer"
        finally:
            # Restore our real id so the autouse registry reset can reclaim the
            # entry (clear_shared_registry skips foreign-built live entries).
            _cell.builders[key] = real_id

    @pytest.mark.asyncio
    async def test_unowned_after_release(self, tmp_path: Path):
        await SylanneEngine.shared(tmp_path, llm=_llm())
        await SylanneEngine.release_shared(tmp_path)
        assert SylanneEngine.role(tmp_path) == "unowned"

    @pytest.mark.asyncio
    async def test_unknown_copy_id_reads_observer_when_live(self, tmp_path: Path, monkeypatch):
        # If this copy's identity cannot be resolved, it must never claim driver
        # over a live engine someone else owns — fail safe to observer.
        from sylanne_core import _sharing

        await SylanneEngine.shared(tmp_path, llm=_llm())
        monkeypatch.setattr(_sharing, "_self_identity", lambda: {})
        assert SylanneEngine.role(tmp_path) == "observer"


class TestAcquire:
    @pytest.mark.asyncio
    async def test_first_acquire_is_driver(self, tmp_path: Path):
        from sylanne_core import AcquireResult

        result = await SylanneEngine.acquire(tmp_path, llm=_llm())
        assert isinstance(result, AcquireResult)
        assert result.role == "driver"
        assert result.is_driver is True
        assert isinstance(result.engine, SylanneEngine)
        assert result.observer is None
        assert result.handle is result.engine
        assert result.engine.status == "running"
        # The driver handle can actually drive.
        surface = await result.engine.process("s1", "hi")
        assert surface["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_foreign_owner_yields_observer_view(self, tmp_path: Path):
        from sylanne_core import ObserverView
        from sylanne_core._sharing import _cell, _make_key, _self_identity

        # An engine already owned by another co-resident copy.
        await SylanneEngine.shared(tmp_path, llm=_llm())
        key = _make_key(tmp_path)
        real_id = _self_identity()["copy_id"]
        _cell.builders[key] = "foreign-copy-deadbeef"
        try:
            result = await SylanneEngine.acquire(tmp_path, llm=_llm())
            assert result.role == "observer"
            assert result.engine is None
            assert isinstance(result.observer, ObserverView)
            assert result.handle is result.observer
            # Structurally listen-only: the driving methods are simply absent.
            assert not hasattr(result.observer, "process")
            assert not hasattr(result.observer, "tick")
            assert not hasattr(result.observer, "inject")
            assert not hasattr(result.observer, "shutdown")
            # But it can listen and read.
            assert hasattr(result.observer, "on")
            assert result.observer.status == "running"
            assert result.observer.role == "observer"
        finally:
            _cell.builders[key] = real_id

    @pytest.mark.asyncio
    async def test_as_observer_unowned_when_no_driver(self, tmp_path: Path):
        result = await SylanneEngine.acquire(tmp_path, as_observer=True)
        assert result.role == "unowned"
        assert result.engine is None
        assert result.observer is None
        assert result.handle is None

    @pytest.mark.asyncio
    async def test_as_observer_attaches_to_existing_driver(self, tmp_path: Path):
        from sylanne_core import ObserverView

        await SylanneEngine.shared(tmp_path, llm=_llm())  # a driver is up
        result = await SylanneEngine.acquire(tmp_path, as_observer=True)
        assert result.role == "observer"
        assert isinstance(result.observer, ObserverView)
        assert result.observer.status == "running"

    @pytest.mark.asyncio
    async def test_driver_path_without_llm_and_no_engine_raises(self, tmp_path: Path):
        # acquire() without as_observer is the driver path; building needs an llm.
        with pytest.raises(ValueError, match="llm is required"):
            await SylanneEngine.acquire(tmp_path)

    @pytest.mark.asyncio
    async def test_acquire_without_llm_attaches_to_existing(self, tmp_path: Path):
        first = await SylanneEngine.shared(tmp_path, llm=_llm())
        # No llm, but an engine already exists -> attach (same copy -> driver).
        result = await SylanneEngine.acquire(tmp_path)
        assert result.role == "driver"
        assert result.engine is first

    @pytest.mark.asyncio
    async def test_observer_view_receives_driver_pushes(self, tmp_path: Path):
        # The whole point: one engine computes, the observer just listens.
        driver = (await SylanneEngine.acquire(tmp_path, llm=_llm())).engine
        view = (await SylanneEngine.acquire(tmp_path, as_observer=True)).observer
        assert view is not None and driver is not None

        received: list[tuple[str, object]] = []
        view.on(lambda sid, surf: received.append((sid, surf)))

        await driver.process("s1", "hello")
        assert len(received) == 1
        assert received[0][0] == "s1"

        # The observer can read the session the driver advanced, without driving.
        assert view.exists("s1") is True
        snap = await view.state("s1")
        assert snap["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_observer_survives_driver_release(self, tmp_path: Path):
        # The "one plugin is disabled while others keep running" case — and the
        # exact shape of the prior audit's resurrection BLOCKER. An observer must
        # not crash, must stay unable to drive, and must not open a write path.
        driver = (await SylanneEngine.acquire(tmp_path, llm=_llm())).engine
        view = (await SylanneEngine.acquire(tmp_path, as_observer=True)).observer
        assert driver is not None and view is not None
        await driver.process("s1", "hi")

        await SylanneEngine.release_shared(tmp_path)  # driver plugin shuts down
        assert driver.status == "closed"

        # The view still references the (now closed) engine: no crash, still no
        # driving methods, and the registry is free again (role -> unowned).
        assert view.status == "closed"
        assert not hasattr(view, "process")
        # on() does not crash, but registering on a released engine is a dead drop
        # (the listener list is on the closed object and can never fire again);
        # the observer must re-acquire to receive pushes — there is no auto-rebind.
        view.on(lambda sid, surf: None)
        # The write path is closed too: reading state() on a released shared engine
        # refuses to rehydrate a host (resurrection guard) instead of silently
        # rebuilding it from disk. Re-acquire is the only correct path forward.
        with pytest.raises(RuntimeError, match="released"):
            await view.state("s1")
        assert SylanneEngine.role(tmp_path) == "unowned"
        # A fresh acquire rebuilds a NEW engine (not the released one).
        rebuilt = await SylanneEngine.acquire(tmp_path, llm=_llm())
        assert rebuilt.is_driver and rebuilt.engine is not driver


class TestSharedDataDir:
    def test_explicit_wins(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("SYLANNE_DATA_DIR", str(tmp_path / "from_env"))
        got = SylanneEngine.shared_data_dir(tmp_path / "explicit")
        assert got == (tmp_path / "explicit").resolve()

    def test_env_var_used_when_no_explicit(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("SYLANNE_DATA_DIR", str(tmp_path / "from_env"))
        got = SylanneEngine.shared_data_dir()
        assert got == (tmp_path / "from_env").resolve()

    def test_empty_env_is_ignored(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("SYLANNE_DATA_DIR", "   ")
        got = SylanneEngine.shared_data_dir()
        # Falls through to the per-user default, not the blank env value.
        assert got == (Path.home() / ".sylanne" / "shared").resolve()

    def test_default_is_stable(self, monkeypatch):
        monkeypatch.delenv("SYLANNE_DATA_DIR", raising=False)
        a = SylanneEngine.shared_data_dir()
        b = SylanneEngine.shared_data_dir()
        assert a == b == (Path.home() / ".sylanne" / "shared").resolve()

    def test_not_created(self, tmp_path: Path):
        target = tmp_path / "never_made"
        resolved = SylanneEngine.shared_data_dir(target)
        assert resolved == target.resolve()
        assert not target.exists()  # resolving must not create the directory

    @pytest.mark.asyncio
    async def test_resolved_dir_converges_to_one_engine(self, tmp_path: Path):
        # Two acquisitions routed through the resolved path hit one engine.
        d = SylanneEngine.shared_data_dir(tmp_path / "host")
        a = await SylanneEngine.acquire(d, llm=_llm())
        b = await SylanneEngine.acquire(d, llm=_llm())
        assert a.engine is b.engine
        assert len(SylanneEngine.list_shared()) == 1
