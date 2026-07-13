"""v2.6.0 Phase 0 值域适配器契约 —— [0,1] ↔ (-1,1) tanh 存储帧（纯函数、additive）。

对照 docs/design/v26-upgrade-path.md §1（红队 e-core "domain mismatch" BLOCKER 的解药）。守护：
- 往返恒等（base∈[-1,1] 与 E∈[0,1] 各自值域内严格互逆）；
- 边界与非有限消毒（越界快照/NaN 不外溢）；
- ``decay`` 的仿射等变性（只 remap Φ_eq 与整体折进折出等价）——这是 T1/T3 只对均衡点做
  域变换的正确性依据；``saturating_update`` 则**不**具此性质，必须整体折进折出。
"""

from __future__ import annotations

import math

from sylanne_core.compute.affect_dynamics import (
    N_DIMS,
    decay,
    from_unit_interval,
    saturating_update,
    to_unit_interval,
)


class TestRoundTrip:
    def test_base_to_unit_and_back_identity(self) -> None:
        base = [-1.0, -0.7, -0.25, 0.0, 0.1, 0.5, 0.9, 1.0]
        rt = from_unit_interval(to_unit_interval(base))
        assert all(abs(a - b) < 1e-12 for a, b in zip(base, rt, strict=True)), rt

    def test_unit_to_base_and_back_identity(self) -> None:
        e = [0.0, 0.1, 0.25, 0.5, 0.6, 0.75, 0.9, 1.0]
        rt = to_unit_interval(from_unit_interval(e))
        assert all(abs(a - b) < 1e-12 for a, b in zip(e, rt, strict=True)), rt

    def test_midpoints_map_across_frames(self) -> None:
        assert all(abs(x - 0.5) < 1e-12 for x in to_unit_interval([0.0] * N_DIMS))
        assert all(abs(x) < 1e-12 for x in from_unit_interval([0.5] * N_DIMS))


class TestBoundedAndSanitized:
    def test_to_unit_bounded_for_any_input(self) -> None:
        # 复原快照可能越界 (±1 外)——末端夹 [0,1]，绝不外溢。
        out = to_unit_interval([-3.0, -1.5, -1.0, 0.0, 1.0, 1.5, 3.0, 42.0])
        assert all(0.0 <= o <= 1.0 for o in out), out

    def test_from_unit_bounded_for_any_input(self) -> None:
        out = from_unit_interval([-2.0, -0.5, 0.0, 0.3, 1.0, 1.5, 9.0, 0.5])
        assert all(-1.0 <= o <= 1.0 for o in out), out

    def test_nonfinite_neutralized(self) -> None:
        nan, inf = float("nan"), float("inf")
        u = to_unit_interval([nan, inf, -inf, 0.0])
        assert all(math.isfinite(x) for x in u)
        assert abs(u[0] - 0.5) < 1e-12 and abs(u[1] - 0.5) < 1e-12 and abs(u[2] - 0.5) < 1e-12
        b = from_unit_interval([nan, inf, -inf, 0.5])
        assert all(math.isfinite(x) for x in b)
        assert abs(b[0]) < 1e-12 and abs(b[1]) < 1e-12 and abs(b[2]) < 1e-12


class TestDecayAffineEquivariance:
    """decay 是仿射 lerp ⇒ 仿射等变：整体折进折出 == 只把 Φ_eq remap 到 native、base 留原帧。"""

    def test_remap_eq_only_equals_full_roundtrip(self) -> None:
        base = [-0.8, -0.3, 0.0, 0.2, 0.5, 0.7, -0.5, 0.9]  # native (-1,1)
        eq_unit = [0.15, 0.85, 0.5, 0.3, 0.45, 0.55, 0.25, 0.45]  # Φ_eq ∈ [0,1]
        h = [90.0, 30.0, 60.0, 45.0, 40.0, 50.0, 25.0, 120.0]
        dt = 37.0

        # 路线 A：整体折进 [0,1]、在单位区间衰减、再折回 native。
        full = from_unit_interval(decay(to_unit_interval(base), eq_unit, [x * 60.0 for x in h], dt))
        # 路线 B：base 留 native，只把 Φ_eq 折回 native 作为衰减目标（T1/T3 采用的捷径）。
        shortcut = decay(base, from_unit_interval(eq_unit), [x * 60.0 for x in h], dt)

        assert all(abs(a - b) < 1e-12 for a, b in zip(full, shortcut, strict=True)), (
            full,
            shortcut,
        )

    def test_saturating_update_is_not_affine_equivariant(self) -> None:
        # 反证：饱和更新硬编 0/1 界，直接喂 native base 与折进折出结果**不同**——钉死"必须适配"。
        # 分歧只在**负向** a 暴露：unit 帧"拉向 0"= 拉向地板 (native −1)，native 帧却拉向中点 0，
        # 语义完全不同（负效价事件应压向底，而非拉回中性）——正是必须走适配器的根因。
        base = [-0.6, -0.2, 0.0, 0.3, 0.5, 0.7, -0.4, 0.8]
        a_k = [-0.5] * N_DIMS
        gain = [1.0] * N_DIMS
        proper = from_unit_interval(saturating_update(to_unit_interval(base), a_k, gain))
        naive = saturating_update(base, a_k, gain)  # 错用：base 未折进单位区间
        assert any(abs(a - b) > 1e-6 for a, b in zip(proper, naive, strict=True))
        assert all(-1.0 <= p <= 1.0 for p in proper)  # 正确路线仍有界
