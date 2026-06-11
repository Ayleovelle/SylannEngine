"""Shared fixtures for Sylanne-Core tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from sylanne_core import SylanneEngine


@pytest.fixture(autouse=True)
def _reset_shared_registry() -> Iterator[None]:
    """Keep the process-global shared-engine registry from leaking across tests."""
    SylanneEngine.clear_shared_registry()
    yield
    SylanneEngine.clear_shared_registry()
