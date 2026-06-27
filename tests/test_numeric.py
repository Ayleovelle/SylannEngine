"""Guards for the shared None-safe float coercion (`sylanne_core._numeric`)."""

from __future__ import annotations

import math

import pytest

from sylanne_core._numeric import _coerce_float


class TestCoerceFloat:
    def test_in_range_passthrough(self):
        assert _coerce_float(0.42, 0.0, 1.0, 0.0) == pytest.approx(0.42)
        assert _coerce_float(-0.3, -1.0, 1.0, 0.0) == pytest.approx(-0.3)

    def test_clamps_to_bounds(self):
        assert _coerce_float(5.0, 0.0, 1.0, 0.0) == 1.0
        assert _coerce_float(-9.0, -1.0, 1.0, 0.0) == -1.0

    def test_none_and_non_numeric_fall_back(self):
        assert _coerce_float(None, 0.0, 1.0, 0.3) == 0.3
        assert _coerce_float("sad", 0.0, 1.0, 0.3) == 0.3
        assert _coerce_float([1], 0.0, 1.0, 0.3) == 0.3

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"])
    def test_non_finite_falls_back_not_clamped(self, bad):
        # float("NaN") is a *valid* float, so it slips past the except; the bare clamp
        # would map it to a bound (NaN wound_risk -> 1.0). Must fall back to default.
        out = _coerce_float(bad, 0.0, 1.0, 0.0)
        assert out == 0.0
        assert math.isfinite(out)

    def test_overflowing_int_falls_back(self):
        # float(huge_int) raises OverflowError, not ValueError — must be caught.
        assert _coerce_float(10**400, 0.0, 1.0, 0.0) == 0.0
