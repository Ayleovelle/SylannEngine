"""exp02 — warmth 行为标定 harness（v26 A.4）。

在真实 E 律代码（takeover 路径）上跑规范情景，产出"隔夜该多冷"决策所需的具体数字：
- 情景 A：吵架（生气×3）→ 静默 Δt → 醒来时各维离均衡还剩多少；
- 情景 B：吵架 → 2h 静默 → 道歉——同会话修复的即时幅度；
- 情景 C：撒娇的即时响应幅度；
- 半衰期敏感性：h×0.5 / h×1 / h×2 三档下情景 A 的隔夜残留对比。

确定性（无 LLM、无随机）；输出 markdown，供 docs/design/affect-calibration-memo.md 引用。
用法：python experiments/exp02_warmth_calibration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sylanne_core.compute import affect_dynamics  # noqa: E402
from sylanne_core.compute.scar_algebra import ScarredState  # noqa: E402

_DIMS = ("warmth", "arousal", "valence", "tension", "curiosity", "repair", "expr", "boundary")
# 苏思澜画像先验（与测试一致的傲娇位）：高敏、克制、外冷内热。
_TRAITS: dict[str, float] = {
    "warmth_bias": 0.6,
    "perception_acuity": 0.7,
    "curiosity": 0.7,
    "expression_drive_trait": 0.6,
    "relational_gravity": 0.7,
    "sovereignty_guard": 0.8,
    "inner_order": 0.6,
    "neuroticism": 0.6,
    "extraversion": 0.4,
}
_ANGER = dict(valence=-0.8, arousal=0.9, wound=0.75, intent="生气")
_APOLOGY = dict(valence=0.5, arousal=0.5, wound=0.0, intent="道歉")
_COAX = dict(valence=0.8, arousal=0.6, wound=0.0, intent="撒娇")


def _fresh(ts: float = 1000.0) -> ScarredState:
    st = ScarredState(n_dims=8, affect_enabled=True)
    st.set_affect_params(_TRAITS, takeover=True)
    st.base = affect_dynamics.from_unit_interval(
        affect_dynamics.equilibrium(_TRAITS, 0.5)
    )  # 从均衡出发
    st._e_last_wall_ts = ts
    return st


def _hit(st: ScarredState, ev: dict, ts: float) -> None:
    # 注意：step() 除顶部衰减外还会跑遗留 MLP 主步演化（D1 像差的来源，非"纯衰减"）。
    st.step([0.0] * 8, timestamp=ts)
    # 镜像生产 assessor 路径的创伤注入（computation_spine/resonance_integration 的
    # wound_risk>0.7 分支）——否则吵架情景零伤痕、scar 粘滞从不参战（红队修订）。
    if ev["wound"] > 0.7:
        wound_vec = [0.0] * 8
        wound_vec[3] = ev["wound"] * 0.8
        wound_vec[5] = ev["wound"] * 0.5
        st.step(wound_vec, 0.0, heal=False)
    ok = st.apply_affect_takeover(ev["valence"], ev["arousal"], ev["wound"], ev["intent"])
    assert ok, "takeover must engage in this harness"


def _unit(st: ScarredState) -> list[float]:
    return affect_dynamics.to_unit_interval(st.base)


def _fight(st: ScarredState, t0: float) -> float:
    for i in range(3):
        _hit(st, _ANGER, t0 + i * 60.0)
    return t0 + 120.0


def _fmt(vals: list[float]) -> str:
    return " | ".join(f"{v:.3f}" for v in vals)


def _residual(st: ScarredState) -> list[float]:
    """各维距均衡的残留（单位帧，有符号：正=高于均衡）。"""
    eq = affect_dynamics.equilibrium(_TRAITS, 0.5)
    u = _unit(st)
    return [u[i] - eq[i] for i in range(8)]


def scenario_overnight(gap_hours: float, h_scale: float = 1.0) -> list[float]:
    """吵架 ×3 → 静默 gap → 醒来残留。h_scale 缩放半衰期先验（敏感性分析）。"""
    orig = affect_dynamics._H_BASE_MIN
    affect_dynamics._H_BASE_MIN = tuple(h * h_scale for h in orig)
    try:
        st = _fresh()
        t_end = _fight(st, 1000.0)
        # 醒来一步 = E 律衰减（顶部）+ 遗留 MLP 主步演化——正是 D1 像差的观测点。
        st.step([0.0] * 8, timestamp=t_end + gap_hours * 3600.0)
        return _residual(st)
    finally:
        affect_dynamics._H_BASE_MIN = orig


def scenario_apology() -> tuple[list[float], list[float]]:
    """吵架 → 2h 静默 → 道歉。返回（道歉前残留, 道歉后残留）。"""
    st = _fresh()
    t_end = _fight(st, 1000.0)
    st.step([0.0] * 8, timestamp=t_end + 7200.0)
    before = _residual(st)
    _hit(st, _APOLOGY, t_end + 7200.0 + 1.0)
    return before, _residual(st)


def scenario_coax() -> list[float]:
    """均衡态一句撒娇的即时位移。"""
    st = _fresh()
    _hit(st, _COAX, 1060.0)
    return _residual(st)


def main() -> None:
    eq = affect_dynamics.equilibrium(_TRAITS, 0.5)
    print("## warmth 标定 harness 输出（确定性，真实 takeover 代码路径）\n")
    print(f"画像均衡 Φ_eq：`{_fmt(eq)}`（维序 {'/'.join(_DIMS)}）\n")

    print("### 情景 A：吵架×3 后静默——醒来时距均衡的残留（+高于/−低于均衡）\n")
    print("| 静默时长 | " + " | ".join(_DIMS) + " |")
    print("|---|" + "---|" * 8)
    for hrs in (0.5, 2.0, 8.0, 24.0):
        r = scenario_overnight(hrs)
        print(f"| {hrs:>4.1f}h | " + _fmt(r).replace(" | ", " | ") + " |")

    print("\n### 半衰期敏感性（8h 隔夜，h×0.5 / ×1 / ×2）\n")
    print("| h 缩放 | " + " | ".join(_DIMS) + " |")
    print("|---|" + "---|" * 8)
    for sc in (0.5, 1.0, 2.0):
        r = scenario_overnight(8.0, h_scale=sc)
        print(f"| ×{sc:<3} | " + _fmt(r) + " |")

    print("\n### 情景 B：吵架 → 2h → 一句道歉（同会话修复幅度）\n")
    before, after = scenario_apology()
    print("| 时点 | " + " | ".join(_DIMS) + " |")
    print("|---|" + "---|" * 8)
    print("| 道歉前 | " + _fmt(before) + " |")
    print("| 道歉后 | " + _fmt(after) + " |")
    delta = [after[i] - before[i] for i in range(8)]
    print("| 修复量 | " + _fmt(delta) + " |")

    print("\n### 情景 C：均衡态一句撒娇的即时位移\n")
    print("| " + " | ".join(_DIMS) + " |")
    print("|" + "---|" * 8)
    print("| " + _fmt(scenario_coax()) + " |")


if __name__ == "__main__":
    main()
