"""Experiment 1: Convergence Analysis.

Validates: "lite converges in ≤10, pro ≤15, max ≤20 iterations"
Protocol: 1000 process calls per tier, 10 repeats. Record iteration count per call.
Output: iteration count distribution (histogram) per tier.
"""

from __future__ import annotations

import numpy as np
from utils import (
    N_REPEATS,
    N_TICKS,
    SAMPLE_TEXTS,
    make_spine,
    print_stats,
    process_text,
    save_figure,
)


def run_single(tier: str, n_ticks: int, seed: int) -> list[int]:
    spine = make_spine(tier)
    iterations = []
    base_time = 1_000_000.0 + seed * 100_000
    for i in range(n_ticks):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + i * 60.0
        process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        iters = meta.get("iterations", 0)
        iterations.append(iters)
    return iterations


def main():
    import matplotlib.pyplot as plt

    tiers = ["lite", "pro", "max"]
    tier_limits = {"lite": 10, "pro": 15, "max": 20}
    all_data = {}

    for tier in tiers:
        print(f"  Running {tier} tier ({N_REPEATS} repeats x {N_TICKS} ticks)...")
        tier_iters = []
        for rep in range(N_REPEATS):
            iters = run_single(tier, N_TICKS, seed=rep)
            tier_iters.extend(iters)
        all_data[tier] = tier_iters
        arr = np.array(tier_iters)
        limit = tier_limits[tier]
        convergence_rate = np.mean(arr < limit) * 100
        print_stats(f"{tier} iterations", tier_iters)
        print(f"    Convergence rate (< {limit}): {convergence_rate:.1f}%")
        print(f"    Max observed: {arr.max()}")

    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    colors = ["#2196F3", "#FF9800", "#E91E63"]

    for ax, tier, color in zip(axes, tiers, colors):
        data = np.array(all_data[tier])
        limit = tier_limits[tier]
        bins = np.arange(0, limit + 2) - 0.5
        ax.hist(data, bins=bins, color=color, alpha=0.8, edgecolor="white")
        ax.axvline(limit, color="red", linestyle="--", linewidth=1.5, label=f"max={limit}")
        ax.set_xlabel("Iterations to convergence")
        ax.set_title(f"{tier.upper()} tier")
        ax.legend()
        ax.set_xlim(-0.5, limit + 1.5)

    axes[0].set_ylabel("Frequency")
    fig.suptitle("Resonance Field Convergence (1000 ticks × 10 repeats)", fontsize=12)
    plt.tight_layout()
    save_figure(fig, "fig02_convergence")
    plt.close(fig)


if __name__ == "__main__":
    main()
