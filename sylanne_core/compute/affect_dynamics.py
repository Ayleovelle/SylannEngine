"""情感核 E 律 —— 墙钟衰减 / 饱和快更新 / 人格均衡（v2.6.0 T1，纯函数层）。

设计对照：docs/design/v26-affect-dynamics-design.md §2.2 / §3.3 / §8（含 §0.5 canonical 对账）。

位置：情感核 E 即 ``ScarredState.base``（8 维，维序见 ``VoidScarEngine._DIM_NAMES``）。本模块提供
E 的动力学**纯函数**——墙钟惰性衰减到人格均衡、每轮饱和快更新、以及派生这两者所需的人格函数
（均衡 Φ_eq / 半衰期 / 增益 G）。**本层全部无状态、无 IO、无 LLM，不改动任何现有引擎状态**；
把它们接入 ``ScarredState.step()`` 时间推进与两个 assessor 写入点，是后续 T1 切片（届时按
"零行为变更 + 影子并跑证等价"纪律推进）。

人格驱动全参数：Φ_eq / 半衰期 / 增益全部派生自 canonical 人格 traits（Embodiment Five +
Sylanne Six，见 personality.py:26-43）。有界性硬前提 G_i∈(0,1]，由 ``validate_gain`` 守（越界即
fail-closed 抛，不带病更新）；κ/μ/ρ 的良定域断言集中于此供 T4/T5 与 config 校验复用。

数值纪律：非有限输入（NaN/inf）一律消毒/守卫，杜绝污染 E 并落盘（T1 code-review F1/F4）。
"""

from __future__ import annotations

import math
from collections.abc import Mapping

N_DIMS: int = 8
_I_WARMTH, _I_AROUSAL, _I_VALENCE, _I_TENSION = 0, 1, 2, 3
_I_CURIOSITY, _I_REPAIR, _I_EXPR, _I_BOUNDARY = 4, 5, 6, 7

# 均衡值域强制内收 → 均衡永不落角落（反吸收态①，§2.2）。
_EQ_LO, _EQ_HI = 0.15, 0.85
# 伤痕粘滞封顶（反吸收态②）：σ·scarload 使半衰期最多变长 ×3。
_STICKY_CAP, _SIGMA = 3.0, 1.0
# 半衰期基线（分钟，影子期可标定先验）：arousal/expr 短，boundary/warmth 长。
_H_BASE_MIN: tuple[float, ...] = (90.0, 30.0, 60.0, 45.0, 40.0, 50.0, 25.0, 120.0)
_SECONDS_PER_MIN = 60.0


def _finite(x: float, fallback: float) -> float:
    return x if math.isfinite(x) else fallback


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _trait(traits: Mapping[str, float] | None, name: str, default: float = 0.5) -> float:
    """安全读 canonical 人格维度（Embodiment Five / Sylanne Six 键名），缺失/非有限给中性。"""
    if not traits:
        return default
    try:
        v = float(traits.get(name, default))
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


# ===========================================================================
# 参数良定域断言（越界 = fail-closed；κ/μ/ρ 供 T4/T5 与 SylanneConfig 校验复用）
# ===========================================================================

def validate_gain(gain: list[float]) -> None:
    """G_i ∈ (0,1] 逐维（否则饱和更新 E 越界，§3.3）。越界抛 ValueError。"""
    if len(gain) != N_DIMS:
        raise ValueError(f"gain 维度须为 {N_DIMS}，得到 {len(gain)}")
    for i, g in enumerate(gain):
        if not (0.0 < g <= 1.0):
            raise ValueError(f"G[{i}]={g} 越界，须 ∈ (0,1]（§8 参数良定域）")


def validate_scalar_params(kappa: float, mu: float, rho: float) -> None:
    """κ∈(0,1]、μ∈(0,1)、ρ∈(0,1)（传染凸组合 / 漏桶收敛 / 漂移锚回弹收缩，§8）。"""
    if not (0.0 < kappa <= 1.0):
        raise ValueError(f"κ={kappa} 越界，须 ∈ (0,1]")
    if not (0.0 < mu < 1.0):
        raise ValueError(f"μ={mu} 越界，须 ∈ (0,1)")
    if not (0.0 < rho < 1.0):
        raise ValueError(f"ρ={rho} 越界，须 ∈ (0,1)")


# ===========================================================================
# 人格函数：Φ_eq（均衡）/ 半衰期 / 增益 G —— 全部派生自 canonical traits
# ===========================================================================

def equilibrium(traits: Mapping[str, float] | None, relationship: float = 0.5) -> list[float]:
    """Φ_eq(T,R)：canonical 人格 + 关系决定的常驻情绪基线，值域强制内收 [0.15,0.85]（§2.2）。

    用 canonical trait 键（personality.py:26-43）：warmth_bias→warmth，perception_acuity→tension，
    curiosity→curiosity，expression_drive_trait→expression_drive，sovereignty_guard/inner_order→
    boundary，relational_gravity→valence。系数为影子期可标定先验；方向性由测试锚定单调。
    """
    warmth_bias = _trait(traits, "warmth_bias")
    percept = _trait(traits, "perception_acuity")     # neuroticism-like（对张力敏感）
    curio = _trait(traits, "curiosity")
    expr_drive = _trait(traits, "expression_drive_trait")
    rel_grav = _trait(traits, "relational_gravity")
    sov = _trait(traits, "sovereignty_guard")
    order = _trait(traits, "inner_order")
    rel = _clamp01(_finite(float(relationship), 0.5))

    eq = [0.0] * N_DIMS
    eq[_I_WARMTH] = 0.50 + 0.30 * (rel - 0.5) + 0.20 * (warmth_bias - 0.5)
    eq[_I_AROUSAL] = 0.35 + 0.20 * (expr_drive - 0.5) + 0.15 * (percept - 0.5)
    eq[_I_VALENCE] = 0.55 + 0.20 * (rel_grav - 0.5) - 0.20 * (percept - 0.5)
    eq[_I_TENSION] = 0.30 + 0.25 * (percept - 0.5)
    eq[_I_CURIOSITY] = 0.45 + 0.25 * (curio - 0.5)
    eq[_I_REPAIR] = 0.25 + 0.15 * (percept - 0.5)
    eq[_I_EXPR] = 0.45 + 0.30 * (expr_drive - 0.5)
    eq[_I_BOUNDARY] = 0.45 + 0.20 * (sov - 0.5) + 0.10 * (order - 0.5)
    return [_clamp(x, _EQ_LO, _EQ_HI) for x in eq]


def half_lives(
    traits: Mapping[str, float] | None,
    scarload: list[float] | None = None,
) -> list[float]:
    """半衰期 h_i（秒）= h_base_i · g_i(T) · min(1+σ·scarload_i, 3)（§2.2）。

    高 perception_acuity → tension 半衰期长（会反刍）；活跃伤痕使维度粘滞（封顶 ×3）。
    T1 的 scarload 默认全零（钩子留给 T5 慢通道反哺）。
    """
    percept = _trait(traits, "perception_acuity")
    g = [1.0] * N_DIMS
    g[_I_TENSION] = max(0.3, 1.0 + (percept - 0.5) * 2.0)     # 高敏 → tension 更粘（反刍）
    sc = scarload if scarload and len(scarload) == N_DIMS else [0.0] * N_DIMS
    out = [0.0] * N_DIMS
    for i in range(N_DIMS):
        load = _finite(float(sc[i]), 0.0)
        sticky = min(1.0 + _SIGMA * max(0.0, load), _STICKY_CAP)
        out[i] = _H_BASE_MIN[i] * g[i] * sticky * _SECONDS_PER_MIN
    return out


def gain_vector(traits: Mapping[str, float] | None) -> list[float]:
    """快更新增益 G(T) ∈ (0,1] 逐维（§3.3 有界性前提）。

    perception_acuity→tension 增益↑，expression_drive_trait→expression_drive 增益↑。
    全维夹进 (0,1] 保饱和更新有界。
    """
    percept = _trait(traits, "perception_acuity")
    expr_drive = _trait(traits, "expression_drive_trait")
    g = [0.5] * N_DIMS
    g[_I_TENSION] = 0.40 + 0.30 * percept
    g[_I_EXPR] = 0.40 + 0.30 * expr_drive
    return [_clamp(x, 1e-3, 1.0) for x in g]


# ===========================================================================
# 衰减 / 饱和更新（纯函数）
# ===========================================================================

def decay(e0: list[float], e_eq: list[float], h_secs: list[float], dt_secs: float) -> list[float]:
    """闭式惰性衰减：E(t) = E_eq + (E₀−E_eq)·2^(−Δt/h)（半衰期形式，§2.2）。

    dt≤0 或非有限（时钟回拨/NaN 墙钟）⇒ 原样返回（F4 守卫）。h≤0 视作瞬时回到 E_eq。
    """
    if not math.isfinite(dt_secs) or dt_secs <= 0.0:
        return list(e0)
    out = [0.0] * N_DIMS
    for i in range(N_DIMS):
        h = h_secs[i]
        if h <= 0.0:
            out[i] = e_eq[i]
        else:
            out[i] = e_eq[i] + (e0[i] - e_eq[i]) * (2.0 ** (-dt_secs / h))
    return out


def saturating_update(e: list[float], a_k: list[float], gain: list[float]) -> list[float]:
    """饱和快更新：E ← E + G⊙[a]₊⊙(1−E) − G⊙[a]₋⊙E（§3.3）。

    [a]₊=max(a,0)、[a]₋=max(−a,0) 均非负幅度；正向拉向 1、负向拉向 0，近边界降幅→0。
    G_i∈(0,1] 由 validate_gain 保证；此处仍夹 [0,1] + 消毒非有限，防浮点/NaN 漏出。
    """
    out = [0.0] * N_DIMS
    for i in range(N_DIMS):
        ai = _finite(a_k[i], 0.0)
        ap = ai if ai > 0.0 else 0.0
        am = -ai if ai < 0.0 else 0.0
        nxt = e[i] + gain[i] * ap * (1.0 - e[i]) - gain[i] * am * e[i]
        out[i] = _clamp01(_finite(nxt, e[i]))
    return out


__all__ = [
    "N_DIMS",
    "equilibrium",
    "half_lives",
    "gain_vector",
    "decay",
    "saturating_update",
    "validate_gain",
    "validate_scalar_params",
]
