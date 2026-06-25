"""P2 spine-integration tests for PEL-Core (techspec §5, PEL enabled).

Covers the merge-blocking gates the P2 spine graft owns:

* #2  — plasticity is non-constant: a varying session drifts ``W_gen`` and
        spreads the precisions across dims (``var(Pi_obs) > tol``).
* #5  — within-session error drop: a repeated affect pattern drives the mean
        absolute bottom-up error ``|e0|`` down as the generative model adapts.
* #8  — DEPLOYMENT-REALISTIC plasticity gate: a full ``ResonanceSpine`` replays a
        non-repeating corpus with a sparse-assessor cadence and the *real*
        ``PredictiveCodingGate`` surprise. Asserts the surprise is NOT empirically
        pinned (else the gate would go red — reported, not fudged) and that both
        ``W_gen`` drift and the early→late error drop are non-trivial.
* #12 — cost: a real 500-tick benchmark on the live spine, asserting the
        techspec hard gate of < 10 ms/tick (measured, not estimated).

Plus the additive-key contract for D-1 (``result["resonance"]["free_energy"]``)
and the D-10 non-semantic ``assessor_advisable`` gate signal surfaced via
``diagnostics()`` — signal only, never wired to skip a downstream call.
"""

from __future__ import annotations

import math
import statistics
import time
from typing import TYPE_CHECKING

from sylanne_core.compute.pel_core import PELCore
from sylanne_core.compute.predictive_coding import PredictiveCodingGate
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.config import build_profile

if TYPE_CHECKING:
    from pytest import MonkeyPatch

TSUNDERE: dict[str, float] = {
    "openness": 0.7,
    "neuroticism": 0.7,
    "extraversion": 0.4,
    "agreeableness": 0.3,
    "conscientiousness": 0.6,
    "sovereignty_guard": 0.8,
}

# A non-repeating-ish corpus (mixed zh/en, varied topic/tone/length) so the real
# predictive-coding gate produces a genuinely varying surprise signal.
CORPUS: list[str] = [
    "你好，今天过得怎么样？",
    "I had a stressful day at work today.",
    "量子纠缠是一种神奇的物理现象",
    "Let's talk about neural synchronization and resonance.",
    "我不太想说话，有点累了",
    "The weather is changing rapidly this season.",
    "有时候我觉得很孤独，需要一点温暖",
    "System convergence depends on coupling strength.",
    "今天遇到了一件非常开心的事",
    "Higher-order interactions produce explosive sync.",
    "你能理解我的感受吗",
    "Dissipative structures emerge far from equilibrium.",
    "我想去旅行，放松一下心情",
    "Phase transitions occur at critical thresholds.",
    "谢谢你一直陪着我",
    "Kuramoto oscillators model biological rhythms.",
    "明天我们去哪里？",
    "The Hodge Laplacian encodes topological invariants.",
    "我讨厌下雨天，感觉什么都没有动力",
    "Autopoietic systems maintain themselves through repair.",
    "今天的咖啡特别好喝",
    "Attractor dynamics constrain reachable states.",
    "你让我感到温暖和安心",
    "Criticality maximizes dynamic range in networks.",
]


def _frobenius(a: list[list[float]], b: list[list[float]]) -> float:
    return math.sqrt(
        sum((a[i][j] - b[i][j]) ** 2 for i in range(len(a)) for j in range(len(a[0])))
    )


# --------------------------------------------------------------------------- #
# Test #2 — plasticity is non-constant                                        #
# --------------------------------------------------------------------------- #
def test_plasticity_non_constant() -> None:
    core = PELCore.from_personality(TSUNDERE)
    w0 = [list(row) for row in core.state.w_gen]
    # A varying session: a few dims are driven with large, hard-to-predict swings
    # (their e0 stays large => lower learned precision) while others stay quiet
    # (e0 ~ 0 => precision saturates). This spreads the precisions across dims.
    for t in range(50):
        hard = 0.95 * (1.0 if t % 2 == 0 else -1.0)
        x = [
            hard,
            0.02,
            0.9 * ((t % 4) - 1.5) / 1.5,
            0.0,
            0.03,
            0.85 * (1.0 if t % 3 else -1.0),
            0.01,
            0.8 * ((t % 2) * 2 - 1),
        ]
        core.step(x, 0.6)
    drift = _frobenius(w0, core.state.w_gen)
    var_pi = statistics.pvariance(core.state.pi_obs)
    assert drift > 1e-3, drift
    assert var_pi > 1e-3, (var_pi, core.state.pi_obs)


# --------------------------------------------------------------------------- #
# Test #5 — within-session error drop on a repeated pattern                   #
# --------------------------------------------------------------------------- #
def test_within_session_error_drops() -> None:
    core = PELCore.from_personality(TSUNDERE)
    x = [0.6, -0.4, 0.5, 0.2, -0.3, 0.1, 0.4, -0.2]
    e0: list[float] = []
    for _ in range(40):
        core.step(x, 0.5)
        e0.append(core.diagnostics()["mean_abs_e0"])
    early = sum(e0[:5]) / 5
    late = sum(e0[-5:]) / 5
    assert late < early - 1e-3, (early, late)


# --------------------------------------------------------------------------- #
# Test #8 — deployment-realistic plasticity gate (REAL surprise)              #
# --------------------------------------------------------------------------- #
def test_deployment_realistic_plasticity_gate() -> None:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    scar = spine._engine.scar_state
    assert scar.pel_active()
    assert scar._pel is not None
    w0 = [list(row) for row in scar._pel.state.w_gen]

    surprises: list[float] = []
    e0: list[float] = []
    for t in range(160):
        # Sparse, realistic assessor cadence — most ticks have no LLM read.
        assessment = None
        if t % 5 == 0:
            assessment = {
                "valence": 0.3,
                "arousal": 0.5,
                "wound_risk": 0.1,
                "confidence": 0.7,
            }
        spine.process(CORPUS[t % len(CORPUS)], timestamp=float(t + 1), assessment=assessment)
        surprises.append(spine._last_surprise)
        diag = scar.pel_diagnostics()
        assert diag is not None
        e0.append(float(diag["mean_abs_e0"]))

    # Guard against an empirically pinned surprise signal: if the real gate were
    # flat the plasticity story would be vacuous. This goes RED loudly rather than
    # silently passing on a dead signal (techspec §5 / §4.2 must-fix).
    assert max(surprises) - min(surprises) > 0.02, (min(surprises), max(surprises))
    assert len({round(s, 3) for s in surprises}) > 10, "surprise nearly constant"

    drift = _frobenius(w0, scar._pel.state.w_gen)
    early = sum(e0[:20]) / 20
    late = sum(e0[-20:]) / 20
    assert drift > 1e-3, drift
    assert early - late > 1e-3, (early, late)


# --------------------------------------------------------------------------- #
# Test #12 — cost: real 500-tick benchmark, < 10 ms/tick hard gate            #
# --------------------------------------------------------------------------- #
def test_cost_under_10ms_per_tick() -> None:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    # warm-up (exclude import/JIT-ish first-tick costs from the measurement)
    for t in range(10):
        spine.process(CORPUS[t % len(CORPUS)], timestamp=float(t + 1))

    ticks = 500
    t0 = time.perf_counter()
    for t in range(ticks):
        spine.process(CORPUS[t % len(CORPUS)], timestamp=float(1000 + t))
    ms_per_tick = (time.perf_counter() - t0) / ticks * 1000.0
    assert ms_per_tick < 10.0, ms_per_tick


# --------------------------------------------------------------------------- #
# D-1 — additive free_energy key in result["resonance"]                       #
# --------------------------------------------------------------------------- #
def test_free_energy_additive_key_present_only_with_pel() -> None:
    on = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    off = ResonanceSpine(profile=build_profile("lite"), pel_enabled=False)
    on.apply_personality(TSUNDERE)
    off.apply_personality(TSUNDERE)
    r_on = on.process("free energy please", timestamp=1.0)
    r_off = off.process("free energy please", timestamp=1.0)
    # PEL on => additive key present and finite; PEL off => result shape unchanged.
    assert "free_energy" in r_on["resonance"]
    assert math.isfinite(r_on["resonance"]["free_energy"])
    assert "free_energy" not in r_off["resonance"]


# --------------------------------------------------------------------------- #
# D-10 — non-semantic assessor_advisable gate signal (signal only)           #
# --------------------------------------------------------------------------- #
def test_assessor_advisable_signal_surfaced_in_diagnostics() -> None:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    spine.process("a novel and surprising message", timestamp=1.0)
    diag = spine.diagnostics()
    assert "pel" in diag
    pel = diag["pel"]
    assert isinstance(pel["assessor_advisable"], bool)
    assert "surprise" in pel
    assert len(pel["pi_obs"]) == 8
    assert len(pel["pi_top"]) == 8


def test_assessor_advisable_true_on_wound_hint(monkeypatch: MonkeyPatch) -> None:
    # Asymmetric safety (D-10): ANY engine wound forces advisable True even when the
    # surprise branch would say "skip". This drives a REAL fresh scar through the live
    # scar algebra — the exact lever D-10 reads (``engine_result["scar"]["new_scars"]``)
    # — while NEUTRALISING the surprise branch by pinning the running-mean surprise
    # above any observed surprise, so ``surprise < mean`` is always True (low-novelty
    # => surprise branch contributes False). Advisable can then be True ONLY via the
    # wound path; if that path regressed, the final assertion would go red.
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    # Warm a genuine surprise history first so the live gate is real, not cold.
    for t in range(8):
        spine.process(CORPUS[t], timestamp=float(t + 1))

    # Neutralise the surprise branch: force every tick to read as low-novelty.
    monkeypatch.setattr(PredictiveCodingGate, "mean_surprise", lambda self: 2.0)

    # Control: surprise branch neutralised AND no wound => advisable MUST be False.
    # This proves the neutralisation is real and the gate is not pinned to True
    # (so a True later is attributable to the wound, not a constant signal).
    spine.process("I am calm and fine today.", timestamp=100.0)
    assert spine.diagnostics()["pel"]["assessor_advisable"] is False

    # Drive a REAL engine fresh-scar: a near-zero wound threshold makes the live scar
    # algebra form scars from this tick's modulated input (new_scars non-empty).
    before = len(spine._engine.scar_state.scars)
    spine._engine.scar_state.wound_threshold = -1.0
    spine.process("hello there friend", timestamp=101.0)
    after = len(spine._engine.scar_state.scars)
    assert after > before, "no real wound formed — test would not exercise the rule"
    assert spine.diagnostics()["pel"]["assessor_advisable"] is True


def test_assessor_advisable_signal_is_non_constant_in_realistic_regime() -> None:
    # D-10 recalibration guard (must-fix #2): the adaptive running-mean low-novelty
    # rule must NOT collapse to a deployment-time constant the way the old absolute
    # 0.25 threshold did (always True, dead "low => False" branch). Replaying the
    # realistic corpus, the signal takes BOTH values — some ticks advise calling, some
    # advise skipping — so the low-surprise branch is provably live.
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    seen: set[bool] = set()
    for t in range(160):
        spine.process(CORPUS[t % len(CORPUS)], timestamp=float(t + 1))
        seen.add(spine.diagnostics()["pel"]["assessor_advisable"])
    assert seen == {True, False}, seen


def test_assessor_advisable_off_when_pel_disabled() -> None:
    # With PEL off the gate signal is absent entirely (no contract change).
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=False)
    spine.apply_personality(TSUNDERE)
    spine.process("anything", timestamp=1.0)
    assert "pel" not in spine.diagnostics()
