"""Tests for per-copy SDK identity (sylanne_core._identity).

The copy_id is a write-once persistent label: stable across restarts and across
in-place version upgrades, distinct per physical copy, with a deterministic
non-persistent fallback when the package directory is read-only.
"""

from __future__ import annotations

import json
from pathlib import Path

import sylanne_core._identity as identity


def test_mints_and_persists(tmp_path: Path):
    rec = identity.resolve_identity(tmp_path, "2.3.1", "sylanne_core")
    assert rec["persistent"] is True
    assert len(rec["copy_id"]) == 32  # uuid4().hex
    assert rec["short"].startswith("sylc-")
    assert rec["version"] == "2.3.1"
    assert rec["module"] == "sylanne_core"
    assert rec["path"] == str(tmp_path)
    assert rec["born"] is not None
    # The id is durably written next to the package.
    assert (tmp_path / "_identity.json").exists()


def test_stable_across_calls_and_upgrade(tmp_path: Path):
    a = identity.resolve_identity(tmp_path, "2.3.1", "sylanne_core")
    b = identity.resolve_identity(tmp_path, "2.5.0", "sylanne_core")  # version bumped in place
    # Same physical copy -> same id even after an in-place upgrade; version refreshes.
    assert a["copy_id"] == b["copy_id"]
    assert a["born"] == b["born"]
    assert b["version"] == "2.5.0"


def test_distinct_dirs_get_distinct_ids(tmp_path: Path):
    d1, d2 = tmp_path / "a", tmp_path / "b"
    d1.mkdir()
    d2.mkdir()
    a = identity.resolve_identity(d1, "2.3.1", "plugin_a.deps.sylanne_core")
    b = identity.resolve_identity(d2, "2.3.1", "plugin_b.deps.sylanne_core")
    assert a["copy_id"] != b["copy_id"]


def test_adopts_preexisting_file(tmp_path: Path):
    # Simulate a copy installed earlier or by another process.
    preexisting = {"copy_id": "deadbeefdeadbeefdeadbeefdeadbeef", "born": "2026-01-01T00:00:00Z"}
    (tmp_path / "_identity.json").write_text(json.dumps(preexisting), encoding="utf-8")
    rec = identity.resolve_identity(tmp_path, "2.3.1", "sylanne_core")
    assert rec["copy_id"] == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert rec["born"] == "2026-01-01T00:00:00Z"
    assert rec["persistent"] is True


def test_corrupt_file_is_reminted(tmp_path: Path):
    (tmp_path / "_identity.json").write_text("{ not json", encoding="utf-8")
    rec = identity.resolve_identity(tmp_path, "2.3.1", "sylanne_core")
    # Unparseable id file is treated as absent; a fresh persistent id is minted.
    assert rec["persistent"] is True
    assert len(rec["copy_id"]) == 32


def test_readonly_fallback_is_deterministic(tmp_path: Path, monkeypatch):
    # Simulate an unwritable package dir: minting cannot create the file.
    monkeypatch.setattr(identity, "_mint_persistent", lambda path: None)
    a = identity.resolve_identity(tmp_path, "2.3.1", "sylanne_core")
    b = identity.resolve_identity(tmp_path, "2.3.1", "sylanne_core")
    assert a["persistent"] is False
    assert a["born"] is None
    assert a["short"].startswith("sylc-")
    # Deterministic path hash: same dir -> same id, no file written.
    assert a["copy_id"] == b["copy_id"]
    assert not (tmp_path / "_identity.json").exists()
