"""Tests for the privacy-safe distillation corpus sink (par1).

Covers the four hard guarantees: default-off (no write), numeric-only rows,
no raw text / raw session key in the file, salted session hashing, the
path-traversal guard, and end-to-end engine wiring (on and off).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneConfig, SylanneEngine
from sylanne_core.telemetry import (
    FEATURE_SCHEMA_VERSION,
    DistillationSink,
    anonymize_session,
)

_LLM_AFFECT = '{"confidence":0.9,"flags":["safe"],"valence":0.4,"arousal":0.3,"wound_risk":0.1}'


class TestDistillationSink:
    def test_disabled_sink_writes_nothing(self, tmp_path: Path) -> None:
        sink = DistillationSink(enabled=False, path=None, salt="", base_dir=tmp_path)
        assert sink.enabled is False
        assert sink.path is None
        sink.record_tick(session_key="u", row={"f_warmth": 1.0})
        sink.close()
        assert list(tmp_path.iterdir()) == []

    def test_enabled_sink_writes_numeric_row(self, tmp_path: Path) -> None:
        base = tmp_path / "telemetry"
        sink = DistillationSink(enabled=True, path=base / "c.jsonl", salt="s", base_dir=base)
        sink.record_tick(session_key="u1", row={"tick": 3, "f_warmth": 0.5, "a_valence": -0.2})
        sink.close()
        lines = (base / "c.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["schema_version"] == FEATURE_SCHEMA_VERSION
        assert rec["session_hash"] == anonymize_session("u1", "s")
        assert rec["f_warmth"] == 0.5
        assert rec["tick"] == 3

    def test_raw_session_key_never_written(self, tmp_path: Path) -> None:
        base = tmp_path / "telemetry"
        sink = DistillationSink(enabled=True, path=base / "c.jsonl", salt="s", base_dir=base)
        sink.record_tick(session_key="platform:user:SECRET12345", row={"f_warmth": 0.1})
        sink.close()
        data = (base / "c.jsonl").read_bytes()
        assert b"SECRET12345" not in data
        assert b"platform:user" not in data

    def test_session_hash_is_anonymized(self, tmp_path: Path) -> None:
        base = tmp_path / "telemetry"
        sink = DistillationSink(enabled=True, path=base / "c.jsonl", salt="pepper", base_dir=base)
        h = sink.session_hash("aylovelle@qq")
        sink.close()
        assert h == anonymize_session("aylovelle@qq", "pepper")
        assert h != "aylovelle@qq"
        assert len(h) == 16
        int(h, 16)  # raises if not hex

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        base = tmp_path / "telemetry"
        base.mkdir()
        with pytest.raises(ValueError):
            DistillationSink(enabled=True, path=base / ".." / "evil.jsonl", salt="s", base_dir=base)

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        base = tmp_path / "telemetry"
        sink = DistillationSink(enabled=True, path=base / "c.jsonl", salt="s", base_dir=base)
        sink.close()
        sink.close()  # must not raise


class TestAnonymizeSession:
    def test_deterministic_and_salt_sensitive(self) -> None:
        a = anonymize_session("u", "salt1")
        assert a == anonymize_session("u", "salt1")
        assert a != anonymize_session("u", "salt2")
        assert a != anonymize_session("other", "salt1")
        assert len(a) == 16
        int(a, 16)  # hex


class TestEngineIntegration:
    @pytest.mark.asyncio
    async def test_engine_collects_when_enabled(self, tmp_path: Path) -> None:
        llm = AsyncMock(return_value=_LLM_AFFECT)
        cfg = SylanneConfig(training_data_sink=True, training_data_salt="t")
        engine = SylanneEngine(data_dir=tmp_path, llm=llm, config=cfg)
        await engine.start()
        await engine.process("user_1", "hello there")
        await engine.shutdown()
        corpus = tmp_path / "telemetry" / "distill_corpus.jsonl"
        assert corpus.exists()
        lines = corpus.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 1
        rec = json.loads(lines[0])
        assert "a_valence" in rec
        assert "f_warmth" in rec
        raw = corpus.read_bytes()
        assert b"hello there" not in raw  # no raw message text
        assert b"user_1" not in raw  # session id is hashed

    @pytest.mark.asyncio
    async def test_engine_no_collection_when_disabled(self, tmp_path: Path) -> None:
        llm = AsyncMock(return_value=_LLM_AFFECT)
        engine = SylanneEngine(data_dir=tmp_path, llm=llm)  # default: sink off
        await engine.start()
        await engine.process("user_1", "hello")
        await engine.shutdown()
        assert not (tmp_path / "telemetry").exists()
