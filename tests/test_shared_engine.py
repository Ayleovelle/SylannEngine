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
        # Two shared() calls routed through the resolved path hit one engine.
        d = SylanneEngine.shared_data_dir(tmp_path / "host")
        a = await SylanneEngine.shared(d, llm=_llm())
        b = await SylanneEngine.shared(d, llm=_llm())
        assert a is b
        assert len(SylanneEngine.list_shared()) == 1


class TestPreSubmitBuilderWarning:
    """2.4.0: attaching to an engine built by a pre-2.4 copy (no submit()) must
    warn loudly — this is the KS4 fix, adapted from the deleted TestRole/
    TestAcquire pattern of faking a foreign co-resident copy directly in the
    rendezvous cell (poking cell.registry/cell.builders)."""

    @pytest.mark.asyncio
    async def test_engine_without_submit_warns_on_attach(self, tmp_path: Path, caplog):
        import weakref

        from sylanne_core._sharing import _cell, _Entry, _make_key

        class _PreSubmitEngine:
            """Stand-in for an engine built by a pre-2.4 sylanne_core copy:
            has no submit() at all."""

            status = "running"

        key = _make_key(tmp_path)
        loop = asyncio.get_running_loop()
        fake_engine = _PreSubmitEngine()
        entry = _Entry(fake_engine, SylanneConfig(), _llm(), None, weakref.ref(loop))
        with _cell.lock:
            _cell.registry[key] = entry
        try:
            with caplog.at_level("WARNING", logger="sylanne_core"):
                got = await SylanneEngine.shared(tmp_path, llm=_llm())
            assert got is fake_engine  # attaches to the existing (submit-less) engine
            assert any("submit() dedup is UNAVAILABLE" in r.message for r in caplog.records)
        finally:
            with _cell.lock:
                _cell.registry.pop(key, None)
                _cell.builders.pop(key, None)

    @pytest.mark.asyncio
    async def test_engine_with_submit_does_not_warn(self, tmp_path: Path, caplog):
        # Sanity counterpart: a normal 3.0 engine (has submit()) never trips it.
        await SylanneEngine.shared(tmp_path, llm=_llm())
        with caplog.at_level("WARNING", logger="sylanne_core"):
            await SylanneEngine.shared(tmp_path, llm=_llm())
        assert not any("submit() dedup is UNAVAILABLE" in r.message for r in caplog.records)


class TestPre2CopyScanWarning:
    """嫁接B: the one-shot sys.modules scan for pre-2.0 copies (KS4 sibling —
    these cannot reach the rendezvous cell at all, so the only mitigation is a
    loud diagnostic naming them)."""

    @pytest.mark.asyncio
    async def test_pre2_copy_in_sys_modules_warns(self, monkeypatch, caplog):
        import sys
        import types

        from sylanne_core import _sharing

        fake = types.ModuleType("vendored_sylanne_core")
        fake.__version__ = "1.0.0"  # type: ignore[attr-defined]
        fake.__file__ = "C:/fake/vendored_sylanne_core/__init__.py"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "vendored_sylanne_core", fake)
        monkeypatch.setattr(_sharing, "_SCANNED_FOR_OLD_COPIES", False)

        with caplog.at_level("WARNING", logger="sylanne_core"):
            _sharing._scan_for_pre2_copies()

        assert any(
            "pre-2.0 sylanne_core copy" in r.message and "vendored_sylanne_core" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_scan_runs_only_once_per_process(self, monkeypatch, caplog):
        import sys
        import types

        from sylanne_core import _sharing

        fake = types.ModuleType("vendored_sylanne_core")
        fake.__version__ = "1.0.0"  # type: ignore[attr-defined]
        fake.__file__ = "C:/fake/vendored_sylanne_core/__init__.py"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "vendored_sylanne_core", fake)
        monkeypatch.setattr(_sharing, "_SCANNED_FOR_OLD_COPIES", False)

        with caplog.at_level("WARNING", logger="sylanne_core"):
            _sharing._scan_for_pre2_copies()
            caplog.clear()
            _sharing._scan_for_pre2_copies()  # second call: guarded, must be silent
        assert not any("pre-2.0 sylanne_core copy" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_current_version_copy_does_not_warn(self, monkeypatch, caplog):
        from sylanne_core import _sharing

        monkeypatch.setattr(_sharing, "_SCANNED_FOR_OLD_COPIES", False)
        with caplog.at_level("WARNING", logger="sylanne_core"):
            _sharing._scan_for_pre2_copies()
        assert not any("pre-2.0 sylanne_core copy" in r.message for r in caplog.records)


class TestPeekAndWaitShared:
    def test_peek_none_when_absent(self, tmp_path: Path):
        assert SylanneEngine.peek_shared(tmp_path) is None

    @pytest.mark.asyncio
    async def test_peek_returns_live_engine_without_building(self, tmp_path: Path):
        assert SylanneEngine.peek_shared(tmp_path) is None
        assert SylanneEngine.is_shared(tmp_path) is False  # peek alone never builds
        built = await SylanneEngine.shared(tmp_path, llm=_llm())
        assert SylanneEngine.peek_shared(tmp_path) is built

    @pytest.mark.asyncio
    async def test_wait_shared_timeout_returns_none(self, tmp_path: Path):
        result = await SylanneEngine.wait_shared(tmp_path, timeout=0.2, interval=0.05)
        assert result is None

    @pytest.mark.asyncio
    async def test_wait_shared_resolves_once_another_task_builds(self, tmp_path: Path):
        async def build_later() -> None:
            await asyncio.sleep(0.1)
            await SylanneEngine.shared(tmp_path, llm=_llm())

        builder_task = asyncio.create_task(build_later())
        try:
            result = await SylanneEngine.wait_shared(tmp_path, timeout=5.0, interval=0.02)
        finally:
            await builder_task
        assert result is not None
        assert result.status == "running"


class TestSetLlm:
    @pytest.mark.asyncio
    async def test_set_llm_swaps_main_callback(self, tmp_path: Path, caplog):
        old, new = _llm(), _llm()
        engine = SylanneEngine(tmp_path, llm=old)
        await engine.start()
        await engine.process("s1", "hello")
        assert old.call_count == 1
        with caplog.at_level("INFO", logger="sylanne_core"):
            engine.set_llm(new)
        await engine.process("s1", "hello again")
        assert new.call_count == 1
        assert old.call_count == 1  # the dead builder's closure is never touched again
        assert any("llm swapped" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_set_llm_only_swaps_assessor_when_given(self, tmp_path: Path):
        main = _llm()
        assessor_old, assessor_new = _llm(), _llm()
        engine = SylanneEngine(tmp_path, llm=main, assessor_llm=assessor_old)
        await engine.start()
        await engine.process("s1", "hi")
        assert assessor_old.call_count == 1
        engine.set_llm(main, assessor_llm=assessor_new)
        await engine.process("s1", "hi again")
        assert assessor_new.call_count == 1
        assert assessor_old.call_count == 1
