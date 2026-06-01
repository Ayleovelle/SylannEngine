"""Experiment 12: v1 (Sequential Pipeline) vs v2 (Resonance Field) Comparison.

Validates: "Resonance field produces richer dynamics than sequential pipeline"
Protocol: Run identical input sequences through both ComputationSpine (v1) and
          ResonanceSpine (v2) at pro tier. Compare energy evolution, expression
          rates, response diversity, and plasticity effects.
Output: Side-by-side comparison figures.
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
    save_figure,
)

from sylanne_core.compute.computation_spine import ComputationSpine
from sylanne_core.config import build_profile


def make_v1_spine(tier: str = "pro") -> ComputationSpine:
    """Create a v1 sequential pipeline spine."""
    profile = build_profile(tier)
    spine = ComputationSpine(profile=profile)
    return spine


def run_comparison(tier: str, n_ticks: int, seed: int) -> dict:
    """Run identical input through v1 and v2, collect metrics."""
    np.random.seed(seed)

    # Create both spines
    v1 = make_v1_spine(tier)
    v2 = make_spine(tier)

    # Apply same personality
    personality = {
        "extraversion": 0.6,
        "neuroticism": 0.4,
        "openness": 0.7,
        "conscientiousness": 0.5,
        "agreeableness": 0.6,
        "patience": 0.52,
        "sovereignty_guard": 0.68,
    }
    v1.apply_personality(personality)
    v2.apply_personality(personality)

    # Build input sequence: mixed normal + stress + positive
    all_texts = SAMPLE_TEXTS * 40 + STRESS_TEXTS * 20 + POSITIVE_TEXTS * 20
    texts = all_texts[:n_ticks]
    np.random.shuffle(texts)

    base_time = 1_000_000.0 + seed * 100_000

    # Metrics storage
    v1_energies = []
    v2_energies = []
    v1_express_count = 0
    v2_express_count = 0
    v1_decisions = []
    v2_decisions = []

    for i in range(n_ticks):
        text = texts[i % len(texts)]
        now = base_time + i * 60.0

        # v1 process
        r1 = v1.process(text, now)
        v1_energy = (
            sum(abs(v) for v in r1.get("emotion", {}).values()) if r1.get("emotion") else 0.0
        )
        v1_energies.append(v1_energy)
        if r1.get("should_express", False):
            v1_express_count += 1
        route = r1.get("route", "normal")
        v1_decisions.append(route)

        # v2 process
        r2 = v2.process(text, now)
        v2_energy = (
            sum(abs(v) for v in r2.get("emotion", {}).values()) if r2.get("emotion") else 0.0
        )
        v2_energies.append(v2_energy)
        if r2.get("should_express", False):
            v2_express_count += 1
        v2_decisions.append("resonance")

    # Compute diversity (unique emotion patterns) using fresh spines
    # to avoid contamination from the 500-tick experiment
    v1_fresh = make_v1_spine(tier)
    v2_fresh = make_spine(tier)
    v1_fresh.apply_personality(personality)
    v2_fresh.apply_personality(personality)
    v1_diversity = len(
        set(
            tuple(round(v, 2) for v in r.get("emotion", {}).values())
            for r in [
                v1_fresh.process(t, base_time + 999 * 60 + j) for j, t in enumerate(SAMPLE_TEXTS)
            ]
        )
    )
    v2_diversity = len(
        set(
            tuple(round(v, 2) for v in r.get("emotion", {}).values())
            for r in [
                v2_fresh.process(t, base_time + 999 * 60 + j) for j, t in enumerate(SAMPLE_TEXTS)
            ]
        )
    )

    return {
        "v1_energies": v1_energies,
        "v2_energies": v2_energies,
        "v1_express_rate": v1_express_count / n_ticks,
        "v2_express_rate": v2_express_count / n_ticks,
        "v1_diversity": v1_diversity,
        "v2_diversity": v2_diversity,
        "v1_mean_energy": np.mean(v1_energies),
        "v2_mean_energy": np.mean(v2_energies),
        "v1_energy_std": np.std(v1_energies),
        "v2_energy_std": np.std(v2_energies),
    }


def main():
    import matplotlib.pyplot as plt

    tier = "lite"
    n_ticks = 500
    print(f"  Running v1 vs v2 comparison ({N_REPEATS} repeats x {n_ticks} ticks, {tier} tier)...")

    all_results = []
    for rep in range(N_REPEATS):
        print(f"    Repeat {rep + 1}/{N_REPEATS}...")
        result = run_comparison(tier, n_ticks, seed=rep)
        all_results.append(result)

    # Aggregate metrics
    v1_express_rates = [r["v1_express_rate"] for r in all_results]
    v2_express_rates = [r["v2_express_rate"] for r in all_results]
    v1_mean_energies = [r["v1_mean_energy"] for r in all_results]
    v2_mean_energies = [r["v2_mean_energy"] for r in all_results]
    v1_energy_stds = [r["v1_energy_std"] for r in all_results]
    v2_energy_stds = [r["v2_energy_std"] for r in all_results]
    v1_diversities = [r["v1_diversity"] for r in all_results]
    v2_diversities = [r["v2_diversity"] for r in all_results]

    print_stats("v1 expression rate", v1_express_rates)
    print_stats("v2 expression rate", v2_express_rates)
    print_stats("v1 mean energy", v1_mean_energies)
    print_stats("v2 mean energy", v2_mean_energies)
    print_stats("v1 energy variability", v1_energy_stds)
    print_stats("v2 energy variability", v2_energy_stds)
    print_stats("v1 response diversity", [float(d) for d in v1_diversities])
    print_stats("v2 response diversity", [float(d) for d in v2_diversities])

    # --- Figure: 2x2 comparison ---
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    # Panel A: Energy trajectory (single representative run)
    ax = axes[0, 0]
    rep_idx = 0
    v1_e = all_results[rep_idx]["v1_energies"]
    v2_e = all_results[rep_idx]["v2_energies"]
    window = 20
    v1_smooth = np.convolve(v1_e, np.ones(window) / window, mode="valid")
    v2_smooth = np.convolve(v2_e, np.ones(window) / window, mode="valid")
    ax.plot(v1_smooth, color="#666666", alpha=0.8, label="v1 (Sequential)", linewidth=1.2)
    ax.plot(v2_smooth, color="#E91E63", alpha=0.8, label="v2 (Resonance)", linewidth=1.2)
    ax.set_xlabel("Tick")
    ax.set_ylabel("Total |emotion|")
    ax.set_title("A. Energy Trajectory (smoothed)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    # Panel B: Expression rate comparison
    ax = axes[0, 1]
    x = np.arange(N_REPEATS)
    width = 0.35
    ax.bar(x - width / 2, v1_express_rates, width, color="#666666", alpha=0.8, label="v1")
    ax.bar(x + width / 2, v2_express_rates, width, color="#E91E63", alpha=0.8, label="v2")
    ax.set_xlabel("Repeat")
    ax.set_ylabel("Expression Rate")
    ax.set_title("B. Expression Rate per Repeat")
    ax.legend()
    ax.set_xticks(x)
    ax.grid(True, alpha=0.3, axis="y")

    # Panel C: Energy variability (box plot)
    ax = axes[1, 0]
    bp = ax.boxplot(
        [v1_energy_stds, v2_energy_stds],
        labels=["v1 (Sequential)", "v2 (Resonance)"],
        patch_artist=True,
    )
    bp["boxes"][0].set_facecolor("#CCCCCC")
    bp["boxes"][1].set_facecolor("#F8BBD0")
    ax.set_ylabel("Energy Std Dev")
    ax.set_title("C. Dynamic Richness (Energy Variability)")
    ax.grid(True, alpha=0.3, axis="y")

    # Panel D: Summary bar chart
    ax = axes[1, 1]
    metrics = ["Mean Energy", "Energy Std", "Express Rate", "Diversity"]
    v1_vals = [
        np.mean(v1_mean_energies),
        np.mean(v1_energy_stds),
        np.mean(v1_express_rates) * 10,  # scale for visibility
        np.mean(v1_diversities),
    ]
    v2_vals = [
        np.mean(v2_mean_energies),
        np.mean(v2_energy_stds),
        np.mean(v2_express_rates) * 10,
        np.mean(v2_diversities),
    ]
    x = np.arange(len(metrics))
    ax.bar(x - width / 2, v1_vals, width, color="#666666", alpha=0.8, label="v1")
    ax.bar(x + width / 2, v2_vals, width, color="#E91E63", alpha=0.8, label="v2")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_title("D. Aggregate Comparison")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle(
        f"v1 (Sequential Pipeline) vs v2 (Resonance Field) — {tier} tier, {n_ticks} ticks × {N_REPEATS} repeats",
        fontsize=12,
    )
    plt.tight_layout()
    save_figure(fig, "fig13_v1_v2_comparison")
    plt.close(fig)


if __name__ == "__main__":
    main()
