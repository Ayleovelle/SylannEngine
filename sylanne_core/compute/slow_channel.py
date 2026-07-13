"""慢通道编排器（v2.6.0 T5，Gate C：不可逆人格漂移，默认关）。

设计对照：docs/design/v26-affect-dynamics-design.md §4.2 / §8（含 v26-upgrade-path §2 T5）。

职责：把逐回合的刻骨 appraisal 累积成 poignancy 漏桶；越阈 + 墙钟冷却触发一次**反思**，对
Embodiment 人格做一次有界、锚回弹、可回滚的 **macro 漂移**。纯数学在 ``affect_dynamics``；本类
只做有状态编排，宿主为 spine（持 ``_embodiment_traits``）。

红队更正已折入：
- drift #1 原子性：反思**先** snapshot 环 → 再变异特质；变异中途异常从 snapshot 自恢复，绝不留
  半变异态。
- drift #2 批量≠逐拍：macro 漂移经既有 ``compute_embodiment_drift`` 单写路径（速率闸/震荡检测/
  归因/TraitMemory.update 一致），**不**声称与逐拍字节一致；这是一次显式的有界漂移事件。
- 锚回弹朝**不可变 anchor**（非自适应 set_point），防 z-gate "自适应基线追信号" 失败模式。

未定项（影子期可标定先验，待产品签字）：appraisal→trait 方向映射、θ/μ/η/ρ/cooldown 数值。
持久化：runtime-only（in-flight poignancy 不落盘；已提交的漂移经 TraitMemory.anchor/value 落盘）。
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from . import affect_dynamics

if TYPE_CHECKING:
    from .personality import (
        DriftAttribution,
        OscillationDetector,
        TraitMemory,
    )

# --- 反思参数（校准先验；模块加载即过良定域断言，typo 立崩） ---
_THETA = 3.0  # poignancy 反思阈
_MU = 0.10  # 漏桶泄漏率/tick
_ETA = 0.30  # macro 漂移步长
_RHO = 0.20  # 锚回弹收缩率
_COOLDOWN_SECS = 1800.0  # 反思墙钟冷却（30 min）
_REFLECTION_DT = 30.0  # 传给 compute_embodiment_drift 的名义 dt（走同一速率闸）
_RING_MAXLEN = 5

affect_dynamics.validate_slowchannel_params(_THETA, _MU, _ETA, _RHO, _COOLDOWN_SECS)

# appraisal a_k 维序：warmth0 arousal1 valence2 tension3 curiosity4 repair5 expr6 boundary7。
# 方向映射：反复的某类情感事件把对应 Embodiment 特质朝某方向漂（校准先验）。
_TRAIT_DRIFT_MAP: dict[str, list[tuple[int, float]]] = {
    "expression_drive_trait": [(6, 1.0), (1, 0.3)],  # 表达 + 唤醒 → 更外放
    "perception_acuity": [(3, 0.8)],  # 张力 → 更警觉
    "boundary_permeability": [(7, -1.0)],  # 边界坚固 → 更不可渗透
    "inner_order": [(3, -0.5), (5, -0.3)],  # 张力/修复压 → 侵蚀秩序
    "relational_gravity": [(0, 0.7), (2, 0.5)],  # 温度 + 效价 → 更强关系引力
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _snapshot_traits(traits: dict[str, TraitMemory]) -> dict[str, Any]:
    """Full per-trait snapshot for atomic rollback. Captures ``_frozen_ticks`` and the
    immutable ``anchor`` explicitly — ``TraitMemory.to_dict`` may omit both (red-team #3),
    so restoring via ``from_dict`` alone would silently un-freeze mid-cooldown traits and
    reset the anchor."""
    return {name: (tm.to_dict(), tm._frozen_ticks, tm.anchor) for name, tm in traits.items()}


def _restore_traits(traits: dict[str, TraitMemory], snapshot: dict[str, Any]) -> None:
    from .personality import TraitMemory

    for name, (td, frozen, anchor) in snapshot.items():
        if name in traits:
            tm = TraitMemory.from_dict(td)
            tm._frozen_ticks = frozen
            tm.anchor = anchor
            traits[name] = tm


class SlowChannel:
    """有状态慢通道：poignancy 累积 + 反思触发 + 原子锚回弹 macro 漂移 + 回滚环。"""

    __slots__ = (
        "active",
        "_pi",
        "_pending",
        "_events",
        "_reflection_count",
        "_last_reflection_wall",
        "_ring",
    )

    def __init__(self, active: bool = False) -> None:
        self.active = active
        self._pi: float = 0.0
        self._pending: dict[str, float] = {}
        self._events: int = 0
        self._reflection_count: int = 0
        self._last_reflection_wall: float = 0.0
        self._ring: deque[dict[str, Any]] = deque(maxlen=_RING_MAXLEN)

    def observe(self, a_k: list[float]) -> None:
        """累积一次刻骨 appraisal：更新 poignancy 漏桶 + 逐特质方向累积。"""
        if not self.active:
            return
        inflow = affect_dynamics.poignancy_magnitude(a_k)
        self._pi = affect_dynamics.poignancy_update(self._pi, inflow, _MU)
        for trait, mapping in _TRAIT_DRIFT_MAP.items():
            contrib = sum(w * (a_k[d] if d < len(a_k) else 0.0) for d, w in mapping)
            self._pending[trait] = self._pending.get(trait, 0.0) + contrib
        self._events += 1

    def ready(self, now: float) -> bool:
        return self.active and affect_dynamics.reflection_ready(
            self._pi, _THETA, now, self._last_reflection_wall, _COOLDOWN_SECS
        )

    def maybe_reflect(
        self,
        traits: dict[str, TraitMemory],
        now: float,
        drift_tick: int,
        dialogue_quality: float = 0.5,
        oscillation_detector: OscillationDetector | None = None,
        drift_attribution: DriftAttribution | None = None,
    ) -> bool:
        """越阈+冷却则原子提交一次反思漂移。返回 True=已提交。

        原子性（drift #1）：先把当前**特质**态（含 _frozen_ticks）存入回滚环，再变异；
        ``compute_embodiment_drift`` 抛异常时从环快照逐特质自恢复，poignancy/pending 也不清
        （下次重试），绝不留半变异的特质。**注意**：原子性只覆盖 ``traits``——传入的
        OscillationDetector/DriftAttribution 是诊断累积器，失败时其记录不回滚（红队 #6-minor，
        仅观测层，不影响特质正确性）。
        """
        from .personality import compute_embodiment_drift

        if not self.ready(now):
            return False

        # 1) 先快照（原子提交的回滚点）——drift #1：变异前先备份（含 _frozen_ticks）。
        snapshot = _snapshot_traits(traits)

        # 2) 质量条件化 + 锚回弹算 macro_deltas。方向 = 累积方向按事件数归一后夹 [-1,1]。
        q = affect_dynamics.q_dc(dialogue_quality)
        norm = max(1, self._events)
        macro_deltas: dict[str, float] = {}
        for name, tm in traits.items():
            direction = _clamp(self._pending.get(name, 0.0) / norm, -1.0, 1.0)
            macro_deltas[name] = q * affect_dynamics.drift_step(
                tm.anchor, tm.value, direction, _ETA, _RHO
            )

        # 3) 经单写路径提交；失败从快照回滚，pending/pi 保留待重试。
        try:
            compute_embodiment_drift(
                traits,
                {},
                drift_tick,
                oscillation_detector=oscillation_detector,
                drift_attribution=drift_attribution,
                dt=_REFLECTION_DT,
                macro_deltas=macro_deltas,
            )
        except Exception:
            _restore_traits(traits, snapshot)
            return False

        # 4) 成功：入环、清账、推进冷却。
        self._ring.append(snapshot)
        self._pi = 0.0
        self._pending = {}
        self._events = 0
        self._reflection_count += 1
        self._last_reflection_wall = float(now)
        return True

    def rollback_last(self, traits: dict[str, TraitMemory]) -> bool:
        """从环回滚最近一次已提交的反思漂移（外部撤销钩子）。返回 True=已回滚。"""
        if not self._ring:
            return False
        _restore_traits(traits, self._ring.pop())
        if self._reflection_count > 0:
            self._reflection_count -= 1
        return True

    def status(self) -> dict[str, Any]:
        """诊断快照（只读）。"""
        return {
            "active": self.active,
            "poignancy": round(self._pi, 4),
            "reflection_count": self._reflection_count,
            "last_reflection_wall": self._last_reflection_wall,
            "pending_events": self._events,
            "ring_depth": len(self._ring),
        }


__all__ = ["SlowChannel"]
