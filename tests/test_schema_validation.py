"""Tests for sylanne_core.schema — the zero-dependency serialization validator.

Covers:
    - Structural validation (type, bounds, required fields, patterns)
    - Cross-field semantic validation
    - Round-trip: SylanneCore.snapshot() -> validate -> restore -> compare
    - Round-trip: SylanneAlphaHost.snapshot() -> validate -> restore -> compare
    - Migration framework

Run with: pytest tests/test_schema_validation.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from sylanne_core.schema import (
    CURRENT_SCHEMA_VERSION,
    SYLANNE_SCHEMA,
    migrate,
    validate,
    validate_cross_field,
)
from sylanne_core.standard import SylanneCore, SylanneStimulus

# ---------------------------------------------------------------------------
# Fixtures: canonical test documents
# ---------------------------------------------------------------------------


def _minimal_doc() -> dict[str, Any]:
    """Smallest valid interchange document."""
    return {
        "sylanne_version": "1.0.0",
        "schema_version": 1,
        "session_key": "test-session",
        "personality": {
            "openness": 0.6,
            "warmth": 0.7,
            "assertiveness": 0.5,
            "stability": 0.6,
            "sensitivity": 0.4,
        },
        "state": {
            "primary": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5},
            "mood": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5},
            "delta": {"valence": 0.0, "arousal": 0.0, "dominance": 0.0},
            "confidence": 0.0,
            "epoch": 0,
        },
        "scars": [],
        "metadata": {"implementation": "sylanne_core"},
    }


def _full_doc() -> dict[str, Any]:
    """Document with all optional fields populated."""
    return {
        "sylanne_version": "1.0.0-rc3",
        "schema_version": 1,
        "session_key": "full-session-xyz",
        "personality": {
            "openness": 0.7,
            "warmth": 0.8,
            "assertiveness": 0.5,
            "stability": 0.6,
            "sensitivity": 0.4,
            "curiosity": 0.65,  # extension trait
        },
        "state": {
            "primary": {"valence": 0.3, "arousal": 0.6, "dominance": 0.4},
            "mood": {"valence": 0.1, "arousal": 0.3, "dominance": 0.5},
            "delta": {"valence": 0.05, "arousal": 0.02, "dominance": -0.01},
            "confidence": 0.85,
            "epoch": 42,
        },
        "scars": [
            {
                "dimension": 0,
                "intensity": 0.6,
                "created_at": 1000,
                "source_tag": "boundary_violation",
            },
            {
                "dimension": 2,
                "intensity": 0.3,
                "created_at": 2000,
                "source_tag": "trust_repair",
            },
        ],
        "hot_pool": {"temperature": 0.4, "volume": 0.6, "pressure": 0.2},
        "metadata": {"implementation": "sylanne_core", "tier": "pro"},
    }


# ---------------------------------------------------------------------------
# Structural validation tests
# ---------------------------------------------------------------------------


class TestValidMinimalDocument:
    """Smallest valid document passes validation."""

    def test_valid_minimal_document(self):
        doc = _minimal_doc()
        is_valid, errors = validate(doc)
        assert is_valid is True
        assert errors == []


class TestValidFullDocument:
    """Document with all optional fields passes validation."""

    def test_valid_full_document(self):
        doc = _full_doc()
        is_valid, errors = validate(doc)
        assert is_valid is True
        assert errors == []


class TestInvalidOutOfRange:
    """Out-of-range numeric values are rejected."""

    def test_valence_too_high(self):
        doc = _minimal_doc()
        doc["state"]["primary"]["valence"] = 2.0
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("valence" in e and "maximum" in e for e in errors)

    def test_valence_too_low(self):
        doc = _minimal_doc()
        doc["state"]["primary"]["valence"] = -1.5
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("valence" in e and "minimum" in e for e in errors)

    def test_arousal_negative(self):
        doc = _minimal_doc()
        doc["state"]["primary"]["arousal"] = -0.1
        is_valid, errors = validate(doc)
        assert is_valid is False

    def test_personality_trait_above_one(self):
        doc = _minimal_doc()
        doc["personality"]["openness"] = 1.5
        is_valid, errors = validate(doc)
        assert is_valid is False

    def test_scar_intensity_above_one(self):
        doc = _full_doc()
        doc["scars"][0]["intensity"] = 1.2
        is_valid, errors = validate(doc)
        assert is_valid is False


class TestInvalidMissingRequired:
    """Missing required fields are rejected."""

    def test_missing_session_key(self):
        doc = _minimal_doc()
        del doc["session_key"]
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("session_key" in e for e in errors)

    def test_missing_personality(self):
        doc = _minimal_doc()
        del doc["personality"]
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("personality" in e for e in errors)

    def test_missing_state(self):
        doc = _minimal_doc()
        del doc["state"]
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("state" in e for e in errors)

    def test_missing_personality_core_trait(self):
        doc = _minimal_doc()
        del doc["personality"]["openness"]
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("openness" in e for e in errors)

    def test_missing_scar_source_tag(self):
        doc = _full_doc()
        del doc["scars"][0]["source_tag"]
        is_valid, errors = validate(doc)
        assert is_valid is False


class TestInvalidWrongType:
    """Wrong types are rejected."""

    def test_personality_as_array(self):
        doc = _minimal_doc()
        doc["personality"] = [0.5, 0.6, 0.7, 0.8, 0.9]
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("personality" in e for e in errors)

    def test_session_key_as_int(self):
        doc = _minimal_doc()
        doc["session_key"] = 12345
        is_valid, errors = validate(doc)
        assert is_valid is False

    def test_schema_version_as_string(self):
        doc = _minimal_doc()
        doc["schema_version"] = "1"
        is_valid, errors = validate(doc)
        assert is_valid is False

    def test_scars_as_dict(self):
        doc = _minimal_doc()
        doc["scars"] = {"scar1": "data"}
        is_valid, errors = validate(doc)
        assert is_valid is False

    def test_epoch_as_float(self):
        doc = _minimal_doc()
        doc["state"]["epoch"] = 1.5
        is_valid, errors = validate(doc)
        assert is_valid is False


class TestAdditionalProperties:
    """additionalProperties enforcement."""

    def test_extra_top_level_field_rejected(self):
        doc = _minimal_doc()
        doc["unknown_field"] = "surprise"
        is_valid, errors = validate(doc)
        assert is_valid is False
        assert any("unknown_field" in e for e in errors)

    def test_extra_state_field_rejected(self):
        doc = _minimal_doc()
        doc["state"]["extra"] = 99
        is_valid, errors = validate(doc)
        assert is_valid is False

    def test_hot_pool_extra_fields_allowed(self):
        """hot_pool uses additionalProperties: true for forward compat."""
        doc = _full_doc()
        doc["hot_pool"]["custom_metric"] = 0.9
        is_valid, errors = validate(doc)
        assert is_valid is True


# ---------------------------------------------------------------------------
# Cross-field (semantic) validation tests
# ---------------------------------------------------------------------------


class TestCrossFieldValidation:
    """Semantic rules beyond structural schema."""

    def test_initial_confidence_must_be_zero(self):
        doc = _minimal_doc()
        doc["state"]["epoch"] = 0
        doc["state"]["confidence"] = 0.5  # violation
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is False
        assert any("initial_confidence" in e for e in errors)

    def test_initial_state_valid_when_confidence_zero(self):
        doc = _minimal_doc()
        doc["state"]["epoch"] = 0
        doc["state"]["confidence"] = 0.0
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is True

    def test_personality_all_zero_rejected(self):
        doc = _minimal_doc()
        for key in doc["personality"]:
            doc["personality"][key] = 0.0
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is False
        assert any("personality_all_zero" in e for e in errors)

    def test_personality_all_one_rejected(self):
        doc = _minimal_doc()
        for key in doc["personality"]:
            doc["personality"][key] = 1.0
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is False
        assert any("personality_all_one" in e for e in errors)

    def test_scars_out_of_order_rejected(self):
        doc = _full_doc()
        doc["scars"] = [
            {"dimension": 0, "intensity": 0.5, "created_at": 5000, "source_tag": "a"},
            {"dimension": 1, "intensity": 0.3, "created_at": 1000, "source_tag": "b"},
        ]
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is False
        assert any("scar_order" in e for e in errors)

    def test_scars_equal_timestamps_allowed(self):
        doc = _full_doc()
        doc["scars"] = [
            {"dimension": 0, "intensity": 0.5, "created_at": 1000, "source_tag": "a"},
            {"dimension": 1, "intensity": 0.3, "created_at": 1000, "source_tag": "b"},
        ]
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is True

    def test_schema_version_mismatch(self):
        doc = _minimal_doc()
        doc["schema_version"] = 99
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is False
        assert any("schema_version" in e for e in errors)

    def test_negative_epoch_rejected(self):
        doc = _minimal_doc()
        doc["state"]["epoch"] = -1
        is_valid, errors = validate_cross_field(doc)
        assert is_valid is False
        assert any("epoch" in e for e in errors)


# ---------------------------------------------------------------------------
# Round-trip tests: Layer 0 (SylanneCore)
# ---------------------------------------------------------------------------


def _core_snapshot_to_interchange(core: SylanneCore) -> dict[str, Any]:
    """Convert a SylanneCore snapshot to interchange format for validation."""
    snap = core.snapshot()
    state = snap["state"]
    return {
        "sylanne_version": "1.0.0",
        "schema_version": 1,
        "session_key": "roundtrip-layer0",
        "personality": {
            "openness": 0.6,
            "warmth": 0.7,
            "assertiveness": 0.5,
            "stability": 0.6,
            "sensitivity": 0.4,
        },
        "state": {
            "primary": state["primary"],
            "mood": state["mood"],
            "delta": state["last_delta"],
            "confidence": 0.0 if state["epoch"] == 0 else 0.5,
            "epoch": state["epoch"],
        },
        "scars": [],
        "metadata": {"source": "SylanneCore.snapshot()"},
    }


class TestRoundTripLayer0:
    """SylanneCore.snapshot() -> validate -> SylanneCore.restore() -> compare."""

    def test_round_trip_layer0(self):
        core = SylanneCore()
        # Process a few stimuli to get non-trivial state
        core.process(
            SylanneStimulus(valence=0.5, arousal=0.6, dominance=0.4, magnitude=0.8, timestamp=1)
        )
        core.process(
            SylanneStimulus(valence=-0.3, arousal=0.2, dominance=0.7, magnitude=0.5, timestamp=2)
        )

        # Snapshot -> interchange format -> validate
        interchange = _core_snapshot_to_interchange(core)
        is_valid, errors = validate(interchange)
        assert is_valid is True, f"Validation errors: {errors}"

        # Restore from original snapshot and compare
        snap = core.snapshot()
        restored = SylanneCore.restore(snap)
        restored_snap = restored.snapshot()

        assert snap["state"]["primary"] == restored_snap["state"]["primary"]
        assert snap["state"]["mood"] == restored_snap["state"]["mood"]
        assert snap["state"]["epoch"] == restored_snap["state"]["epoch"]


# ---------------------------------------------------------------------------
# Round-trip tests: Full (SylanneAlphaHost)
# ---------------------------------------------------------------------------


class TestRoundTripFull:
    """SylanneAlphaHost.snapshot() -> validate -> restore -> compare."""

    def test_round_trip_full(self, tmp_path):
        from sylanne_core.compute.host import SylanneAlphaHost

        host = SylanneAlphaHost(root=tmp_path, session_key="rt-full")
        # Drive a tick to populate state
        host.on_request(
            {
                "text": "hello",
                "confidence": 0.7,
                "flags": ["safe"],
                "now": 1000.0,
                "values": {},
            }
        )

        snap = host.snapshot()

        # Validate the snapshot has expected structure
        assert "schema_version" in snap
        assert "session_key" in snap
        assert snap["session_key"] == "rt-full"
        assert "body" in snap
        assert "personality" in snap

        # Restore from snapshot
        from sylanne_core.compute.kernel import AlphaKernel

        restored_kernel = AlphaKernel.restore(snap)
        restored_snap = restored_kernel.snapshot()

        # Key fields must match
        assert restored_snap["session_key"] == snap["session_key"]
        assert restored_snap["turns"] == snap["turns"]
        assert restored_snap["body"] == snap["body"]


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestMigration:
    """Schema version migration framework."""

    def test_migration_v1_to_v1_identity(self):
        doc = _minimal_doc()
        result = migrate(doc, target_version=1)
        assert result == doc
        # Must be a deep copy, not the same object
        assert result is not doc

    def test_migration_unknown_version_raises(self):
        doc = _minimal_doc()
        doc["schema_version"] = 99
        with pytest.raises(ValueError, match="No migration path"):
            migrate(doc, target_version=1)

    def test_migration_forward_compat(self):
        """Adding unknown fields to metadata still validates (open schema)."""
        doc = _full_doc()
        doc["metadata"]["future_field"] = {"nested": True}
        doc["metadata"]["experiment_id"] = "abc-123"
        is_valid, errors = validate(doc)
        assert is_valid is True
        assert errors == []


# ---------------------------------------------------------------------------
# Schema object tests
# ---------------------------------------------------------------------------


class TestSchemaObject:
    """Verify the SYLANNE_SCHEMA dict itself."""

    def test_schema_is_dict(self):
        assert isinstance(SYLANNE_SCHEMA, dict)

    def test_schema_has_required_fields(self):
        assert "required" in SYLANNE_SCHEMA
        required = SYLANNE_SCHEMA["required"]
        assert "sylanne_version" in required
        assert "schema_version" in required
        assert "session_key" in required
        assert "personality" in required
        assert "state" in required
        assert "scars" in required
        assert "metadata" in required

    def test_current_schema_version(self):
        assert CURRENT_SCHEMA_VERSION == 1
