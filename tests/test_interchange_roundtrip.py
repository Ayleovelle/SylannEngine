"""Round-trip test framework for Sylanne interchange format.

Tests the retraction property: serialize(deserialize(serialize(x))) == serialize(x)
This ensures the JSON serialization is a section-retraction pair — no information
is lost or corrupted through the serialize/validate/deserialize cycle.

Run with: pytest tests/test_interchange_roundtrip.py -v
"""

from __future__ import annotations

import json
from typing import Any

import pytest

try:
    from sylanne_core.interchange_validator import (
        SemanticValidationError,
        migrate,
        validate,
        validate_strict,
    )
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)

# ---------------------------------------------------------------------------
# Fixtures: canonical test documents
# ---------------------------------------------------------------------------


def _minimal_valid_doc() -> dict[str, Any]:
    """Minimal valid Level 1 interchange document."""
    return {
        "sylanne_version": "1.0.0",
        "schema_version": 1,
        "session_key": "test-session-001",
        "personality": {
            "openness": 0.7,
            "warmth": 0.8,
            "assertiveness": 0.5,
            "stability": 0.6,
            "sensitivity": 0.4,
        },
        "state": {
            "primary": {"valence": 0.3, "arousal": 0.5, "dominance": 0.4},
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
        "metadata": {"implementation": "sylanne_core", "tier": "pro"},
    }


def _initial_state_doc() -> dict[str, Any]:
    """Document at epoch 0 (initial state)."""
    doc = _minimal_valid_doc()
    doc["state"]["epoch"] = 0
    doc["state"]["confidence"] = 0.0
    doc["scars"] = []
    return doc


def _doc_with_hot_pool() -> dict[str, Any]:
    """Level 2 document with hot_pool extension."""
    doc = _minimal_valid_doc()
    doc["hot_pool"] = {"temperature": 0.4, "volume": 0.6, "pressure": 0.2}
    return doc


# ---------------------------------------------------------------------------
# Serialization helpers (simulate real serialize/deserialize cycle)
# ---------------------------------------------------------------------------


def serialize(doc: dict[str, Any]) -> str:
    """Serialize to JSON string with deterministic key ordering."""
    return json.dumps(doc, sort_keys=True, ensure_ascii=False)


def deserialize(json_str: str) -> dict[str, Any]:
    """Deserialize from JSON string."""
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Verify the retraction property: serialize . deserialize . serialize = serialize."""

    @pytest.mark.parametrize(
        "doc_factory,name",
        [
            (_minimal_valid_doc, "minimal"),
            (_initial_state_doc, "initial_state"),
            (_doc_with_hot_pool, "with_hot_pool"),
        ],
    )
    def test_roundtrip_retraction(self, doc_factory, name):
        """serialize(deserialize(serialize(x))) == serialize(x)"""
        doc = doc_factory()
        first_pass = serialize(doc)
        reconstructed = deserialize(first_pass)
        second_pass = serialize(reconstructed)
        assert first_pass == second_pass, f"Round-trip failed for {name}"

    @pytest.mark.parametrize(
        "doc_factory",
        [_minimal_valid_doc, _initial_state_doc, _doc_with_hot_pool],
    )
    def test_validate_after_roundtrip(self, doc_factory):
        """Document remains valid after round-trip."""
        doc = doc_factory()
        json_str = serialize(doc)
        restored = deserialize(json_str)
        errors = validate(restored)
        assert errors == [], f"Validation errors after round-trip: {errors}"

    def test_deep_equality_preserved(self):
        """Deserialized document is deeply equal to original."""
        doc = _minimal_valid_doc()
        restored = deserialize(serialize(doc))
        assert doc == restored


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Test that the JSON Schema correctly accepts/rejects documents."""

    def test_valid_minimal(self):
        assert validate(_minimal_valid_doc()) == []

    def test_missing_required_field(self):
        doc = _minimal_valid_doc()
        del doc["session_key"]
        errors = validate(doc, semantic=False)
        assert any("session_key" in e for e in errors)

    def test_valence_out_of_range(self):
        doc = _minimal_valid_doc()
        doc["state"]["primary"]["valence"] = 1.5
        errors = validate(doc, semantic=False)
        assert len(errors) > 0

    def test_arousal_negative_rejected(self):
        doc = _minimal_valid_doc()
        doc["state"]["primary"]["arousal"] = -0.1
        errors = validate(doc, semantic=False)
        assert len(errors) > 0

    def test_personality_trait_out_of_range(self):
        doc = _minimal_valid_doc()
        doc["personality"]["openness"] = 1.5
        errors = validate(doc, semantic=False)
        assert len(errors) > 0

    def test_scar_missing_source_tag(self):
        doc = _minimal_valid_doc()
        del doc["scars"][0]["source_tag"]
        errors = validate(doc, semantic=False)
        assert len(errors) > 0

    def test_schema_version_must_be_positive_int(self):
        doc = _minimal_valid_doc()
        doc["schema_version"] = 0
        errors = validate(doc, semantic=False)
        assert len(errors) > 0

    def test_extra_properties_rejected_at_top_level(self):
        doc = _minimal_valid_doc()
        doc["unknown_field"] = "surprise"
        errors = validate(doc, semantic=False)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Semantic rule tests
# ---------------------------------------------------------------------------


class TestSemanticRules:
    """Test cross-field validation rules beyond JSON Schema."""

    def test_initial_state_confidence_must_be_zero(self):
        doc = _minimal_valid_doc()
        doc["state"]["epoch"] = 0
        doc["state"]["confidence"] = 0.5  # violation
        with pytest.raises(SemanticValidationError, match="initial_confidence"):
            validate_strict(doc)

    def test_initial_state_valid_when_confidence_zero(self):
        doc = _initial_state_doc()
        errors = validate(doc)
        assert errors == []

    def test_personality_all_zero_rejected(self):
        doc = _minimal_valid_doc()
        for key in doc["personality"]:
            doc["personality"][key] = 0.0
        with pytest.raises(SemanticValidationError, match="personality_all_zero"):
            validate_strict(doc)

    def test_personality_all_one_rejected(self):
        doc = _minimal_valid_doc()
        for key in doc["personality"]:
            doc["personality"][key] = 1.0
        with pytest.raises(SemanticValidationError, match="personality_all_one"):
            validate_strict(doc)

    def test_scars_out_of_order_rejected(self):
        doc = _minimal_valid_doc()
        doc["scars"] = [
            {"dimension": 0, "intensity": 0.5, "created_at": 5000, "source_tag": "a"},
            {"dimension": 1, "intensity": 0.3, "created_at": 1000, "source_tag": "b"},
        ]
        with pytest.raises(SemanticValidationError, match="scar_order"):
            validate_strict(doc)

    def test_scars_equal_timestamps_allowed(self):
        doc = _minimal_valid_doc()
        doc["scars"] = [
            {"dimension": 0, "intensity": 0.5, "created_at": 1000, "source_tag": "a"},
            {"dimension": 1, "intensity": 0.3, "created_at": 1000, "source_tag": "b"},
        ]
        errors = validate(doc)
        assert errors == []


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestMigration:
    """Test schema version migration support."""

    def test_migrate_v1_to_v1_is_identity(self):
        doc = _minimal_valid_doc()
        result = migrate(doc, target_version=1)
        assert result == doc

    def test_migrate_unknown_version_raises(self):
        doc = _minimal_valid_doc()
        doc["schema_version"] = 99
        with pytest.raises(ValueError, match="No migration path"):
            migrate(doc, target_version=1)
