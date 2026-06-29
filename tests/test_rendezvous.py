"""Tests for the process-global rendezvous cell (sylanne_core._rendezvous).

The cell relocates the shared-engine registry out of the per-copy module so that
vendored copies converge on ONE registry, and carries per-copy identities so a
version skew between copies can be surfaced.
"""

from __future__ import annotations

import builtins
import dataclasses
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


@dataclasses.dataclass
class _ForeignEntry:
    """Stand-in for another vendored copy's _Entry — a DIFFERENT class, so
    isinstance(x, sharing._Entry) is False (the genuine cross-copy case the old
    test failed to exercise by reusing the local _Entry)."""

    engine: object
    config: object
    llm: object
    embedding: object
    loop_ref: object


def test_clear_keeps_foreign_class_live_entry():
    cell = get_cell()
    my_id = sharing._self_identity()["copy_id"]
    foreign = _ForeignEntry(
        engine=object(), config=None, llm=None, embedding=None, loop_ref=lambda: None
    )
    mine = sharing._Entry(
        engine=object(), config=None, llm=None, embedding=None, loop_ref=lambda: None
    )
    try:
        with cell.lock:
            cell.registry.clear()
            cell.identities.clear()
            cell.builders.clear()
            cell.registry["foreign"] = foreign  # a genuinely different _Entry class
            cell.builders["foreign"] = "some-other-copy"
            cell.registry["mine"] = mine
            cell.builders["mine"] = my_id
        sharing.clear_shared_registry()
        # The foreign-class live entry must survive (duck-typed liveness), not be
        # orphaned because isinstance(_Entry) returned False.
        assert "foreign" in cell.registry
        assert "mine" not in cell.registry  # this copy's own entry is cleared
    finally:
        with cell.lock:
            cell.registry.clear()
            cell.identities.clear()
            cell.builders.clear()


def test_list_shared_sees_foreign_class_entry():
    cell = get_cell()

    class _Eng:
        status = "running"

    class _FE:  # another copy's entry class
        engine = _Eng()

    try:
        with cell.lock:
            cell.registry.clear()
            cell.identities.clear()
            cell.builders.clear()
            cell.registry["k"] = _FE()
        listing = sharing.list_shared()
        assert any(item["status"] == "running" for item in listing)
    finally:
        with cell.lock:
            cell.registry.clear()
            cell.identities.clear()
            cell.builders.clear()
