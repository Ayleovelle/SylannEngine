"""Spine + emergence integration tests.

Extracted from the former ``test_resonance_field.py`` when the dead simplicial
resonance-field stack (``resonance_field*``/``coupling_dynamics``/``topology_gate``)
was deleted (v2.5: the serving path is DeterministicFusion + PEL-Core, not the
iterate-to-convergence field). These classes test the LIVE surfaces — the
``EmergenceTracker`` primitives and the ``ResonanceSpine`` it feeds — and never
touched the deleted field, so they carry over unchanged.
"""

from __future__ import annotations

import math

from sylanne_core.compute.emergence import (
    AttractorLandscape,
    OrderParameterTracker,
    PhiCalculator,
    TemporalNarrative,
)
from sylanne_core.compute.resonance_integration import ResonanceSpine


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

    def test_process_tolerates_null_affect_fields(self):
        # process(assessment=...) is a public entry: a caller (e.g. the plugin's own
        # LLM) may hand in an assessment whose affect fields came back explicitly null.
        # These must not float(None) -> TypeError and topple the tick.
        spine = ResonanceSpine()
        assessment = {
            "confidence": None,
            "wound_risk": None,
            "valence": None,
            "arousal": None,
            "flags": [],
        }
        result = spine.process("你好", timestamp=1.0, assessment=assessment)
        assert "emotion" in result  # tick completed, no raise
        assert result["tick"] == 1

    def test_process_tolerates_non_dict_assessment(self):
        # process() is public: a caller may pass a malformed CONTAINER (a bare list /
        # str / int — the same non-dict shape an LLM emits) where a dict was expected.
        # It must be dropped, not AttributeError on assessment.get(...).
        spine = ResonanceSpine()
        for bad in (["hurt"], "angry", 42, 3.14):
            result = spine.process("在吗", timestamp=1.0, assessment=bad)
            assert "emotion" in result  # tick completed, no raise

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


class TestAssessmentInjection:
    """The assessor (external LLM) is the SDK's only semantic organ. These guard
    that its continuous affect read actually reaches the emotion core — the
    ``wound_risk``/``valence`` path was previously a dead no-op (the assessor never
    emitted those keys). The scar MLP is seeded deterministically, so two fresh
    spines on identical input differ only by the injected assessment."""

    NEG = {
        "confidence": 0.9,
        "flags": ["negative"],
        "valence": -0.9,
        "arousal": 0.7,
        "wound_risk": 0.0,
    }
    POS = {
        "confidence": 0.9,
        "flags": ["positive"],
        "valence": 0.9,
        "arousal": 0.3,
        "wound_risk": 0.0,
    }
    NEUTRAL = {
        "confidence": 0.5,
        "flags": ["idle"],
        "valence": 0.0,
        "arousal": 0.0,
        "wound_risk": 0.0,
    }

    def test_negative_read_lowers_valence(self):
        baseline = ResonanceSpine().process("说点什么", timestamp=1.0)
        negative = ResonanceSpine().process("说点什么", timestamp=1.0, assessment=self.NEG)
        assert negative["emotion"]["valence"] < baseline["emotion"]["valence"]

    def test_positive_read_raises_valence(self):
        baseline = ResonanceSpine().process("说点什么", timestamp=1.0)
        positive = ResonanceSpine().process("说点什么", timestamp=1.0, assessment=self.POS)
        assert positive["emotion"]["valence"] > baseline["emotion"]["valence"]

    def test_high_wound_risk_injects_tension(self):
        baseline = ResonanceSpine().process("随便说", timestamp=1.0)
        wounded = ResonanceSpine().process(
            "随便说",
            timestamp=1.0,
            assessment={
                "confidence": 0.95,
                "flags": ["conflict", "negative"],
                "valence": -0.8,
                "arousal": 0.8,
                "wound_risk": 0.9,
            },
        )
        assert wounded["emotion"]["tension"] > baseline["emotion"]["tension"]

    def test_neutral_assessment_is_noop_on_emotion(self):
        # All-zero affect must not perturb the emotion core (gated by magnitude).
        baseline = ResonanceSpine().process("hi", timestamp=1.0)
        neutral = ResonanceSpine().process("hi", timestamp=1.0, assessment=self.NEUTRAL)
        assert neutral["emotion"] == baseline["emotion"]

    def test_absent_assessment_is_noop_on_emotion(self):
        # Regression guard: assessment=None never reaches the injection path.
        baseline = ResonanceSpine().process("hi", timestamp=1.0)
        explicit_none = ResonanceSpine().process("hi", timestamp=1.0, assessment=None)
        assert explicit_none["emotion"] == baseline["emotion"]


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
