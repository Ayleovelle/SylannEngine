"""Experiment 9: Long-Term Stability (1000+ ticks).

Validates: "Energy bounded, no NaN/Inf, no divergence over extended operation"
Protocol: 1500 ticks of mixed input (stress + positive + neutral + idle). 10 repeats.
Output: Energy envelope, NaN/Inf check, state norm trajectory.
"""

from __future__ import annotations

import numpy as np
from utils import (
    N_REPEATS,
    POSITIVE_TEXTS,
    SAMPLE_TEXTS,
    STRESS_TEXTS,
    make_spine,
    print_stats,
    process_text,
    save_figure,
)


def run_single(tier: str, seed: int) -> dict:
    spine = make_spine(tier)
    field = spine._field
    base_time = 1_000_000.0 + seed * 100_000

    energies = []
    state_norms = []
    nan_count = 0
    inf_count = 0

    np.random.seed(seed)
    all_texts = SAMPLE_TEXTS * 50 + STRESS_TEXTS * 50 + POSITIVE_TEXTS * 50
    np.random.shuffle(all_texts)

    for i in range(1500):
        if i < len(all_texts):
            text = all_texts[i]
        else:
            text = all_texts[i % len(all_texts)]

        now = base_time + i * 60.0

        # Mix in idle ticks (20% of the time)
        if np.random.random() < 0.2:
            spine.process("", now)
        else:
            process_text(spine, text, now=now)

        energy = field._last_energy
        energies.append(energy)

        # Check for NaN/Inf in state
        states = field._module_states
        for s in states:
            if np.any(np.isnan(s)):
                nan_count += 1
            if np.any(np.isinf(s)):
                inf_count += 1

        state_norm = float(np.sqrt(sum(np.sum(np.array(s) ** 2) for s in states)))
        state_norms.append(state_norm)

    return {
        "energies": energies,
        "state_norms": state_norms,
        "nan_count": nan_count,
        "inf_count": inf_count,
        "max_energy": float(max(energies)),
        "final_energy": float(energies[-1]),
        "energy_stable": float(np.std(energies[-100:])),
    }


def main():
    import matplotlib.pyplot as plt

    tiers = ["lite", "pro", "max"]
    colors = ["#2196F3", "#FF9800", "#E91E63"]
    all_results = {t: [] for t in tiers}

    for tier in tiers:
        print(f"  Running stability test: {tier} ({N_REPEATS} repeats x 1500 ticks)...")
        for rep in range(N_REPEATS):
            result = run_single(tier, seed=rep)
            all_results[tier].append(result)

        # Report
        nan_total = sum(r["nan_count"] for r in all_results[tier])
        inf_total = sum(r["inf_count"] for r in all_results[tier])
        print(f"    NaN occurrences: {nan_total}")
        print(f"    Inf occurrences: {inf_total}")
        print_stats("    Max energy", [r["max_energy"] for r in all_results[tier]])
        print_stats(
            "    Final energy std (last 100)", [r["energy_stable"] for r in all_results[tier]]
        )

    # Figure
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    for tier, color in zip(tiers, colors):
        # Energy envelope (mean ± std across repeats)
        energies = np.array([r["energies"] for r in all_results[tier]])
        e_mean = energies.mean(axis=0)
        e_max = energies.max(axis=0)
        e_min = energies.min(axis=0)

        ax1.plot(e_mean, color=color, linewidth=1, label=f"{tier.upper()}")
        ax1.fill_between(range(len(e_mean)), e_min, e_max, color=color, alpha=0.1)

    ax1.set_ylabel("Field Energy")
    ax1.set_title("Energy Envelope (1500 ticks, 10 repeats)")
    ax1.legend()

    for tier, color in zip(tiers, colors):
        norms = np.array([r["state_norms"] for r in all_results[tier]])
        n_mean = norms.mean(axis=0)
        ax2.plot(n_mean, color=color, linewidth=1, label=f"{tier.upper()}")

    ax2.set_ylabel("State Norm ||x||")
    ax2.set_title("State Norm Trajectory")
    ax2.legend()

    # Stability metric: rolling std of energy (window=50)
    for tier, color in zip(tiers, colors):
        energies = np.array([r["energies"] for r in all_results[tier]])
        e_mean = energies.mean(axis=0)
        rolling_std = []
        window = 50
        for i in range(len(e_mean)):
            start = max(0, i - window)
            rolling_std.append(np.std(e_mean[start : i + 1]))
        ax3.plot(rolling_std, color=color, linewidth=1, label=f"{tier.upper()}")

    ax3.set_xlabel("Tick")
    ax3.set_ylabel("Rolling Energy Std (window=50)")
    ax3.set_title("Energy Stability Over Time")
    ax3.legend()

    plt.tight_layout()
    save_figure(fig, "fig10_stability")
    plt.close(fig)


if __name__ == "__main__":
    main()
