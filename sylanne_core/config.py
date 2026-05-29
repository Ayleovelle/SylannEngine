"""Configuration dataclass for SylanneEngine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SylanneConfig:
    diagnostics: bool = False
    memory_capacity: int = 500
    assessor_enabled: bool = True
    persistence_fsync: bool = True
    tick_drift_cap: float = 0.05
    locale: str = "zh"
