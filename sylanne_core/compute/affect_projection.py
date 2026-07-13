"""Appraisal 投影层 —— assessor 三标量 + 意图 → 8 维情感核增量 a_k（v2.6.0 T1）。

设计对照：docs/design/v26-affect-dynamics-design.md §3.1 / §3.2（含 §0.5 canonical 落地对账）。

位置：这是 v2.6.0 双速情感动力学的**快通道输入端**。情感核 E 即 ``ScarredState.base``
（8 维，维序见 ``void_scar_engine.VoidScarEngine._DIM_NAMES`` :256-265），本模块把 assessor
的稀疏出参 ``{v∈[-1,1], a∈[0,1], w∈[0,1], intent:str}`` 确定性投影成对齐该维序的 8 维
appraisal 增量 a_k，供饱和快更新 ``E ← E + G⊙[a]₊⊙(1−E) − G⊙[a]₋⊙E`` 消费（接入
``apply_assessment`` / ``_apply_assessment_to_engine`` 两个写入点是后续 T1 切片）。

canonical 现状：``apply_assessment``（computation_spine.py:526）用 ``intent=="撒娇"/"生气"``
精确匹配 + w>0.7 阈值直调 base——本模块把那套手写阶跃规则连续化、可标定化。canonical 无
任何 8 维投影逻辑，故本模块是**纯新件**：无状态、无 IO、无 LLM，不改动任何现有引擎状态。

数值纪律：assessor 若返回非有限值（NaN/inf），在入口消毒为中性有限值，杜绝 NaN 顺投影
污染 E 并落盘（fail-closed，见设计附录 T1 code-review F1）。
"""

from __future__ import annotations

import math

# a_k 维度数与索引（维序 = VoidScarEngine._DIM_NAMES，见 void_scar_engine.py:256-265）。
# 不 import 私有类属性以避免耦合；改用 test_affect_projection 里的一致性断言钉死对齐。
N_DIMS: int = 8
_I_WARMTH, _I_AROUSAL, _I_VALENCE, _I_TENSION = 0, 1, 2, 3
_I_CURIOSITY, _I_REPAIR, _I_EXPR, _I_BOUNDARY = 4, 5, 6, 7

# 意图规范类的偏置向量（维度索引 → 增量）。系数为影子期可标定先验。
_COAX: dict[int, float] = {_I_WARMTH: 0.30, _I_TENSION: -0.20, _I_EXPR: 0.10}
_ANGER: dict[int, float] = {_I_TENSION: 0.40, _I_WARMTH: -0.20, _I_BOUNDARY: 0.20}
_APOLOGIZE: dict[int, float] = {_I_REPAIR: -0.40, _I_WARMTH: 0.20, _I_TENSION: -0.20}
_ASK: dict[int, float] = {_I_CURIOSITY: 0.30, _I_EXPR: 0.10}
_SHARE: dict[int, float] = {_I_CURIOSITY: 0.20, _I_WARMTH: 0.15, _I_EXPR: 0.20}
_COLD: dict[int, float] = {_I_WARMTH: -0.15, _I_EXPR: -0.20}
_PRESS: dict[int, float] = {_I_BOUNDARY: 0.40, _I_TENSION: 0.20}

# 规范类：(类名, 触发关键词, 偏置)。顺序即优先级——首个命中即返回，专类（道歉/越界）
# 排在泛类（分享/提问）前，避免泛类抢走专类（如"生气道歉"应归 apologize）。
INTENT_CLASSES: tuple[tuple[str, tuple[str, ...], dict[int, float]], ...] = (
    ("apologize", ("道歉", "认错", "对不起", "抱歉", "求和", "服软", "和好", "哄"), _APOLOGIZE),
    ("anger", ("生气", "指责", "质问", "埋怨", "愤怒", "恼", "不满", "吵", "骂", "怪你"), _ANGER),
    ("press", ("越界", "施压", "逼", "强迫", "命令", "胁迫", "得寸进尺", "冒犯"), _PRESS),
    ("coax", ("撒娇", "亲昵", "亲亲", "抱抱", "想你", "求抱", "卖萌", "蹭", "黏"), _COAX),
    ("share", ("分享", "报喜", "炫耀", "好消息", "显摆", "开心", "高兴", "兴奋"), _SHARE),
    ("ask", ("提问", "求助", "请教", "求教", "咨询", "疑问", "帮忙", "怎么", "问"), _ASK),
    ("cold", ("冷淡", "敷衍", "疏离", "冷漠", "无所谓", "淡漠", "应付"), _COLD),
)


def _finite(x: float, fallback: float) -> float:
    """非有限值（NaN/inf）消毒为中性有限值（fail-closed，防 NaN 污染 E）。"""
    return x if math.isfinite(x) else fallback


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def classify_intent(intent: str | None) -> str | None:
    """把自由意图串归一到规范类名；无法识别返回 None（调用方须落日志 + 计数）。"""
    if not intent:
        return None
    s = str(intent)
    for name, keywords, _bias in INTENT_CLASSES:
        for kw in keywords:
            if kw in s:
                return name
    return None


def intent_bias(class_name: str | None) -> list[float]:
    """规范类名 → 8 维偏置向量；None/未知类 → 全零。"""
    vec = [0.0] * N_DIMS
    if class_name is None:
        return vec
    for name, _keywords, bias in INTENT_CLASSES:
        if name == class_name:
            for idx, delta in bias.items():
                vec[idx] = delta
            break
    return vec


def project_appraisal(
    valence: float,
    arousal: float,
    wound_risk: float,
    intent: str | None,
) -> tuple[list[float], str | None]:
    """assessor 三标量 + 意图 → 8 维 appraisal 增量 a_k ∈ [−1,1]^8。

    Args:
        valence: 效价 v ∈ [−1,1]。
        arousal: 唤醒 a ∈ [0,1]。
        wound_risk: 受伤风险 w ∈ [0,1]（= assessor 的 w，非 warmth）。
        intent: 自由意图串。

    Returns:
        (a_k, matched_class)：a_k 为末端 clip 到 [−1,1] 的 8 维列表（维序 = _DIM_NAMES）；
        matched_class 为命中的规范类名或 None（None ⇒ 调用方须落 unmatched 日志 + 计数）。

    非有限输入在入口消毒为中性有限值（v→0、a→0.3 中性、w→0），杜绝 NaN 传染。
    线性部分秩仅 3（curiosity/boundary 几乎全靠意图偏置）——影子期须监控这两维方差，
    接近零 = 死链前兆（见设计 §3.1）。
    """
    v = _clip(_finite(float(valence), 0.0), -1.0, 1.0)
    a = _clip(_finite(float(arousal), 0.3), 0.0, 1.0)
    w = _clip(_finite(float(wound_risk), 0.0), 0.0, 1.0)
    vp = v if v > 0.0 else 0.0  # v⁺ = max(v,0)
    vm = -v if v < 0.0 else 0.0  # v⁻ = max(−v,0)

    matched = classify_intent(intent)
    d = intent_bias(matched)

    a_k = [0.0] * N_DIMS
    a_k[_I_WARMTH] = 0.5 * vp * (1.0 - w) - 0.4 * w * vm + d[_I_WARMTH]
    a_k[_I_AROUSAL] = (a - 0.3) + d[_I_AROUSAL]
    a_k[_I_VALENCE] = v + d[_I_VALENCE]
    a_k[_I_TENSION] = 0.7 * w + 0.3 * vm * a - 0.2 * vp * (1.0 - w) + d[_I_TENSION]
    a_k[_I_CURIOSITY] = 0.2 * a * vp + d[_I_CURIOSITY]
    a_k[_I_REPAIR] = 0.6 * w * vm + d[_I_REPAIR]
    a_k[_I_EXPR] = 0.5 * a * (0.5 + 0.5 * v) + d[_I_EXPR]
    a_k[_I_BOUNDARY] = 0.3 * w * (1.0 - vp) + d[_I_BOUNDARY]

    # 末端统一 clip（§3.1：线性 + 意图偏置叠加可越界，如 a_tension 极值 1.4）。
    # clip 作用于 appraisal 增量、不作用于状态 E，故不影响饱和更新的有界性。
    return [_clip(x) for x in a_k], matched


__all__ = [
    "N_DIMS",
    "INTENT_CLASSES",
    "classify_intent",
    "intent_bias",
    "project_appraisal",
]
