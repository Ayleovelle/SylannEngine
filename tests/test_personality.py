"""Tests for sylanne_core.compute.personality module."""

from sylanne_core.compute.personality import (
    DriftSignalExtractor,
    OscillationDetector,
    TraitMemory,
    compute_embodiment_drift,
    drift_sylanne_traits,
    initial_personality,
    normalize_personality,
    should_explore,
    sylanne_bounds_from_embodiment,
)


class TestTraitMemory:
    def test_initial_value(self):
        tm = TraitMemory(0.6)
        assert tm.value == 0.6
        assert tm.set_point == 0.6

    def test_update_positive(self):
        tm = TraitMemory(0.5)
        actual = tm.update(0.01)
        assert tm.value > 0.5
        assert actual > 0

    def test_update_clamped(self):
        tm = TraitMemory(0.94)
        tm.update(0.1)
        assert tm.value <= 0.95

    def test_freeze(self):
        tm = TraitMemory(0.5)
        tm.freeze(5)
        assert tm.frozen is True
        actual = tm.update(0.1)
        assert actual == 0.0
        assert tm.value == 0.5

    def test_recovery_pull(self):
        tm = TraitMemory(0.5)
        tm.value = 0.8
        pull = tm.recovery_pull()
        assert pull < 0

    def test_roundtrip(self):
        tm = TraitMemory(0.7)
        tm.update(0.02)
        data = tm.to_dict()
        restored = TraitMemory.from_dict(data)
        assert abs(restored.value - tm.value) < 1e-6


class TestOscillationDetector:
    def test_no_oscillation_initially(self):
        od = OscillationDetector()
        assert od.record("trait_a", 0.01) is False
        assert od.record("trait_a", 0.01) is False

    def test_detects_oscillation(self):
        od = OscillationDetector()
        detected = False
        for i in range(12):
            sign = 1.0 if i % 2 == 0 else -1.0
            if od.record("trait_a", sign * 0.01):
                detected = True
                break
        assert detected is True


class TestDriftSignalExtractor:
    def test_empty_result(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({})
        assert isinstance(signals, dict)

    def test_expression_fired(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({"should_express": True})
        assert signals.get("expression_fired") == 1.0

    def test_high_tension(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({"emotion": {"tension": 0.9}})
        assert "high_tension" in signals

    def test_dialogue_quality_high(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({"dialogue_quality": 0.95})
        assert signals.get("dialogue_quality_high", 0.0) > 0.0
        assert "dialogue_quality_low" not in signals

    def test_dialogue_quality_low(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({"dialogue_quality": 0.05})
        assert signals.get("dialogue_quality_low", 0.0) > 0.0
        assert "dialogue_quality_high" not in signals

    def test_dialogue_quality_mid_neutral(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({"dialogue_quality": 0.5})
        assert "dialogue_quality_high" not in signals
        assert "dialogue_quality_low" not in signals

    def test_dialogue_quality_absent(self):
        ext = DriftSignalExtractor()
        signals = ext.extract({"should_express": False})
        assert not any(k.startswith("dialogue_quality") for k in signals)

    def test_dialogue_quality_high_maps_to_traits(self):
        # high-quality 信号经 canonical 漂移应抬升表达欲 + 拉近关系引力
        traits = {
            name: TraitMemory(0.5)
            for name in (
                "expression_drive_trait",
                "perception_acuity",
                "boundary_permeability",
                "inner_order",
                "relational_gravity",
            )
        }
        compute_embodiment_drift(
            traits, {"dialogue_quality_high": 1.0}, tick_count=0, dt=30.0
        )
        assert traits["expression_drive_trait"].value > 0.5
        assert traits["relational_gravity"].value > 0.5


class TestComputeEmbodimentDrift:
    def test_no_signals_no_drift(self):
        traits = {
            name: TraitMemory(0.5)
            for name in (
                "expression_drive_trait",
                "perception_acuity",
                "boundary_permeability",
                "inner_order",
                "relational_gravity",
            )
        }
        compute_embodiment_drift(traits, {}, tick_count=10)
        for tm in traits.values():
            assert abs(tm.value - 0.5) < 0.02

    def test_signal_causes_drift(self):
        traits = {
            name: TraitMemory(0.5)
            for name in (
                "expression_drive_trait",
                "perception_acuity",
                "boundary_permeability",
                "inner_order",
                "relational_gravity",
            )
        }
        signals = {"feedback_accepted": 1.0}
        compute_embodiment_drift(traits, signals, tick_count=10)
        assert traits["expression_drive_trait"].value > 0.5

    def test_dt_scale_amplifies(self):
        def run_drift(dt: float) -> float:
            traits = {
                name: TraitMemory(0.5)
                for name in (
                    "expression_drive_trait",
                    "perception_acuity",
                    "boundary_permeability",
                    "inner_order",
                    "relational_gravity",
                )
            }
            signals = {"feedback_accepted": 1.0}
            compute_embodiment_drift(traits, signals, tick_count=10, dt=dt)
            return traits["expression_drive_trait"].value

        val_30s = run_drift(30.0)
        val_240s = run_drift(240.0)
        assert val_240s > val_30s

    def test_drift_cap(self):
        traits = {
            name: TraitMemory(0.5)
            for name in (
                "expression_drive_trait",
                "perception_acuity",
                "boundary_permeability",
                "inner_order",
                "relational_gravity",
            )
        }
        signals = {
            "feedback_accepted": 1.0,
            "high_tension": 1.0,
            "high_void_pressure": 1.0,
            "high_surprise_positive": 1.0,
        }
        compute_embodiment_drift(traits, signals, tick_count=0, dt=30.0)
        total = sum(abs(tm.value - 0.5) for tm in traits.values())
        assert total <= 0.06


class TestDriftSylanneTraits:
    def test_basic_drift(self):
        personality = initial_personality("test")
        result = drift_sylanne_traits(personality, event={"text": "温柔", "confidence": 0.8})
        assert "traits" in result
        assert result["traits"]["warmth_bias"] >= personality["traits"]["warmth_bias"]

    def test_embodiment_bounds(self):
        personality = initial_personality("test")
        embodiment = {
            "relational_gravity": TraitMemory(0.1),
            "boundary_permeability": TraitMemory(0.5),
            "inner_order": TraitMemory(0.5),
            "expression_drive_trait": TraitMemory(0.5),
            "perception_acuity": TraitMemory(0.5),
        }
        result = drift_sylanne_traits(
            personality,
            event={"text": "温柔靠近想你", "confidence": 1.0},
            embodiment=embodiment,
        )
        bounds = sylanne_bounds_from_embodiment(embodiment)
        lo, hi = bounds["warmth_bias"]
        assert result["traits"]["warmth_bias"] <= hi + 1e-6


class TestInitialPersonality:
    def test_deterministic(self):
        p1 = initial_personality("session_a")
        p2 = initial_personality("session_a")
        assert p1["traits"] == p2["traits"]

    def test_different_sessions(self):
        p1 = initial_personality("session_a")
        p2 = initial_personality("session_b")
        assert p1["signature"] != p2["signature"]

    def test_structure(self):
        p = initial_personality("test")
        assert "schema_version" in p
        assert "traits" in p
        assert "voice" in p
        assert "drift" in p
        assert len(p["traits"]) == 6


class TestNormalizePersonality:
    def test_legacy_to_new(self):
        legacy = {"extraversion": 0.7}
        result = normalize_personality(legacy)
        assert result["expression_drive_trait"] == 0.7

    def test_new_to_legacy(self):
        new = {"expression_drive_trait": 0.8}
        result = normalize_personality(new)
        assert result["extraversion"] == 0.8


class TestShouldExplore:
    def test_high_curiosity_low_entropy(self):
        assert should_explore(0.8, 0.1, 0.6) is True

    def test_low_curiosity(self):
        assert should_explore(0.3, 0.1, 0.6) is False

    def test_low_energy(self):
        assert should_explore(0.8, 0.1, 0.2) is False
