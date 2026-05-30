"""Type definitions for Sylanne-Core SDK output."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


EngineStatus = Literal["init", "running", "degraded", "closed"]


class RhythmState(TypedDict):
    beat: float
    stability: float
    strain: float


class ConnectionState(TypedDict):
    warmth: float
    circulation: float
    memory_flow: float


class AdaptationState(TypedDict):
    plasticity: float
    sensitivity: float
    repetition: int
    threshold_drift: float


class ResponsivenessState(TypedDict):
    readiness: float
    fatigue: float
    trained_reach: float


class ValenceState(TypedDict):
    warmth: float
    volatility: float
    recovery_heat: float


class DamageState(TypedDict):
    open: float
    accumulated: float
    sensitivity: float
    recovery: float


class BoundaryState(TypedDict):
    pressure: float
    autonomy: float
    interruption_budget: float
    cooldown: float
    paused: bool


class CapacityState(TypedDict):
    load: float
    exhaustion: float
    recovery_debt: float


class NeedsState(TypedDict):
    expression: float
    quiet: float
    recovery: float
    contact: float


class AffectiveState(TypedDict):
    rhythm: RhythmState
    connection: ConnectionState
    adaptation: AdaptationState
    responsiveness: ResponsivenessState
    valence: ValenceState
    damage: DamageState
    boundary: BoundaryState
    capacity: CapacityState
    needs: NeedsState


class DeepPersonality(TypedDict):
    expression_drive: float
    perception_acuity: float
    boundary_permeability: float
    inner_coherence: float
    relational_gravity: float


class SurfacePersonality(TypedDict):
    warmth_bias: float
    directness: float
    curiosity: float
    patience: float
    intimacy_pull: float
    autonomy_guard: float


class PersonalityState(TypedDict):
    schema_version: str
    deep: DeepPersonality
    surface: SurfacePersonality


class Decision(TypedDict):
    action: str
    reason: str
    reason_code: str
    confidence: float
    urgency: float


class Guard(TypedDict):
    allowed: bool
    reason: str
    risk_score: float
    constraints: list[str]


class MemoryEntry(TypedDict):
    text: str
    relevance: float
    created_at: float
    layer: str


class MemoryResult(TypedDict):
    recalled: list[MemoryEntry]
    total_stored: int


class HealthStatus(TypedDict):
    status: EngineStatus
    active_sessions: int
    data_dir_exists: bool
    llm_configured: bool
    embedding_configured: bool


class Surface(TypedDict):
    schema_version: str
    session_id: str
    turns: int
    timestamp: float
    state: AffectiveState
    personality: PersonalityState
    decision: Decision
    guard: Guard
    memory: MemoryResult
    pipeline: dict[str, Any]
    dynamics: dict[str, Any]
    debug: dict[str, Any] | None
