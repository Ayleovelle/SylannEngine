"""Configuration dataclass for SylanneEngine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SylanneConfig:
    """Engine configuration options.

    Attributes:
        diagnostics: Include pipeline debug info in Surface output.
        memory_capacity: Max memory traces per session (oldest evicted).
        assessor_enabled: Use LLM for semantic assessment. Disable for local-only mode.
        persistence_fsync: fsync after state writes (safer but slower).
        tick_drift_cap: Max personality drift per tick [0, 1].
        locale: Language for internal prompts ("zh" or "en").
    """

    diagnostics: bool = False
    memory_capacity: int = 500
    assessor_enabled: bool = True
    persistence_fsync: bool = True
    tick_drift_cap: float = 0.05
    locale: str = "zh"
