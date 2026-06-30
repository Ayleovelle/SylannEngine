"""Surface schema compatibility guardrail — additive-only contract lock.

Cross-plugin / cross-version sharing only stays safe if the Surface stays
ADDITIVE-ONLY: a consumer pinned to an older SDK must keep finding every field it
already reads. These tests freeze the CURRENT Surface contract so that REMOVING a
field, RETYPING a top-level field, or BUMPING the schema tag fails CI loudly.
Adding new (optional) fields is always allowed — the golden checks containment,
never equality.

If you intentionally break the contract, do it consciously: bump
``sylanne.engine.vN`` AND update the golden in this file in the SAME commit. That
is the "I am breaking downstream consumers, on purpose" gate — see the Surface
contract section of AGENT_GUIDE.md.
"""

from __future__ import annotations

import typing
from unittest.mock import AsyncMock

import pytest

from sylanne_core import SylanneEngine
from sylanne_core import types as t
from sylanne_core.adapter import _SCHEMA_VERSION


def _ann_str(annotation: object) -> str:
    """Normalize a TypedDict annotation to its source string.

    Under ``from __future__ import annotations`` the TypedDict machinery stores
    each field annotation as a ``ForwardRef`` (e.g. ``ForwardRef('dict[str, Any]')``),
    not a bare string — unwrap it so the golden compares against the written type.
    """
    if isinstance(annotation, typing.ForwardRef):
        return annotation.__forward_arg__
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", str(annotation))


# The engine Surface schema tag. Bumping it is a deliberate breaking change.
SURFACE_SCHEMA_TAG = "sylanne.engine.v1"

# Top-level Surface: field name -> declared annotation. Missing key = removal,
# changed value = retype. Both break downstream. New keys are allowed.
GOLDEN_SURFACE_TOPLEVEL: dict[str, str] = {
    "schema_version": "str",
    "session_id": "str",
    "turns": "int",
    "timestamp": "float",
    "state": "AffectiveState",
    "personality": "PersonalityState",
    "decision": "Decision",
    "guard": "Guard",
    "pipeline": "dict[str, Any]",
    "dynamics": "Dynamics",
    "pad": "PADOutput",
    "debug": "dict[str, Any] | None",
}

# Every nested TypedDict in the Surface tree -> the field NAMES a consumer may
# already read. Names only (locking nested type strings too would be brittle);
# this catches removal/rename at any depth. Additions allowed.
GOLDEN_NESTED_FIELDS: dict[str, set[str]] = {
    "AffectiveState": {
        "rhythm",
        "connection",
        "adaptation",
        "responsiveness",
        "valence",
        "damage",
        "boundary",
        "capacity",
        "needs",
    },
    "RhythmState": {"beat", "stability", "strain"},
    "ConnectionState": {"warmth", "circulation", "memory_flow"},
    "AdaptationState": {"plasticity", "sensitivity", "repetition", "threshold_drift"},
    "ResponsivenessState": {"readiness", "fatigue", "trained_reach"},
    "ValenceState": {"warmth", "volatility", "recovery_heat"},
    "DamageState": {"open", "accumulated", "sensitivity", "recovery"},
    "BoundaryState": {"pressure", "autonomy", "interruption_budget", "cooldown", "paused"},
    "CapacityState": {"load", "exhaustion", "recovery_debt"},
    "NeedsState": {"expression", "quiet", "recovery", "contact"},
    "PersonalityState": {"schema_version", "deep", "surface"},
    "DeepPersonality": {
        "expression_drive",
        "perception_acuity",
        "boundary_permeability",
        "inner_coherence",
        "relational_gravity",
    },
    "SurfacePersonality": {
        "warmth_bias",
        "directness",
        "curiosity",
        "patience",
        "intimacy_pull",
        "autonomy_guard",
    },
    "Decision": {"action", "reason", "reason_code", "confidence", "urgency"},
    "Guard": {"allowed", "reason", "risk_score", "constraints"},
    "Dynamics": {"affect", "moral_state", "uncertainty", "relational_time", "hot_pool"},
    "AffectDynamics": {"recovery_drive", "expression_drive", "quiet_drive"},
    "MoralState": {"state", "events"},
    "UncertaintyState": {"claim_caution", "events"},
    "RelationalTime": {"interval_seconds", "total_duration", "phase"},
    "HotPoolDiagnostics": {
        "temperature",
        "volume",
        "pressure",
        "material_count",
        "cascade_active",
        "cascade_intensity",
        "sensitivity_multiplier",
        "in_recovery",
        "collapse_count",
    },
    "PADOutput": {"valence", "arousal", "dominance", "label", "confidence"},
}

# Parent TypedDict -> {field: child TypedDict name}. Locks the WIRING of the
# Surface tree: a parent could otherwise be re-pointed at a thinner type (e.g.
# ``rhythm: RhythmState`` -> ``rhythm: dict[str, Any]``) while the now-orphaned
# RhythmState class keeps passing its own field check. This pins every edge so
# the tree shape itself is additive-only, and it drives the recursive runtime
# walk below.
GOLDEN_EDGES: dict[str, dict[str, str]] = {
    "Surface": {
        "state": "AffectiveState",
        "personality": "PersonalityState",
        "decision": "Decision",
        "guard": "Guard",
        "dynamics": "Dynamics",
        "pad": "PADOutput",
    },
    "AffectiveState": {
        "rhythm": "RhythmState",
        "connection": "ConnectionState",
        "adaptation": "AdaptationState",
        "responsiveness": "ResponsivenessState",
        "valence": "ValenceState",
        "damage": "DamageState",
        "boundary": "BoundaryState",
        "capacity": "CapacityState",
        "needs": "NeedsState",
    },
    "PersonalityState": {"deep": "DeepPersonality", "surface": "SurfacePersonality"},
    "Dynamics": {
        "affect": "AffectDynamics",
        "moral_state": "MoralState",
        "uncertainty": "UncertaintyState",
        "relational_time": "RelationalTime",
        "hot_pool": "HotPoolDiagnostics",
    },
}

# HealthStatus is a SECOND public typed output (engine.health(), re-exported in
# sylanne_core.__all__) — not reachable from Surface, so it sits outside the tree
# golden, but it is still a downstream-readable contract and gets its own lock.
GOLDEN_HEALTHSTATUS: set[str] = {
    "status",
    "active_sessions",
    "data_dir_exists",
    "llm_configured",
    "embedding_configured",
}


def _llm() -> AsyncMock:
    return AsyncMock(return_value="ok")


def _assert_subtree(emitted: object, cls_name: str, path: str) -> None:
    """Assert the EMITTED dict carries every golden field of ``cls_name``, recursively.

    Walks the golden tree (field names + edges) against real runtime output, so an
    adapter-side drop of ANY leaf — not just the few hot paths — fails CI, even
    though types.py still declares the field.
    """
    assert isinstance(emitted, dict), f"runtime Surface node {path!r} is not a dict"
    for field in GOLDEN_NESTED_FIELDS[cls_name]:
        assert field in emitted, (
            f"runtime Surface dropped {path}.{field!r} — the adapter stopped emitting "
            "a contracted leaf. Additive-only contract (the type may still declare it)."
        )
    for field, child in GOLDEN_EDGES.get(cls_name, {}).items():
        _assert_subtree(emitted[field], child, f"{path}.{field}")


class TestSurfaceContractLock:
    def test_schema_tag_pinned(self):
        assert _SCHEMA_VERSION == SURFACE_SCHEMA_TAG, (
            f"Surface schema tag changed to {_SCHEMA_VERSION!r}. If this is an "
            "intentional breaking change, bump the tag AND update the golden in "
            "this file in the same commit; otherwise you are silently breaking "
            "downstream consumers (e.g. embedded-SDK plugins on an older version)."
        )

    def test_toplevel_fields_not_removed_or_retyped(self):
        ann = dict(t.Surface.__annotations__)
        for name, declared in GOLDEN_SURFACE_TOPLEVEL.items():
            assert name in ann, (
                f"Surface lost top-level field {name!r} — removal breaks every "
                "consumer that reads it. Additive-only contract."
            )
            actual = _ann_str(ann[name])
            assert actual == declared, (
                f"Surface field {name!r} was retyped {declared!r} -> {actual!r}. "
                "Retyping breaks consumers. If intentional, bump the schema tag."
            )

    def test_nested_fields_not_removed(self):
        for cls_name, fields in GOLDEN_NESTED_FIELDS.items():
            cls = getattr(t, cls_name)
            current = set(cls.__annotations__.keys())
            missing = fields - current
            assert not missing, (
                f"{cls_name} lost field(s) {sorted(missing)} — removing a nested "
                "field breaks consumers reading that path. Additive-only contract."
            )

    def test_nested_edges_not_rewired(self):
        # Each parent's annotation for a sub-field must still resolve to the
        # expected nested class. Catches a parent re-pointed at a thinner type
        # (e.g. dict[str, Any]) while the orphaned child class still passes
        # test_nested_fields_not_removed in isolation.
        for parent, edges in GOLDEN_EDGES.items():
            ann = getattr(t, parent).__annotations__
            for field, child in edges.items():
                assert field in ann, f"{parent} lost sub-field {field!r}"
                actual = _ann_str(ann[field])
                assert actual == child, (
                    f"{parent}.{field} was rewired {child!r} -> {actual!r}. The tree "
                    "shape is part of the contract. If intentional, bump the schema tag."
                )

    def test_healthstatus_fields_not_removed(self):
        current = set(t.HealthStatus.__annotations__.keys())
        missing = GOLDEN_HEALTHSTATUS - current
        assert not missing, (
            f"HealthStatus lost field(s) {sorted(missing)} — engine.health() is a "
            "public re-exported output; removing a field breaks its consumers."
        )

    @pytest.mark.asyncio
    async def test_runtime_surface_emits_full_contract(self, tmp_path):
        engine = SylanneEngine(tmp_path, llm=_llm())
        await engine.start()
        surface = await engine.process("s1", "hello")
        try:
            # Every contracted top-level key is actually emitted (debug/pipeline
            # are present even with diagnostics off — None / {} respectively).
            for name in GOLDEN_SURFACE_TOPLEVEL:
                assert name in surface, f"runtime Surface missing top-level {name!r}"
            assert surface["schema_version"] == SURFACE_SCHEMA_TAG
            # Recursively tie the WHOLE declared tree to real output, so an
            # adapter-side drop of any leaf (not just hot paths) is caught even
            # while types.py still declares it.
            for field, child in GOLDEN_EDGES["Surface"].items():
                _assert_subtree(surface[field], child, field)
            # The second public output contract is emitted in full too.
            assert GOLDEN_HEALTHSTATUS.issubset(engine.health())
        finally:
            await engine.shutdown()
