"""记忆-情感耦合原语（v2.6.0 T4，纯函数层）。

设计对照：docs/design/v26-affect-dynamics-design.md §5（含 v26-upgrade-path §2 T4 更正）。

⚠ canonical 现状：**无**逐条打分的长期记忆库可接（``body.py`` 是信号计数、``shadow_memory`` 是
非持久顾问层）——§5 原设计针对的是**下游插件**的记忆库。故本模块只出**可复用纯原语**（情绪
相似度、传染凸混合、κ 人格函数），零调用点、零 IO、零状态。真正的记忆库出现前 flag-and-defer，
不接下游 ``MemoryItem``（SDK 未稳规则，见 feedback_no_premature_downstream）。

值域：情感核 E 即 ``ScarredState.base``（8 维，tanh (-1,1)）；本模块与 ``affect_dynamics`` 一致
以单位区间 [0,1] 立式，调用方接 base 时须先走 Phase 0 域适配器（``to_unit_interval``）。

红队 memory #1：κ（传染强度）是**人格函数**，不是扁平 config 标量——``contagion_blend`` 收 κ 为
**实参**；需要时用 ``contagion_kappa(traits)`` 派生，经 ``validate_scalar_params`` 守域。**不**加
SylanneConfig 字段。
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from .affect_dynamics import N_DIMS, validate_scalar_params

# κ 派生用的中性缺省 μ/ρ（仅为复用 validate_scalar_params 的三元断言凑数，不外泄）。
_MU_NEUTRAL, _RHO_NEUTRAL = 0.5, 0.5


def _finite(x: float, fallback: float) -> float:
    return x if math.isfinite(x) else fallback


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _trait(traits: Mapping[str, float] | None, name: str, default: float = 0.5) -> float:
    """安全读 canonical 人格维度，缺失/非有限给中性（与 affect_dynamics._trait 同型）。"""
    if not traits:
        return default
    try:
        v = float(traits.get(name, default))
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def emotion_match(e_now: list[float], m_e: list[float]) -> float:
    """当前 E 与记忆情绪指纹 ``m_e`` 的余弦相似度 ∈ [-1,1]。

    任一向量近零范数（无方向）⇒ 0.0（无匹配，而非 NaN）。长度不一致 ⇒ ValueError（契约违背，
    fail-closed，不静默截断）。非有限分量消毒为 0.0。
    """
    if len(e_now) != len(m_e):
        raise ValueError(f"emotion_match 维度不一致：{len(e_now)} vs {len(m_e)}")
    a = [_finite(x, 0.0) for x in e_now]
    b = [_finite(x, 0.0) for x in m_e]
    dot = sum(a[i] * b[i] for i in range(len(a)))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def contagion_blend(e: list[float], m_e: list[float], kappa: float) -> list[float]:
    """情绪传染凸混合：E' = (1−κ)·E + κ·m_e，逐维（§5）。

    κ 为**实参**（人格函数产物，见 ``contagion_kappa``），此处夹 [0,1] 保证是合法凸权重；
    E、m_e 均设在单位区间 [0,1] ⇒ 结果亦 ∈ [0,1]（凸组合保界）。长度不一致 ⇒ ValueError。
    非有限分量消毒。κ=0 ⇒ 忽略记忆（返回 E）；κ=1 ⇒ 完全采纳记忆情绪。
    """
    if len(e) != len(m_e):
        raise ValueError(f"contagion_blend 维度不一致：{len(e)} vs {len(m_e)}")
    k = _clamp01(_finite(float(kappa), 0.0))
    out = [0.0] * len(e)
    for i in range(len(e)):
        ei = _finite(e[i], 0.0)
        mi = _finite(m_e[i], 0.0)
        out[i] = _clamp01((1.0 - k) * ei + k * mi)
    return out


def contagion_kappa(traits: Mapping[str, float] | None) -> float:
    """传染强度 κ(T) ∈ (0,1]（人格函数，红队 memory #1）。

    高共情/关系引力 → 更易被记忆情绪传染。基线 0.3，随 ``relational_gravity`` /
    ``agreeableness`` 上调，末端夹 (0,1] 并过 ``validate_scalar_params`` 断言良定域。
    """
    rel_grav = _trait(traits, "relational_gravity")
    agree = _trait(traits, "agreeableness")
    kappa = 0.30 + 0.35 * (rel_grav - 0.5 + agree - 0.5)
    kappa = min(1.0, max(1e-3, kappa))
    validate_scalar_params(kappa, _MU_NEUTRAL, _RHO_NEUTRAL)
    return kappa


__all__ = [
    "N_DIMS",
    "emotion_match",
    "contagion_blend",
    "contagion_kappa",
]
