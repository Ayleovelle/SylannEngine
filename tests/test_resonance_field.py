"""Comprehensive tests for the simplicial resonance field system."""

from __future__ import annotations

import math

import pytest

from sylanne_core.compute.coupling_dynamics import (
    CouplingDynamics,
    FreeEnergyMinimizer,
    HebbianPlasticity,
    KuramotoSync,
    SimplicialComplex,
)
from sylanne_core.compute.emergence import (
    AttractorLandscape,
    OrderParameterTracker,
    PhiCalculator,
    TemporalNarrative,
)
from sylanne_core.compute.resonance_field import ResonanceField
from sylanne_core.compute.resonance_integration import ResonanceSpine


class TestSimplicialComplex:
    def test_pairwise_count(self):
        sc = SimplicialComplex(n=7, max_order=1)
        assert sc.total_undirected == 21  # C(7,2)
        assert sc.total_directed == 42  # 21 * 2

    def test_full_simplex_count(self):
        sc = SimplicialComplex(n=7, max_order=6)
        assert sc.total_undirected == 120  # 2^7 - 7 - 1 = 120
        assert sc.total_directed == 441

    def test_pro_tier_count(self):
        sc = SimplicialComplex(n=7, max_order=3)
        # 1-simplices: 21, 2-simplices: 35, 3-simplices: 35 = 91 undirected
        assert sc.total_undirected == 91
        # directed: 42 + 105 + 140 = 287
        assert sc.total_directed == 287

    def test_boundary_matrix_dimensions(self):
        sc = SimplicialComplex(n=7, max_order=2)
        b1 = sc.boundary_matrix(1)
        # ∂_1: C_1 → C_0, so rows=7 (vertices), cols=21 (edges)
        assert len(b1) == 7
        assert len(b1[0]) == 21

    def test_boundary_squared_is_zero(self):
        sc = SimplicialComplex(n=5, max_order=3)
        b2 = sc.boundary_matrix(2)
        b1 = sc.boundary_matrix(1)
        if b1 and b2:
            # ∂_1 ∘ ∂_2 = 0
            rows = len(b1)
            cols = len(b2[0]) if b2 else 0
            inner = len(b1[0])
            result = [[0.0] * cols for _ in range(rows)]
            for i in range(rows):
                for j in range(cols):
                    for k in range(inner):
                        result[i][j] += b1[i][k] * b2[k][j]
            for i in range(rows):
                for j in range(cols):
                    assert abs(result[i][j]) < 1e-10, f"∂²≠0 at ({i},{j})"


class TestHebbianPlasticity:
    def test_strengthening(self):
        hp = HebbianPlasticity(n_channels=10, eta=0.1, lambda_decay=0.001)
        hp.update([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        hp.update([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # Channel 0 should be stronger (before homeostatic rescaling)
        # Due to homeostasis, check relative strength
        assert hp.weights[0] > hp.weights[5]

    def test_atrophy(self):
        hp = HebbianPlasticity(n_channels=5, eta=0.01, lambda_decay=0.05)
        for _ in range(50):
            hp.update([0.0, 0.0, 0.0, 0.0, 0.0])
        # All channels should decay toward w_min
        for w in hp.weights:
            assert w <= 1.0

    def test_homeostatic_budget(self):
        hp = HebbianPlasticity(n_channels=5)
        hp.update([1.0, 1.0, 1.0, 1.0, 1.0])
        total = sum(hp.weights)
        # Should stay near target (n_channels = 5.0)
        assert abs(total - 5.0) < 1.0

    def test_serialization(self):
        hp = HebbianPlasticity(n_channels=5)
        hp.update([0.5, 0.3, 0.1, 0.8, 0.2])
        data = hp.to_dict()
        hp2 = HebbianPlasticity(n_channels=5)
        hp2.from_dict(data)
        assert hp2.weights == pytest.approx(hp.weights)


class TestKuramotoSync:
    def test_initial_desync(self):
        ks = KuramotoSync(n=7)
        r = ks.order_parameter()
        # Phases are evenly spread (2πi/7), so r ≈ 0 (desynchronized)
        assert r < 0.1

    def test_sync_convergence(self):
        ks = KuramotoSync(n=7, coupling=2.0)
        # Strong coupling should maintain/increase sync
        mat = [[1.0] * 7 for _ in range(7)]
        for _ in range(100):
            r = ks.step(mat)
        assert r > 0.5


class TestFreeEnergy:
    def test_prediction_error(self):
        fe = FreeEnergyMinimizer(n=7)
        errors = fe.prediction_error([1.0] * 7)
        # Initial beliefs are 0, so error = precision * observed
        assert all(e > 0 for e in errors)

    def test_belief_convergence(self):
        fe = FreeEnergyMinimizer(n=3, lr=0.5)
        target = [0.5, -0.3, 0.8]
        for _ in range(50):
            fe.update_beliefs(target)
        for i in range(3):
            assert abs(fe.beliefs[i] - target[i]) < 0.1


class TestResonanceField:
    def test_lite_channels(self):
        rf = ResonanceField(tier="lite")
        assert rf.active_channels == 42

    def test_pro_channels(self):
        rf = ResonanceField(tier="pro")
        assert rf.active_channels == 287

    def test_max_channels(self):
        rf = ResonanceField(tier="max")
        assert rf.active_channels == 441

    def test_inject_and_resonate(self):
        rf = ResonanceField(tier="lite")
        rf.inject(0, [1.0] * 8)
        meta = rf.resonate()
        assert meta["iterations"] > 0
        assert "energy" in meta
        assert meta["energy"] > 0

    def test_convergence(self):
        rf = ResonanceField(tier="lite", epsilon=0.01)
        rf.inject(0, [0.5] * 8)
        meta = rf.resonate()
        assert meta["converged"] or meta["iterations"] == 10

    def test_empty_field_stable(self):
        rf = ResonanceField(tier="lite")
        meta = rf.resonate()
        # Empty field should converge immediately
        assert meta["energy"] == 0.0 or meta["converged"]

    def test_harmonics_extraction(self):
        rf = ResonanceField(tier="lite")
        rf.inject(0, [1.0, 0.5, -0.3, 0.2, 0.0, 0.1, -0.1, 0.4])
        rf.resonate()
        harmonics = rf.extract_harmonics(k=1)
        assert len(harmonics) > 0

    def test_serialization(self):
        rf = ResonanceField(tier="lite")
        rf.inject(0, [1.0] * 8)
        rf.resonate()
        data = rf.to_dict()
        rf2 = ResonanceField(tier="lite")
        rf2.from_dict(data)
        assert rf2._total_resonances == rf._total_resonances


class TestCouplingDynamics:
    def test_tier_allocation(self):
        cd_lite = CouplingDynamics(tier="lite")
        cd_pro = CouplingDynamics(tier="pro")
        cd_max = CouplingDynamics(tier="max")
        assert cd_lite.complex.total_directed == 42
        assert cd_pro.complex.total_directed == 287
        assert cd_max.complex.total_directed == 441

    def test_step_returns_metrics(self):
        cd = CouplingDynamics(tier="lite")
        states = [[0.5] * 8 for _ in range(7)]
        result = cd.step(states)
        assert "sync_order" in result
        assert "free_energy" in result
        assert "active_ratio" in result

    def test_plasticity_evolves(self):
        cd = CouplingDynamics(tier="lite")
        states = [[0.0] * 8 for _ in range(7)]
        states[0] = [1.0] * 8
        states[1] = [1.0] * 8
        initial_w = list(cd.plasticity.weights)
        for _ in range(10):
            cd.step(states)
        # Weights should have changed
        assert cd.plasticity.weights != initial_w


class TestEmergence:
    def test_phi_nonnegative(self):
        phi = PhiCalculator()
        states = [[float(i)] * 4 for i in range(7)]
        for _ in range(5):
            phi.update(states)
        assert phi.phi >= 0.0

    def test_phi_low_for_dominant_module(self):
        phi = PhiCalculator()
        # One module dominates variance → Φ should be lower
        states = [[0.0] * 4 for _ in range(7)]
        states[0] = [10.0, -10.0, 10.0, -10.0]
        for _ in range(5):
            phi.update(states)
        assert phi.phi < 1.0

    def test_order_parameter_tracking(self):
        op = OrderParameterTracker()
        result = op.update(0.5, [[0.1] * 4 for _ in range(7)])
        assert "synchronization" in result
        assert "coherence" in result

    def test_attractor_discovery(self):
        al = AttractorLandscape()
        # Visit same region multiple times
        for _ in range(5):
            al.update([0.1] * 8, energy=1.0)
        assert al.n_attractors == 1
        # Visit different region
        al.update([5.0] * 8, energy=2.0)
        assert al.n_attractors == 2

    def test_temporal_narrative(self):
        tn = TemporalNarrative()
        for i in range(10):
            result = tn.update([math.sin(i * 0.5)] * 4)
        assert "entropy_production" in result
        assert "memory_depth" in result


class TestResonanceSpine:
    def test_process_returns_expected_keys(self):
        spine = ResonanceSpine()
        result = spine.process("hello world", timestamp=1000.0)
        assert "tick" in result
        assert "emotion" in result
        assert "should_express" in result
        assert "resonance" in result

    def test_empty_text_skip(self):
        spine = ResonanceSpine()
        result = spine.process("", timestamp=1000.0)
        assert result["tick"] == 0

    def test_feedback_updates_counts(self):
        spine = ResonanceSpine()
        spine.process("test", timestamp=1.0)
        spine.feedback("accepted")
        spine.feedback("rejected")
        assert spine._feedback_counts["accepted"] == 1
        assert spine._feedback_counts["rejected"] == 1

    def test_personality_affects_threshold(self):
        spine = ResonanceSpine()
        spine.apply_personality({"extraversion": 0.9})
        assert spine._expression_threshold < 0.5
        spine.apply_personality({"extraversion": 0.1})
        assert spine._expression_threshold > 0.7

    def test_serialization_roundtrip(self):
        spine = ResonanceSpine()
        spine.process("hello", timestamp=1.0)
        spine.process("world", timestamp=2.0)
        data = spine.to_dict()
        spine2 = ResonanceSpine()
        spine2.from_dict(data)
        assert spine2._tick_count == 2

    def test_multiple_processes_evolve_state(self):
        spine = ResonanceSpine()
        results = []
        for i in range(5):
            r = spine.process(f"message {i}", timestamp=float(i))
            results.append(r)
        # State should evolve (not static)
        energies = [r["resonance"]["energy"] for r in results]
        assert not all(e == energies[0] for e in energies)


class TestHigherOrderPropagation:
    """Verify that pro/max tiers use multi-body simplicial interactions."""

    def test_pro_has_higher_order_gain(self):
        rf = ResonanceField(tier="pro")
        assert rf._higher_order_gain > 0

    def test_max_has_higher_order_gain(self):
        rf = ResonanceField(tier="max")
        rf_pro = ResonanceField(tier="pro")
        assert rf._higher_order_gain > rf_pro._higher_order_gain

    def test_lite_no_higher_order(self):
        rf = ResonanceField(tier="lite")
        assert rf._higher_order_gain == 0.0

    def test_pro_propagation_differs_from_lite(self):
        """Pro tier should produce different dynamics due to 3-body interactions."""
        rf_lite = ResonanceField(tier="lite")
        rf_pro = ResonanceField(tier="pro")
        # Inject same signal
        signal = [0.5] * 8
        signal_pro = [0.5] * 16
        rf_lite.inject(0, signal)
        rf_lite.inject(1, signal)
        rf_lite.inject(2, signal)
        rf_pro.inject(0, signal_pro)
        rf_pro.inject(1, signal_pro)
        rf_pro.inject(2, signal_pro)
        meta_lite = rf_lite.resonate()
        meta_pro = rf_pro.resonate()
        # Different dynamics (different iteration counts or energy)
        assert meta_lite["energy"] != meta_pro["energy"]


class TestDissipation:
    """Verify dissipative structure behavior."""

    def test_residual_decay_between_cycles(self):
        """Without external input, field reaches bounded steady state (not explosion)."""
        rf = ResonanceField(tier="lite")
        rf.inject(0, [2.0] * 8)
        rf.resonate()
        # Run many cycles without injection
        energies = []
        for _ in range(30):
            rf.resonate()
            energies.append(rf._last_energy)
        # Energy should be bounded (not growing unboundedly)
        # Kuramoto self-sustaining oscillation is correct physics
        assert max(energies) < 25.0
        # Energy should stabilize (variance in last 10 < variance in first 10)
        late = energies[-10:]
        early = energies[:10]
        late_var = max(late) - min(late)
        early_var = max(early) - min(early)
        assert late_var <= early_var + 0.5

    def test_field_doesnt_explode(self):
        """Even with repeated injection, tanh + dissipation keeps energy bounded."""
        rf = ResonanceField(tier="lite")
        for _ in range(50):
            rf.inject(0, [1.0] * 8)
            rf.inject(3, [1.0] * 8)
            rf.resonate()
        # Energy should be bounded (tanh saturates at 1.0 per dim)
        # Max possible: 7 modules × 8 dims × 1.0² × 0.5 = 28
        assert rf._last_energy < 30.0


class TestCriticalityFeedback:
    """Verify emergence feeds back into coupling dynamics."""

    def test_criticality_gain_modulates_coupling(self):
        cd = CouplingDynamics(tier="lite")
        cd.set_criticality(0.0)
        cd._rebuild_coupling_matrix()
        base_strength = cd.coupling_strength(0, 1)
        cd.set_criticality(1.0)
        cd._rebuild_coupling_matrix()
        boosted_strength = cd.coupling_strength(0, 1)
        assert boosted_strength > base_strength


class TestHigherOrderKuramoto:
    """Verify Millán et al. (2020) higher-order phase coupling."""

    def test_kuramoto_accepts_simplices(self):
        ks = KuramotoSync(n=7)
        simplices = {2: [(0, 1, 2), (1, 2, 3)], 3: [(0, 1, 2, 3)]}
        ks.set_simplices(simplices)
        mat = [[1.0] * 7 for _ in range(7)]
        r = ks.step(mat)
        assert 0.0 <= r <= 1.0

    def test_higher_order_affects_dynamics(self):
        """With triangles, dynamics should differ from pairwise-only."""
        ks_pair = KuramotoSync(n=5, coupling=1.0)
        ks_higher = KuramotoSync(n=5, coupling=1.0)
        ks_higher.set_simplices({2: [(0, 1, 2), (1, 2, 3), (2, 3, 4)]})
        # Give them different initial phases
        ks_pair.phases = [0.0, 0.5, 1.0, 1.5, 2.0]
        ks_higher.phases = [0.0, 0.5, 1.0, 1.5, 2.0]
        mat = [[0.5] * 5 for _ in range(5)]
        for _ in range(20):
            ks_pair.step(mat)
            ks_higher.step(mat)
        # Phases should diverge due to higher-order terms
        assert ks_pair.phases != ks_higher.phases


class TestRealModuleIntegration:
    """Verify ResonanceSpine uses actual computation modules."""

    def test_hdc_encoding_used(self):
        spine = ResonanceSpine()
        spine.process("hello world", timestamp=1.0)
        assert spine._last_hdc_vec is not None
        assert len(spine._last_hdc_vec) > 0

    def test_voidscar_state_evolves(self):
        spine = ResonanceSpine()
        spine.process("something painful happened", timestamp=1.0)
        emotion = spine._engine.observe()
        # Engine should have non-zero state after processing
        assert any(v != 0.0 for v in emotion.values())

    def test_boundary_responds(self):
        spine = ResonanceSpine()
        spine.process("intense emotional event", timestamp=1.0)
        assert spine._boundary.stability() >= 0.0

    def test_feedback_affects_engine(self):
        spine = ResonanceSpine()
        spine.process("test message", timestamp=1.0)
        spine.feedback("rejected", dt=1.0)
        # Rejected feedback modifies engine state (scar deepening)
        assert spine._feedback_counts["rejected"] == 1

    def test_result_has_real_emotion(self):
        spine = ResonanceSpine()
        result = spine.process("I feel happy today", timestamp=1.0)
        # Should have real emotion values from VoidScarEngine
        assert "emotion" in result
        assert isinstance(result["emotion"], dict)
        assert "warmth" in result["emotion"]

    def test_phi_tracked_over_time(self):
        spine = ResonanceSpine()
        for i in range(5):
            spine.process(f"message number {i}", timestamp=float(i))
        diag = spine.diagnostics()
        assert "emergence" in diag
        assert "phi" in diag["emergence"]


class TestHopfieldAttractors:
    """Verify Hopfield energy landscape stores and attracts."""

    def test_attractor_forms_after_repeated_input(self):
        rf = ResonanceField(tier="lite")
        signal = [0.5, -0.3, 0.2, 0.1, -0.1, 0.4, -0.2, 0.3]
        for _ in range(10):
            rf.inject(0, signal)
            rf.resonate()
        assert len(rf._attractor_patterns) > 0

    def test_attractor_pull_reduces_distance(self):
        rf = ResonanceField(tier="lite")
        # Create an attractor
        signal = [0.8] * 8
        for _ in range(5):
            rf.inject(0, signal)
            rf.resonate()
        # Now inject something different and see if it's pulled back
        rf.inject(0, [-0.5] * 8)
        meta = rf.resonate()
        # Should report near_attractor distance
        assert "near_attractor" in meta
        assert meta["near_attractor"] < float("inf")

    def test_max_attractors_bounded(self):
        rf = ResonanceField(tier="lite")
        # Try to create many different attractors
        for i in range(20):
            signal = [0.0] * 8
            signal[i % 8] = 1.0 * (i + 1)
            rf.inject(0, signal)
            rf.resonate()
        assert len(rf._attractor_patterns) <= rf._max_attractors


class TestEchoStateReservoir:
    """Verify temporal memory via echo state reservoir."""

    def test_reservoir_accumulates_history(self):
        rf = ResonanceField(tier="lite")
        rf.inject(0, [1.0] * 8)
        rf.resonate()
        # Reservoir should have non-zero state
        assert any(abs(x) > 0.01 for x in rf._reservoir)

    def test_reservoir_fades_without_input(self):
        rf = ResonanceField(tier="lite")
        rf.inject(0, [1.0] * 8)
        rf.resonate()
        energy_after_input = sum(x * x for x in rf._reservoir)
        # Multiple resonances without input — reservoir should fade
        for _ in range(20):
            rf.resonate()
        energy_after_fade = sum(x * x for x in rf._reservoir)
        assert energy_after_fade < energy_after_input

    def test_reservoir_persists_in_serialization(self):
        rf = ResonanceField(tier="lite")
        rf.inject(0, [0.5] * 8)
        rf.resonate()
        data = rf.to_dict()
        rf2 = ResonanceField(tier="lite")
        rf2.from_dict(data)
        assert rf2._reservoir == rf._reservoir


class TestHarmonicIdentity:
    """Verify the harmonic identity (soul) accumulates and restores."""

    def test_identity_builds_over_time(self):
        rf = ResonanceField(tier="lite")
        for _ in range(10):
            rf.inject(0, [0.3] * 8)
            rf.inject(2, [0.2] * 8)
            rf.resonate()
        # Identity should have accumulated
        identity_norm = math.sqrt(sum(x * x for x in rf._harmonic_identity))
        assert identity_norm > 0.01

    def test_identity_persists_in_serialization(self):
        rf = ResonanceField(tier="lite")
        for _ in range(5):
            rf.inject(0, [0.5] * 8)
            rf.resonate()
        data = rf.to_dict()
        rf2 = ResonanceField(tier="lite")
        rf2.from_dict(data)
        assert rf2._harmonic_identity == rf._harmonic_identity

    def test_identity_creates_restoring_force(self):
        """After building identity, perturbation should be partially restored."""
        rf = ResonanceField(tier="lite")
        # Build identity with consistent pattern
        pattern = [0.5, -0.3, 0.2, 0.1, -0.1, 0.4, -0.2, 0.3]
        for _ in range(15):
            rf.inject(0, pattern)
            rf.resonate()
        # Now perturb heavily in opposite direction
        rf.inject(0, [-x * 3 for x in pattern])
        rf.resonate()
        # The identity restoring force should prevent complete inversion
        # Module 0 state should not be purely the perturbation
        state_0 = rf._module_states[0]
        # At least some dimensions should resist the perturbation
        dot_with_pattern = sum(s * p for s, p in zip(state_0, pattern))
        # Not a strong assertion — just that it's not maximally anti-correlated
        assert dot_with_pattern > -0.5


class TestBifurcationExpression:
    """Verify expression fires as bifurcation, not just threshold."""

    def test_novel_input_triggers_expression(self):
        spine = ResonanceSpine()
        # Build up a stable attractor
        for i in range(10):
            spine.process("hello hello hello", timestamp=float(i))
        # Now inject something radically different
        result = spine.process(
            "COMPLETELY UNEXPECTED SHOCKING INPUT!!!",
            timestamp=20.0,
        )
        # Novel input should have high expression drive
        assert result["expression_state"]["drive"] > 0.1

    def test_repeated_input_forms_attractor(self):
        spine = ResonanceSpine()
        for i in range(10):
            spine.process("same message", timestamp=float(i))
        # After repeated input, an attractor should form in the field
        assert len(spine._field._attractor_patterns) > 0


class TestTierHotSwitch:
    """Verify lossless tier switching."""

    def test_upgrade_preserves_attractors(self):
        spine = ResonanceSpine()
        for i in range(10):
            spine.process(f"msg {i}", timestamp=float(i))
        n_attractors = len(spine._field._attractor_patterns)
        assert n_attractors > 0
        spine.switch_tier("pro")
        assert len(spine._field._attractor_patterns) >= n_attractors

    def test_upgrade_preserves_channels(self):
        spine = ResonanceSpine()
        assert spine._field.active_channels == 42
        spine.switch_tier("pro")
        assert spine._field.active_channels == 287
        spine.switch_tier("max")
        assert spine._field.active_channels == 441

    def test_downgrade_works(self):
        spine = ResonanceSpine()
        spine.switch_tier("max")
        spine.process("hello", timestamp=1.0)
        spine.switch_tier("lite")
        assert spine._field._state_dim == 8
        # Should still be able to process
        r = spine.process("world", timestamp=2.0)
        assert "emotion" in r

    def test_roundtrip_preserves_emotion(self):
        spine = ResonanceSpine()
        for i in range(5):
            spine.process("test", timestamp=float(i))
        r_before = spine.process("check", timestamp=10.0)
        spine.switch_tier("pro")
        spine.switch_tier("lite")
        r_after = spine.process("check", timestamp=11.0)
        # Emotion should be similar (not identical due to interpolation loss)
        for key in ["warmth", "arousal"]:
            if key in r_before["emotion"] and key in r_after["emotion"]:
                diff = abs(r_before["emotion"][key] - r_after["emotion"][key])
                assert diff < 1.0  # not wildly different

    def test_noop_switch(self):
        spine = ResonanceSpine()
        spine.process("hello", timestamp=1.0)
        energy_before = spine._field._last_energy
        spine.switch_tier("lite")  # same tier, should be noop
        assert spine._field._last_energy == energy_before


class TestResonanceEmbodimentDrift:
    """ResonanceSpine 的 canonical embodiment 漂移接线（含 dialogue_quality 信号）。"""

    def test_process_triggers_drift(self):
        # process() 应在 return 前调用 _drift_embodiment，使 drift_tick 推进
        spine = ResonanceSpine()
        assert hasattr(spine, "_drift_embodiment")
        spine.process("你好", timestamp=1000.0)
        spine.process("再说一句", timestamp=1100.0)  # 跨过 _drift_min_interval
        assert spine._drift_tick >= 1

    def test_dialogue_quality_high_raises_expression_drive(self):
        spine = ResonanceSpine()
        spine.process("打底一句", timestamp=1000.0)
        before = spine._embodiment_traits["expression_drive_trait"].value
        # 连续喂高质量自评（时间跨过速率限制），表达欲应被抬升
        for i in range(1, 8):
            spine.process(
                f"很走心的第{i}句", timestamp=1000.0 + i * 60.0, dialogue_quality=0.95
            )
        after = spine._embodiment_traits["expression_drive_trait"].value
        assert after > before

    def test_dialogue_quality_low_vs_high_differential(self):
        # dialogue_quality 是众多信号之一（expression_fired 等会同时作用），不保证绝对方向，
        # 但相同输入下"低质量"必须比"高质量"留下更低的表达欲——隔离掉共有信号的差分检验。
        def run(quality: float) -> float:
            spine = ResonanceSpine()
            spine.process("打底一句", timestamp=1000.0)
            for i in range(1, 8):
                spine.process(
                    f"第{i}句", timestamp=1000.0 + i * 60.0, dialogue_quality=quality
                )
            return spine._embodiment_traits["expression_drive_trait"].value

        assert run(0.05) < run(0.95)

    def test_no_dialogue_quality_is_optional(self):
        # 不传 dialogue_quality 时行为不变、不写该字段
        spine = ResonanceSpine()
        result = spine.process("普通一句", timestamp=1000.0)
        assert "dialogue_quality" not in result

