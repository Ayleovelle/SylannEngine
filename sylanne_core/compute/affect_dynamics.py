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
    """安全读 canonical 人格维度（Embodiment Five / Sylanne Six 键名），缺失/非有限给中性。

    末端夹 [0,1]：在 affect_dynamics 入口硬性执行特质域假设（推导 A6），而非依赖上游
    恰好用 TraitMemory 供值——否则越域 trait（如 percept=5.0）会把 g_tension 推到 10，
    半衰期上界失守、k̲→0（定理 3 的"永不冻结"被打穿；数学红队 slow-channel 发现）。
    """
    if not traits:
        return default
    try:
        v = float(traits.get(name, default))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return _clamp01(v)


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
    percept = _trait(traits, "perception_acuity")  # neuroticism-like（对张力敏感）
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
    g[_I_TENSION] = max(0.3, 1.0 + (percept - 0.5) * 2.0)  # 高敏 → tension 更粘（反刍）
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

    ⚠ 值域契约：本式硬编 0/1 上下界（``1-E``/``E`` 因子），**非仿射等变**——喂入的 E 必须已在
    单位区间 [0,1]。接 ``ScarredState.base``（tanh (-1,1)）时**必须**先 ``to_unit_interval`` 再
    ``from_unit_interval``，不可走 ``decay`` 那种只 remap 均衡点的仿射捷径（设计 v26-upgrade-path §1）。
    """
    out = [0.0] * N_DIMS
    for i in range(N_DIMS):
        ai = _finite(a_k[i], 0.0)
        ap = ai if ai > 0.0 else 0.0
        am = -ai if ai < 0.0 else 0.0
        nxt = e[i] + gain[i] * ap * (1.0 - e[i]) - gain[i] * am * e[i]
        out[i] = _clamp01(_finite(nxt, e[i]))
    return out


# ===========================================================================
# Delta-rule 增益可塑性（v26 A.2，推导 §6 / 引理 6 投影契约）
# ===========================================================================
# G_{t+1} = Π_{[ε,1]}(G_t + α·δ_t·φ_t)：δ = clip(quality − q̂)，q̂ 为 quality 的 EMA
# 基线，φ 为逐维资格迹（近期 |a| 活动的泄漏累积——只有参与了情绪反应的维度领赏罚，
# 注 6.2 的信用分配结构件）。安全由投影 Π 保证（引理 6：定理 1–4 只用 G 的界），
# 与学习信号质量无关。α 按注 6.1 时标排序取：α ≪ 典型 k·Δt_turn。学习态 G 一旦
# 建立即与 T 解耦（人格漂移不再跳变 G——注 6.1 第三时标在 learned-G 下消失）。

_GAIN_FLOOR: float = 0.05  # ε：投影下限（防增益死亡；ε>0 保 (A3)）
_PLASTICITY_ALPHA: float = 0.0005  # α：学习率（时标排序 conformance 锚定：最慢典型维
# k·Δt=ln2/(120·2min)·60s≈0.0029，α 留 ~5.8× 裕度。刻意冰川速度——人格毗邻态就该慢，
# 持续超预期反馈下移动一个 0.1 的增益量级需 ~200 次显式 quality 反馈（数天活跃聊天）。
_PHI_GAMMA: float = 0.6  # 资格迹保持率（泄漏 = 1−γ）
_Q_EMA_BETA: float = 0.1  # quality 基线 EMA 步长


def eligibility_update(phi: list[float], a_k: list[float]) -> list[float]:
    """资格迹更新：φ ← clamp01(γ·φ + |a|)。逐维、非有限消毒、恒 ∈ [0,1]。"""
    out = [0.0] * N_DIMS
    for i in range(N_DIMS):
        p = _finite(phi[i], 0.0) if i < len(phi) else 0.0
        a = abs(_finite(a_k[i], 0.0)) if i < len(a_k) else 0.0
        out[i] = _clamp01(_PHI_GAMMA * p + a)
    return out


def quality_baseline_update(q_hat: float, quality: float) -> float:
    """quality 基线 EMA：q̂ ← (1−β)·q̂ + β·q。非有限消毒、恒 ∈ [0,1]。"""
    qh = _clamp01(_finite(float(q_hat), 0.5))
    q = _clamp01(_finite(float(quality), 0.5))
    return _clamp01((1.0 - _Q_EMA_BETA) * qh + _Q_EMA_BETA * q)


def plasticity_step(
    gain: list[float],
    quality: float,
    q_hat: float,
    phi: list[float],
    alpha: float = _PLASTICITY_ALPHA,
) -> list[float]:
    """delta-rule 增益步：G ← Π_{[ε,1]}(G + α·δ·φ)，δ = clip(q − q̂, [−1,1])。

    投影 Π 无条件执行（引理 6 的全部安全负担在此）；对抗/噪声 quality 序列下输出
    恒 ∈ [ε,1] ⊂ (0,1]，`validate_gain` 恒通过。非有限一律消毒。
    """
    q = _clamp01(_finite(float(quality), 0.5))
    qh = _clamp01(_finite(float(q_hat), 0.5))
    delta = _clamp(q - qh, -1.0, 1.0)
    a = _finite(float(alpha), 0.0)
    out = [0.0] * N_DIMS
    for i in range(N_DIMS):
        g = _finite(gain[i], 0.5) if i < len(gain) else 0.5
        p = _clamp01(_finite(phi[i], 0.0)) if i < len(phi) else 0.0
        nxt = g + a * delta * p
        out[i] = min(1.0, max(_GAIN_FLOOR, _finite(nxt, g)))  # Π_{[ε,1]}
    return out


# ===========================================================================
# 值域适配器（Phase 0）—— [0,1] ↔ (-1,1) tanh 存储帧
# ===========================================================================
# 情感核 E 即 ``ScarredState.base``，由 tanh 写入（scar_algebra.py:391/397、pel_core），实际
# 值域 (-1,1)；而本模块 decay/saturating_update 均以 E∈[0,1] 立式（反吸收态、饱和因子都按 [0,1]
# 定义）。接入前必须过此适配器把 base 折进单位区间、算完再折回，否则语义系统性偏置（设计
# v26-upgrade-path §1，红队 e-core "domain mismatch" BLOCKER）。两个适配器在 [-1,1]/[0,1] 内
# 严格互逆（往返恒等，见 tests/test_affect_domain_adapter）。


def to_unit_interval(base: list[float]) -> list[float]:
    """tanh 存储帧 (-1,1) → 单位区间 [0,1]：E_unit = (base+1)/2。

    非有限值消毒为中性 0.5；末端夹 [0,1]（越界的复原快照/浮点毛刺不外溢）。逐元素映射，
    对任意长度列表安全（不硬编 N_DIMS，供 base 维数即 8 的情感核直接用）。
    """
    return [_clamp01(_finite((x + 1.0) * 0.5, 0.5)) for x in base]


def from_unit_interval(e: list[float]) -> list[float]:
    """单位区间 [0,1] → tanh 存储帧 (-1,1)：base = 2·E_unit − 1（``to_unit_interval`` 的逆）。

    非有限值消毒为中性 0.0；末端夹 [-1,1]。与 ``to_unit_interval`` 在各自值域内严格互逆。
    """
    return [_clamp(_finite(2.0 * x - 1.0, 0.0), -1.0, 1.0) for x in e]


# ===========================================================================
# 慢通道（T5）：poignancy 漏桶 → 反思触发 → 锚回弹 macro 漂移（纯函数）
# ===========================================================================
# 设计 §4.2/§8（含 v26-upgrade-path §2 T5）。全部纯函数、无状态；有状态编排（漏桶累积、
# 反思冷却、回滚环、原子提交）在 AlphaKernel。κ/μ/ρ 良定域复用 validate_scalar_params。
# 刻骨质量的维权重：强调 valence/tension/repair（受伤相关维），warmth/arousal 次之。
_POIGNANCY_DIM_W: tuple[float, ...] = (0.5, 0.5, 1.0, 1.0, 0.3, 1.0, 0.4, 0.6)


def poignancy_magnitude(a_k: list[float]) -> float:
    """一次 appraisal 的"刻骨"质量 ≥ 0：受伤相关维加权的 L2 范数（§4.2）。"""
    return math.sqrt(
        sum(
            (_POIGNANCY_DIM_W[i] * _finite(a_k[i] if i < len(a_k) else 0.0, 0.0)) ** 2
            for i in range(N_DIMS)
        )
    )


def poignancy_update(pi: float, inflow: float, mu: float, dt_ticks: float = 1.0) -> float:
    """poignancy 漏桶：π ← π·(1−μ)^dt + inflow，夹 ≥0（§4.2）。

    μ 为每 tick 泄漏率 ∈ (0,1)；inflow 为本回合注入的刻骨质量（≥0）。dt_ticks 为经过的 tick 数
    （长静默多漏）。非有限消毒；负 inflow 视作 0。
    """
    p = max(0.0, _finite(pi, 0.0))
    leak = float((1.0 - _clamp01(mu)) ** max(0.0, _finite(dt_ticks, 1.0)))
    return max(0.0, p * leak + max(0.0, _finite(inflow, 0.0)))


def reflection_ready(
    pi: float, theta: float, now: float, last_reflection_wall: float, cooldown_secs: float
) -> bool:
    """π 越阈 θ 且距上次反思墙钟冷却已过 ⇒ 可反思（§4.2；墙钟冷却，非 tick 冷却）。"""
    if not (_finite(pi, 0.0) >= theta):
        return False
    if last_reflection_wall <= 0.0:
        return True
    return (float(now) - float(last_reflection_wall)) >= float(cooldown_secs)


def scarload_decay(scarload: list[float], rate: float) -> list[float]:
    """scarload 自愈：逐维朝 0 收缩 s ← s·(1−rate)（§2.2 self-heal 钩子——half_lives 只读不减）。"""
    r = _clamp01(rate)
    return [max(0.0, _finite(s, 0.0)) * (1.0 - r) for s in scarload]


def q_dc(dialogue_quality_ema: float, s_ref: float = 0.5) -> float:
    """对话质量条件化的漂移门 ∈ [0,1]：质量越高越放行 macro 漂移（缺失回落 s_ref）。"""
    return _clamp01(_finite(dialogue_quality_ema, s_ref))


def drift_step(anchor: float, value: float, direction: float, eta: float, rho: float) -> float:
    """单步 macro 漂移增量：Δ = η·dir − ρ·(value − anchor)（锚回弹，§4.2/§8）。

    dir 为归一化漂移方向 ∈ [−1,1]（由刻骨事件方向给出，见 kernel）；η 步长；ρ 锚回弹收缩率——
    朝**不可变 anchor**（非自适应 set_point）回拉，防越漂/防自适应基线追信号（z-gate 失败模式）。
    """
    return eta * _finite(direction, 0.0) - rho * (_finite(value, 0.0) - _finite(anchor, 0.0))


def validate_slowchannel_params(
    theta: float, mu: float, eta: float, rho: float, cooldown_secs: float
) -> None:
    """慢通道参数良定域：θ>0、μ∈(0,1)、η∈(0,1)、ρ∈(0,1)、cooldown≥0（越界 fail-closed）。"""
    if not (theta > 0.0):
        raise ValueError(f"reflection θ={theta} 须 >0")
    # μ/ρ 复用 validate_scalar_params 的 (0,1) 断言；η 单独查（用 kappa 位凑合会误导）。
    if not (0.0 < mu < 1.0):
        raise ValueError(f"μ={mu} 须 ∈ (0,1)")
    if not (0.0 < eta < 1.0):
        raise ValueError(f"η={eta} 须 ∈ (0,1)")
    if not (0.0 < rho < 1.0):
        raise ValueError(f"ρ={rho} 须 ∈ (0,1)")
    if cooldown_secs < 0.0:
        raise ValueError(f"cooldown={cooldown_secs} 须 ≥0")


__all__ = [
    "N_DIMS",
    "equilibrium",
    "half_lives",
    "gain_vector",
    "decay",
    "saturating_update",
    "to_unit_interval",
    "from_unit_interval",
    "eligibility_update",
    "quality_baseline_update",
    "plasticity_step",
    "validate_gain",
    "validate_scalar_params",
    "poignancy_magnitude",
    "poignancy_update",
    "reflection_ready",
    "scarload_decay",
    "q_dc",
    "drift_step",
    "validate_slowchannel_params",
]
