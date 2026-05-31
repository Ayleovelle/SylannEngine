"""Configuration dataclass for SylanneEngine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SylanneConfig:
    """Engine configuration options.

    Attributes:
        diagnostics: Include pipeline debug info in Surface output.
        assessor_enabled: Use LLM for semantic assessment. Disable for local-only mode.
        persistence_fsync: fsync after state writes (safer but slower).
        tick_drift_cap: Max personality drift per tick [0, 1].
        locale: Language for internal prompts ("zh" or "en").
    """

    diagnostics: bool = False
    assessor_enabled: bool = True
    persistence_fsync: bool = True
    tick_drift_cap: float = 0.05
    locale: str = "zh"

    def __post_init__(self) -> None:
        if not (0.0 <= self.tick_drift_cap <= 1.0):
            raise ValueError("tick_drift_cap must be in [0.0, 1.0]")
        if self.locale not in ("zh", "en"):
            raise ValueError("locale must be 'zh' or 'en'")
