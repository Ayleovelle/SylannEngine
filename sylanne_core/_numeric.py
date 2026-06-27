"""Shared numeric-coercion helpers (leaf module, stdlib-only).

Lives at the package root so both the LLM assessor (``sylanne_core.assessor``) and
the compute core (``sylanne_core.compute.*``) can borrow the same None-safe float
coercion without an import cycle or a layering inversion — neither side has to reach
into the other for a four-line numeric guard.
"""

from __future__ import annotations

from typing import Any


def _coerce_float(value: Any, lo: float, hi: float, default: float) -> float:
    """Best-effort float clamped to ``[lo, hi]``.

    Untrusted input — a missing/``None`` field from an external LLM, or a
    non-numeric string — falls back to ``default`` instead of raising. Keeps a
    single malformed scalar from toppling the whole tick.
    """
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default
