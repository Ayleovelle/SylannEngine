"""Experiment 4: Kuramoto Synchronization and Explosive Transitions.

Validates: "Higher-order coupling (3-body, 4-body) produces explosive synchronization"
Protocol: Sweep coupling strength K from 0 to 2.0, measure order parameter r.
          Compare pairwise-only (lite) vs higher-order (pro/max). 10 repeats.
Output: Phase transition curve r(K) showing explosive vs gradual sync.
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


def measure_sync_at_coupling(tier: str, k_scale: float, n_ticks: int, seed: int) -> float:
    """Run n_ticks and return final sync order parameter at given coupling scale."""
    spine = make_spine(tier)
    field = spine._field
    kuramoto = field._coupling.kuramoto

    # Scale all coupling constants
    kuramoto._k1 = 1.0 * k_scale
    if hasattr(kuramoto, "_k2"):
        kuramoto._k2 = 0.5 * k_scale
    if hasattr(kuramoto, "_k3"):
        kuramoto._k3 = 0.25 * k_scale

    base_time = 1_000_000.0 + seed * 100_000
    sync_values = []

    for i in range(n_ticks):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + i * 60.0
        process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        sync_values.append(meta.get("sync_order", 0.0))

    # Return mean of last 100 ticks (steady state)
    return float(np.mean(sync_values[-100:])) if len(sync_values) >= 100 else float(np.mean(sync_values))


def run_sweep(tier: str, k_values: np.ndarray, n_ticks: int = 200) -> list[list[float]]:
    """Sweep coupling strength, return r values for each K (repeats x K)."""
    all_r = []
    for rep in range(N_REPEATS):
        r_values = []
        for k in k_values:
            r = measure_sync_at_coupling(tier, float(k), n_ticks, seed=rep)
            r_values.append(r)
        all_r.append(r_values)
    return all_r


def main():
    import matplotlib.pyplot as plt

    k_values = np.linspace(0.0, 2.5, 20)
    tiers = ["lite", "pro", "max"]
    colors = ["#2196F3", "#FF9800", "#E91E63"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Phase transition curves
    for tier, color in zip(tiers, colors):
        print(f"  Sweeping {tier} tier (20 K values x {N_REPEATS} repeats x 200 ticks)...")
        results = run_sweep(tier, k_values, n_ticks=200)
        r_mean = np.mean(results, axis=0)
        r_std = np.std(results, axis=0)

        ax1.plot(k_values, r_mean, color=color, linewidth=2, label=f"{tier.upper()}")
        ax1.fill_between(k_values, r_mean - r_std, r_mean + r_std,
                         color=color, alpha=0.15)

    ax1.set_xlabel("Coupling Strength K (scaled)")
    ax1.set_ylabel("Order Parameter r")
    ax1.set_title("Kuramoto Phase Transition: r(K)")
    ax1.legend()
    ax1.set_ylim(0, 1.05)
    ax1.axhline(0.5, color="gray", linestyle=":", alpha=0.5)

    # Time evolution of r at fixed K=1.0
    print("  Running time evolution at K=1.0...")
    for tier, color in zip(tiers, colors):
        spine = make_spine(tier)
        sync_history = []
        base_time = 1_000_000.0
        for i in range(500):
            text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
            now = base_time + i * 60.0
            process_text(spine, text, now=now)
            meta = spine._last_resonance_meta
            sync_history.append(meta.get("sync_order", 0.0))
        ax2.plot(sync_history, color=color, alpha=0.8, label=f"{tier.upper()}")

    ax2.set_xlabel("Tick")
    ax2.set_ylabel("Order Parameter r")
    ax2.set_title("Synchronization Evolution (K=1.0)")
    ax2.legend()

    plt.tight_layout()
    save_figure(fig, "fig05_kuramoto_sync")
    plt.close(fig)

    # Statistical test: max tier should have higher r than lite at K=1.0
    lite_r = [measure_sync_at_coupling("lite", 1.0, 200, seed=i) for i in range(N_REPEATS)]
    max_r = [measure_sync_at_coupling("max", 1.0, 200, seed=i) for i in range(N_REPEATS)]
    print_stats("lite r at K=1.0", lite_r)
    print_stats("max r at K=1.0", max_r)

    try:
        from scipy.stats import mannwhitneyu
        stat, p = mannwhitneyu(max_r, lite_r, alternative="greater")
        print(f"  Mann-Whitney U (max > lite): p={p:.6f}")
    except ImportError:
        print("  (scipy not available for statistical test)")


if __name__ == "__main__":
    main()
