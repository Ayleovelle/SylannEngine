"""Tests for sylanne_core.compute.kernel module."""

from sylanne_core.compute.kernel import AlphaKernel, AlphaKernelEvent


class TestKernelBoot:
    def test_boot_fresh(self):
        kernel = AlphaKernel.boot("test_session")
        assert kernel.session_key == "test_session"
        assert kernel.turns == 0
        assert kernel.body.pulse.beat == 0.0

    def test_boot_with_legacy_none(self):
        kernel = AlphaKernel.boot("s1", legacy=None)
        assert kernel.turns == 0


class TestKernelTick:
    def test_tick_increments_turns(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hello", now=1.0))
        assert kernel.turns == 1

    def test_tick_returns_surface(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        assert "surface" in result
        assert "decision" in result
        assert "guard" in result

    def test_tick_with_dict_event(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick({"text": "hello", "now": 1.0, "flags": ["safe"]})
        assert result["decision"]["action"] in {
            "wait",
            "explore",
            "express",
            "reach_out",
            "repair",
            "withdraw",
            "recover",
        }

    def test_tick_with_none_event(self):
        kernel = AlphaKernel.boot("s1")
        result = kernel.tick(None)
        assert "surface" in result

    def test_multiple_ticks(self):
        kernel = AlphaKernel.boot("s1")
        for i in range(5):
            kernel.tick(AlphaKernelEvent(text=f"msg {i}", now=float(i + 1)))
        assert kernel.turns == 5

    def test_tick_exception_returns_fallback(self):
        from unittest.mock import patch

        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="setup", now=1.0))
        with patch(
            "sylanne_core.compute.computation_spine.ComputationSpine.process",
            side_effect=RuntimeError("boom"),
        ):
            result = kernel.tick(AlphaKernelEvent(text="crash", now=2.0))
        assert "surface" in result
        assert "decision" in result


class TestKernelDecision:
    def test_default_decision_is_wait(self):
        kernel = AlphaKernel.boot("s1")
        decision = kernel._decide()
        assert decision["action"] == "wait"

    def test_repair_decision(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.needs["need_repair"] = 0.5
        decision = kernel._decide()
        assert decision["action"] == "repair"

    def test_withdraw_decision(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.immunity.boundary_pressure = 0.9
        decision = kernel._decide()
        assert decision["action"] == "withdraw"

    def test_express_decision(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.needs["need_expression"] = 0.5
        decision = kernel._decide()
        assert decision["action"] == "express"


class TestKernelGuard:
    def test_guard_allows_by_default(self):
        kernel = AlphaKernel.boot("s1")
        decision = kernel._decide()
        guard = kernel._guard(decision)
        assert guard["allowed"] is True

    def test_guard_blocks_on_pause(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.immunity.paused = True
        decision = kernel._decide()
        guard = kernel._guard(decision)
        assert guard["allowed"] is False
        assert "user_pause" in guard["flags"]

    def test_guard_blocks_on_exhaustion(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.mortality.exhaustion = 0.9
        decision = kernel._decide()
        guard = kernel._guard(decision)
        assert guard["allowed"] is False
        assert "exhaustion" in guard["flags"]

    def test_guard_blocks_low_sovereignty(self):
        kernel = AlphaKernel.boot("s1")
        kernel.body.immunity.sovereignty = 0.3
        decision = {
            "action": "reach_out",
            "reason": "test",
            "reason_code": "test",
            "confidence": 0.5,
        }
        guard = kernel._guard(decision)
        assert guard["allowed"] is False


class TestKernelSnapshot:
    def test_snapshot_roundtrip(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hello", now=1.0))
        snap = kernel.snapshot()
        restored = AlphaKernel.restore(snap)
        assert restored.session_key == "s1"
        assert restored.turns == 1
        assert restored.body.pulse.beat == kernel.body.pulse.beat

    def test_restore_from_empty(self):
        kernel = AlphaKernel.restore({})
        assert kernel.session_key == "default"
        assert kernel.turns == 0

    def test_restore_preserves_personality(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        snap = kernel.snapshot()
        restored = AlphaKernel.restore(snap)
        assert restored.personality == kernel.personality


class TestKernelSurface:
    def test_surface_structure(self):
        kernel = AlphaKernel.boot("s1")
        kernel.tick(AlphaKernelEvent(text="hi", now=1.0))
        surface = kernel.surface()
        assert "schema_version" in surface
        assert "body" in surface
        assert "decision" in surface
        assert "guard" in surface
        assert "workset" in surface
        assert "diagnostics" in surface

    def test_surface_session_key(self):
        kernel = AlphaKernel.boot("my_session")
        surface = kernel.surface()
        assert surface["session_key"] == "my_session"


class TestAffectDebtProactiveTiming:
    """Emotion-driven reach_out timing (allostatic threshold bias).

    The LLM's affective read feeds an asymmetric-leak ``_affect_debt`` that lowers
    reach_out's need_contact threshold — so a bruising exchange brings her back
    sooner than flat silence would. need_contact alone is content-blind; this is
    the dimension it structurally cannot carry. Safety gates (_guard) stay fully in
    front, and at zero debt behaviour is byte-identical to the original literals.
    """

    # --- D: zero-debt baseline is unchanged (no regression) -------------------
    def test_zero_debt_threshold_matches_original_literals(self):
        k = AlphaKernel.boot("s1")
        k._affect_debt = 0.0
        assert k._reach_threshold(proactive=True) == 0.1
        assert k._reach_threshold(proactive=False) == 0.2

    def test_zero_debt_preserves_reach_out_boundary(self):
        k = AlphaKernel.boot("s1")
        k.last_event = {"flags": ["proactive"]}
        k._affect_debt = 0.0
        k.body.needs["need_contact"] = 0.1
        assert k._decide()["action"] == "reach_out"  # >= 0.1 still triggers
        k.body.needs["need_contact"] = 0.09
        assert k._decide()["action"] != "reach_out"

    # --- A: not a third wheel — emotion shifts timing at fixed need_contact ----
    def test_emotion_shifts_timing_at_fixed_need_contact(self):
        calm = AlphaKernel.boot("s1")
        calm.last_event = {"flags": ["proactive"]}
        calm.body.needs["need_contact"] = 0.06
        calm._affect_debt = 0.0
        assert calm._decide()["action"] != "reach_out"  # holds back when untroubled

        bruised = AlphaKernel.boot("s2")
        bruised.last_event = {"flags": ["proactive"]}
        bruised.body.needs["need_contact"] = 0.06  # identical need_contact
        bruised._affect_debt = 0.6
        assert bruised._decide()["action"] == "reach_out"  # comes back sooner

    def test_asymmetric_leak_holds_slow_soothes_fast(self):
        k = AlphaKernel.boot("s1")
        k._update_affect_debt({"valence": -0.8, "wound_risk": 0.7})
        hurt = k._affect_debt
        assert hurt > 0.3  # a bruising read spikes it
        for _ in range(3):  # idle ticks decay it only slowly
            k._update_affect_debt(None)
        assert k._affect_debt > hurt * 0.5  # still carrying most of the hurt
        k._update_affect_debt({"valence": 0.9, "wound_risk": 0.0})  # being soothed
        assert k._affect_debt < hurt * 0.5  # clears fast — the asymmetry

    def test_idle_only_leaks_never_rises(self):
        k = AlphaKernel.boot("s1")
        k._affect_debt = 0.5
        k._update_affect_debt(None)  # no assessment -> leak only
        assert k._affect_debt < 0.5

    # --- B: safety gates are never bypassed by emotion ------------------------
    def test_max_debt_never_bypasses_guard(self):
        k = AlphaKernel.boot("s1")
        k.last_event = {"flags": ["proactive"]}
        k.body.needs["need_contact"] = 0.06
        k._affect_debt = 1.0
        decision = k._decide()
        assert decision["action"] == "reach_out"  # emotion drove the urge
        k.body.immunity.paused = True  # but a single gate blocks it
        guard = k._guard(decision)
        assert guard["allowed"] is False
        assert "user_pause" in guard["flags"]

    def test_proactive_threshold_has_floor(self):
        k = AlphaKernel.boot("s1")
        k._affect_debt = 1.0
        assert k._reach_threshold(proactive=True) >= 0.04  # never collapses to 0

    # --- C: successful reach-out spends the debt (no delayed-talkative) --------
    def test_discharge_relaxes_threshold_back(self):
        k = AlphaKernel.boot("s1")
        k._affect_debt = 0.7
        lowered = k._reach_threshold(proactive=True)
        k.discharge_affect_debt()  # she reached out; debt spent
        assert k._affect_debt < 0.7
        assert k._reach_threshold(proactive=True) > lowered  # relaxes -> no re-fire spam

    # --- persistence round-trips the debt -------------------------------------
    def test_affect_debt_survives_snapshot(self):
        k = AlphaKernel.boot("s1")
        k._affect_debt = 0.42
        restored = AlphaKernel.restore(k.snapshot())
        assert restored._affect_debt == 0.42

    def test_old_snapshot_without_debt_defaults_zero(self):
        k = AlphaKernel.boot("s1")
        snap = k.snapshot()
        del snap["_affect_debt"]  # simulate a pre-feature archive
        restored = AlphaKernel.restore(snap)
        assert restored._affect_debt == 0.0
