"""Tests for sylanne_core.compute.runtime module."""

from pathlib import Path

from sylanne_core.compute.kernel import AlphaKernel, AlphaKernelEvent
from sylanne_core.compute.runtime import AlphaRuntime


class TestRuntimeLoadSave:
    def test_save_and_load(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        kernel = AlphaKernel.boot("session_1")
        kernel.tick(AlphaKernelEvent(text="hello", now=1.0))
        runtime.save(kernel)
        loaded = runtime.load("session_1")
        assert loaded.session_key == "session_1"
        assert loaded.turns == 1

    def test_load_nonexistent(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        kernel = runtime.load("new_session")
        assert kernel.session_key == "new_session"
        assert kernel.turns == 0

    def test_load_corrupted_json(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        path = tmp_path / "bad_session.alpha.json"
        path.write_text("not valid json {{{", encoding="utf-8")
        kernel = runtime.load("bad_session")
        assert kernel.session_key == "bad_session"
        assert kernel.turns == 0
        assert path.with_suffix(".json.damaged").exists()

    def test_atomic_write(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        kernel = AlphaKernel.boot("atomic_test")
        runtime.save(kernel)
        path = tmp_path / "atomic_test.alpha.json"
        assert path.exists()
        tmp_file = path.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_reset(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        runtime.save(kernel)
        fresh = runtime.reset("s1")
        assert fresh.turns == 0


class TestRuntimeExport:
    def test_export_empty(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        result = runtime.export_all()
        assert result["sessions"] == {}
        assert result["recovered"] == []

    def test_export_with_sessions(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        for name in ("a", "b"):
            kernel = AlphaKernel.boot(name)
            runtime.save(kernel)
        result = runtime.export_all()
        assert "a" in result["sessions"]
        assert "b" in result["sessions"]


class TestRuntimeBuffer:
    def test_save_and_load_buffer(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        data = {"messages": ["hello", "world"], "cursor": 2}
        runtime.save_buffer("s1", data)
        loaded = runtime.load_buffer("s1")
        assert loaded == data

    def test_load_missing_buffer(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        assert runtime.load_buffer("nonexistent") is None


class TestRuntimePathSafety:
    def test_special_characters_in_session_key(self, tmp_path: Path):
        runtime = AlphaRuntime(tmp_path)
        kernel = AlphaKernel.boot("user@host/path:port")
        runtime.save(kernel)
        loaded = runtime.load("user@host/path:port")
        assert loaded.session_key == "user@host/path:port"
