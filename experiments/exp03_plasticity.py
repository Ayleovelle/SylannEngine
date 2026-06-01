"""Experiment 3: Hebbian Plasticity — Use-Dependent Strengthening.

Validates: "channels strengthen with use, atrophy without (LTP + LTD + homeostatic scaling)"
Protocol: Repeatedly activate specific module pairs, observe weight evolution.
          Then stop activation and observe atrophy. 10 repeats.
Output: Weight evolution curves for active vs inactive channels.
"""

from __future__ import annotations

import numpy as np

from utils import (
    N_REPEATS,
    SAMPLE_TEXTS,
    make_spine,
    print_stats,
    process_text,
    save_figure,
)


def run_single(seed: int) -> dict:
    spine = make_spine("pro")
    field = spine._field
    plasticity = field._coupling.plasticity

    n_channels = len(plasticity.weights)
    initial_weights = np.array(plasticity.weights)

    # Phase 1: 500 ticks of normal activity (builds up some channels)
    weight_history_active = []
    weight_history_inactive = []
    total_weight_history = []
    base_time = 1_000_000.0 + seed * 100_000

    for i in range(500):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + i * 60.0
        process_text(spine, text, now=now)

        weights = np.array(plasticity.weights)
        # Track top-5 most active and bottom-5 least active
        sorted_idx = np.argsort(weights)
        weight_history_active.append(np.mean(weights[sorted_idx[-5:]]))
        weight_history_inactive.append(np.mean(weights[sorted_idx[:5]]))
        total_weight_history.append(np.sum(weights))

    # Phase 2: 500 idle ticks (atrophy)
    for i in range(500):
        now = base_time + (500 + i) * 60.0
        spine.process("", now)

        weights = np.array(plasticity.weights)
        sorted_idx = np.argsort(weights)
        weight_history_active.append(np.mean(weights[sorted_idx[-5:]]))
        weight_history_inactive.append(np.mean(weights[sorted_idx[:5]]))
        total_weight_history.append(np.sum(weights))

    final_weights = np.array(plasticity.weights)

    return {
        "active": weight_history_active,
        "inactive": weight_history_inactive,
        "total": total_weight_history,
        "initial_std": float(np.std(initial_weights)),
        "final_std": float(np.std(final_weights)),
        "ltp_ratio": float(np.mean(final_weights > initial_weights)),
        "ltd_ratio": float(np.mean(final_weights < initial_weights)),
    }


def main():
    import matplotlib.pyplot as plt

    print(f"  Running plasticity experiment ({N_REPEATS} repeats x 1000 ticks)...")
    all_results = []
    for rep in range(N_REPEATS):
        result = run_single(seed=rep)
        all_results.append(result)

    # Stats
    ltp_ratios = [r["ltp_ratio"] for r in all_results]
    ltd_ratios = [r["ltd_ratio"] for r in all_results]
    print_stats("LTP ratio (channels strengthened)", ltp_ratios)
    print_stats("LTD ratio (channels weakened)", ltd_ratios)
    print_stats("Initial weight std", [r["initial_std"] for r in all_results])
    print_stats("Final weight std", [r["final_std"] for r in all_results])

    # Figure
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4))

    # Weight evolution (mean across repeats)
    active_mean = np.mean([r["active"] for r in all_results], axis=0)
    active_std = np.std([r["active"] for r in all_results], axis=0)
    inactive_mean = np.mean([r["inactive"] for r in all_results], axis=0)
    inactive_std = np.std([r["inactive"] for r in all_results], axis=0)
    x = np.arange(len(active_mean))

    ax1.plot(x, active_mean, color="#E91E63", label="Top-5 active")
    ax1.fill_between(x, active_mean - active_std, active_mean + active_std,
                     color="#E91E63", alpha=0.2)
    ax1.plot(x, inactive_mean, color="#2196F3", label="Bottom-5 inactive")
    ax1.fill_between(x, inactive_mean - inactive_std, inactive_mean + inactive_std,
                     color="#2196F3", alpha=0.2)
    ax1.axvline(500, color="gray", linestyle="--", label="Idle phase starts")
    ax1.set_xlabel("Tick")
    ax1.set_ylabel("Mean Weight")
    ax1.set_title("Channel Weight Evolution (LTP vs LTD)")
    ax1.legend(fontsize=8)

    # Homeostatic budget conservation
    total_mean = np.mean([r["total"] for r in all_results], axis=0)
    total_std = np.std([r["total"] for r in all_results], axis=0)
    ax2.plot(x, total_mean, color="#4CAF50")
    ax2.fill_between(x, total_mean - total_std, total_mean + total_std,
                     color="#4CAF50", alpha=0.2)
    ax2.axvline(500, color="gray", linestyle="--")
    ax2.set_xlabel("Tick")
    ax2.set_ylabel("Total Weight (sum)")
    ax2.set_title("Homeostatic Budget Conservation")

    # LTP/LTD ratio bar chart
    ax3.bar(["LTP\n(strengthened)", "LTD\n(weakened)"],
            [np.mean(ltp_ratios), np.mean(ltd_ratios)],
            yerr=[np.std(ltp_ratios), np.std(ltd_ratios)],
            color=["#E91E63", "#2196F3"], alpha=0.7, capsize=5)
    ax3.set_ylabel("Fraction of channels")
    ax3.set_title("LTP vs LTD After 1000 Ticks")
    ax3.set_ylim(0, 1)

    plt.tight_layout()
    save_figure(fig, "fig04_plasticity")
    plt.close(fig)


if __name__ == "__main__":
    main()
