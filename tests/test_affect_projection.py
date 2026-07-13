"""v2.6.0 T1 appraisal 投影层行为契约（纯新件，不碰现有引擎状态）。

对照 docs/design/v26-affect-dynamics-design.md §3.1 / §3.2。守护：
- 8 维投影公式 + 末端 clip 越界兜底；
- 意图归一化的规范类命中与优先级（专类先于泛类）；
- 维序与 VoidScarEngine._DIM_NAMES 对齐（防投影与引擎错位）；
- 非有限输入（NaN/inf）入口消毒，杜绝污染 E（T1 code-review F1）。
"""

from __future__ import annotations

import math

from sylanne_core.compute.affect_projection import (
    N_DIMS,
    classify_intent,
    intent_bias,
    project_appraisal,
)
from sylanne_core.compute.void_scar_engine import VoidScarEngine

_I_WARMTH, _I_AROUSAL, _I_VALENCE, _I_TENSION = 0, 1, 2, 3
_I_CURIOSITY, _I_REPAIR, _I_EXPR, _I_BOUNDARY = 4, 5, 6, 7


class TestProjectionFormula:
    def test_identity_and_neutral(self) -> None:
        a_k, matched = project_appraisal(0.5, 0.8, 0.0, None)
        assert matched is None
        assert abs(a_k[_I_VALENCE] - 0.5) < 1e-9  # a_valence = v
        assert abs(a_k[_I_AROUSAL] - 0.5) < 1e-9  # a_arousal = a − 0.3
        assert abs(a_k[_I_WARMTH] - 0.25) < 1e-9  # 0.5·v⁺·(1−w)
        assert abs(a_k[_I_EXPR] - 0.3) < 1e-9  # 0.5·a·(0.5+0.5v)
        assert all(-1.0 <= x <= 1.0 for x in a_k)

    def test_terminal_clip_on_tension_overshoot(self) -> None:
        # w=1,v=−1,a=1,意图=生气 → a_tension = 0.7+0.3+0.4 = 1.4，须末端 clip 到 1.0
        a_k, matched = project_appraisal(-1.0, 1.0, 1.0, "我生气了")
        assert matched == "anger"
        assert abs(a_k[_I_TENSION] - 1.0) < 1e-9
        assert abs(a_k[_I_VALENCE] - (-1.0)) < 1e-9
        assert all(-1.0 <= x <= 1.0 for x in a_k)

    def test_length_is_eight(self) -> None:
        a_k, _ = project_appraisal(0.0, 0.0, 0.0, None)
        assert len(a_k) == N_DIMS == 8


class TestIntentNormalizer:
    def test_all_classes_match(self) -> None:
        assert classify_intent("撒娇一下") == "coax"
        assert classify_intent("你怎么这样，指责") == "anger"
        assert classify_intent("对不起嘛") == "apologize"
        assert classify_intent("分享个好消息") == "share"
        assert classify_intent("这个怎么办") == "ask"
        assert classify_intent("你越界了") == "press"
        assert classify_intent("随便敷衍两句") == "cold"

    def test_unmatched_and_empty(self) -> None:
        assert classify_intent("qwerty乱码意图") is None
        assert classify_intent(None) is None
        assert classify_intent("") is None

    def test_priority_specific_beats_generic(self) -> None:
        # "生气道歉" 同含"道歉"(专)与"生气"(泛)，专类 apologize 须优先（顺序契约）
        assert classify_intent("生气到最后还是道歉了") == "apologize"

    def test_bias_applied_to_projection(self) -> None:
        base, _ = project_appraisal(0.0, 0.3, 0.0, None)
        coax, matched = project_appraisal(0.0, 0.3, 0.0, "抱抱")
        assert matched == "coax"
        assert abs(coax[_I_WARMTH] - (base[_I_WARMTH] + 0.3)) < 1e-9
        assert abs(coax[_I_TENSION] - (base[_I_TENSION] - 0.2)) < 1e-9
        assert abs(coax[_I_EXPR] - (base[_I_EXPR] + 0.1)) < 1e-9

    def test_intent_bias_unknown_class_is_zero(self) -> None:
        assert intent_bias("not_a_real_class") == [0.0] * N_DIMS
        assert intent_bias(None) == [0.0] * N_DIMS


class TestNaNSanitization:
    """F1：assessor 若返回 NaN/inf，投影入口须消毒，输出恒有限 + 有界。"""

    def test_nan_inputs_produce_finite_bounded(self) -> None:
        nan = float("nan")
        a_k, _ = project_appraisal(nan, nan, nan, "撒娇")
        assert all(math.isfinite(x) for x in a_k)
        assert all(-1.0 <= x <= 1.0 for x in a_k)

    def test_inf_inputs_clipped(self) -> None:
        inf = float("inf")
        a_k, _ = project_appraisal(inf, inf, inf, None)
        assert all(math.isfinite(x) for x in a_k)
        assert all(-1.0 <= x <= 1.0 for x in a_k)

    def test_partial_nan_only_that_axis_neutralized(self) -> None:
        # valence=NaN 消成 0，其余正常：warmth 应与 v=0 的结果一致
        a_k, _ = project_appraisal(float("nan"), 0.8, 0.0, None)
        base, _ = project_appraisal(0.0, 0.8, 0.0, None)
        assert all(math.isfinite(x) for x in a_k)
        assert abs(a_k[_I_WARMTH] - base[_I_WARMTH]) < 1e-9


class TestDimOrderAlignment:
    """投影维序必须与引擎的 8 维情感核 _DIM_NAMES 逐位对齐（防错位）。"""

    def test_matches_void_scar_dim_names(self) -> None:
        expected = (
            "warmth",
            "arousal",
            "valence",
            "tension",
            "curiosity",
            "repair_pressure",
            "expression_drive",
            "boundary_firmness",
        )
        assert expected == VoidScarEngine._DIM_NAMES
        assert len(VoidScarEngine._DIM_NAMES) == N_DIMS
