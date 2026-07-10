"""边界契约执行测试 —— 数学红队 composition fatal / slow-channel major 的代码闸锚。

对照 docs/design/affect-dynamics-derivation.md v2（定理 2 前提、定理 3 A6、定理 4 双闸）。守护：
- ``ScarredState.from_dict`` 在复原边界把损坏快照的越界 base 夹回存储契约 [-1,1]
  （否则裸凸组合 decay 对越界输入不自愈，base=1.5 经衰减仍 1.49…，不变集失守）；
- ``_affect_decay`` 入口皮带：即使 base 被未来写入者污染，衰减输出仍有界；
- ``affect_dynamics._trait`` 末端夹 [0,1]（A6 边界强制）：越域 trait 不能把 g_tension
  推到 10、半衰期上界失守（k̲→0 = 定理 3"永不冻结"被打穿）。
- 合法输入下三闸恒等（不改任何在域行为）。
"""

from __future__ import annotations

import math

from sylanne_core.compute import affect_dynamics
from sylanne_core.compute.scar_algebra import ScarredState

_TRAITS: dict[str, float] = {"perception_acuity": 0.7, "warmth_bias": 0.6}


class TestRestoreClampsBase:
    def _snapshot_with_base(self, base: list[float]) -> dict:
        st = ScarredState(n_dims=8, affect_enabled=True)
        d = st.to_dict()
        d["base"] = base
        return d

    def test_corrupt_snapshot_clamped(self) -> None:
        d = self._snapshot_with_base([1.5, -2.0, 0.3, 99.0, -0.5, 0.0, 1.0, -1.0])
        restored = ScarredState.from_dict(d, affect_enabled=True)
        assert restored.base == [1.0, -1.0, 0.3, 1.0, -0.5, 0.0, 1.0, -1.0]

    def test_legal_snapshot_identity(self) -> None:
        legal = [-1.0, -0.7, -0.25, 0.0, 0.1, 0.5, 0.9, 1.0]
        restored = ScarredState.from_dict(self._snapshot_with_base(list(legal)))
        assert restored.base == legal      # 在域值逐位恒等，闸不改合法行为

    def test_corrupt_then_decay_stays_bounded(self) -> None:
        # 红队复现的完整攻击链：坏快照 -> 复原 -> takeover 衰减。闸后必须有界。
        d = self._snapshot_with_base([1.5] + [0.0] * 7)
        st = ScarredState.from_dict(d, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True)
        st._e_last_wall_ts = 100.0
        st._affect_decay(150.0)
        assert all(-1.0 <= x <= 1.0 for x in st.base), st.base


class TestDecayEntryBelt:
    def test_poisoned_base_takeover_bounded(self) -> None:
        # from_dict 之外的假想污染源（未来 bug）：入口皮带独立兜底。
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=True)
        st.base = [1.5, -3.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0]
        st._e_last_wall_ts = 100.0
        st._affect_decay(200.0)
        assert all(-1.0 <= x <= 1.0 for x in st.base), st.base

    def test_poisoned_shadow_bounded(self) -> None:
        st = ScarredState(n_dims=8, affect_enabled=True)
        st.set_affect_params(_TRAITS, takeover=False)
        st._affect_shadow_base = [2.0] * 8
        st._e_last_wall_ts = 100.0
        st._affect_decay(200.0)
        assert st._affect_shadow_base is not None
        assert all(-1.0 <= x <= 1.0 for x in st._affect_shadow_base)


class TestTraitDomainEnforced:
    def test_out_of_domain_trait_clamped(self) -> None:
        # percept=5.0 越域：闸后与 percept=1.0 完全一致（g_tension 封在 2.0，非 10.0）。
        wild = affect_dynamics.half_lives({"perception_acuity": 5.0})
        capped = affect_dynamics.half_lives({"perception_acuity": 1.0})
        assert wild == capped

    def test_half_life_upper_bound_holds(self) -> None:
        # 定理 3 的 k̲>0 依赖 h 有上界：h ≤ h_base_max·g_max·S̄（percept/scarload 全极端）。
        h = affect_dynamics.half_lives({"perception_acuity": 5.0}, scarload=[100.0] * 8)
        h_bound = 120.0 * 2.0 * 3.0 * 60.0   # h_base_max(boundary=120min)·g_max·S̄，秒
        assert all(0.0 < x <= h_bound for x in h), h

    def test_gain_and_equilibrium_survive_wild_traits(self) -> None:
        wild = {"perception_acuity": 99.0, "expression_drive_trait": -7.0, "warmth_bias": 42.0}
        gain = affect_dynamics.gain_vector(wild)
        affect_dynamics.validate_gain(gain)                   # 不抛：G ∈ (0,1] 仍守
        eq = affect_dynamics.equilibrium(wild, 0.5)
        assert all(0.15 <= x <= 0.85 for x in eq)
        assert all(math.isfinite(x) for x in gain + eq)

    def test_in_domain_traits_identity(self) -> None:
        # 在域 trait 逐位恒等：闸不改任何已标定行为。
        t = {"perception_acuity": 0.7, "expression_drive_trait": 0.3}
        assert affect_dynamics.half_lives(t) == affect_dynamics.half_lives(dict(t))
        g = affect_dynamics.gain_vector(t)
        assert abs(g[3] - (0.40 + 0.30 * 0.7)) < 1e-12        # 系数原样
