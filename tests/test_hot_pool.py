"""Comprehensive unit tests for sylanne_core.compute.hot_pool module."""

from __future__ import annotations

import time

import pytest

from sylanne_core.compute.hot_pool import (
    CascadeState,
    CollapseRecord,
    HotMaterial,
    HotPool,
    Influence,
    _clamp,
    _safe_float,
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _make_influence(
    inf_type: str = "reinforcement",
    intensity: float = 0.5,
    target_dimension: str = "test_dim",
    source: str = "test_source",
) -> Influence:
    """Factory for Influence objects with sensible defaults."""
    return Influence(
        source=source,
        type=inf_type,  # type: ignore[arg-type]
        intensity=intensity,
        target_dimension=target_dimension,
        timestamp=time.time(),
    )


def _make_pool_with_material(
    heat: float = 0.5, mass: float = 0.5, origin_type: str = "test"
) -> tuple[HotPool, HotMaterial]:
    """Create a pool with a single pre-loaded material."""
    pool = HotPool()
    mat = HotMaterial(
        id="mat_001",
        origin_type=origin_type,
        heat=heat,
        mass=mass,
        peak_heat=heat,
        last_ignition=time.time(),
    )
    pool._materials.append(mat)
    return pool, mat


# ---------------------------------------------------------------------------
# Tests: helper functions
# ---------------------------------------------------------------------------


class TestClamp:
    def test_clamp_within_range(self):
        assert _clamp(0.5) == 0.5

    def test_clamp_below_lo(self):
        assert _clamp(-0.1) == 0.0

    def test_clamp_above_hi(self):
        assert _clamp(1.5) == 1.0

    def test_clamp_custom_bounds(self):
        assert _clamp(5.0, lo=2.0, hi=4.0) == 4.0
        assert _clamp(1.0, lo=2.0, hi=4.0) == 2.0


class TestSafeFloat:
    def test_valid_number(self):
        assert _safe_float(3.14) == 3.14

    def test_string_number(self):
        assert _safe_float("2.5") == 2.5

    def test_invalid_string(self):
        assert _safe_float("abc", 0.0) == 0.0

    def test_none_returns_default(self):
        assert _safe_float(None, 1.0) == 1.0

    def test_inf_returns_default(self):
        assert _safe_float(float("inf"), 0.0) == 0.0

    def test_nan_returns_default(self):
        assert _safe_float(float("nan"), 0.0) == 0.0


# ---------------------------------------------------------------------------
# Tests: HotMaterial
# ---------------------------------------------------------------------------


class TestHotMaterial:
    def test_default_values(self):
        mat = HotMaterial(id="m1", origin_type="test")
        assert mat.heat == 0.0
        assert mat.mass == 0.0
        assert mat.age_ticks == 0
        assert mat.reflection_count == 0
        assert mat.peak_heat == 0.0

    def test_to_dict_roundtrip(self):
        mat = HotMaterial(
            id="m1",
            origin_type="wound",
            heat=0.7,
            mass=0.4,
            age_ticks=5,
            reflection_count=2,
            peak_heat=0.8,
            source_text_hash=12345,
        )
        d = mat.to_dict()
        restored = HotMaterial.from_dict(d)
        assert restored.id == mat.id
        assert restored.origin_type == mat.origin_type
        assert abs(restored.heat - mat.heat) < 1e-5
        assert abs(restored.mass - mat.mass) < 1e-5
        assert restored.age_ticks == mat.age_ticks
        assert restored.reflection_count == mat.reflection_count
        assert abs(restored.peak_heat - mat.peak_heat) < 1e-5
        assert restored.source_text_hash == mat.source_text_hash

    def test_from_dict_missing_fields(self):
        mat = HotMaterial.from_dict({})
        assert mat.id == "unknown"
        assert mat.origin_type == "unknown"
        assert mat.heat == 0.0


# ---------------------------------------------------------------------------
# Tests: CascadeState
# ---------------------------------------------------------------------------


class TestCascadeState:
    def test_default_state(self):
        cs = CascadeState()
        assert cs.active is False
        assert cs.intensity == 0.0
        assert cs.momentum == 0.0
        assert cs.ticks_above_critical == 0
        assert cs.sensitivity_multiplier == 1.0

    def test_reset(self):
        cs = CascadeState(
            active=True,
            intensity=0.8,
            momentum=0.6,
            ticks_above_critical=10,
            sensitivity_multiplier=2.5,
        )
        cs.reset()
        assert cs.active is False
        assert cs.intensity == 0.0
        assert cs.momentum == 0.0
        assert cs.ticks_above_critical == 0
        assert cs.sensitivity_multiplier == 1.0

    def test_to_dict_roundtrip(self):
        cs = CascadeState(
            active=True,
            intensity=0.7,
            momentum=0.4,
            ticks_above_critical=3,
            sensitivity_multiplier=2.0,
            peak_intensity=0.9,
        )
        d = cs.to_dict()
        restored = CascadeState.from_dict(d)
        assert restored.active is True
        assert abs(restored.intensity - 0.7) < 1e-5
        assert abs(restored.momentum - 0.4) < 1e-5
        assert restored.ticks_above_critical == 3
        assert abs(restored.sensitivity_multiplier - 2.0) < 1e-5
        assert abs(restored.peak_intensity - 0.9) < 1e-5


# ---------------------------------------------------------------------------
# Tests: CollapseRecord
# ---------------------------------------------------------------------------


class TestCollapseRecord:
    def test_to_dict_roundtrip(self):
        record = CollapseRecord(
            timestamp=1000.0,
            trigger_temperature=0.9,
            trigger_pressure=0.8,
            cascade_duration_ticks=12,
            pre_collapse_traits={"neuroticism": 0.6},
            post_collapse_traits={"neuroticism": 0.8},
            trait_deltas={"neuroticism": 0.2},
            recovery_ticks_remaining=45,
        )
        d = record.to_dict()
        restored = CollapseRecord.from_dict(d)
        assert abs(restored.timestamp - 1000.0) < 1e-5
        assert abs(restored.trigger_temperature - 0.9) < 1e-5
        assert restored.cascade_duration_ticks == 12
        assert restored.trait_deltas == {"neuroticism": 0.2}
        assert restored.recovery_ticks_remaining == 45


# ---------------------------------------------------------------------------
# Tests: HotPool — Basic Thermodynamics
# ---------------------------------------------------------------------------


class TestHotPoolThermodynamics:
    def test_empty_pool_has_zero_state(self):
        pool = HotPool()
        assert pool.temperature == 0.0
        assert pool.volume == 0.0
        assert pool.pressure == 0.0
        assert pool.materials == []

    def test_adding_material_increases_temperature_and_volume(self):
        pool = HotPool()
        pool._materials.append(HotMaterial(id="m1", origin_type="test", heat=0.8, mass=0.6))
        pool.tick()
        # After tick, temperature and volume should be positive
        assert pool.temperature > 0.0
        assert pool.volume > 0.0

    def test_passive_cooling_reduces_heat(self):
        pool, mat = _make_pool_with_material(heat=0.8, mass=0.5)
        initial_heat = mat.heat
        pool.tick()
        assert mat.heat < initial_heat

    def test_dead_materials_are_cleaned_up(self):
        pool = HotPool()
        # Material with near-zero heat and mass should be removed
        pool._materials.append(HotMaterial(id="dead", origin_type="test", heat=0.0005, mass=0.005))
        pool.tick()
        assert len(pool.materials) == 0

    def test_pressure_grows_with_volume(self):
        pool, _ = _make_pool_with_material(heat=0.8, mass=0.8)
        pool.tick()
        p1 = pool.pressure
        pool.tick()
        p2 = pool.pressure
        # Pressure should grow when there is volume
        assert p2 > p1

    def test_pressure_decays_when_temperature_low(self):
        pool = HotPool()
        pool._pressure = 0.5
        # No materials, temperature will be low
        pool.tick()
        assert pool.pressure < 0.5

    def test_age_ticks_increments(self):
        pool, mat = _make_pool_with_material(heat=0.5, mass=0.5)
        assert mat.age_ticks == 0
        pool.tick()
        assert mat.age_ticks == 1
        pool.tick()
        assert mat.age_ticks == 2


# ---------------------------------------------------------------------------
# Tests: HotPool — Influence Reception
# ---------------------------------------------------------------------------


class TestInfluenceReception:
    def test_contradiction_reignites_existing_material(self):
        pool, mat = _make_pool_with_material(heat=0.3, mass=0.5, origin_type="contradiction")
        mat.reflection_count = 3
        initial_heat = mat.heat
        inf = _make_influence(
            inf_type="contradiction", intensity=0.8, target_dimension="contradiction"
        )
        pool.receive_influence(inf)
        assert mat.heat > initial_heat
        assert mat.reflection_count == 0  # reset by contradiction

    def test_contradiction_creates_new_material_if_no_match(self):
        pool = HotPool()
        inf = _make_influence(
            inf_type="contradiction", intensity=0.7, target_dimension="nonexistent"
        )
        pool.receive_influence(inf)
        assert len(pool.materials) == 1
        assert pool.materials[0].origin_type == "contradiction"

    def test_reinforcement_heats_and_adds_mass(self):
        pool, mat = _make_pool_with_material(heat=0.3, mass=0.3, origin_type="reinforcement")
        initial_heat = mat.heat
        initial_mass = mat.mass
        inf = _make_influence(
            inf_type="reinforcement", intensity=0.6, target_dimension="reinforcement"
        )
        pool.receive_influence(inf)
        assert mat.heat > initial_heat
        assert mat.mass > initial_mass

    def test_revelation_creates_new_material(self):
        pool = HotPool()
        inf = _make_influence(inf_type="revelation", intensity=0.8, target_dimension="new_dim")
        pool.receive_influence(inf)
        assert len(pool.materials) == 1
        assert pool.materials[0].origin_type == "revelation"
        assert pool.materials[0].heat > 0.0

    def test_revelation_heats_existing_material(self):
        pool, mat = _make_pool_with_material(heat=0.2, mass=0.2, origin_type="revelation")
        initial_heat = mat.heat
        inf = _make_influence(inf_type="revelation", intensity=0.9, target_dimension="revelation")
        pool.receive_influence(inf)
        assert mat.heat > initial_heat

    def test_betrayal_global_heat_spike(self):
        pool = HotPool()
        # Add two existing materials
        mat1 = HotMaterial(id="m1", origin_type="test1", heat=0.2, mass=0.3)
        mat2 = HotMaterial(id="m2", origin_type="test2", heat=0.3, mass=0.4)
        pool._materials.extend([mat1, mat2])
        inf = _make_influence(inf_type="betrayal", intensity=0.9, target_dimension="trust")
        pool.receive_influence(inf)
        # All existing materials should be heated
        assert mat1.heat > 0.2
        assert mat2.heat > 0.3
        # New high-heat material created
        assert len(pool.materials) == 3
        new_mat = pool.materials[-1]
        assert new_mat.origin_type == "betrayal"
        assert new_mat.heat > 0.7

    def test_validation_cools_all_materials(self):
        pool = HotPool()
        mat1 = HotMaterial(id="m1", origin_type="test1", heat=0.8, mass=0.5)
        mat2 = HotMaterial(id="m2", origin_type="test2", heat=0.6, mass=0.4)
        pool._materials.extend([mat1, mat2])
        inf = _make_influence(inf_type="validation", intensity=0.8, target_dimension="any")
        pool.receive_influence(inf)
        assert mat1.heat < 0.8
        assert mat2.heat < 0.6

    def test_cascade_amplifies_influence(self):
        pool, mat = _make_pool_with_material(heat=0.3, mass=0.5, origin_type="reinforcement")
        # Activate cascade manually
        pool._cascade.active = True
        pool._cascade.sensitivity_multiplier = 2.0
        initial_heat = mat.heat
        inf = _make_influence(
            inf_type="reinforcement", intensity=0.4, target_dimension="reinforcement"
        )
        pool.receive_influence(inf)
        # Effective intensity = 0.4 * 2.0 = 0.8, heat_delta = 0.8 * 0.5 = 0.4
        assert mat.heat > initial_heat + 0.3  # significant boost


# ---------------------------------------------------------------------------
# Tests: HotPool — Cascade Mechanics
# ---------------------------------------------------------------------------


class TestCascadeMechanics:
    def test_cascade_activates_when_score_exceeds_trigger(self):
        pool = HotPool()
        pool._cascade_trigger = 0.3
        # Set temperature and pressure so their product exceeds trigger
        pool._temperature = 0.8
        pool._pressure = 0.6
        # cascade_score = 0.8 * 0.6 = 0.48 > 0.3
        pool._evolve_cascade(0.48)
        assert pool.cascade.active is True
        assert pool.cascade.sensitivity_multiplier > 1.0

    def test_cascade_does_not_activate_below_trigger(self):
        pool = HotPool()
        pool._cascade_trigger = 0.6
        pool._evolve_cascade(0.3)
        assert pool.cascade.active is False

    def test_sensitivity_multiplier_increases_during_cascade(self):
        pool = HotPool()
        pool._cascade_trigger = 0.3
        pool._evolve_cascade(0.8)  # activate
        assert pool.cascade.sensitivity_multiplier > 1.0
        # Higher intensity -> higher multiplier
        initial_mult = pool.cascade.sensitivity_multiplier
        pool._evolve_cascade(0.95)
        assert pool.cascade.sensitivity_multiplier >= initial_mult

    def test_cascade_deactivates_when_score_drops_and_momentum_depletes(self):
        pool = HotPool()
        pool._cascade_trigger = 0.3
        pool._evolve_cascade(0.5)  # activate
        assert pool.cascade.active is True
        # Drop below trigger repeatedly to deplete momentum
        for _ in range(20):
            pool._evolve_cascade(0.1)
        assert pool.cascade.active is False
        assert pool.cascade.sensitivity_multiplier == 1.0

    def test_ticks_above_critical_increments(self):
        pool = HotPool()
        pool._cascade_trigger = 0.3
        pool._collapse_threshold = 0.5
        # Activate with intensity above collapse_threshold
        pool._evolve_cascade(0.8)
        assert pool.cascade.active is True
        assert pool.cascade.ticks_above_critical == 1
        pool._evolve_cascade(0.9)
        assert pool.cascade.ticks_above_critical == 2

    def test_ticks_above_critical_decrements_below_threshold(self):
        pool = HotPool()
        pool._cascade_trigger = 0.3
        pool._collapse_threshold = 0.8
        # Activate with intensity below collapse_threshold
        pool._evolve_cascade(0.5)  # activate, intensity=0.5 < 0.8
        assert pool.cascade.active is True
        # ticks_above_critical should not increment (intensity < threshold)
        assert pool.cascade.ticks_above_critical == 0


# ---------------------------------------------------------------------------
# Tests: HotPool — Personality Collapse
# ---------------------------------------------------------------------------


class TestPersonalityCollapse:
    def _setup_collapse_ready_pool(self) -> HotPool:
        """Create a pool on the verge of collapse."""
        pool = HotPool()
        pool._cascade_trigger = 0.1
        pool._collapse_threshold = 0.2
        pool._neuroticism = 1.0  # collapse_ticks_required = 5
        pool._decay_rate = 0.001  # minimal cooling
        pool._pressure_growth_rate = 0.05
        # Add high-heat materials
        for i in range(5):
            pool._materials.append(
                HotMaterial(
                    id=f"hot_{i}",
                    origin_type="betrayal",
                    heat=0.95,
                    mass=0.8,
                    peak_heat=0.95,
                )
            )
        return pool

    def test_collapse_triggers_after_sustained_critical_ticks(self):
        pool = self._setup_collapse_ready_pool()
        collapse_record = None
        for _ in range(100):
            result = pool.tick()
            if result is not None:
                collapse_record = result
                break
        assert collapse_record is not None
        assert isinstance(collapse_record, CollapseRecord)
        assert collapse_record.trait_deltas != {}

    def test_collapse_returns_record_with_trait_deltas(self):
        pool = self._setup_collapse_ready_pool()
        collapse_record = None
        for _ in range(100):
            result = pool.tick()
            if result is not None:
                collapse_record = result
                break
        assert collapse_record is not None
        # Betrayal-dominated collapse should have specific deltas
        assert "neuroticism" in collapse_record.trait_deltas
        assert "agreeableness" in collapse_record.trait_deltas

    def test_pool_enters_recovery_after_collapse(self):
        pool = self._setup_collapse_ready_pool()
        for _ in range(100):
            result = pool.tick()
            if result is not None:
                break
        assert pool.in_recovery is True
        assert pool.recovery_ticks_remaining > 0

    def test_materials_partially_drained_after_collapse(self):
        pool = self._setup_collapse_ready_pool()
        # Record pre-collapse heat
        for _ in range(100):
            result = pool.tick()
            if result is not None:
                break
        # After collapse, materials should have reduced heat and mass
        for mat in pool.materials:
            # Heat should be significantly reduced (multiplied by 0.3)
            assert mat.heat < 0.5

    def test_recovery_period_counts_down(self):
        pool = HotPool()
        pool._in_recovery = True
        pool._recovery_ticks_remaining = 5
        pool.tick()
        assert pool.recovery_ticks_remaining == 4
        for _ in range(4):
            pool.tick()
        assert pool.in_recovery is False
        assert pool.recovery_ticks_remaining == 0


# ---------------------------------------------------------------------------
# Tests: HotPool — Personality Influence
# ---------------------------------------------------------------------------


class TestPersonalityInfluence:
    def test_high_neuroticism_lowers_cascade_trigger(self):
        pool = HotPool()
        pool.apply_personality({"neuroticism": 0.9})
        # cascade_trigger = 0.8 - 0.9 * 0.4 = 0.44
        assert pool._cascade_trigger < 0.5

    def test_high_neuroticism_lowers_collapse_threshold(self):
        pool = HotPool()
        pool.apply_personality({"neuroticism": 0.9})
        # collapse_threshold = 0.9 - 0.9 * 0.3 = 0.63
        assert pool._collapse_threshold < 0.7

    def test_low_neuroticism_raises_thresholds(self):
        pool = HotPool()
        pool.apply_personality({"neuroticism": 0.1})
        # cascade_trigger = 0.8 - 0.1 * 0.4 = 0.76
        assert pool._cascade_trigger > 0.7
        # collapse_threshold = 0.9 - 0.1 * 0.3 = 0.87
        assert pool._collapse_threshold > 0.8

    def test_high_conscientiousness_increases_decay_rate(self):
        pool = HotPool()
        pool.apply_personality({"conscientiousness": 0.9})
        # decay_rate = 0.01 + 0.9 * 0.03 = 0.037
        assert pool._decay_rate > 0.03

    def test_low_conscientiousness_low_decay_rate(self):
        pool = HotPool()
        pool.apply_personality({"conscientiousness": 0.1})
        # decay_rate = 0.01 + 0.1 * 0.03 = 0.013
        assert pool._decay_rate < 0.015

    def test_apply_personality_derives_all_thresholds(self):
        pool = HotPool()
        personality = {
            "neuroticism": 0.6,
            "conscientiousness": 0.7,
            "openness": 0.5,
            "agreeableness": 0.8,
        }
        pool.apply_personality(personality)
        # Verify all derived values are in expected ranges
        assert 0.4 <= pool._cascade_trigger <= 0.8
        assert 0.6 <= pool._collapse_threshold <= 0.9
        assert 0.01 <= pool._decay_rate <= 0.04
        assert 0.01 <= pool._pressure_growth_rate <= 0.02
        assert 0.3 <= pool._validation_effectiveness <= 0.5

    def test_high_openness_reduces_pressure_growth(self):
        pool = HotPool()
        pool.apply_personality({"openness": 0.9})
        # pressure_growth_rate = 0.02 - 0.9 * 0.01 = 0.011
        assert pool._pressure_growth_rate < 0.012

    def test_high_agreeableness_increases_validation_effectiveness(self):
        pool = HotPool()
        pool.apply_personality({"agreeableness": 0.9})
        # validation_effectiveness = 0.3 + 0.9 * 0.2 = 0.48
        assert pool._validation_effectiveness > 0.45


# ---------------------------------------------------------------------------
# Tests: HotPool — Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_empty_pool_roundtrip(self):
        pool = HotPool()
        d = pool.to_dict()
        restored = HotPool.from_dict(d)
        assert restored.temperature == 0.0
        assert restored.volume == 0.0
        assert restored.pressure == 0.0
        assert restored.materials == []

    def test_pool_with_materials_roundtrip(self):
        pool = HotPool()
        pool._materials.append(HotMaterial(id="m1", origin_type="wound", heat=0.7, mass=0.4))
        pool._materials.append(HotMaterial(id="m2", origin_type="betrayal", heat=0.9, mass=0.6))
        pool._temperature = 0.8
        pool._volume = 0.5
        pool._pressure = 0.3
        pool._tick = 42

        d = pool.to_dict()
        restored = HotPool.from_dict(d)
        assert len(restored.materials) == 2
        assert restored.materials[0].id == "m1"
        assert abs(restored.materials[0].heat - 0.7) < 1e-5
        assert restored.materials[1].id == "m2"
        assert abs(restored.temperature - 0.8) < 1e-5
        assert abs(restored.volume - 0.5) < 1e-5
        assert abs(restored.pressure - 0.3) < 1e-5
        assert restored._tick == 42

    def test_cascade_state_survives_serialization(self):
        pool = HotPool()
        pool._cascade.active = True
        pool._cascade.intensity = 0.75
        pool._cascade.momentum = 0.6
        pool._cascade.sensitivity_multiplier = 2.5
        pool._cascade.ticks_above_critical = 7
        pool._cascade.peak_intensity = 0.85

        d = pool.to_dict()
        restored = HotPool.from_dict(d)
        assert restored.cascade.active is True
        assert abs(restored.cascade.intensity - 0.75) < 1e-5
        assert abs(restored.cascade.momentum - 0.6) < 1e-5
        assert abs(restored.cascade.sensitivity_multiplier - 2.5) < 1e-5
        assert restored.cascade.ticks_above_critical == 7
        assert abs(restored.cascade.peak_intensity - 0.85) < 1e-5

    def test_recovery_state_survives_serialization(self):
        pool = HotPool()
        pool._in_recovery = True
        pool._recovery_ticks_remaining = 25

        d = pool.to_dict()
        restored = HotPool.from_dict(d)
        assert restored.in_recovery is True
        assert restored.recovery_ticks_remaining == 25

    def test_params_survive_serialization(self):
        pool = HotPool()
        pool.apply_personality(
            {
                "neuroticism": 0.7,
                "conscientiousness": 0.8,
                "openness": 0.6,
                "agreeableness": 0.9,
            }
        )

        d = pool.to_dict()
        restored = HotPool.from_dict(d)
        assert abs(restored._cascade_trigger - pool._cascade_trigger) < 1e-5
        assert abs(restored._collapse_threshold - pool._collapse_threshold) < 1e-5
        assert abs(restored._decay_rate - pool._decay_rate) < 1e-5
        assert abs(restored._pressure_growth_rate - pool._pressure_growth_rate) < 1e-5
        assert abs(restored._validation_effectiveness - pool._validation_effectiveness) < 1e-5

    def test_schema_version_present(self):
        pool = HotPool()
        d = pool.to_dict()
        assert "schema_version" in d
        assert d["schema_version"] == "sylanne.alpha.hot_pool.v1"


# ---------------------------------------------------------------------------
# Tests: HotPool — Integration Hooks
# ---------------------------------------------------------------------------


class _MockTemperature:
    def __init__(self):
        self.volatility = 0.0


class _MockImmunity:
    def __init__(self):
        self.boundary_pressure = 0.0
        self.sovereignty = 0.5


class _MockMortality:
    def __init__(self):
        self.load = 0.0


class _MockPulse:
    def __init__(self):
        self.strain = 0.0


class _MockBody:
    def __init__(self):
        self.temperature = _MockTemperature()
        self.immunity = _MockImmunity()
        self.mortality = _MockMortality()
        self.pulse = _MockPulse()


class _MockSpine:
    def __init__(self):
        self._drift_min_interval = 30.0


class TestIntegrationHooks:
    def test_feed_body_temperature_volatility(self):
        pool, _ = _make_pool_with_material(heat=0.8, mass=0.6)
        pool._temperature = 0.7
        body = _MockBody()
        pool.feed_body(body)
        assert body.temperature.volatility > 0.0

    def test_feed_body_pressure_boundary(self):
        pool = HotPool()
        pool._pressure = 0.6
        body = _MockBody()
        pool.feed_body(body)
        assert body.immunity.boundary_pressure > 0.0

    def test_feed_body_cascade_active_increases_load_and_strain(self):
        pool = HotPool()
        pool._cascade.active = True
        pool._cascade.intensity = 0.8
        body = _MockBody()
        pool.feed_body(body)
        assert body.mortality.load > 0.0
        assert body.pulse.strain > 0.0

    def test_feed_body_cascade_inactive_no_load(self):
        pool = HotPool()
        pool._cascade.active = False
        body = _MockBody()
        pool.feed_body(body)
        assert body.mortality.load == 0.0
        assert body.pulse.strain == 0.0

    def test_feed_body_recovery_reduces_sovereignty(self):
        pool = HotPool()
        pool._in_recovery = True
        pool._recovery_ticks_remaining = 30
        body = _MockBody()
        initial_sovereignty = body.immunity.sovereignty
        pool.feed_body(body)
        assert body.immunity.sovereignty < initial_sovereignty

    def test_drift_rate_multiplier_normal(self):
        pool = HotPool()
        assert pool.drift_rate_multiplier() == 1.0

    def test_drift_rate_multiplier_cascade(self):
        pool = HotPool()
        pool._cascade.active = True
        assert pool.drift_rate_multiplier() == 10.0

    def test_drift_rate_multiplier_recovery(self):
        pool = HotPool()
        pool._in_recovery = True
        assert pool.drift_rate_multiplier() == 2.0

    def test_drift_cap_multiplier_normal(self):
        pool = HotPool()
        assert pool.drift_cap_multiplier() == 1.0

    def test_drift_cap_multiplier_recovery(self):
        pool = HotPool()
        pool._in_recovery = True
        assert pool.drift_cap_multiplier() == 2.0

    def test_amplify_event_no_cascade(self):
        pool = HotPool()
        event = {"confidence": 0.5, "flags": ["hurt"], "values": {}}
        result = pool.amplify_event(event)
        # No cascade active, event unchanged
        assert result["confidence"] == 0.5
        assert "cascade_hurt_boost" not in result.get("values", {})

    def test_amplify_event_with_cascade(self):
        pool = HotPool()
        pool._cascade.active = True
        pool._cascade.intensity = 0.8
        pool._cascade.sensitivity_multiplier = 2.0
        event = {"confidence": 0.4, "flags": ["hurt", "boundary"], "values": {}}
        result = pool.amplify_event(event)
        # confidence amplified: 0.4 * 2.0 = 0.8
        assert abs(result["confidence"] - 0.8) < 1e-5
        assert "cascade_hurt_boost" in result["values"]
        assert "cascade_boundary_boost" in result["values"]
        assert result["values"]["cascade_hurt_boost"] == pytest.approx(0.8 * 0.3)
        assert result["values"]["cascade_boundary_boost"] == pytest.approx(0.8 * 0.2)

    def test_reflect_cools_specific_material(self):
        pool = HotPool()
        mat = HotMaterial(id="target", origin_type="test", heat=0.8, mass=0.5)
        other = HotMaterial(id="other", origin_type="test", heat=0.6, mass=0.4)
        pool._materials.extend([mat, other])
        result = pool.reflect("target", cooling_factor=0.5)
        assert result is True
        # target cooled: 0.8 * (1 - 0.5) = 0.4
        assert abs(mat.heat - 0.4) < 1e-5
        assert mat.reflection_count == 1
        # other unchanged
        assert other.heat == 0.6

    def test_reflect_returns_false_for_missing_material(self):
        pool = HotPool()
        result = pool.reflect("nonexistent")
        assert result is False

    def test_modulate_drift_rate_cascade_active(self):
        pool = HotPool()
        pool._cascade.active = True
        spine = _MockSpine()
        pool._modulate_drift_rate(spine)
        assert spine._drift_min_interval == 0.0

    def test_modulate_drift_rate_cascade_inactive(self):
        pool = HotPool()
        pool._cascade.active = False
        spine = _MockSpine()
        spine._drift_min_interval = 0.0
        pool._modulate_drift_rate(spine)
        assert spine._drift_min_interval == 30.0


# ---------------------------------------------------------------------------
# Tests: HotPool — Wound Ingestion & Misc Hooks
# ---------------------------------------------------------------------------


class TestWoundIngestion:
    def test_ingest_wound_below_threshold_does_nothing(self):
        pool = HotPool()
        pool.ingest_wound(0.2)
        assert len(pool.materials) == 0

    def test_ingest_wound_creates_material(self):
        pool = HotPool()
        pool.ingest_wound(0.6)
        assert len(pool.materials) == 1
        assert pool.materials[0].origin_type == "wound"
        assert pool.materials[0].heat > 0.0

    def test_ingest_wound_updates_existing_wound(self):
        pool = HotPool()
        pool._materials.append(HotMaterial(id="wound_old", origin_type="wound", heat=0.2, mass=0.2))
        pool.ingest_wound(0.8)
        assert len(pool.materials) == 1
        assert pool.materials[0].heat >= 0.4  # max(0.2, 0.8*0.5)
        assert pool.materials[0].mass > 0.2


class TestBoundaryIntegrity:
    def test_no_cascade_returns_zero(self):
        pool = HotPool()
        assert pool.boundary_integrity_delta() == 0.0

    def test_cascade_active_returns_negative(self):
        pool = HotPool()
        pool._cascade.active = True
        pool._cascade.intensity = 0.5
        delta = pool.boundary_integrity_delta()
        assert delta < 0.0
        assert abs(delta - (-0.5 * 0.2)) < 1e-5


class TestExpressionPressureBoost:
    def test_no_collapse_history_returns_zero(self):
        pool = HotPool()
        assert pool.expression_pressure_boost() == 0.0


class TestBodyDeltas:
    def test_body_deltas_normal_state(self):
        pool = HotPool()
        pool._temperature = 0.5
        pool._pressure = 0.4
        deltas = pool.body_deltas()
        assert "temperature.volatility" in deltas
        assert "immunity.boundary_pressure" in deltas
        assert "mortality.load" in deltas
        assert "pulse.strain" in deltas
        assert "immunity.sovereignty" in deltas
        assert deltas["mortality.load"] == 0.0  # no cascade
        assert deltas["immunity.sovereignty"] == 0.0  # no recovery

    def test_body_deltas_cascade_active(self):
        pool = HotPool()
        pool._cascade.active = True
        pool._cascade.intensity = 0.6
        deltas = pool.body_deltas()
        assert deltas["mortality.load"] == pytest.approx(0.6 * 0.1)
        assert deltas["pulse.strain"] == pytest.approx(0.6 * 0.05)

    def test_body_deltas_in_recovery(self):
        pool = HotPool()
        pool._in_recovery = True
        pool._recovery_ticks_remaining = 30
        deltas = pool.body_deltas()
        expected = -(30 / 60.0 * 0.1)
        assert deltas["immunity.sovereignty"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests: HotPool — Material Capacity
# ---------------------------------------------------------------------------


class TestMaterialCapacity:
    def test_max_materials_enforced(self):
        pool = HotPool(mode="lite")  # max 8
        for i in range(10):
            pool._add_material(
                HotMaterial(id=f"m{i}", origin_type="test", heat=0.1 * (i + 1), mass=0.3)
            )
        assert len(pool.materials) <= 8

    def test_lowest_heat_material_evicted(self):
        pool = HotPool(mode="lite")  # max 8
        for i in range(8):
            pool._add_material(
                HotMaterial(id=f"m{i}", origin_type="test", heat=0.1 * (i + 1), mass=0.3)
            )
        # Add one more with high heat
        pool._add_material(HotMaterial(id="new_hot", origin_type="test", heat=0.95, mass=0.5))
        assert len(pool.materials) == 8
        # The lowest heat material (m0, heat=0.1) should be evicted
        ids = [m.id for m in pool.materials]
        assert "m0" not in ids
        assert "new_hot" in ids


# ---------------------------------------------------------------------------
# Tests: HotPool — Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    def test_diagnostics_returns_expected_keys(self):
        pool = HotPool()
        diag = pool.diagnostics()
        expected_keys = {
            "temperature",
            "volume",
            "pressure",
            "material_count",
            "cascade_active",
            "cascade_intensity",
            "sensitivity_multiplier",
            "in_recovery",
            "collapse_count",
        }
        assert set(diag.keys()) == expected_keys

    def test_diagnostics_reflects_state(self):
        pool = HotPool()
        pool._temperature = 0.6
        pool._cascade.active = True
        pool._cascade.intensity = 0.7
        pool._in_recovery = True
        diag = pool.diagnostics()
        assert diag["temperature"] == pytest.approx(0.6, abs=1e-3)
        assert diag["cascade_active"] is True
        assert diag["cascade_intensity"] == pytest.approx(0.7, abs=1e-3)
        assert diag["in_recovery"] is True
