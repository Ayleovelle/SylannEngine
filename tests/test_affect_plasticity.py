"""v26 A.2 契约：delta-rule 增益可塑性（推导 §6 / 引理 6 投影契约）。

守护：
- 纯函数层：投影 Π_{[ε,1]} 在对抗 quality 序列下恒有界且 validate_gain 恒过；
  资格迹信用分配（不活跃维不动）；δ 符号方向；EMA 基线；时标排序 conformance（注 6.1）；
- ScarredState：四重门（affect∧takeover∧plasticity∧非PEL）；学习态懒初始化自人格且
  set_affect_params 不清洗；持久化 roundtrip + 复原边界夹域；off = 完全 no-op；
- spine：显式 dialogue_quality 到场才学习，缺省不学。
"""

from __future__ import annotations

import math

from sylanne_core.compute import affect_dynamics
from sylanne_core.compute.affect_dynamics import (
    _GAIN_FLOOR,
    _PLASTICITY_ALPHA,
    N_DIMS,
    eligibility_update,
    plasticity_step,
    quality_baseline_update,
    validate_gain,
)
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.compute.scar_algebra import ScarredState
from sylanne_core.config import build_profile

_TRAITS: dict[str, float] = {
    "perception_acuity": 0.7,
    "expression_drive_trait": 0.6,
    "warmth_bias": 0.6,
    "neuroticism": 0.6,
    "extraversion": 0.4,
}


class TestPureMath:
    def test_projection_bounds_under_adversarial_quality(self) -> None:
        gain = [0.5] * N_DIMS
        phi = [1.0] * N_DIMS
        q_hat = 0.5
        # 对抗序列：极端/NaN/inf 交替，狂轰 500 步——投影后恒 ∈ [ε,1]，validate 恒过。
        seq = [0.0, 1.0, float("nan"), float("inf"), -5.0, 1.0, 0.0] * 72
        for q in seq[:500]:
            gain = plasticity_step(gain, q, q_hat, phi)
            q_hat = quality_baseline_update(q_hat, q)
            assert all(_GAIN_FLOOR <= g <= 1.0 for g in gain)
        validate_gain(gain)   # ⊂ (0,1] 恒成立（引理 6 的安全负担全在 Π）

    def test_eligibility_credit_assignment(self) -> None:
        # 只有活跃维领赏罚：dim0 活跃、dim1 静默 → 正 δ 只推 dim0。
        phi = eligibility_update([0.0] * N_DIMS, [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        assert phi[0] > 0.0 and phi[1] == 0.0
        g0 = [0.5] * N_DIMS
        g1 = plasticity_step(g0, quality=1.0, q_hat=0.5, phi=phi)
        assert g1[0] > 0.5            # 活跃维升
        assert g1[1] == 0.5           # 静默维纹丝不动

    def test_delta_sign_direction(self) -> None:
        phi = [1.0] * N_DIMS
        up = plasticity_step([0.5] * N_DIMS, quality=0.9, q_hat=0.5, phi=phi)
        down = plasticity_step([0.5] * N_DIMS, quality=0.1, q_hat=0.5, phi=phi)
        assert all(u > 0.5 for u in up)       # 超预期 → 增益升
        assert all(d < 0.5 for d in down)     # 逊预期 → 增益降

    def test_eligibility_leaks_and_saturates(self) -> None:
        phi = [1.0] * N_DIMS
        phi = eligibility_update(phi, [0.0] * N_DIMS)
        assert all(abs(p - 0.6) < 1e-12 for p in phi)      # γ=0.6 泄漏
        phi = eligibility_update([0.9] * N_DIMS, [0.9] * N_DIMS)
        assert all(p == 1.0 for p in phi)                   # clamp01 饱和

    def test_baseline_ema(self) -> None:
        q = quality_baseline_update(0.5, 1.0)
        assert abs(q - 0.55) < 1e-12                        # β=0.1
        assert quality_baseline_update(float("nan"), 2.0) <= 1.0   # 消毒+夹域

    def test_timescale_ordering_conformance(self) -> None:
        # 注 6.1：α ≪ 典型 k·Δt_turn。60s 回合、最长非粘滞半衰期（boundary 120min、g≤2）
        # ⟹ 最慢典型速率 k·Δt = ln2/(120·2 min)·60s。α 须留 ≥5× 裕度。
        slowest_typical_k_dt = math.log(2) / (120.0 * 2.0 * 60.0) * 60.0
        assert slowest_typical_k_dt >= _PLASTICITY_ALPHA * 5, (
            _PLASTICITY_ALPHA, slowest_typical_k_dt
        )


class TestScarredStateGating:
    def _state(self, *, plasticity: bool = True) -> ScarredState:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True, plasticity=plasticity)
        return st

    def test_quality_step_gated_off(self) -> None:
        st = self._state(plasticity=False)
        assert st.apply_affect_quality(0.9) is False
        assert st._affect_gain is None                     # 完全 no-op

    def test_learns_under_full_gate(self) -> None:
        st = self._state()
        st.apply_affect_takeover(0.8, 0.7, 0.1, "撒娇")     # 建立资格迹
        assert st.apply_affect_quality(1.0) is True
        assert st._affect_gain is not None
        validate_gain(st._affect_gain)

    def test_pel_active_inert(self) -> None:
        st = ScarredState(n_dims=8, pel_enabled=True, affect_enabled=True)
        st.set_pel_priors({"openness": 0.6, "neuroticism": 0.6})
        st.set_affect_params(_TRAITS, takeover=True, plasticity=True)
        assert st.apply_affect_quality(0.9) is False       # PEL 下惰性

    def test_set_affect_params_preserves_learned_gain(self) -> None:
        st = self._state()
        st.apply_affect_takeover(0.8, 0.7, 0.1, "撒娇")
        st.apply_affect_quality(1.0)
        learned = list(st._affect_gain or [])
        st.set_affect_params(_TRAITS, takeover=True, plasticity=True)   # 人格重注入
        assert st._affect_gain == learned                  # 学习态不被清洗

    def test_persistence_roundtrip_and_restore_clamp(self) -> None:
        st = self._state()
        st.apply_affect_takeover(0.8, 0.7, 0.1, "撒娇")
        st.apply_affect_quality(1.0)
        d = st.to_dict()
        assert "affect_gain" in d and "affect_phi" in d and "affect_q_ema" in d
        rt = ScarredState.from_dict(d, affect_enabled=True)
        assert rt._affect_gain == st._affect_gain
        assert rt._affect_phi == st._affect_phi
        # 复原边界夹域：坏快照里的越界学习态被夹回 [ε,1]/[0,1]。
        d["affect_gain"] = [9.0] * 8
        d["affect_phi"] = [-3.0] * 8
        d["affect_q_ema"] = 42.0
        bad = ScarredState.from_dict(d, affect_enabled=True)
        assert bad._affect_gain == [1.0] * 8
        assert bad._affect_phi == [0.0] * 8
        assert bad._affect_q_ema == 1.0

    def test_no_learned_keys_when_off(self) -> None:
        st = self._state(plasticity=False)
        st.apply_affect_takeover(0.8, 0.7, 0.1, "撒娇")
        assert "affect_gain" not in st.to_dict()           # 关时快照无新增键

    def test_learned_gain_actually_changes_takeover(self) -> None:
        # 学习必须可观测：把增益学高后，同一 appraisal 推动 base 的幅度变大。
        def push_after_training(n_rewards: int) -> float:
            st = self._state()
            for _ in range(60):
                st.apply_affect_takeover(0.9, 0.8, 0.0, "撒娇")
                for _ in range(n_rewards):
                    st.apply_affect_quality(1.0)
            st.base = [0.0] * 8
            before = list(st.base)
            st.apply_affect_takeover(0.9, 0.8, 0.0, "撒娇")
            return sum(abs(st.base[i] - before[i]) for i in range(8))

        assert push_after_training(5) > push_after_training(0) + 1e-6


class TestSpineWiring:
    def _spine(self) -> ResonanceSpine:
        sp = ResonanceSpine(
            profile=build_profile("lite"),
            affect_enabled=True,
            affect_takeover=True,
            affect_plasticity=True,
        )
        sp.apply_personality(_TRAITS)
        return sp

    def test_explicit_quality_triggers_learning(self) -> None:
        sp = self._spine()
        a = {"valence": 0.6, "arousal": 0.6, "wound_risk": 0.1, "confidence": 0.8}
        sp.process("抱抱", timestamp=1.0, assessment=a)                       # 无 quality
        scar = sp._engine.scar_state
        assert scar._affect_q_ema == 0.5                                      # 基线未动=未学习
        sp.process("抱抱", timestamp=2.0, assessment=a, dialogue_quality=0.9)  # 显式 quality
        assert abs(scar._affect_q_ema - 0.54) < 1e-9                          # 学了（EMA 推进）
        assert scar._affect_gain is not None
        validate_gain(scar._affect_gain)

    def test_computation_spine_normal_route_learns(self) -> None:
        # 红队修订：钩子曾只挂在 fast 路由——冷启动前 15 回合走 normal 路由学不到。
        # 钩子已挪到 process() 入口，所有路由必须都学习。
        from sylanne_core.compute.computation_spine import ComputationSpine

        sp = ComputationSpine(
            profile=build_profile("lite"),
            affect_enabled=True,
            affect_takeover=True,
            affect_plasticity=True,
        )
        sp.apply_personality(_TRAITS)
        a = {"valence": 0.6, "arousal": 0.6, "wound_risk": 0.1, "confidence": 0.8}
        sp.process("抱抱我嘛好不好", timestamp=1.0, assessment=a)
        sp.process("再抱一下嘛", timestamp=2.0, assessment=a, dialogue_quality=0.9)
        scar = sp.engine.scar_state
        assert abs(scar._affect_q_ema - 0.54) < 1e-9      # normal 路由也学到了

    def test_quality_consumed_before_current_turn_phi(self) -> None:
        # 红队修订（信用序）：turn N 的 quality 在 turn N+1 自己的 assessment 更新
        # 资格迹**之前**消费——只有 turn N 活跃的维度领赏，turn N+1 独有的维度不领。
        sp = self._spine()
        # turn 1：只推 warmth/valence 类维度（正效价、低唤醒、无意图）
        sp.process("嗯", timestamp=1.0,
                   assessment={"valence": 0.9, "arousal": 0.0, "wound_risk": 0.0,
                               "confidence": 0.9})
        scar = sp._engine.scar_state
        phi_after_t1 = list(scar._affect_phi)
        gain_before = list(scar._affect_gain or [0.5] * 8)
        # turn 2：完全不同的活动形态（高唤醒）+ 对 turn 1 的好评。
        sp.process("！！！", timestamp=2.0,
                   assessment={"valence": 0.0, "arousal": 0.95, "wound_risk": 0.0,
                               "confidence": 0.9},
                   dialogue_quality=1.0)
        gain_after = list(scar._affect_gain or [])
        # 领赏的维度集合必须 ⊆ turn 1 的活跃集合（phi_after_t1>0 的维），
        # 与 turn 2 自己的活动无关（入口消费顺序保证）。
        for i in range(8):
            if phi_after_t1[i] == 0.0:
                assert gain_after[i] == gain_before[i], (
                    f"dim{i} 在 turn1 不活跃却领了 turn1 的赏"
                )

    def test_plasticity_off_never_learns(self) -> None:
        sp = ResonanceSpine(
            profile=build_profile("lite"), affect_enabled=True, affect_takeover=True
        )
        sp.apply_personality(_TRAITS)
        sp.process("抱抱", timestamp=1.0,
                   assessment={"valence": 0.6, "arousal": 0.6, "wound_risk": 0.1},
                   dialogue_quality=0.9)
        assert sp._engine.scar_state._affect_gain is None


class TestConfigValidation:
    def test_requires_takeover(self) -> None:
        import pytest

        from sylanne_core.config import SylanneConfig

        with pytest.raises(ValueError):
            SylanneConfig(affect_dynamics_enabled=True, affect_plasticity_enabled=True)
        SylanneConfig(
            affect_dynamics_enabled=True, affect_takeover=True, affect_plasticity_enabled=True
        )  # no raise

    def test_full_flag_reaches_scar_state(self, tmp_path) -> None:
        from sylanne_core.compute.host import SylanneAlphaHost

        h = SylanneAlphaHost(
            root=str(tmp_path),
            session_key="p",
            profile=build_profile("lite"),
            affect_enabled=True,
            affect_takeover=True,
            affect_plasticity=True,
        )
        assert h.kernel.computation._affect_plasticity is True   # 构造期到 spine
        from sylanne_core.compute.kernel import AlphaKernelEvent

        h.kernel.tick(AlphaKernelEvent(text="你好", now=1.0, confidence=0.5))
        scar = h.kernel.computation._engine.scar_state
        assert scar._affect_plasticity is True   # 首次 apply_personality 后到 scar

    def test_gain_vector_unused_when_learning(self) -> None:
        # 学习态建立后与 T 解耦：改 traits 不再移动生效增益（注 6.1 第三时标消失）。
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True, plasticity=True)
        st.apply_affect_takeover(0.8, 0.7, 0.1, "撒娇")
        st.apply_affect_quality(1.0)
        learned = list(st._affect_gain or [])
        shifted = dict(_TRAITS, perception_acuity=0.1)     # 大改人格
        st.set_affect_params(shifted, takeover=True, plasticity=True)
        assert st._effective_gain() == learned             # 生效增益仍是学习态
        assert affect_dynamics.gain_vector(shifted) != learned
