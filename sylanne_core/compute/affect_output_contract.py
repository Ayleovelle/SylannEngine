"""情感输出契约：E → 离散情绪标签（v2.6.0 T2，纯函数层 + 迟滞）。

设计对照：docs/design/v26-affect-dynamics-design.md §6.1（含 v26-upgrade-path §2 T2 更正）。

⚠ canonical 已有一个**在世**的分类标签器 ``Surface.pad.label``（adapter→pad_interop→types，
位置式 E→Plutchik-8，§0.5 pt4 判其现状已错、超出本轮范围）。本模块是**并行影子**标签器
（带迟滞、只进 diagnostics）：Gate A 只诊断不夺权，``resolve_label`` 是否取代/弃用/共存
``pad.label`` 是 **T6** 的显式决策；此处**共存**，绝不静默上第二个打架的标签器。

值域：读 ``observe()`` 的 base 维（tanh (-1,1)），调用方折进 [0,1] 后传入本模块。§6.1 未点名
LUT 键维——此处取 **valence/arousal** 两维（经典情感环形，circumplex）为默认键（影子期可标定
先验，词表 9 词均待产品签字定稿）；warmth/tension 预留作后续细化。

迟滞：逐维 Schmitt 触发——某键维要跨越量化边界，必须越过 θ_h 死区才切换，防止 E 在边界抖动
时标签频繁翻动（§6.1）。**每真实 tick 至多推进一次**（调用方以 kernel.turns 守）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .affect_dynamics import N_DIMS

# 键维（canonical 维序：warmth0 arousal1 valence2 tension3 ...）。valence/arousal 为 circumplex 两轴。
_KEY_DIMS: tuple[int, ...] = (2, 1)   # (valence, arousal)
# 三档量化切点（单位区间 [0,1]）：<1/3 低、[1/3,2/3) 中、>=2/3 高。
_CUTS: tuple[float, float] = (1.0 / 3.0, 2.0 / 3.0)
_DEFAULT_THETA_H: float = 0.08        # 迟滞死区（可标定）
_DEFAULT_LABEL: str = "中性"

# (valence_level, arousal_level) -> 中文情绪词（circumplex-9，影子期可标定先验）。
EMOTION_LUT: dict[tuple[int, int], str] = {
    (0, 0): "低落",   # 负效价 + 低唤醒
    (0, 1): "郁闷",
    (0, 2): "焦躁",   # 负效价 + 高唤醒
    (1, 0): "平静",
    (1, 1): "中性",
    (1, 2): "警觉",
    (2, 0): "安然",   # 正效价 + 低唤醒
    (2, 1): "愉悦",
    (2, 2): "雀跃",   # 正效价 + 高唤醒
}


@dataclass
class HysteresisState:
    """迟滞状态：当前量化键 + 已解析标签（每 tick 至多更新一次）。"""

    key: tuple[int, ...]
    label: str


def _level(x: float) -> int:
    return 0 if x < _CUTS[0] else 1 if x < _CUTS[1] else 2


def _margin_to_boundary(x: float) -> float:
    """到最近量化切点的距离（越大＝越深入某档，切换越可信）。"""
    return min(abs(x - _CUTS[0]), abs(x - _CUTS[1]))


def quantize(e_unit: list[float], key_dims: tuple[int, ...] = _KEY_DIMS) -> tuple[int, ...]:
    """把单位区间 E 的键维量化成离散键（无迟滞的原始量化）。"""
    return tuple(_level(e_unit[d]) for d in key_dims)


def resolve_label(
    e_unit: list[float],
    prev: HysteresisState | None,
    theta_h: float = _DEFAULT_THETA_H,
) -> tuple[str, HysteresisState]:
    """单位区间 E → (情绪标签, 新迟滞状态)，逐维 Schmitt 死区抗抖。

    - 无前态 ⇒ 直接采纳原始量化键。
    - 某键维想变档：仅当该维值越过边界 ≥ θ_h（决然跨越）才切换；否则该维保持前态档位
      （迟滞 hold），杜绝边界抖动导致标签翻动。
    - 键落 LUT 外 ⇒ 缺省标签 "中性"（不抛，诊断路径 fail-soft）。
    """
    raw = quantize(e_unit)
    if prev is None:
        key = raw
    else:
        merged = list(prev.key)
        for i, d in enumerate(_KEY_DIMS):
            if i < len(prev.key) and raw[i] != prev.key[i]:
                if _margin_to_boundary(e_unit[d]) >= theta_h:
                    merged[i] = raw[i]
                # else: hold prev level for this dim (hysteresis deadband)
            else:
                merged[i] = raw[i]
        key = tuple(merged)
    label = EMOTION_LUT.get(key, _DEFAULT_LABEL)  # type: ignore[arg-type]
    return label, HysteresisState(key=key, label=label)


__all__ = [
    "N_DIMS",
    "EMOTION_LUT",
    "HysteresisState",
    "quantize",
    "resolve_label",
]
