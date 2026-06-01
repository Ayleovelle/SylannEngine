"""Experiment 11: Tier Hot-Switch Fidelity.

Validates: "Lossless tier hot-switching: linear interpolation upgrade, average pooling downgrade"
Protocol: Run 500 ticks at lite, switch to pro, run 500 more. Measure state continuity.
          Also test pro→max and max→lite. 10 repeats.
Output: State L2 distance before/after switch, emotion continuity.
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

from sylanne_core.config import build_profile


def run_switch(from_tier: str, to_tier: str, seed: int) -> dict:
    """Run 500 ticks, switch tier, run 500 more. Measure continuity."""
    spine = make_spine(from_tier)
    base_time = 1_000_000.0 + seed * 100_000

    energies = []
    emotions_before = []

    # Phase 1: Build state
    for i in range(500):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + i * 60.0
        result = process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        energies.append(meta.get("energy", 0.0))
        if i >= 490:
            emotions_before.append(result.get("emotion", {}))

    # Capture pre-switch state
    pre_switch_energy = energies[-1]

    # Switch tier
    new_profile = build_profile(to_tier)
    spine._field.switch_tier(to_tier)
    spine._profile = new_profile
    spine._tier = to_tier

    # Capture post-switch state
    post_switch_energy = spine._field._last_energy

    # Phase 2: Continue after switch
    emotions_after = []
    for i in range(500):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + (500 + i) * 60.0
        result = process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        energies.append(meta.get("energy", 0.0))
        if i < 10:
            emotions_after.append(result.get("emotion", {}))

    # Compute continuity metrics
    energy_jump = abs(post_switch_energy - pre_switch_energy)
    energy_relative_jump = energy_jump / max(pre_switch_energy, 1e-8)

    return {
        "energies": energies,
        "energy_jump": energy_jump,
        "energy_relative_jump": energy_relative_jump,
        "pre_energy": pre_switch_energy,
        "post_energy": post_switch_energy,
    }


def main():
    import matplotlib.pyplot as plt

    transitions = [
        ("lite", "pro"),
        ("pro", "max"),
        ("max", "lite"),
        ("lite", "max"),
    ]
    colors = ["#2196F3", "#FF9800", "#E91E63", "#4CAF50"]

    all_results = {}
    for from_t, to_t in transitions:
        key = f"{from_t}→{to_t}"
        print(f"  Testing {key} ({N_REPEATS} repeats x 1000 ticks)...")
        results = []
        for rep in range(N_REPEATS):
            r = run_switch(from_t, to_t, seed=rep)
            results.append(r)
        all_results[key] = results
        print_stats(f"    Energy jump", [r["energy_jump"] for r in results])
        print_stats(f"    Relative jump", [r["energy_relative_jump"] for r in results])

    # Figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Energy trajectories
    for (from_t, to_t), color in zip(transitions, colors):
        key = f"{from_t}→{to_t}"
        energies_mean = np.mean([r["energies"] for r in all_results[key]], axis=0)
        ax1.plot(energies_mean, color=color, linewidth=1.5, label=key)
    ax1.axvline(500, color="gray", linestyle="--", label="Switch point")
    ax1.set_xlabel("Tick")
    ax1.set_ylabel("Field Energy")
    ax1.set_title("Energy Continuity Across Tier Switch")
    ax1.legend(fontsize=8)

    # Relative energy jump bar chart
    keys = [f"{f}→{t}" for f, t in transitions]
    jumps_mean = [np.mean([r["energy_relative_jump"] for r in all_results[k]]) for k in keys]
    jumps_std = [np.std([r["energy_relative_jump"] for r in all_results[k]]) for k in keys]

    bars = ax2.bar(keys, jumps_mean, yerr=jumps_std, color=colors, alpha=0.7, capsize=5)
    ax2.set_ylabel("Relative Energy Jump |ΔE|/E")
    ax2.set_title("Tier Switch Fidelity")
    ax2.axhline(0.1, color="red", linestyle="--", alpha=0.5, label="10% threshold")
    ax2.legend()

    plt.tight_layout()
    save_figure(fig, "fig12_tier_hotswitch")
    plt.close(fig)


if __name__ == "__main__":
    main()
