"""P1 graft tests for PEL-Core behind the ``pel_core_enabled`` config flag.

Covers the techspec §5 merge-blocking gates that the P1 graft owns:

* #9  — snapshot round-trip on BOTH ``ResonanceSpine`` and ``ComputationSpine``,
        with and without the ``"pel"`` sub-key, plus legacy migration.
* #10 — frozen-contract / API preservation: ``_field`` untouched, ``observe`` /
        ``resonate`` key sets, ``active_channels == 42``, ``route`` /
        ``assessment_source`` literals.
* #11 — tier sweep: PEL's internal K is fixed and ignores ``_mlp_passes`` (G3);
        pro/max (16/128-dim) cores gracefully fall back to the legacy MLP since
        PEL targets the frozen 8-dim emotion space.

The default (``pel_core_enabled=False``) byte-identical path is guarded by the
*entire existing suite* staying green unchanged; here we exercise PEL **on**.
"""

from __future__ import annotations

from typing import Any

from sylanne_core.compute.computation_spine import ComputationSpine
from sylanne_core.compute.pel_core import N as PEL_N
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.scar_algebra import ScarredState
from sylanne_core.config import SylanneConfig, build_profile

TSUNDERE: dict[str, float] = {
    "openness": 0.7,
    "neuroticism": 0.7,
    "extraversion": 0.4,
    "agreeableness": 0.3,
    "conscientiousness": 0.6,
    "sovereignty_guard": 0.8,
}


# --------------------------------------------------------------------------- #
# config flag
# --------------------------------------------------------------------------- #
def test_config_flag_defaults_off() -> None:
    assert SylanneConfig().pel_core_enabled is False
    assert SylanneConfig(pel_core_enabled=True).pel_core_enabled is True


# --------------------------------------------------------------------------- #
# Test #9 — snapshot round-trip (ResonanceSpine + ComputationSpine)            #
# --------------------------------------------------------------------------- #
def _drive_resonance(pel: bool) -> ResonanceSpine:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=pel)
    spine.apply_personality(TSUNDERE)
    for i in range(4):
        spine.process(f"a message number {i}", timestamp=float(i + 1))
    return spine


def _drive_computation(pel: bool) -> ComputationSpine:
    spine = ComputationSpine(profile=build_profile("lite"), pel_enabled=pel)
    spine.apply_personality(TSUNDERE)
    for i in range(4):
        spine.process(f"a message number {i}", timestamp=float(i + 1))
    return spine


def test_resonance_roundtrip_with_pel() -> None:
    spine = _drive_resonance(pel=True)
    assert spine._engine.scar_state.pel_active()
    d1 = spine.to_dict()
    assert "pel" in d1["engine"]["scar"]
    assert d1["engine"]["scar"]["pel"]["v"] == 2  # 更脑 v2 schema (was 1)

    restored = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    restored.apply_personality(TSUNDERE)
    restored.from_dict(d1)
    assert restored._engine.scar_state.pel_active()
    d2 = restored.to_dict()
    assert d1["engine"]["scar"]["pel"] == d2["engine"]["scar"]["pel"]
    assert d1["engine"]["scar"]["base"] == d2["engine"]["scar"]["base"]


def test_computation_roundtrip_with_pel() -> None:
    spine = _drive_computation(pel=True)
    assert spine.engine.scar_state.pel_active()
    d1 = spine.to_dict()
    assert "pel" in d1["engine"]["scar"]

    restored = ComputationSpine(profile=build_profile("lite"), pel_enabled=True)
    restored.apply_personality(TSUNDERE)
    restored.from_dict(d1)
    assert restored.engine.scar_state.pel_active()
    d2 = restored.to_dict()
    assert d1["engine"]["scar"]["pel"] == d2["engine"]["scar"]["pel"]
    assert d1["engine"]["scar"]["base"] == d2["engine"]["scar"]["base"]


def test_scar_state_roundtrip_without_pel_has_no_key() -> None:
    # PEL off => the scar dict must NOT carry a "pel" key (byte-identical legacy).
    state = ScarredState(n_dims=8, pel_enabled=False)
    state.set_pel_priors(TSUNDERE)  # no-op when disabled
    assert not state.pel_active()
    assert "pel" not in state.to_dict()
    rt = ScarredState.from_dict(state.to_dict())
    assert not rt.pel_active()


def test_resonance_legacy_migration_reinits_pel() -> None:
    # A snapshot taken with PEL OFF has no "pel" key. Restoring it into a
    # PEL-configured spine must re-init the latent core from personality.
    legacy = _drive_resonance(pel=False).to_dict()
    assert "pel" not in legacy["engine"]["scar"]

    spine_on = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine_on.apply_personality(TSUNDERE)
    spine_on.from_dict(legacy)
    assert spine_on._engine.scar_state.pel_active()
    # and it keeps running fine post-migration
    spine_on.process("after migration", timestamp=99.0)
    assert all(-1.0 <= v <= 1.0 for v in spine_on._engine.scar_state.base)


def test_computation_legacy_migration_reinits_pel() -> None:
    legacy = _drive_computation(pel=False).to_dict()
    assert "pel" not in legacy["engine"]["scar"]

    spine_on = ComputationSpine(profile=build_profile("lite"), pel_enabled=True)
    spine_on.apply_personality(TSUNDERE)
    spine_on.from_dict(legacy)
    assert spine_on.engine.scar_state.pel_active()
    spine_on.process("after migration", timestamp=99.0)
    assert all(-1.0 <= v <= 1.0 for v in spine_on.engine.scar_state.base)


def test_pel_on_snapshot_does_not_smuggle_into_pel_off_spine() -> None:
    # must-fix #3 (end-to-end, BOTH spine restore paths): a PEL-ON snapshot loaded
    # into a PEL-OFF host must NOT re-enable PEL — the snapshot's "pel" key is
    # ignored, preserving "flag off => byte-identical legacy". (Earlier this test
    # asserted the OPPOSITE round-trip-fidelity behaviour, which must-fix #3 forbids.)
    # A legacy (no-pel) snapshot read by a PEL-off spine also stays legacy.
    legacy = _drive_resonance(pel=False).to_dict()
    off = ResonanceSpine(profile=build_profile("lite"), pel_enabled=False)
    off.from_dict(legacy)
    assert not off._engine.scar_state.pel_active()
    assert "pel" not in off.to_dict()["engine"]["scar"]

    # The smuggle case: a real PEL-ON snapshot (carries a "pel" key) loaded into a
    # PEL-off ResonanceSpine must stay legacy (no PEL, no "pel" key on re-snapshot).
    pel_on = _drive_resonance(pel=True).to_dict()
    assert "pel" in pel_on["engine"]["scar"]
    r_off = ResonanceSpine(profile=build_profile("lite"), pel_enabled=False)
    r_off.from_dict(pel_on)
    assert not r_off._engine.scar_state.pel_active()
    assert "pel" not in r_off.to_dict()["engine"]["scar"]

    # Same for ComputationSpine's restore path.
    c_pel_on = _drive_computation(pel=True).to_dict()
    assert "pel" in c_pel_on["engine"]["scar"]
    c_off = ComputationSpine(profile=build_profile("lite"), pel_enabled=False)
    c_off.from_dict(c_pel_on)
    assert not c_off.engine.scar_state.pel_active()
    assert "pel" not in c_off.to_dict()["engine"]["scar"]


# --------------------------------------------------------------------------- #
# Test #10 — frozen-contract / API preservation                               #
# --------------------------------------------------------------------------- #
_EMOTION_KEYS = (
    "warmth",
    "arousal",
    "valence",
    "tension",
    "curiosity",
    "repair_pressure",
    "expression_drive",
    "boundary_firmness",
)


def test_resonance_route_and_source_literals_unchanged() -> None:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    result = spine.process("contract check", timestamp=1.0)
    assert result["route"] == "resonance"
    assert result["assessment_source"] == "resonance_field"
    assert result["resonance"]["active_channels"] == 42


def test_field_observe_resonate_keysets_identical_on_off() -> None:
    # The DeterministicFusion field is never touched by PEL: its public contract
    # (observe/resonate key sets, 42 channels) is byte-identical PEL on vs off.
    off = ResonanceSpine(profile=build_profile("lite"), pel_enabled=False)
    on = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    off.apply_personality(TSUNDERE)
    on.apply_personality(TSUNDERE)
    off.process("x", timestamp=1.0)
    on.process("x", timestamp=1.0)

    assert set(off._field.observe().keys()) == set(on._field.observe().keys())
    assert set(off._field.resonate().keys()) == set(on._field.resonate().keys())
    assert off._field.observe()["active_channels"] == 42
    assert on._field.observe()["active_channels"] == 42


def test_engine_observe_emotion_keys_present_with_pel() -> None:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    spine.process("emotion keys", timestamp=1.0)
    obs = spine._engine.observe()
    for key in _EMOTION_KEYS:
        assert key in obs


def test_pel_actually_changes_dynamics_vs_legacy() -> None:
    # Adversarial: prove the graft is *live* — PEL on must drive a different
    # emotion trajectory than the legacy MLP on identical input.
    off = ResonanceSpine(profile=build_profile("lite"), pel_enabled=False)
    on = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    off.apply_personality(TSUNDERE)
    on.apply_personality(TSUNDERE)
    for i in range(6):
        off.process(f"drift {i}", timestamp=float(i + 1))
        on.process(f"drift {i}", timestamp=float(i + 1))
    base_off = off._engine.scar_state.base
    base_on = on._engine.scar_state.base
    assert base_off != base_on


# --------------------------------------------------------------------------- #
# Test #11 — tier sweep: PEL K is internal, ignores _mlp_passes                #
# --------------------------------------------------------------------------- #
def _pel_main_step(state: ScarredState, x_t: list[float], surprise: float) -> None:
    state.step([0.0] * state.n_dims, 0.0, pel_ctx=(x_t, surprise, None, 0.0))


def test_pel_ignores_mlp_passes() -> None:
    # G3: PEL's K=2 is fixed. With PEL on, _mlp_passes (lite/pro/max = 1/2/3)
    # must NOT change the emotion trajectory — the latent core ignores it.
    seq = [
        ([0.3, -0.2, 0.5, 0.1, -0.4, 0.2, 0.0, -0.1], 0.5),
        ([0.1, 0.2, -0.3, 0.0, 0.4, -0.1, 0.2, 0.1], 0.7),
        ([-0.2, 0.1, 0.3, -0.1, 0.0, 0.2, -0.3, 0.1], 0.2),
    ]
    bases: list[list[float]] = []
    for passes in (1, 2, 3):
        state = ScarredState(n_dims=8, mlp_passes=passes, pel_enabled=True)
        state.set_pel_priors(TSUNDERE)
        for x_t, surprise in seq:
            _pel_main_step(state, x_t, surprise)
        bases.append(list(state.base))
    assert bases[0] == bases[1] == bases[2], bases


def test_pro_max_fall_back_to_legacy() -> None:
    # PEL targets the frozen 8-dim emotion space; pro/max (16/128-dim) cores
    # gracefully keep the legacy MLP and never crash with the flag on.
    for mode in ("pro", "max"):
        profile = build_profile(mode)  # type: ignore[arg-type]
        spine = ResonanceSpine(profile=profile, pel_enabled=True)
        spine.apply_personality(TSUNDERE)
        assert not spine._engine.scar_state.pel_active()  # PEL inactive off-8-dim
        result = spine.process("tier check", timestamp=1.0)
        assert result["route"] == "resonance"
        assert result["resonance"]["active_channels"] == 42


def test_lite_tier_pel_active() -> None:
    spine = ResonanceSpine(profile=build_profile("lite"), pel_enabled=True)
    spine.apply_personality(TSUNDERE)
    assert spine._engine.scar_state.pel_active()
    assert spine._engine.scar_state.n_dims == PEL_N


# --------------------------------------------------------------------------- #
# wound / feedback routing (D-3 / D-7): cheap affine bias, no mu advance       #
# --------------------------------------------------------------------------- #
def test_wound_and_feedback_do_not_advance_pel_latent() -> None:
    state = ScarredState(n_dims=8, pel_enabled=True)
    state.set_pel_priors(TSUNDERE)
    assert state._pel is not None
    mu_before = list(state._pel.state.mu)
    # wound step (heal=False, no pel_ctx) and a feedback-like step (no pel_ctx)
    state.step([0.5, 0.0, -0.3, 0.4, 0.0, 0.2, 0.0, 0.0], 0.0, heal=False)
    state.step([0.3, 0.0, 0.2, -0.2, 0.1, -0.3, 0.0, 0.0], 0.0)
    mu_after = list(state._pel.state.mu)
    assert mu_before == mu_after  # latent mu untouched by wound/feedback
    assert all(-1.0 <= v <= 1.0 for v in state.base)  # base stays bounded


def test_main_step_advances_pel_latent() -> None:
    state = ScarredState(n_dims=8, pel_enabled=True)
    state.set_pel_priors(TSUNDERE)
    assert state._pel is not None
    mu_before = list(state._pel.state.mu)
    _pel_main_step(state, [0.4, -0.3, 0.2, 0.1, 0.0, -0.2, 0.3, 0.0], 0.6)
    mu_after = list(state._pel.state.mu)
    assert mu_before != mu_after  # main step moves the latent belief


# --------------------------------------------------------------------------- #
# end-to-end via SylanneConfig flag plumbing                                   #
# --------------------------------------------------------------------------- #
def test_config_flag_threads_to_engine(tmp_path: Any) -> None:
    from sylanne_core.compute.host import SylanneAlphaHost

    cfg = SylanneConfig(pel_core_enabled=True)
    host = SylanneAlphaHost(
        root=tmp_path,
        session_key="s1",
        profile=cfg.profile(),
        pel_enabled=cfg.pel_core_enabled,
    )
    host.kernel.computation.apply_personality(TSUNDERE)
    spine = host.kernel.computation
    scar = spine.engine.scar_state  # type: ignore[union-attr]
    assert scar.pel_active()
