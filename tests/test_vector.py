"""Tests for sylanne_core.compute.vector module."""

from sylanne_core.compute.vector import (
    EVENT_AXES,
    STATE_AXES,
    WEIGHTS,
    clamp,
    linear_delta,
)


class TestClamp:
    def test_normal_value(self):
        assert clamp(0.5) == 0.5

    def test_below_lower_bound(self):
        assert clamp(-0.3) == 0.0

    def test_above_upper_bound(self):
        assert clamp(1.5) == 1.0

    def test_exact_bounds(self):
        assert clamp(0.0) == 0.0
        assert clamp(1.0) == 1.0

    def test_custom_bounds(self):
        assert clamp(5.0, lo=2.0, hi=8.0) == 5.0
        assert clamp(1.0, lo=2.0, hi=8.0) == 2.0
        assert clamp(9.0, lo=2.0, hi=8.0) == 8.0

    def test_nan_returns_lo(self):
        assert clamp(float("nan")) == 0.0
        assert clamp(float("nan"), lo=0.5) == 0.5

    def test_inf_returns_lo(self):
        assert clamp(float("inf")) == 0.0
        assert clamp(float("-inf")) == 0.0

    def test_string_coercion(self):
        assert clamp("0.7") == 0.7  # type: ignore[arg-type]


class TestLinearDelta:
    def test_zero_event_produces_zero_delta(self):
        event = {axis: 0.0 for axis in EVENT_AXES}
        delta = linear_delta(event)
        assert all(v == 0.0 for v in delta.values())

    def test_has_text_event(self):
        event = {axis: 0.0 for axis in EVENT_AXES}
        event["has_text"] = 1.0
        event["elapsed"] = 1.0
        delta = linear_delta(event)
        assert delta["nerve.plasticity"] > 0
        assert delta["bloodflow.circulation"] > 0
        assert delta["muscle.readiness"] > 0

    def test_hurt_event(self):
        event = {axis: 0.0 for axis in EVENT_AXES}
        event["hurt"] = 1.0
        event["elapsed"] = 1.0
        delta = linear_delta(event)
        assert delta["wound.open"] > 0
        assert delta["needs.need_repair"] > 0
        assert delta["pulse.strain"] > 0

    def test_safe_event(self):
        event = {axis: 0.0 for axis in EVENT_AXES}
        event["safe"] = 1.0
        event["elapsed"] = 1.0
        delta = linear_delta(event)
        assert delta["immunity.boundary_pressure"] < 0
        assert delta["bloodflow.warmth"] > 0

    def test_all_state_axes_present(self):
        event = {axis: 1.0 for axis in EVENT_AXES}
        delta = linear_delta(event)
        for axis in STATE_AXES:
            assert axis in delta

    def test_weights_coverage(self):
        for axis in WEIGHTS:
            assert axis in STATE_AXES
