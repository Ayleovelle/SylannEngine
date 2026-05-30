"""Tests for sylanne_core.compute.host module."""

import time
from pathlib import Path

from sylanne_core.compute.host import SylanneAlphaHost, SylanneAlphaHostEvent


class TestHostLifecycle:
    def test_init(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        assert host.session_key == "s1"
        assert host.kernel is not None

    def test_on_request(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        surface = host.on_request({"text": "hello", "now": time.time()})
        assert "decision" in surface
        assert "guard" in surface

    def test_on_response(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        host.on_request({"text": "hi", "now": time.time()})
        surface = host.on_response({"text": "reply", "now": time.time()})
        assert "decision" in surface

    def test_on_chat(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        result = host.on_chat({"text": "hello", "now": time.time()})
        assert "reply_text" in result
        assert result["ok"] is True

    def test_diagnostics(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        host.on_request({"text": "hi", "now": time.time()})
        diag = host.diagnostics()
        assert "schema_version" in diag

    def test_snapshot(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        host.on_request({"text": "hi", "now": time.time()})
        snap = host.snapshot()
        assert snap["session_key"] == "s1"


class TestHostPersistence:
    def test_flush(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        host.on_request({"text": "hi", "now": time.time()})
        host.flush()
        assert (tmp_path / "s1.alpha.json").exists()

    def test_state_survives_reload(self, tmp_path: Path):
        host1 = SylanneAlphaHost(root=tmp_path, session_key="s1")
        host1.on_request({"text": "hello", "now": 1.0})
        host1.flush()
        host2 = SylanneAlphaHost(root=tmp_path, session_key="s1")
        assert host2.kernel.turns == 1


class TestHostEvent:
    def test_dict_event(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        surface = host.on_request(
            {"text": "test", "confidence": 0.8, "flags": ["safe"], "now": 1.0}
        )
        assert "decision" in surface

    def test_typed_event(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        event = SylanneAlphaHostEvent(
            text="hello", confidence=0.5, flags=["safe"], now=1.0
        )
        surface = host.on_request(event)
        assert "decision" in surface

    def test_none_event(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        surface = host.on_request(None)
        assert "decision" in surface


class TestHostProactive:
    def test_proactive_check(self, tmp_path: Path):
        host = SylanneAlphaHost(root=tmp_path, session_key="s1")
        surface = host.on_proactive_check(
            {"text": "", "flags": ["proactive"], "now": time.time()}
        )
        assert "host_payload" in surface
