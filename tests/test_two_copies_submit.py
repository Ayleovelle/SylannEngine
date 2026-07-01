"""Real two-physical-copies harness (KS6a fix).

The prior "cross-copy" tests all faked a foreign copy by poking
``_cell.builders``/``_cell.registry`` directly with the SAME local ``_Entry``
class — that can never exercise the submit() dedup table across genuinely
distinct module objects. This harness copies the ``sylanne_core`` package to
disk under a fresh top-level module name, imports it via ``importlib``, and
proves TWO physically-distinct copies converge on ONE engine via the
process-global rendezvous cell (``builtins``) — and that ``submit()`` calls
routed through either copy's class join into a single compute.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

import sylanne_core as _dev_copy


def _llm() -> AsyncMock:
    return AsyncMock(return_value="ok")


def _import_physical_copy(tmp_path: Path, label: str) -> ModuleType:
    """Copy the sylanne_core package tree to disk under a fresh unique name
    and import it fresh via importlib — a genuinely distinct module/class,
    not just a re-imported alias of the dev copy running this test process.
    """
    src = Path(_dev_copy.__file__).resolve().parent
    unique_name = f"{label}_{uuid.uuid4().hex[:8]}"
    dst_parent = tmp_path / f"_vendor_parent_{unique_name}"
    dst_parent.mkdir(parents=True, exist_ok=True)
    dst = dst_parent / unique_name
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "_identity.json", "*.pyc"),
    )
    sys.path.insert(0, str(dst_parent))
    try:
        import importlib

        mod = importlib.import_module(unique_name)
    finally:
        if str(dst_parent) in sys.path:
            sys.path.remove(str(dst_parent))
    return mod


def _cleanup_physical_copy(mod: ModuleType) -> None:
    prefix = mod.__name__
    for name in [n for n in list(sys.modules) if n == prefix or n.startswith(prefix + ".")]:
        del sys.modules[name]


def _reset_cell_fully() -> None:
    """The autouse clear_shared_registry fixture only clears entries built by
    THIS (dev-copy) copy_id — a foreign-copy-built entry from the harness
    would otherwise leak across tests. Nuke the whole cell instead."""
    from sylanne_core._rendezvous import get_cell

    cell = get_cell()
    with cell.lock:
        cell.registry.clear()
        cell.identities.clear()
        cell.builders.clear()


class TestTwoPhysicalCopiesConverge:
    @pytest.mark.asyncio
    async def test_copies_are_genuinely_distinct_classes(self, tmp_path: Path):
        mod_a = _import_physical_copy(tmp_path, "vendor_a")
        try:
            assert mod_a.SylanneEngine is not _dev_copy.SylanneEngine
            assert mod_a.__name__ != _dev_copy.__name__
        finally:
            _cleanup_physical_copy(mod_a)
            _reset_cell_fully()

    @pytest.mark.asyncio
    async def test_two_copies_converge_to_one_engine(self, tmp_path: Path):
        mod_a = _import_physical_copy(tmp_path, "vendor_a")
        mod_b = _import_physical_copy(tmp_path, "vendor_b")
        try:
            data_dir = tmp_path / "shared_data"
            llm = _llm()

            engine_a = await mod_a.SylanneEngine.shared(data_dir, llm=llm)
            engine_b = await mod_b.SylanneEngine.shared(data_dir, llm=llm)
            # Converged via the builtins-backed rendezvous cell to ONE engine,
            # despite mod_a.SylanneEngine and mod_b.SylanneEngine being
            # distinct classes from distinct on-disk copies.
            assert engine_a is engine_b
        finally:
            _cleanup_physical_copy(mod_a)
            _cleanup_physical_copy(mod_b)
            _reset_cell_fully()

    @pytest.mark.asyncio
    async def test_cross_copy_submit_joins_one_compute(self, tmp_path: Path):
        mod_a = _import_physical_copy(tmp_path, "vendor_a")
        mod_b = _import_physical_copy(tmp_path, "vendor_b")
        try:
            data_dir = tmp_path / "shared_data"
            llm = _llm()

            engine_a = await mod_a.SylanneEngine.shared(data_dir, llm=llm)
            engine_b = await mod_b.SylanneEngine.shared(data_dir, llm=llm)
            assert engine_a is engine_b

            # Two "plugins" — one on each physical copy — submit the SAME
            # platform event concurrently. This is the exact repro shape of
            # the 2.4.0 deployment-mode failure (N co-resident plugins, one
            # shared engine), now going through submit() instead of process().
            ra, rb = await asyncio.gather(
                engine_a.submit("s1", "hello", msg_id="evt-1"),
                engine_b.submit("s1", "hello", msg_id="evt-1"),
            )
            assert ra is rb
            assert llm.call_count == 1
        finally:
            _cleanup_physical_copy(mod_a)
            _cleanup_physical_copy(mod_b)
            _reset_cell_fully()

    @pytest.mark.asyncio
    async def test_cross_copy_submit_serial_join_within_window(self, tmp_path: Path):
        mod_a = _import_physical_copy(tmp_path, "vendor_a")
        mod_b = _import_physical_copy(tmp_path, "vendor_b")
        try:
            data_dir = tmp_path / "shared_data"
            llm = _llm()

            engine_a = await mod_a.SylanneEngine.shared(data_dir, llm=llm)
            engine_b = await mod_b.SylanneEngine.shared(data_dir, llm=llm)

            ra = await engine_a.submit("s1", "hello", msg_id="evt-1")
            rb = await engine_b.submit("s1", "hello", msg_id="evt-1")
            assert ra is rb
            assert llm.call_count == 1
            stats = engine_a.submit_stats()
            assert stats["computed"] == 1
            assert stats["joined"] == 1
        finally:
            _cleanup_physical_copy(mod_a)
            _cleanup_physical_copy(mod_b)
            _reset_cell_fully()
