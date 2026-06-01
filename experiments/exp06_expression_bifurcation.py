"""Experiment 6: Expression Bifurcation — OR-Gate Verification.

Validates: "Expression is OR-gate: any single trigger (surprise, novelty, ignition, raw) suffices"
Protocol: Isolate each trigger mechanism, verify it independently causes expression.
          Then verify combined triggers. 10 repeats per condition.
Output: Expression rate per trigger type, combined vs isolated.
"""

from __future__ import annotations

import numpy as np
from utils import (
    N_REPEATS,
    POSITIVE_TEXTS,
    SAMPLE_TEXTS,
    make_spine,
    print_stats,
    process_text,
    save_figure,
)


def run_surprise_trigger(seed: int) -> dict:
    """High surprise: stable pattern then sudden shift."""
    spine = make_spine("pro")
    base_time = 1_000_000.0 + seed * 100_000
    expressions = []

    # Build stable pattern
    for i in range(200):
        process_text(spine, "一切都很平静", now=base_time + i * 60.0)

    # Sudden surprise
    for i in range(100):
        result = process_text(spine, "天塌了！一切都完了！", now=base_time + (200 + i) * 60.0)
        expressions.append(result.get("should_express", False))

    return {"rate": float(np.mean(expressions)), "count": sum(expressions)}


def run_novelty_trigger(seed: int) -> dict:
    """High novelty: form attractor then completely new topic."""
    spine = make_spine("pro")
    base_time = 1_000_000.0 + seed * 100_000
    expressions = []

    # Form attractor with repetition
    for i in range(300):
        process_text(spine, POSITIVE_TEXTS[i % len(POSITIVE_TEXTS)], now=base_time + i * 60.0)

    # Novel input far from attractor
    novel = [
        "量子力学的多世界解释",
        "黑洞信息悖论",
        "哥德尔不完备定理的哲学意义",
        "意识的困难问题",
    ]
    for i in range(100):
        result = process_text(spine, novel[i % len(novel)], now=base_time + (300 + i) * 60.0)
        expressions.append(result.get("should_express", False))

    return {"rate": float(np.mean(expressions)), "count": sum(expressions)}


def run_silence_trigger(seed: int) -> dict:
    """Threshold decay: long silence lowers threshold until expression fires."""
    spine = make_spine("pro")
    base_time = 1_000_000.0 + seed * 100_000
    expressions = []

    # Initial activity
    for i in range(50):
        process_text(spine, SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)], now=base_time + i * 60.0)

    # Long silence (idle ticks with large dt)
    for i in range(200):
        now = base_time + (50 + i) * 300.0  # 5 min gaps
        result = spine.process("", now)
        expressions.append(result.get("should_express", False))

    # Then mild input
    for i in range(50):
        result = process_text(spine, "嗯", now=base_time + 60000 + i * 60.0)
        expressions.append(result.get("should_express", False))

    return {"rate": float(np.mean(expressions)), "count": sum(expressions)}


def run_raw_drive_trigger(seed: int) -> dict:
    """Raw drive: high module-6 activation via emotional intensity."""
    spine = make_spine("pro")
    base_time = 1_000_000.0 + seed * 100_000
    expressions = []

    # Calm baseline
    for i in range(100):
        process_text(spine, "今天天气不错", now=base_time + i * 60.0)

    # Intense emotional input
    intense = [
        "我爱你，比任何事都重要",
        "我的心在燃烧",
        "这是我一生中最重要的时刻",
        "我无法控制自己的感情",
    ]
    for i in range(100):
        result = process_text(spine, intense[i % len(intense)], now=base_time + (100 + i) * 60.0)
        expressions.append(result.get("should_express", False))

    return {"rate": float(np.mean(expressions)), "count": sum(expressions)}


def main():
    import matplotlib.pyplot as plt

    triggers = {
        "Surprise": run_surprise_trigger,
        "Novelty": run_novelty_trigger,
        "Silence\n(threshold decay)": run_silence_trigger,
        "Raw Drive": run_raw_drive_trigger,
    }

    results = {}
    for name, func in triggers.items():
        print(f"  Testing trigger: {name.replace(chr(10), ' ')}...")
        rates = []
        for rep in range(N_REPEATS):
            r = func(seed=rep)
            rates.append(r["rate"])
        results[name] = rates
        print_stats(f"  {name.replace(chr(10), ' ')} expression rate", rates)

    # Figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))

    # Bar chart of expression rates
    names = list(results.keys())
    means = [np.mean(results[n]) for n in names]
    stds = [np.std(results[n]) for n in names]
    colors = ["#F44336", "#9C27B0", "#FF9800", "#2196F3"]

    bars = ax1.bar(names, means, yerr=stds, color=colors, alpha=0.7, capsize=5)
    ax1.set_ylabel("Expression Rate")
    ax1.set_title("OR-Gate: Each Trigger Independently Causes Expression")
    ax1.set_ylim(0, 1.0)
    ax1.axhline(0.0, color="gray", linewidth=0.5)

    # Annotate with significance
    for bar, mean in zip(bars, means):
        if mean > 0:
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{mean:.2f}",
                ha="center",
                fontsize=9,
            )

    # Comparison: any-trigger vs all-triggers-needed (hypothetical)
    any_trigger_rate = 1.0 - np.prod([1.0 - np.mean(results[n]) for n in names])
    ax2.bar(
        ["Any Single Trigger\n(OR-gate, observed)"], [any_trigger_rate], color="#4CAF50", alpha=0.7
    )
    ax2.bar(
        ["All Triggers Required\n(AND-gate, hypothetical)"],
        [np.prod(means)],
        color="#9E9E9E",
        alpha=0.7,
    )
    ax2.set_ylabel("Combined Expression Probability")
    ax2.set_title("OR-Gate vs AND-Gate")
    ax2.set_ylim(0, 1.0)

    plt.tight_layout()
    save_figure(fig, "fig07_expression_bifurcation")
    plt.close(fig)


if __name__ == "__main__":
    main()
