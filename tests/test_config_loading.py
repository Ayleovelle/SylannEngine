"""Tests for shared-config-file loading and assessor-llm fallback.

The engine self-reads ``<data_dir>/sylanne.config.json`` when no config is passed,
so users edit one stable file; an ``assessor_model`` block routes assessment to a
small dedicated model, otherwise assessment falls back to the main llm.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core._assessor_llm import _resolve_env, build_from_config
from sylanne_core._config_store import CONFIG_FILENAME, load_config
from sylanne_core.config import SylanneConfig


def _write_config(data_dir: Path, payload: dict) -> None:
    (data_dir / CONFIG_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


class TestLoadConfig:
    def test_absent_file_defaults(self, tmp_path: Path):
        cfg, block = load_config(tmp_path)
        assert cfg == SylanneConfig()
        assert block is None

    def test_reads_known_fields(self, tmp_path: Path):
        _write_config(tmp_path, {"mode": "pro", "assessor_enabled": False})
        cfg, block = load_config(tmp_path)
        assert cfg.mode == "pro"
        assert cfg.assessor_enabled is False
        assert block is None

    def test_ignores_unknown_keys(self, tmp_path: Path):
        _write_config(tmp_path, {"mode": "lite", "bogus_key": 123})
        cfg, _ = load_config(tmp_path)
        assert cfg.mode == "lite"  # unknown key ignored, no crash

    def test_invalid_value_falls_back(self, tmp_path: Path, caplog):
        _write_config(tmp_path, {"mode": "nonsense"})
        with caplog.at_level("WARNING", logger="sylanne_core"):
            cfg, _ = load_config(tmp_path)
        assert cfg == SylanneConfig()
        assert any("invalid config" in r.message for r in caplog.records)

    def test_corrupt_json_falls_back(self, tmp_path: Path):
        (tmp_path / CONFIG_FILENAME).write_text("{ not json", encoding="utf-8")
        cfg, block = load_config(tmp_path)
        assert cfg == SylanneConfig()
        assert block is None

    def test_assessor_block_extracted(self, tmp_path: Path):
        _write_config(
            tmp_path,
            {"mode": "lite", "assessor_model": {"api_base": "http://x/v1", "model": "m"}},
        )
        cfg, block = load_config(tmp_path)
        assert cfg.mode == "lite"
        assert block == {"api_base": "http://x/v1", "model": "m"}


class TestAssessorBuilder:
    def test_resolve_env(self, monkeypatch):
        monkeypatch.setenv("SYL_TEST_KEY", "secret123")
        assert _resolve_env("${SYL_TEST_KEY}") == "secret123"
        assert _resolve_env("plain") == "plain"
        assert _resolve_env("${MISSING_XYZ_KEY}") == ""

    def test_requires_api_base_and_model(self):
        assert build_from_config(None) is None
        assert build_from_config({"model": "m"}) is None
        assert build_from_config({"api_base": "http://x"}) is None

    def test_builds_callable_when_complete(self):
        fn = build_from_config({"api_base": "http://x/v1", "model": "m"})
        assert callable(fn)


class TestEngineConfigFile:
    def test_engine_reads_config_file(self, tmp_path: Path):
        _write_config(tmp_path, {"mode": "pro", "assessor_enabled": False})
        engine = SylanneEngine(tmp_path, llm=AsyncMock())
        assert engine._config.mode == "pro"
        assert engine._config.assessor_enabled is False

    def test_explicit_config_overrides_file(self, tmp_path: Path):
        _write_config(tmp_path, {"mode": "pro"})
        engine = SylanneEngine(tmp_path, llm=AsyncMock(), config=SylanneConfig(mode="lite"))
        assert engine._config.mode == "lite"

    @pytest.mark.asyncio
    async def test_shared_reads_config_file(self, tmp_path: Path):
        _write_config(tmp_path, {"mode": "pro"})
        engine = await SylanneEngine.shared(tmp_path, llm=AsyncMock())
        assert engine._config.mode == "pro"


class TestAssessorFallback:
    @pytest.mark.asyncio
    async def test_assessor_llm_used_for_assessment(self, tmp_path: Path):
        main = AsyncMock(return_value="ok")
        assessor = AsyncMock(return_value="ok")
        engine = SylanneEngine(tmp_path, llm=main, assessor_llm=assessor)
        await engine.start()
        await engine.process("s1", "hello")
        # Assessment routed to the dedicated assessor llm; the main llm is untouched.
        assert assessor.await_count >= 1
        assert main.await_count == 0

    @pytest.mark.asyncio
    async def test_falls_back_to_main_llm_when_no_assessor(self, tmp_path: Path):
        main = AsyncMock(return_value="ok")
        engine = SylanneEngine(tmp_path, llm=main)
        await engine.start()
        await engine.process("s1", "hello")
        assert main.await_count >= 1

    @pytest.mark.asyncio
    async def test_assessor_model_block_wires_assessor(self, tmp_path: Path):
        # An assessor_model block in the file becomes the engine's assessor llm.
        _write_config(
            tmp_path,
            {"assessor_model": {"api_base": "http://x/v1", "model": "m"}},
        )
        engine = SylanneEngine(tmp_path, llm=AsyncMock())
        assert engine._assessor_llm is not None
