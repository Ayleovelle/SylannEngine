"""Sylanne Reference Test Vectors -- Conformance Suite.

Analogous to IEEE 754 Appendix test vectors (Kahan 1996), these golden
input/output pairs numerically define correct behavior for the Sylanne
Layer 0 affective computation kernel.

A third-party implementation passes conformance if and only if it
reproduces ALL reference vectors within tolerance (6 decimal places).

Axiom IDs:
    A1 -- Compact state space: S = [-1,1] x [0,1] x [0,1]
    A2 -- Identity element: zero stimulus preserves state
    A3 -- Lipschitz continuity: ||delta|| <= max_delta * magnitude
    A4 -- Convergence: exponential decay toward attractor (Lyapunov stable)
    A5 -- Determinism: same input + same state => same output
    A6 -- Scar formation: high-magnitude stimuli leave persistent traces
    A7 -- Algebraic properties: blend commutativity, normalize idempotency
"""

from __future__ import annotations

import unittest
from typing import Any

from sylanne_core.standard import (
    EmotionVector,
    SylanneCore,
    SylanneState,
    SylanneStimulus,
    _clamp_vector,
)

# Attempt to import algebra module (may not exist yet)
try:
    from sylanne_core.algebra import blend, decay, distance, normalize

    HAS_ALGEBRA = True
except ImportError:
    HAS_ALGEBRA = False


# ---------------------------------------------------------------------------
# REFERENCE_VECTORS: Single-step golden input/output pairs
# ---------------------------------------------------------------------------

REFERENCE_VECTORS: list[dict[str, Any]] = [
    # (a) ZERO STIMULUS -- identity element
    {
        "name": "zero_stimulus",
        "input": {
            "valence": 0.0,
            "arousal": 0.0,
            "dominance": 0.0,
            "magnitude": 0.0,
            "timestamp": 0,
        },
        "config": None,
        "expected_output": {
            "primary": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5},
            "mood": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5},
            "delta": {"valence": 0.0, "arousal": 0.0, "dominance": 0.0},
            "confidence": 0.0,
            "epoch": 1,
        },
        "axioms_tested": ["A1", "A2", "A5"],
    },
    # (b) UNIT POSITIVE -- maximum bounded response
    {
        "name": "unit_positive",
        "input": {
            "valence": 1.0,
            "arousal": 1.0,
            "dominance": 1.0,
            "magnitude": 1.0,
            "timestamp": 1,
        },
        "config": None,
        "expected_output": {
            "primary": {
                "valence": 0.173205,
                "arousal": 0.273205,
                "dominance": 0.673205,
            },
            "mood": {
                "valence": 0.008660,
                "arousal": 0.108660,
                "dominance": 0.508660,
            },
            "delta": {
                "valence": 0.173205,
                "arousal": 0.173205,
                "dominance": 0.173205,
            },
            "confidence": 0.778210,
            "epoch": 1,
        },
        "axioms_tested": ["A1", "A3"],
    },
    # (c) UNIT NEGATIVE -- minimum bounded response
    {
        "name": "unit_negative",
        "input": {
            "valence": -1.0,
            "arousal": 0.0,
            "dominance": 0.0,
            "magnitude": 1.0,
            "timestamp": 1,
        },
        "config": None,
        "expected_output": {
            "primary": {"valence": -0.300000, "arousal": 0.1, "dominance": 0.5},
            "mood": {"valence": -0.015000, "arousal": 0.1, "dominance": 0.5},
            "delta": {"valence": -0.300000, "arousal": 0.0, "dominance": 0.0},
            "confidence": 0.778210,
            "epoch": 1,
        },
        "axioms_tested": ["A1", "A3"],
    },
    # (d) LIPSCHITZ BOUNDARY -- delta norm exactly at Lipschitz bound
    {
        "name": "lipschitz_boundary",
        "input": {
            "valence": 1.0,
            "arousal": 1.0,
            "dominance": 1.0,
            "magnitude": 1.0,
            "timestamp": 1,
        },
        "config": None,
        "expected_output": {
            "primary": {
                "valence": 0.173205,
                "arousal": 0.273205,
                "dominance": 0.673205,
            },
            "mood": {
                "valence": 0.008660,
                "arousal": 0.108660,
                "dominance": 0.508660,
            },
            "delta": {
                "valence": 0.173205,
                "arousal": 0.173205,
                "dominance": 0.173205,
            },
            "confidence": 0.778210,
            "epoch": 1,
        },
        "axioms_tested": ["A3"],
        "extra_checks": {"delta_norm_equals_bound": 0.3},
    },
    # (e) CONVERGENCE SEQUENCE -- mood converges toward primary
    # (tested as multi-step in TestConvergenceSequence below)
    # (f) DETERMINISM PAIR -- same stimulus from same state
    {
        "name": "determinism_pair",
        "input": {
            "valence": 0.7,
            "arousal": 0.3,
            "dominance": 0.6,
            "magnitude": 0.5,
            "timestamp": 1,
        },
        "config": None,
        "expected_output": {
            "primary": {
                "valence": 0.108299,
                "arousal": 0.146414,
                "dominance": 0.592828,
            },
            "mood": {
                "valence": 0.005415,
                "arousal": 0.102321,
                "dominance": 0.504641,
            },
            "delta": {
                "valence": 0.108299,
                "arousal": 0.046414,
                "dominance": 0.092828,
            },
            "confidence": 0.437637,
            "epoch": 1,
        },
        "axioms_tested": ["A5"],
    },
    # (g) SCAR FORMATION -- magnitude > 0.8 triggers scar condition
    {
        "name": "scar_formation",
        "input": {
            "valence": -0.9,
            "arousal": 0.8,
            "dominance": 0.2,
            "magnitude": 0.9,
            "timestamp": 1,
        },
        "config": None,
        "expected_output": {
            "primary": {
                "valence": -0.199073,
                "arousal": 0.276954,
                "dominance": 0.544239,
            },
            "mood": {
                "valence": -0.009954,
                "arousal": 0.108848,
                "dominance": 0.502212,
            },
            "delta": {
                "valence": -0.199073,
                "arousal": 0.176954,
                "dominance": 0.044239,
            },
            "confidence": 0.716275,
            "epoch": 1,
        },
        "axioms_tested": ["A6"],
        "extra_checks": {"magnitude_exceeds_scar_threshold": True},
    },
]


# ---------------------------------------------------------------------------
# GOLDEN_SEQUENCES: Multi-step stimulus trajectories with expected state
# ---------------------------------------------------------------------------

GOLDEN_SEQUENCES: list[dict[str, Any]] = [
    # Sequence 1: calm_to_excited
    # Neutral state -> progressive positive stimuli -> high arousal
    {
        "name": "calm_to_excited",
        "config": None,
        "steps": [
            {
                "stimulus": {
                    "valence": 0.3,
                    "arousal": 0.5,
                    "dominance": 0.6,
                    "magnitude": 0.4,
                    "timestamp": 1,
                },
                "expected": {
                    "primary": {
                        "valence": 0.043028,
                        "arousal": 0.171714,
                        "dominance": 0.586056,
                    },
                    "mood": {
                        "valence": 0.002151,
                        "arousal": 0.103586,
                        "dominance": 0.504303,
                    },
                    "confidence": 0.359066,
                    "epoch": 1,
                },
            },
            {
                "stimulus": {
                    "valence": 0.5,
                    "arousal": 0.7,
                    "dominance": 0.5,
                    "magnitude": 0.6,
                    "timestamp": 2,
                },
                "expected": {
                    "primary": {
                        "valence": 0.133482,
                        "arousal": 0.298348,
                        "dominance": 0.676510,
                    },
                    "mood": {
                        "valence": 0.008718,
                        "arousal": 0.113324,
                        "dominance": 0.512913,
                    },
                    "confidence": 0.469961,
                    "epoch": 2,
                },
            },
            {
                "stimulus": {
                    "valence": 0.8,
                    "arousal": 0.9,
                    "dominance": 0.7,
                    "magnitude": 0.8,
                    "timestamp": 3,
                },
                "expected": {
                    "primary": {
                        "valence": 0.271330,
                        "arousal": 0.453427,
                        "dominance": 0.797127,
                    },
                    "mood": {
                        "valence": 0.021849,
                        "arousal": 0.130329,
                        "dominance": 0.527124,
                    },
                    "confidence": 0.537121,
                    "epoch": 3,
                },
            },
            {
                "stimulus": {
                    "valence": 0.6,
                    "arousal": 0.8,
                    "dominance": 0.6,
                    "magnitude": 0.7,
                    "timestamp": 4,
                },
                "expected": {
                    "primary": {
                        "valence": 0.379374,
                        "arousal": 0.597486,
                        "dominance": 0.905171,
                    },
                    "mood": {
                        "valence": 0.039725,
                        "arousal": 0.153687,
                        "dominance": 0.546026,
                    },
                    "confidence": 0.420595,
                    "epoch": 4,
                },
            },
        ],
    },
    # Sequence 2: anger_decay
    # Strong negative stimulus -> zero input -> mood converges toward primary
    {
        "name": "anger_decay",
        "config": None,
        "steps": [
            {
                "stimulus": {
                    "valence": -1.0,
                    "arousal": 0.9,
                    "dominance": 0.1,
                    "magnitude": 1.0,
                    "timestamp": 0,
                },
                "expected": {
                    "primary": {
                        "valence": -0.222375,
                        "arousal": 0.300137,
                        "dominance": 0.522237,
                    },
                    "mood": {
                        "valence": -0.011119,
                        "arousal": 0.110007,
                        "dominance": 0.501112,
                    },
                    "confidence": 0.778210,
                    "epoch": 1,
                },
            },
            {
                "stimulus": {
                    "valence": 0.0,
                    "arousal": 0.0,
                    "dominance": 0.0,
                    "magnitude": 0.0,
                    "timestamp": 1,
                },
                "expected": {
                    "primary": {
                        "valence": -0.222375,
                        "arousal": 0.300137,
                        "dominance": 0.522237,
                    },
                    "mood": {
                        "valence": -0.021682,
                        "arousal": 0.119513,
                        "dominance": 0.502168,
                    },
                    "confidence": 0.0,
                    "epoch": 2,
                },
            },
            {
                "stimulus": {
                    "valence": 0.0,
                    "arousal": 0.0,
                    "dominance": 0.0,
                    "magnitude": 0.0,
                    "timestamp": 2,
                },
                "expected": {
                    "primary": {
                        "valence": -0.222375,
                        "arousal": 0.300137,
                        "dominance": 0.522237,
                    },
                    "mood": {
                        "valence": -0.031716,
                        "arousal": 0.128545,
                        "dominance": 0.503172,
                    },
                    "confidence": 0.0,
                    "epoch": 3,
                },
            },
            {
                "stimulus": {
                    "valence": 0.0,
                    "arousal": 0.0,
                    "dominance": 0.0,
                    "magnitude": 0.0,
                    "timestamp": 3,
                },
                "expected": {
                    "primary": {
                        "valence": -0.222375,
                        "arousal": 0.300137,
                        "dominance": 0.522237,
                    },
                    "mood": {
                        "valence": -0.041249,
                        "arousal": 0.137124,
                        "dominance": 0.504125,
                    },
                    "confidence": 0.0,
                    "epoch": 4,
                },
            },
        ],
    },
    # Sequence 3: personality_modulation
    # Same stimuli with different kernel configs -> different outputs
    {
        "name": "personality_modulation",
        "configs": [
            {
                "max_delta": 0.3,
                "decay_rate": 0.05,
                "attractor": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5},
            },
            {
                "max_delta": 0.5,
                "decay_rate": 0.1,
                "attractor": {"valence": 0.0, "arousal": 0.1, "dominance": 0.5},
            },
            {
                "max_delta": 0.2,
                "decay_rate": 0.02,
                "attractor": {"valence": 0.2, "arousal": 0.2, "dominance": 0.6},
            },
        ],
        "stimuli": [
            {"valence": 0.5, "arousal": 0.6, "dominance": 0.4, "magnitude": 0.7, "timestamp": 1},
            {"valence": -0.3, "arousal": 0.4, "dominance": 0.3, "magnitude": 0.5, "timestamp": 2},
            {"valence": 0.2, "arousal": 0.2, "dominance": 0.5, "magnitude": 0.3, "timestamp": 3},
        ],
        "expected_final_per_config": [
            # Config 0: default (max_delta=0.3, decay_rate=0.05)
            {
                "primary": {
                    "valence": 0.073818,
                    "arousal": 0.377823,
                    "dominance": 0.751236,
                },
                "mood": {
                    "valence": 0.011109,
                    "arousal": 0.132079,
                    "dominance": 0.525094,
                },
                "confidence": 0.223914,
                "epoch": 3,
            },
            # Config 1: high reactivity (max_delta=0.5, decay_rate=0.1)
            {
                "primary": {
                    "valence": 0.123030,
                    "arousal": 0.563039,
                    "dominance": 0.918727,
                },
                "mood": {
                    "valence": 0.034830,
                    "arousal": 0.202662,
                    "dominance": 0.580731,
                },
                "confidence": 0.199748,
                "epoch": 3,
            },
            # Config 2: low reactivity, shifted attractor (max_delta=0.2, decay_rate=0.02)
            {
                "primary": {
                    "valence": 0.249212,
                    "arousal": 0.385216,
                    "dominance": 0.767491,
                },
                "mood": {
                    "valence": 0.203072,
                    "arousal": 0.208764,
                    "dominance": 0.606835,
                },
                "confidence": 0.241341,
                "epoch": 3,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

TOLERANCE = 6  # decimal places for assertAlmostEqual


def _make_stimulus(params: dict) -> SylanneStimulus:
    """Construct a SylanneStimulus from a parameter dict."""
    return SylanneStimulus(
        valence=params["valence"],
        arousal=params["arousal"],
        dominance=params["dominance"],
        magnitude=params["magnitude"],
        timestamp=params["timestamp"],
    )


def _assert_vector_equal(
    tc: unittest.TestCase, actual: EmotionVector, expected: dict, label: str
) -> None:
    """Assert each component of an EmotionVector matches expected values."""
    tc.assertAlmostEqual(
        actual.valence,
        expected["valence"],
        places=TOLERANCE,
        msg=f"{label}.valence",
    )
    tc.assertAlmostEqual(
        actual.arousal,
        expected["arousal"],
        places=TOLERANCE,
        msg=f"{label}.arousal",
    )
    tc.assertAlmostEqual(
        actual.dominance,
        expected["dominance"],
        places=TOLERANCE,
        msg=f"{label}.dominance",
    )


def _assert_state_equal(
    tc: unittest.TestCase, actual: SylanneState, expected: dict, label: str
) -> None:
    """Assert a SylanneState matches expected output dict."""
    _assert_vector_equal(tc, actual.primary, expected["primary"], f"{label}.primary")
    _assert_vector_equal(tc, actual.mood, expected["mood"], f"{label}.mood")
    if "delta" in expected:
        _assert_vector_equal(tc, actual.delta, expected["delta"], f"{label}.delta")
    tc.assertAlmostEqual(
        actual.confidence,
        expected["confidence"],
        places=TOLERANCE,
        msg=f"{label}.confidence",
    )
    tc.assertEqual(actual.epoch, expected["epoch"], msg=f"{label}.epoch")


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestReferenceVectors(unittest.TestCase):
    """Verify all single-step reference vectors against the kernel."""

    def test_all_vectors(self) -> None:
        """Each reference vector must produce exact golden output."""
        for vec in REFERENCE_VECTORS:
            with self.subTest(name=vec["name"]):
                kernel = SylanneCore(config=vec["config"])
                stimulus = _make_stimulus(vec["input"])
                result = kernel.process(stimulus)
                _assert_state_equal(self, result, vec["expected_output"], vec["name"])

    def test_lipschitz_delta_norm(self) -> None:
        """Lipschitz boundary vector: delta norm equals max_delta * magnitude."""
        vec = next(v for v in REFERENCE_VECTORS if v["name"] == "lipschitz_boundary")
        kernel = SylanneCore(config=vec["config"])
        stimulus = _make_stimulus(vec["input"])
        result = kernel.process(stimulus)
        expected_bound = vec["extra_checks"]["delta_norm_equals_bound"]
        self.assertAlmostEqual(
            result.delta.norm(),
            expected_bound,
            places=TOLERANCE,
            msg="delta norm must equal Lipschitz bound (max_delta * magnitude)",
        )

    def test_scar_magnitude_threshold(self) -> None:
        """Scar formation vector: magnitude exceeds scar threshold (0.8)."""
        vec = next(v for v in REFERENCE_VECTORS if v["name"] == "scar_formation")
        stimulus = _make_stimulus(vec["input"])
        self.assertGreater(
            stimulus.magnitude,
            0.8,
            msg="Scar formation requires magnitude > 0.8",
        )


class TestDeterminism(unittest.TestCase):
    """Axiom A5: identical inputs from identical states produce identical outputs."""

    def test_determinism_pair(self) -> None:
        """Two kernels with same config + same stimulus must yield identical state."""
        vec = next(v for v in REFERENCE_VECTORS if v["name"] == "determinism_pair")
        k1 = SylanneCore(config=vec["config"])
        k2 = SylanneCore(config=vec["config"])
        stimulus = _make_stimulus(vec["input"])
        s1 = k1.process(stimulus)
        s2 = k2.process(stimulus)
        # Exact equality (not approximate -- determinism means bit-identical)
        self.assertEqual(s1.primary.valence, s2.primary.valence)
        self.assertEqual(s1.primary.arousal, s2.primary.arousal)
        self.assertEqual(s1.primary.dominance, s2.primary.dominance)
        self.assertEqual(s1.mood.valence, s2.mood.valence)
        self.assertEqual(s1.mood.arousal, s2.mood.arousal)
        self.assertEqual(s1.mood.dominance, s2.mood.dominance)
        self.assertEqual(s1.delta.valence, s2.delta.valence)
        self.assertEqual(s1.delta.arousal, s2.delta.arousal)
        self.assertEqual(s1.delta.dominance, s2.delta.dominance)
        self.assertEqual(s1.confidence, s2.confidence)
        self.assertEqual(s1.epoch, s2.epoch)

    def test_repeated_processing(self) -> None:
        """Processing same stimulus N times from fresh kernel always gives same result."""
        stimulus = SylanneStimulus(
            valence=0.42,
            arousal=0.67,
            dominance=0.31,
            magnitude=0.55,
            timestamp=99,
        )
        results = []
        for _ in range(5):
            k = SylanneCore()
            results.append(k.process(stimulus))
        for r in results[1:]:
            self.assertEqual(r.primary.valence, results[0].primary.valence)
            self.assertEqual(r.primary.arousal, results[0].primary.arousal)
            self.assertEqual(r.confidence, results[0].confidence)


class TestConvergenceSequence(unittest.TestCase):
    """Axiom A4: mood exponentially converges toward primary (Lyapunov stable)."""

    def test_mood_converges_toward_primary(self) -> None:
        """After perturbation, zero stimuli cause mood to approach primary monotonically."""
        kernel = SylanneCore()
        # Perturb
        stim = SylanneStimulus(
            valence=1.0,
            arousal=1.0,
            dominance=1.0,
            magnitude=1.0,
            timestamp=0,
        )
        state = kernel.process(stim)
        prev_distance = state.mood.distance_to(state.primary)
        self.assertGreater(prev_distance, 0.0, "Initial perturbation must create gap")

        # 10 zero stimuli -- distance must decrease each step
        for i in range(10):
            stim = SylanneStimulus(
                valence=0.0,
                arousal=0.0,
                dominance=0.0,
                magnitude=0.0,
                timestamp=i + 1,
            )
            state = kernel.process(stim)
            curr_distance = state.mood.distance_to(state.primary)
            self.assertLess(
                curr_distance,
                prev_distance,
                msg=f"Step {i + 1}: distance must decrease monotonically",
            )
            prev_distance = curr_distance

    def test_convergence_rate_is_exponential(self) -> None:
        """Distance ratio between consecutive steps is constant (1 - decay_rate)."""
        decay_rate = 0.05
        expected_ratio = 1.0 - decay_rate  # 0.95
        kernel = SylanneCore()
        stim = SylanneStimulus(
            valence=1.0,
            arousal=1.0,
            dominance=1.0,
            magnitude=1.0,
            timestamp=0,
        )
        kernel.process(stim)

        distances = []
        for i in range(5):
            stim = SylanneStimulus(
                valence=0.0,
                arousal=0.0,
                dominance=0.0,
                magnitude=0.0,
                timestamp=i + 1,
            )
            state = kernel.process(stim)
            distances.append(state.mood.distance_to(state.primary))

        # Check ratio is constant at expected_ratio
        for i in range(1, len(distances)):
            ratio = distances[i] / distances[i - 1]
            self.assertAlmostEqual(
                ratio,
                expected_ratio,
                places=TOLERANCE,
                msg=f"Convergence ratio at step {i + 1} must equal (1 - decay_rate)",
            )


class TestBlendCommutativity(unittest.TestCase):
    """Axiom A7: blend(a, b, 0.5) == blend(b, a, 0.5) numerically."""

    def _blend(self, a: EmotionVector, b: EmotionVector, t: float) -> EmotionVector:
        """Linear interpolation: (1-t)*a + t*b."""
        return EmotionVector(
            valence=(1 - t) * a.valence + t * b.valence,
            arousal=(1 - t) * a.arousal + t * b.arousal,
            dominance=(1 - t) * a.dominance + t * b.dominance,
        )

    def test_blend_commutativity_at_half(self) -> None:
        """blend(a, b, 0.5) must equal blend(b, a, 0.5) exactly."""
        a = EmotionVector(valence=0.5, arousal=0.3, dominance=0.7)
        b = EmotionVector(valence=-0.2, arousal=0.8, dominance=0.4)
        blend_ab = self._blend(a, b, 0.5)
        blend_ba = self._blend(b, a, 0.5)
        self.assertAlmostEqual(blend_ab.valence, blend_ba.valence, places=TOLERANCE)
        self.assertAlmostEqual(blend_ab.arousal, blend_ba.arousal, places=TOLERANCE)
        self.assertAlmostEqual(blend_ab.dominance, blend_ba.dominance, places=TOLERANCE)
        # Expected values
        self.assertAlmostEqual(blend_ab.valence, 0.15, places=TOLERANCE)
        self.assertAlmostEqual(blend_ab.arousal, 0.55, places=TOLERANCE)
        self.assertAlmostEqual(blend_ab.dominance, 0.55, places=TOLERANCE)

    def test_blend_boundary_values(self) -> None:
        """blend(a, b, 0) == a and blend(a, b, 1) == b."""
        a = EmotionVector(valence=0.8, arousal=0.2, dominance=0.9)
        b = EmotionVector(valence=-0.5, arousal=0.7, dominance=0.1)
        blend_0 = self._blend(a, b, 0.0)
        blend_1 = self._blend(a, b, 1.0)
        self.assertAlmostEqual(blend_0.valence, a.valence, places=TOLERANCE)
        self.assertAlmostEqual(blend_0.arousal, a.arousal, places=TOLERANCE)
        self.assertAlmostEqual(blend_0.dominance, a.dominance, places=TOLERANCE)
        self.assertAlmostEqual(blend_1.valence, b.valence, places=TOLERANCE)
        self.assertAlmostEqual(blend_1.arousal, b.arousal, places=TOLERANCE)
        self.assertAlmostEqual(blend_1.dominance, b.dominance, places=TOLERANCE)

    @unittest.skipUnless(HAS_ALGEBRA, "sylanne_core.algebra not available")
    def test_algebra_blend_matches(self) -> None:
        """If algebra module exists, its blend must match reference implementation."""
        a = EmotionVector(valence=0.5, arousal=0.3, dominance=0.7)
        b = EmotionVector(valence=-0.2, arousal=0.8, dominance=0.4)
        result = blend(a, b, 0.5)
        self.assertAlmostEqual(result.valence, 0.15, places=TOLERANCE)
        self.assertAlmostEqual(result.arousal, 0.55, places=TOLERANCE)
        self.assertAlmostEqual(result.dominance, 0.55, places=TOLERANCE)


class TestNormalizeIdempotency(unittest.TestCase):
    """Axiom A7: normalize(normalize(x)) == normalize(x) -- projection is idempotent."""

    def test_idempotent_within_bounds(self) -> None:
        """Vector already in S is unchanged by normalize."""
        v = EmotionVector(valence=0.5, arousal=0.3, dominance=0.7)
        n = _clamp_vector(v)
        self.assertEqual(n.valence, v.valence)
        self.assertEqual(n.arousal, v.arousal)
        self.assertEqual(n.dominance, v.dominance)

    def test_idempotent_out_of_bounds(self) -> None:
        """Vector outside S: normalize applied twice equals normalize applied once."""
        v = EmotionVector(valence=1.5, arousal=-0.3, dominance=2.0)
        n1 = _clamp_vector(v)
        n2 = _clamp_vector(n1)
        self.assertEqual(n1.valence, n2.valence)
        self.assertEqual(n1.arousal, n2.arousal)
        self.assertEqual(n1.dominance, n2.dominance)
        # Verify clamped values
        self.assertAlmostEqual(n1.valence, 1.0, places=TOLERANCE)
        self.assertAlmostEqual(n1.arousal, 0.0, places=TOLERANCE)
        self.assertAlmostEqual(n1.dominance, 1.0, places=TOLERANCE)

    def test_idempotent_negative_extremes(self) -> None:
        """Extreme negative values clamp correctly and idempotently."""
        v = EmotionVector(valence=-5.0, arousal=-1.0, dominance=-0.5)
        n1 = _clamp_vector(v)
        n2 = _clamp_vector(n1)
        self.assertEqual(n1, n2)
        self.assertAlmostEqual(n1.valence, -1.0, places=TOLERANCE)
        self.assertAlmostEqual(n1.arousal, 0.0, places=TOLERANCE)
        self.assertAlmostEqual(n1.dominance, 0.0, places=TOLERANCE)

    @unittest.skipUnless(HAS_ALGEBRA, "sylanne_core.algebra not available")
    def test_algebra_normalize_idempotent(self) -> None:
        """If algebra module exists, its normalize must be idempotent."""
        v = EmotionVector(valence=2.0, arousal=-1.0, dominance=3.0)
        n1 = normalize(v)
        n2 = normalize(n1)
        self.assertAlmostEqual(n1.valence, n2.valence, places=TOLERANCE)
        self.assertAlmostEqual(n1.arousal, n2.arousal, places=TOLERANCE)
        self.assertAlmostEqual(n1.dominance, n2.dominance, places=TOLERANCE)


class TestDecayMonotonicity(unittest.TestCase):
    """Axiom A4: decay at t1 is closer to attractor than decay at t2 for t1 > t2."""

    def test_mood_distance_decreases_monotonically(self) -> None:
        """After perturbation, mood-to-primary distance strictly decreases each tick."""
        kernel = SylanneCore()
        # Perturb with strong stimulus
        stim = SylanneStimulus(
            valence=0.8,
            arousal=0.7,
            dominance=0.3,
            magnitude=0.9,
            timestamp=0,
        )
        state = kernel.process(stim)

        distances = []
        for i in range(5):
            stim = SylanneStimulus(
                valence=0.0,
                arousal=0.0,
                dominance=0.0,
                magnitude=0.0,
                timestamp=i + 1,
            )
            state = kernel.process(stim)
            distances.append(state.mood.distance_to(state.primary))

        # Golden values
        expected_distances = [
            0.243675,
            0.231491,
            0.219917,
            0.208921,
            0.198475,
        ]
        for i, (actual, expected) in enumerate(zip(distances, expected_distances)):
            self.assertAlmostEqual(
                actual,
                expected,
                places=5,
                msg=f"Distance at t={i + 1}",
            )

        # Strict monotone decrease
        for i in range(len(distances) - 1):
            self.assertGreater(
                distances[i],
                distances[i + 1],
                msg=f"Distance at t={i + 1} must exceed distance at t={i + 2}",
            )


class TestGoldenSequences(unittest.TestCase):
    """Verify multi-step golden sequences produce exact trajectories."""

    def test_calm_to_excited(self) -> None:
        """Neutral -> positive stimuli -> high arousal trajectory."""
        seq = next(s for s in GOLDEN_SEQUENCES if s["name"] == "calm_to_excited")
        kernel = SylanneCore(config=seq.get("config"))
        for i, step in enumerate(seq["steps"]):
            stimulus = _make_stimulus(step["stimulus"])
            state = kernel.process(stimulus)
            _assert_state_equal(
                self,
                state,
                step["expected"],
                f"calm_to_excited.step{i + 1}",
            )

    def test_anger_decay(self) -> None:
        """Strong negative -> zero input -> mood convergence trajectory."""
        seq = next(s for s in GOLDEN_SEQUENCES if s["name"] == "anger_decay")
        kernel = SylanneCore(config=seq.get("config"))
        for i, step in enumerate(seq["steps"]):
            stimulus = _make_stimulus(step["stimulus"])
            state = kernel.process(stimulus)
            _assert_state_equal(
                self,
                state,
                step["expected"],
                f"anger_decay.step{i + 1}",
            )

    def test_personality_modulation(self) -> None:
        """Same stimuli with different configs must produce different outputs."""
        seq = next(s for s in GOLDEN_SEQUENCES if s["name"] == "personality_modulation")
        for ci, cfg in enumerate(seq["configs"]):
            with self.subTest(config_index=ci):
                kernel = SylanneCore(config=cfg)
                for stim_params in seq["stimuli"]:
                    stimulus = _make_stimulus(stim_params)
                    state = kernel.process(stimulus)
                # Verify final state matches golden value
                expected = seq["expected_final_per_config"][ci]
                _assert_state_equal(
                    self,
                    state,
                    expected,
                    f"personality_modulation.config{ci}",
                )

    def test_personality_configs_diverge(self) -> None:
        """Different configs must produce measurably different final states."""
        seq = next(s for s in GOLDEN_SEQUENCES if s["name"] == "personality_modulation")
        final_states = []
        for cfg in seq["configs"]:
            kernel = SylanneCore(config=cfg)
            for stim_params in seq["stimuli"]:
                stimulus = _make_stimulus(stim_params)
                state = kernel.process(stimulus)
            final_states.append(state)

        # All pairs must differ
        for i in range(len(final_states)):
            for j in range(i + 1, len(final_states)):
                dist = final_states[i].primary.distance_to(final_states[j].primary)
                self.assertGreater(
                    dist,
                    0.01,
                    msg=f"Config {i} and {j} must produce different outputs",
                )


class TestCompactStateSpace(unittest.TestCase):
    """Axiom A1: all outputs remain in S = [-1,1] x [0,1] x [0,1]."""

    def _assert_in_bounds(self, v: EmotionVector, label: str) -> None:
        """Assert vector is within compact state space S."""
        self.assertGreaterEqual(v.valence, -1.0, msg=f"{label}.valence >= -1")
        self.assertLessEqual(v.valence, 1.0, msg=f"{label}.valence <= 1")
        self.assertGreaterEqual(v.arousal, 0.0, msg=f"{label}.arousal >= 0")
        self.assertLessEqual(v.arousal, 1.0, msg=f"{label}.arousal <= 1")
        self.assertGreaterEqual(v.dominance, 0.0, msg=f"{label}.dominance >= 0")
        self.assertLessEqual(v.dominance, 1.0, msg=f"{label}.dominance <= 1")

    def test_extreme_stimuli_stay_bounded(self) -> None:
        """Even extreme repeated stimuli cannot push state outside S."""
        kernel = SylanneCore()
        # Hammer with maximum positive stimuli
        for i in range(100):
            stim = SylanneStimulus(
                valence=1.0,
                arousal=1.0,
                dominance=1.0,
                magnitude=1.0,
                timestamp=i,
            )
            state = kernel.process(stim)
            self._assert_in_bounds(state.primary, f"positive.step{i}.primary")
            self._assert_in_bounds(state.mood, f"positive.step{i}.mood")

        kernel.reset()
        # Hammer with maximum negative stimuli
        for i in range(100):
            stim = SylanneStimulus(
                valence=-1.0,
                arousal=1.0,
                dominance=0.0,
                magnitude=1.0,
                timestamp=i,
            )
            state = kernel.process(stim)
            self._assert_in_bounds(state.primary, f"negative.step{i}.primary")
            self._assert_in_bounds(state.mood, f"negative.step{i}.mood")

    def test_alternating_extremes_stay_bounded(self) -> None:
        """Rapid alternation between extremes cannot escape S."""
        kernel = SylanneCore()
        for i in range(50):
            sign = 1.0 if i % 2 == 0 else -1.0
            stim = SylanneStimulus(
                valence=sign,
                arousal=1.0,
                dominance=abs(sign - 0.5),
                magnitude=1.0,
                timestamp=i,
            )
            state = kernel.process(stim)
            self._assert_in_bounds(state.primary, f"alternating.step{i}.primary")
            self._assert_in_bounds(state.mood, f"alternating.step{i}.mood")


if __name__ == "__main__":
    unittest.main()
