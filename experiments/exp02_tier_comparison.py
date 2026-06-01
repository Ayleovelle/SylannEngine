"""Experiment 2: Tier Comparison — Performance and Dynamics.

Validates: "lite ~5ms, pro ~40ms, max ~50ms" + qualitative dynamics differences.
Protocol: 1000 ticks per tier, 10 repeats. Measure wall-clock latency, energy, channel activity.
Output: latency boxplot, energy trajectory, active channel ratio.
"""

from __future__ import annotations

import time

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


def run_single(tier: str, n_ticks: int, seed: int) -> dict:
    spine = make_spine(tier)
    latencies = []
    energies = []
    sync_orders = []
    base_time = 1_000_000.0 + seed * 100_000

    for i in range(n_ticks):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + i * 60.0
        t0 = time.perf_counter_ns()
        process_text(spine, text, now=now)
        t1 = time.perf_counter_ns()
        latencies.append((t1 - t0) / 1e6)

        meta = spine._last_resonance_meta
        energies.append(meta.get("energy", 0.0))
        sync_orders.append(meta.get("sync_order", 0.0))

    return {
        "latencies": latencies,
        "energies": energies,
        "sync_orders": sync_orders,
    }


def main():
    import matplotlib.pyplot as plt

    tiers = ["lite", "pro", "max"]
    results = {t: [] for t in tiers}

    for tier in tiers:
        print(f"  Running {tier} tier ({N_REPEATS} repeats x {N_TICKS} ticks)...")
        for rep in range(N_REPEATS):
            data = run_single(tier, N_TICKS, seed=rep)
            results[tier].append(data)

    # Aggregate latencies
    for tier in tiers:
        all_lat = []
        for r in results[tier]:
            all_lat.extend(r["latencies"])
        arr = np.array(all_lat)
        print(f"  {tier}: p50={np.percentile(arr, 50):.2f}ms, "
              f"p95={np.percentile(arr, 95):.2f}ms, "
              f"p99={np.percentile(arr, 99):.2f}ms")

    # Figure: 3 subplots
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4))
    colors = ["#2196F3", "#FF9800", "#E91E63"]

    # Latency boxplot
    lat_data = []
    for tier in tiers:
        all_lat = []
        for r in results[tier]:
            all_lat.extend(r["latencies"])
        lat_data.append(all_lat)
    bp = ax1.boxplot(lat_data, labels=[t.upper() for t in tiers], patch_artist=True)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax1.set_ylabel("Latency (ms)")
    ax1.set_title("Per-tick Latency")
    ax1.set_yscale("log")

    # Energy trajectory (first repeat)
    for tier, color in zip(tiers, colors):
        energies = results[tier][0]["energies"]
        ax2.plot(energies[:200], color=color, alpha=0.8, label=tier.upper())
    ax2.set_xlabel("Tick")
    ax2.set_ylabel("Field Energy")
    ax2.set_title("Energy Trajectory (first 200 ticks)")
    ax2.legend()

    # Sync order trajectory
    for tier, color in zip(tiers, colors):
        sync = results[tier][0]["sync_orders"]
        ax3.plot(sync[:200], color=color, alpha=0.8, label=tier.upper())
    ax3.set_xlabel("Tick")
    ax3.set_ylabel("Kuramoto Order Parameter r")
    ax3.set_title("Synchronization (first 200 ticks)")
    ax3.legend()

    plt.tight_layout()
    save_figure(fig, "fig03_tier_comparison")
    plt.close(fig)


if __name__ == "__main__":
    main()
