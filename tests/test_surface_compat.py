"""Surface schema compatibility guardrail — additive-only contract lock.

Cross-plugin / cross-version sharing only stays safe if the Surface stays
ADDITIVE-ONLY: a consumer pinned to an older SDK must keep finding every field it
already reads. These tests freeze the CURRENT Surface contract so that REMOVING a
field, RETYPING a top-level field, or BUMPING the schema tag fails CI loudly.
Adding new (optional) fields is always allowed — the golden checks containment,
never equality.

If you intentionally break the contract, do it consciously: bump
``sylanne.engine.vN`` AND update the golden in this file in the SAME commit. That
is the "I am breaking downstream consumers, on purpose" gate — see
SHARING_INTEGRATION.md.
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


def _llm() -> AsyncMock:
    return AsyncMock(return_value="ok")


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
            # Tie the declared contract to real output on the hottest deep paths a
            # downstream consumer navigates, so an adapter-side removal is caught too.
            assert "beat" in surface["state"]["rhythm"]
            assert "action" in surface["decision"]
            assert "allowed" in surface["guard"]
            assert {"deep", "surface"} <= surface["personality"].keys()
            assert "valence" in surface["pad"]
            assert "hot_pool" in surface["dynamics"]
        finally:
            await engine.shutdown()
