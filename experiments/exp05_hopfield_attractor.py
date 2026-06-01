"""Experiment 5: Hopfield Attractor Formation and Escape.

Validates: "Emotional memory as energy minima; expression = escaping attractor"
Protocol: Feed repeated patterns to form attractors, then novel input to trigger escape.
          Measure attractor count, basin radius, escape conditions. 10 repeats.
Output: Attractor landscape visualization, escape dynamics.
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


def run_single(seed: int) -> dict:
    spine = make_spine("pro")
    field = spine._field

    base_time = 1_000_000.0 + seed * 100_000
    attractor_counts = []
    distances_to_nearest = []
    expression_events = []
    energy_history = []

    # Phase 1: Build attractors with repeated patterns (500 ticks)
    pattern_a = POSITIVE_TEXTS
    pattern_b = STRESS_TEXTS

    for i in range(250):
        text = pattern_a[i % len(pattern_a)]
        now = base_time + i * 60.0
        result = process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        attractor_counts.append(meta.get("attractor_count", 0))
        distances_to_nearest.append(meta.get("near_attractor", 1.0))
        energy_history.append(meta.get("energy", 0.0))
        if result.get("should_express", False):
            expression_events.append(("phase1a", i))

    for i in range(250):
        text = pattern_b[i % len(pattern_b)]
        now = base_time + (250 + i) * 60.0
        result = process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        attractor_counts.append(meta.get("attractor_count", 0))
        distances_to_nearest.append(meta.get("near_attractor", 1.0))
        energy_history.append(meta.get("energy", 0.0))
        if result.get("should_express", False):
            expression_events.append(("phase1b", 250 + i))

    attractors_after_training = attractor_counts[-1] if attractor_counts else 0

    # Phase 2: Novel input to trigger escape (500 ticks)
    novel_texts = [
        "我从来没有想过这个问题",
        "这完全出乎我的意料",
        "世界突然变得不一样了",
        "我需要重新思考一切",
        "也许我一直都错了",
    ]

    escape_distances = []
    for i in range(500):
        text = novel_texts[i % len(novel_texts)]
        now = base_time + (500 + i) * 60.0
        result = process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        attractor_counts.append(meta.get("attractor_count", 0))
        d = meta.get("near_attractor", 1.0)
        distances_to_nearest.append(d)
        escape_distances.append(d)
        energy_history.append(meta.get("energy", 0.0))
        if result.get("should_express", False):
            expression_events.append(("escape", 500 + i))

    return {
        "attractor_counts": attractor_counts,
        "distances": distances_to_nearest,
        "energy": energy_history,
        "escape_distances": escape_distances,
        "attractors_formed": attractors_after_training,
        "n_expressions": len(expression_events),
        "escape_expressions": len([e for e in expression_events if e[0] == "escape"]),
    }


def main():
    import matplotlib.pyplot as plt

    print(f"  Running Hopfield attractor experiment ({N_REPEATS} repeats x 1000 ticks)...")
    all_results = []
    for rep in range(N_REPEATS):
        result = run_single(seed=rep)
        all_results.append(result)

    # Stats
    print_stats("Attractors formed", [r["attractors_formed"] for r in all_results])
    print_stats("Expressions during escape", [r["escape_expressions"] for r in all_results])
    print_stats("Mean escape distance", [np.mean(r["escape_distances"]) for r in all_results])

    # Figure
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4))

    # Attractor count over time
    counts_mean = np.mean([r["attractor_counts"] for r in all_results], axis=0)
    ax1.plot(counts_mean, color="#9C27B0", linewidth=1.5)
    ax1.axvline(500, color="gray", linestyle="--", label="Novel input starts")
    ax1.set_xlabel("Tick")
    ax1.set_ylabel("Attractor Count")
    ax1.set_title("Attractor Formation")
    ax1.legend()

    # Distance to nearest attractor
    dist_mean = np.mean([r["distances"] for r in all_results], axis=0)
    dist_std = np.std([r["distances"] for r in all_results], axis=0)
    x = np.arange(len(dist_mean))
    ax2.plot(x, dist_mean, color="#FF5722", linewidth=1)
    ax2.fill_between(x, dist_mean - dist_std, dist_mean + dist_std,
                     color="#FF5722", alpha=0.2)
    ax2.axvline(500, color="gray", linestyle="--", label="Novel input")
    ax2.set_xlabel("Tick")
    ax2.set_ylabel("Distance to Nearest Attractor")
    ax2.set_title("Basin Escape Dynamics")
    ax2.legend()

    # Energy during escape
    energy_mean = np.mean([r["energy"] for r in all_results], axis=0)
    ax3.plot(energy_mean, color="#009688", linewidth=1)
    ax3.axvline(500, color="gray", linestyle="--", label="Novel input")
    ax3.set_xlabel("Tick")
    ax3.set_ylabel("Field Energy")
    ax3.set_title("Energy Landscape")
    ax3.legend()

    plt.tight_layout()
    save_figure(fig, "fig06_hopfield_attractor")
    plt.close(fig)


if __name__ == "__main__":
    main()
