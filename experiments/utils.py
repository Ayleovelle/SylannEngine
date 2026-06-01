"""Shared utilities for SylannEngine v2 experiments.

Provides engine instantiation, data collection helpers, and plotting defaults.
All experiments import from here for consistency.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sylanne_core import SylanneEngine
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.config import SylanneConfig, build_profile

FIGURES_DIR = Path(__file__).parent / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

N_REPEATS = 10
N_TICKS = 1000


async def _dummy_llm(system: str, user: str) -> str:
    return ""


def make_engine(
    tier: str = "lite",
    data_dir: Path | None = None,
    diagnostics: bool = True,
) -> SylanneEngine:
    if data_dir is None:
        data_dir = Path(__file__).parent / ".tmp_data"
    config = SylanneConfig(mode=tier, assessor_enabled=False, diagnostics=diagnostics)
    return SylanneEngine(data_dir=data_dir, llm=_dummy_llm, config=config)


def make_spine(tier: str = "lite") -> ResonanceSpine:
    profile = build_profile(tier)
    return ResonanceSpine(profile)


def get_field(spine: ResonanceSpine):
    """Access the internal ResonanceField from a spine."""
    return spine._field


def get_coupling(spine: ResonanceSpine):
    """Access CouplingDynamics from a spine."""
    return spine._field._coupling


def get_emergence(spine: ResonanceSpine):
    """Access EmergenceTracker from a spine."""
    return spine._emergence


def process_text(spine: ResonanceSpine, text: str, now: float | None = None) -> dict:
    """Process text through the spine and return the result dict."""
    return spine.process(text, now or time.time())


def process_tick(spine: ResonanceSpine, now: float | None = None) -> dict:
    """Process an idle tick."""
    return spine.process("", now or time.time())


def collect_timeseries(
    spine: ResonanceSpine,
    texts: list[str],
    base_time: float = 1_000_000.0,
    dt: float = 60.0,
) -> list[dict]:
    """Run a sequence of texts and collect results."""
    results = []
    for i, text in enumerate(texts):
        now = base_time + i * dt
        result = process_text(spine, text, now=now)
        results.append(result)
    return results


def run_experiment(func, n_repeats: int = N_REPEATS) -> list[Any]:
    """Run an experiment function n_repeats times, return list of results."""
    results = []
    for i in range(n_repeats):
        result = func(seed=i)
        results.append(result)
    return results


def save_figure(fig, name: str, dpi: int = 300):
    """Save figure as both PDF and PNG."""
    fig.savefig(FIGURES_DIR / f"{name}.pdf", dpi=dpi, bbox_inches="tight")
    fig.savefig(FIGURES_DIR / f"{name}.png", dpi=dpi, bbox_inches="tight")
    print(f"  Saved: figures/{name}.pdf + .png")


def print_stats(name: str, values: list[float]):
    """Print mean ± std for a named metric."""
    arr = np.array(values)
    print(f"  {name}: {arr.mean():.4f} +/- {arr.std():.4f} (n={len(values)})")


def wilcoxon_test(a: list[float], b: list[float]) -> float:
    """Wilcoxon signed-rank test, returns p-value."""
    from scipy.stats import wilcoxon

    stat, p = wilcoxon(a, b)
    return p


def ttest(a: list[float], b: list[float]) -> float:
    """Independent t-test, returns p-value."""
    from scipy.stats import ttest_ind

    stat, p = ttest_ind(a, b)
    return p


SAMPLE_TEXTS = [
    "你好，今天过得怎么样？",
    "我觉得有点累了",
    "谢谢你一直陪着我",
    "我不太想说话",
    "你觉得我们之间的关系怎么样？",
    "我今天遇到了一件开心的事",
    "有时候我觉得很孤独",
    "你能理解我的感受吗？",
    "我想休息一下",
    "明天见",
]

STRESS_TEXTS = [
    "你根本不懂我",
    "别烦我了",
    "我讨厌这样",
    "你让我很失望",
    "我不需要你",
]

POSITIVE_TEXTS = [
    "你真好",
    "我很喜欢和你聊天",
    "谢谢你的陪伴",
    "你让我感到温暖",
    "我很开心认识你",
]
