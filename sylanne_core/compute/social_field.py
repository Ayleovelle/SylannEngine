"""Stub for social_field types used in TYPE_CHECKING."""

from __future__ import annotations

from typing import Any, TypedDict


class SocialSignals(TypedDict, total=False):
    group_size: int
    activity_level: float
    topic_coherence: float
    speaker_diversity: float
