"""Tests for the process-global rendezvous cell (sylanne_core._rendezvous).

The cell relocates the shared-engine registry out of the per-copy module so that
vendored copies converge on ONE registry, and carries per-copy identities so a
version skew between copies can be surfaced.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import sylanne_core._sharing as sharing
from sylanne_core import SylanneEngine
from sylanne_core._rendezvous import _RENDEZVOUS_KEY, get_cell


def _reset_cell() -> None:
    cell = get_cell()
    with cell.lock:
        cell.registry.clear()
        cell.identities.clear()
        cell.builders.clear()


def test_cell_is_singleton():
    a = get_cell()
    b = get_cell()
    assert a is b
    assert builtins.__dict__.get(_RENDEZVOUS_KEY) is a


def test_sharing_registry_is_cell_backed():
    # The module-level alias must BE the cell's registry object (so all copies
    # mutating it dedup against each other for real).
    assert sharing._REGISTRY is get_cell().registry
    assert sharing._LOCK is get_cell().lock


def test_get_cell_refills_missing_field():
    cell = get_cell()
    delattr(cell, "builders")
    assert not hasattr(cell, "builders")
    refilled = get_cell()
    assert refilled is cell
    assert hasattr(refilled, "builders")


@pytest.mark.asyncio
async def test_shared_engine_registers_in_cell(tmp_path: Path):
    await SylanneEngine.shared(tmp_path, llm=AsyncMock(return_value="ok"))
    key = sharing._make_key(tmp_path)
    assert key in get_cell().registry  # the live engine entry
    assert key in get_cell().builders  # the building copy recorded itself


def test_version_skew_warns(monkeypatch, caplog):
    _reset_cell()
    key = "skew-key"
    builder = {"copy_id": "aaaaaaaa", "short": "sylc-aaaaaaaa", "version": "2.3.0"}
    consumer = {"copy_id": "bbbbbbbb", "short": "sylc-bbbbbbbb", "version": "2.5.0"}

    monkeypatch.setattr(sharing, "_self_identity", lambda: builder)
    sharing._note_identity(key, built=True)

    monkeypatch.setattr(sharing, "_self_identity", lambda: consumer)
    with caplog.at_level("WARNING", logger="sylanne_core"):
        sharing._note_identity(key, built=False)
    assert any("version skew" in r.message for r in caplog.records)


def test_same_version_does_not_warn(monkeypatch, caplog):
    _reset_cell()
    key = "noskew-key"
    a = {"copy_id": "aaaaaaaa", "short": "sylc-aaaaaaaa", "version": "2.3.1"}
    b = {"copy_id": "bbbbbbbb", "short": "sylc-bbbbbbbb", "version": "2.3.1"}

    monkeypatch.setattr(sharing, "_self_identity", lambda: a)
    sharing._note_identity(key, built=True)
    monkeypatch.setattr(sharing, "_self_identity", lambda: b)
    with caplog.at_level("WARNING", logger="sylanne_core"):
        sharing._note_identity(key, built=False)
    assert not any("version skew" in r.message for r in caplog.records)


def test_same_copy_does_not_warn(monkeypatch, caplog):
    _reset_cell()
    key = "samecopy-key"
    ident = {"copy_id": "aaaaaaaa", "short": "sylc-aaaaaaaa", "version": "2.3.1"}
    monkeypatch.setattr(sharing, "_self_identity", lambda: ident)
    sharing._note_identity(key, built=True)
    with caplog.at_level("WARNING", logger="sylanne_core"):
        sharing._note_identity(key, built=False)  # same copy reusing its own engine
    assert not any("version skew" in r.message for r in caplog.records)
