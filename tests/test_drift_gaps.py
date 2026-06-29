"""Regression tests for the three SDK-backlog drift gaps.

These cover gaps the consuming AstrBot plugin could not fix from the agent layer:

  gap-1  ResonanceSpine.feedback never drifted embodiment traits, so "expression
         persistently ignored" could not lower expression drive on the resonance
         channel (ComputationSpine already did). Fixed by parity injection.
  gap-2  expression_fired reflected the policy's guess, not the agent's real
         SPEAK/SILENT decision. Fixed by a process(expression_outcome=...) channel
         that overrides result["should_express"].
  gap-3  the 30s drift rate-limit silently dropped dialogue_quality feedback on
         fast-chat turns (dt < 30). Fixed by a consume-once bypass that still
         advances _last_drift_time so repeated fast turns stay dt-scaled down.

All use real class names and cross the 30s gate with explicit timestamps; none
hand-set _should_express (process() overwrites it in _update_expression).
"""

from __future__ import annotations

import random

from sylanne_core.compute.computation_spine import ComputationSpine
from sylanne_core.compute.personality import DriftSignalExtractor
from sylanne_core.compute.resonance_integration import ResonanceSpine

_EDT = "expression_drive_trait"


class TestGap1FeedbackIgnoredDrift:
    """ResonanceSpine.feedback now drifts embodiment traits, at parity with
    ComputationSpine — being persistently ignored suppresses expression drive."""

    def test_resonance_feedback_ignored_lowers_expression_drive(self):
        s = ResonanceSpine()
        before = s._embodiment_traits[_EDT].value
        for _ in range(3):
            s.feedback("ignored", dt=30.0)
        assert s._embodiment_traits[_EDT].value < before

    def test_resonance_feedback_accepted_raises_expression_drive(self):
        s = ResonanceSpine()
        before = s._embodiment_traits[_EDT].value
        for _ in range(3):
            s.feedback("accepted", dt=30.0)
        assert s._embodiment_traits[_EDT].value > before

    def test_feedback_ignored_parity_between_spines(self):
        rs, cs = ResonanceSpine(), ComputationSpine()
        rb = rs._embodiment_traits[_EDT].value
        cb = cs._embodiment_traits[_EDT].value
        rs.feedback("ignored", dt=30.0)
        cs.feedback("ignored", dt=30.0)
        assert rs._embodiment_traits[_EDT].value - rb < 0
        assert cs._embodiment_traits[_EDT].value - cb < 0

    def test_feedback_return_contract_unchanged(self):
        s = ResonanceSpine()
        obs = s.feedback("ignored", dt=30.0)
        assert isinstance(obs, dict) and "valence" in obs  # still engine.observe()


class TestGap2ExpressionOutcome:
    """The agent's real SPEAK/SILENT decision overrides the policy guess so
    expression_fired reflects ground truth, not a contextual-bandit prediction."""

    def test_outcome_false_overrides_to_silent(self):
        s = ResonanceSpine()
        r = s.process("how are you", timestamp=1000.0, expression_outcome=False)
        assert r["should_express"] is False
        assert r["route"] == "resonance"  # contract literal unchanged
        assert r["assessment_source"] == "resonance_field"

    def test_outcome_true_fires_expression_signal(self):
        s = ResonanceSpine()
        r = s.process("hello", timestamp=1000.0, expression_outcome=True)
        assert r["should_express"] is True
        assert DriftSignalExtractor().extract(r).get("expression_fired") == 1.0

    def test_outcome_none_preserves_old_behavior(self):
        s = ResonanceSpine()
        r = s.process("test", timestamp=1000.0)
        assert isinstance(r["should_express"], bool)

    def test_silent_suppresses_false_positive_across_gate(self):
        # Cross the 30s gate (dt=100) so this measures suppression, not rate-limiting.
        # The meta-learner draws from the GLOBAL random module (random.gauss), which
        # any prior process() call in the suite advances — so seed it identically
        # before each run to isolate the expression_outcome effect from that shared
        # noise, then restore the global state so this test perturbs no other.
        _rng_state = random.getstate()
        try:
            random.seed(0)
            speak = ResonanceSpine()
            speak.process("warmup", timestamp=1000.0)
            speak.process("p", timestamp=1100.0, expression_outcome=True)
            edt_speak = speak._embodiment_traits[_EDT].value

            random.seed(0)
            silent = ResonanceSpine()
            silent.process("warmup", timestamp=1000.0)
            silent.process("p", timestamp=1100.0, expression_outcome=False)
            edt_silent = silent._embodiment_traits[_EDT].value
        finally:
            random.setstate(_rng_state)

        assert edt_speak > edt_silent  # SPEAK fires expression_fired (+), SILENT does not


class TestGap3FastChatDriftBypass:
    """Explicit dialogue_quality bypasses the 30s gate (so fast chat keeps drifting),
    but consume-once + dt-scaling keep repeated fast turns from blowing the budget."""

    def test_fast_chat_dialogue_quality_drifts(self):
        s = ResonanceSpine()
        s.process("你好", timestamp=1000.0)  # establishes _last_drift_time
        before = s._embodiment_traits[_EDT].value
        s.process("很好啊", timestamp=1010.0, dialogue_quality=0.95)  # dt=10 < 30
        assert s._embodiment_traits[_EDT].value > before

    def test_no_feedback_still_rate_limited(self):
        s = ResonanceSpine()
        s.process("x", timestamp=1000.0)
        before = s._embodiment_traits[_EDT].value
        s.process("y", timestamp=1005.0)  # dt=5 < 30, no feedback -> gated, no drift
        assert s._embodiment_traits[_EDT].value == before

    def test_repeated_fast_feedback_does_not_runaway(self):
        s = ResonanceSpine()
        s.process("a", timestamp=1000.0, dialogue_quality=0.95)
        first = s._embodiment_traits[_EDT].value
        for i in range(1, 6):
            s.process("b", timestamp=1000.0 + i, dialogue_quality=0.95)  # +1s each
        total = s._embodiment_traits[_EDT].value - first
        # dt-scaling (dt=1 -> dt_scale≈0.033) keeps the accumulation tiny.
        assert total < 0.005

    def test_consume_marker_not_leaked(self):
        s = ResonanceSpine()
        r = s.process("z", timestamp=1000.0, dialogue_quality=0.9)
        assert "_consume_dialogue_quality" not in r
        assert r["dialogue_quality"] == 0.9

    def test_computation_spine_fast_chat_bypass(self):
        s = ComputationSpine()
        s.process("hi", timestamp=1000.0)
        before = s._embodiment_traits[_EDT].value
        s.process("good", timestamp=1010.0, dialogue_quality=0.95)  # dt=10 < 30
        assert s._embodiment_traits[_EDT].value != before

    def test_computation_spine_consume_marker_not_leaked(self):
        s = ComputationSpine()
        r = s.process("z", timestamp=1000.0, dialogue_quality=0.9)
        assert "_consume_dialogue_quality" not in r
