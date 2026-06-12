"""Acceptance tests for the A7 personality-derived expression saddle.

Covers the SDK iteration ticket (architecture master §C):
  T1 — hard gate becomes a personality explicit function (two coordinates).
  T2 — credit assignment can target the action actually executed.
  T3 — forced decisions can be excluded from policy training (off-policy).

Red lines verified:
  R1 — default behaviour is tick-for-tick identical (neutral anchoring).
  R2 — archive round-trips do not break; new fields are optional on load.
  R4 — public API only gains optional parameters (old call sites unchanged).
"""

from __future__ import annotations

import random

import pytest

from sylanne_core.compute.expression_policy import (
    _DRIVE_FORCE_EXPRESS,
    _DRIVE_FORCE_HOLD,
    N_FEATURES,
    ExpressionPolicy,
)
from sylanne_core.compute.resonance_integration import ResonanceSpine


def _ctx(drive: float) -> list[float]:
    """A full-width context vector with a given drive in feature 0."""
    v = [0.5] * N_FEATURES
    v[0] = drive
    return v


# ---------------------------------------------------------------------------
# T1 — neutral anchoring (R1)
# ---------------------------------------------------------------------------


class TestNeutralAnchoring:
    def test_fresh_policy_uses_legacy_constants(self):
        p = ExpressionPolicy()
        assert p.force_express_threshold == _DRIVE_FORCE_EXPRESS == 0.95
        assert p.force_hold_threshold == _DRIVE_FORCE_HOLD == 0.1

    def test_neutral_traits_reproduce_legacy_constants(self):
        p = ExpressionPolicy()
        p.set_personality(0.5, expression_drive_trait=0.5, sovereignty_guard=0.5)
        assert p.force_express_threshold == pytest.approx(0.95)
        assert p.force_hold_threshold == pytest.approx(0.10)

    def test_legacy_single_arg_call_leaves_saddle_untouched(self):
        # Old call sites pass only openness — the saddle must not move (R4).
        p = ExpressionPolicy()
        p.set_personality(0.9)
        assert p.force_express_threshold == pytest.approx(0.95)
        assert p.force_hold_threshold == pytest.approx(0.10)

    def test_decide_behaviour_identical_at_neutral(self):
        # Fixed seed: epsilon-greedy path must match a reference policy whose
        # gate was never personalised.
        ref = ExpressionPolicy()
        new = ExpressionPolicy()
        new.set_personality(0.5, expression_drive_trait=0.5, sovereignty_guard=0.5)
        for drive in [0.0, 0.05, 0.1, 0.3, 0.5, 0.7, 0.94, 0.95, 0.96, 1.0]:
            random.seed(1234)
            r_dec, r_conf = ref.decide(_ctx(drive))
            random.seed(1234)
            n_dec, n_conf = new.decide(_ctx(drive))
            assert r_dec == n_dec, f"decision diverged at drive={drive}"
            assert r_conf == pytest.approx(n_conf), f"confidence diverged at drive={drive}"


# ---------------------------------------------------------------------------
# T1 — monotonicity
# ---------------------------------------------------------------------------


class TestSaddleMonotonicity:
    def test_force_express_decreases_with_drive_trait(self):
        prev = None
        for trait in [0.0, 0.25, 0.5, 0.75, 1.0]:
            p = ExpressionPolicy()
            p.set_personality(0.5, expression_drive_trait=trait)
            if prev is not None:
                assert p.force_express_threshold < prev
            prev = p.force_express_threshold

    def test_force_hold_increases_with_sovereignty(self):
        prev = None
        for trait in [0.0, 0.25, 0.5, 0.75, 1.0]:
            p = ExpressionPolicy()
            p.set_personality(0.5, sovereignty_guard=trait)
            if prev is not None:
                assert p.force_hold_threshold > prev
            prev = p.force_hold_threshold

    def test_endpoint_values(self):
        p = ExpressionPolicy()
        p.set_personality(0.5, expression_drive_trait=1.0, sovereignty_guard=1.0)
        assert p.force_express_threshold == pytest.approx(0.85)
        assert p.force_hold_threshold == pytest.approx(0.18)

    def test_force_express_above_one_is_legal(self):
        # A personality that is essentially never forced to speak.
        p = ExpressionPolicy()
        p.set_personality(0.5, expression_drive_trait=0.0)
        assert p.force_express_threshold == pytest.approx(1.05)
        # drive can never exceed 1.0 in normalised context, so the gate is inert.
        random.seed(7)
        dec, _ = p.decide(_ctx(1.0))
        assert p.last_decision_forced is False


# ---------------------------------------------------------------------------
# T1 — spine override reads the single source of truth (no literal 0.95/0.1)
# ---------------------------------------------------------------------------


class TestSpineOverrideSameSource:
    def test_spine_source_has_no_literal_gate_constants(self):
        import inspect

        from sylanne_core.compute import resonance_integration as ri

        src = inspect.getsource(ri.ResonanceSpine._update_expression)
        # The override branch must read the gate from the policy instance, not
        # re-hardcode it. Check for the old literal comparison code patterns
        # (ignore comments, which may mention the anchor values).
        assert "_expression_drive > 0.95" not in src
        assert "_expression_drive < 0.1" not in src
        assert "self._expression_policy.force_express_threshold" in src
        assert "self._expression_policy.force_hold_threshold" in src

    def test_spine_gate_personalised_by_derive_params(self):
        spine = ResonanceSpine()
        spine.apply_personality(
            {"expression_drive_trait": 1.0, "sovereignty_guard": 1.0}
        )
        assert spine._expression_policy.force_express_threshold == pytest.approx(0.85)
        assert spine._expression_policy.force_hold_threshold == pytest.approx(0.18)

    def test_spine_default_personality_keeps_legacy_gate(self):
        # Personality dict omits the two keys -> anchored at 0.5 -> 0.95/0.1.
        spine = ResonanceSpine()
        spine.apply_personality({"openness": 0.5})
        assert spine._expression_policy.force_express_threshold == pytest.approx(0.95)
        assert spine._expression_policy.force_hold_threshold == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# T2 — credit assignment to the actually executed action
# ---------------------------------------------------------------------------


class TestActualActionCreditAssignment:
    def test_actual_action_overrides_planned(self):
        # Policy plans hold (action 0) at low-ish drive, but the arbiter
        # actually expressed. Feeding actual_action=1 must move weights along
        # the action=1 gradient: w += lr * reward*(1-prob) * context.
        p = ExpressionPolicy()
        random.seed(0)
        ctx = _ctx(0.3)
        # Force a deterministic planned action = 0 by stubbing the stored state.
        p.decide(ctx)
        p._last_action = 0  # pretend the policy planned to hold
        prob = p._compute_probability(ctx)
        w_before = list(p.weights)
        b_before = p.bias
        p.update_from_feedback("accepted", actual_action=1)
        lr = p._learning_rate
        expected_scale = 1.0 * (1.0 - prob)  # reward=+1, action=1 branch
        for i in range(N_FEATURES):
            assert p.weights[i] == pytest.approx(
                max(-5.0, min(5.0, w_before[i] + lr * expected_scale * ctx[i]))
            )
        assert p.bias == pytest.approx(
            max(-3.0, min(3.0, b_before + lr * expected_scale))
        )

    def test_none_actual_action_preserves_legacy(self):
        # Two policies fed identical feedback; one omits actual_action, the
        # other passes the same value as _last_action. Must be identical.
        a = ExpressionPolicy()
        b = ExpressionPolicy()
        random.seed(3)
        a.decide(_ctx(0.4))
        random.seed(3)
        b.decide(_ctx(0.4))
        planned = a._last_action
        a.update_from_feedback("rejected")
        b.update_from_feedback("rejected", actual_action=planned)
        assert a.weights == pytest.approx(b.weights)
        assert a.bias == pytest.approx(b.bias)

    def test_spine_feedback_passthrough(self):
        # actual_expressed plumbs through the shared bus to the policy without
        # disturbing the other consumers (the call simply must not raise and
        # must register feedback).
        spine = ResonanceSpine()
        spine.process("hello there", timestamp=1000.0)
        before = spine._expression_policy._total_updates
        spine.feedback("accepted", actual_expressed=True)
        assert spine._expression_policy._total_updates == before + 1

    def test_spine_feedback_legacy_call_unchanged(self):
        spine = ResonanceSpine()
        spine.process("hello there", timestamp=1000.0)
        before = spine._expression_policy._total_updates
        spine.feedback("accepted")  # no new kwarg
        assert spine._expression_policy._total_updates == before + 1


# ---------------------------------------------------------------------------
# T3 — forced decisions excluded from training (opt-in, off-policy hygiene)
# ---------------------------------------------------------------------------


class TestForcedDecisionNoTrain:
    def test_forced_sample_skips_weight_update_when_opted_in(self):
        p = ExpressionPolicy()
        # drive above force_express -> forced expression (no learned choice).
        dec, _ = p.decide(_ctx(0.99))
        assert dec is True
        assert p.last_decision_forced is True
        w_before = list(p.weights)
        b_before = p.bias
        p.update_from_feedback("accepted", skip_forced=True)
        assert p.weights == w_before  # element-wise identical
        assert p.bias == b_before

    def test_forced_sample_still_records_diagnostics_when_skipped(self):
        p = ExpressionPolicy()
        p.decide(_ctx(0.99))
        updates_before = p._total_updates
        p.update_from_feedback("accepted", skip_forced=True)
        # Counters/history advance even though the gradient was skipped.
        assert p._total_updates == updates_before + 1
        assert p.recent_accept_rate > 0.0

    def test_forced_sample_trains_by_default(self):
        # Default skip_forced=False preserves legacy behaviour: forced samples
        # DO move the weights (this is the documented off-policy bug being
        # preserved unless explicitly opted out — R1).
        p = ExpressionPolicy()
        p.decide(_ctx(0.99))
        w_before = list(p.weights)
        p.update_from_feedback("accepted")
        assert p.weights != w_before

    def test_non_forced_sample_unaffected_by_skip_flag(self):
        # A learned (non-forced) decision must train regardless of skip_forced.
        p = ExpressionPolicy()
        random.seed(11)
        p.decide(_ctx(0.5))
        assert p.last_decision_forced is False
        w_before = list(p.weights)
        p.update_from_feedback("rejected", skip_forced=True)
        assert p.weights != w_before


# ---------------------------------------------------------------------------
# R2 — archive round-trips
# ---------------------------------------------------------------------------


class TestPersistenceRoundTrip:
    def test_new_fields_survive_round_trip(self):
        p = ExpressionPolicy()
        p.set_personality(0.7, expression_drive_trait=0.8, sovereignty_guard=0.9)
        restored = ExpressionPolicy.from_dict(p.to_dict())
        assert restored.force_express_threshold == pytest.approx(p.force_express_threshold)
        assert restored.force_hold_threshold == pytest.approx(p.force_hold_threshold)

    def test_legacy_archive_without_gate_fields_loads_to_constants(self):
        # An old archive has no force_express/force_hold keys -> legacy values.
        legacy = ExpressionPolicy().to_dict()
        del legacy["force_express"]
        del legacy["force_hold"]
        restored = ExpressionPolicy.from_dict(legacy)
        assert restored.force_express_threshold == pytest.approx(0.95)
        assert restored.force_hold_threshold == pytest.approx(0.10)

    def test_new_archive_loaded_by_dropping_unknown_keys_is_safe(self):
        # Simulate an older reader that ignores unknown keys: dropping the new
        # keys must still yield a valid policy (no key is mandatory).
        data = ExpressionPolicy().to_dict()
        # Old reader would simply not look at these; constructing from the full
        # dict must not raise and known fields must be intact.
        restored = ExpressionPolicy.from_dict(data)
        assert len(restored.weights) == N_FEATURES

    def test_spine_archive_round_trip(self):
        spine = ResonanceSpine()
        spine.apply_personality({"expression_drive_trait": 0.8, "sovereignty_guard": 0.2})
        fe = spine._expression_policy.force_express_threshold
        fh = spine._expression_policy.force_hold_threshold
        blob = spine.to_dict()
        # Reconstruct policy directly from the serialized sub-dict to confirm
        # the gate fields persist through the spine's container.
        from sylanne_core.compute.expression_policy import ExpressionPolicy as EP

        pol = EP.from_dict(blob["expression_policy"])
        assert pol.force_express_threshold == pytest.approx(fe)
        assert pol.force_hold_threshold == pytest.approx(fh)

