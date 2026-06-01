"""Experiment 10: Personality-Computation Coupling.

Validates: "7 personality dimensions fully determine all coupling parameters"
Protocol: Sweep each personality dimension 0→1, measure resulting system behavior.
Output: Response surface showing personality→dynamics mapping.
"""

from __future__ import annotations

import numpy as np
from utils import (
    N_REPEATS,
    SAMPLE_TEXTS,
    make_spine,
    process_text,
    save_figure,
)

PERSONALITY_DIMS = [
    "extraversion",
    "neuroticism",
    "openness",
    "conscientiousness",
    "agreeableness",
]

SWEEP_VALUES = np.linspace(0.1, 0.9, 9)


def run_sweep_single(dim: str, value: float, seed: int) -> dict:
    """Run 200 ticks with one personality dimension set to value, others at 0.5."""
    spine = make_spine("pro")

    personality = {d: 0.5 for d in PERSONALITY_DIMS}
    personality[dim] = value
    spine.apply_personality(personality)

    base_time = 1_000_000.0 + seed * 100_000
    energies = []
    sync_orders = []
    expression_count = 0

    for i in range(200):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + i * 60.0
        result = process_text(spine, text, now=now)
        meta = spine._last_resonance_meta
        energies.append(meta.get("energy", 0.0))
        sync_orders.append(meta.get("sync_order", 0.0))
        if result.get("should_express", False):
            expression_count += 1

    return {
        "mean_energy": float(np.mean(energies[-50:])),
        "mean_sync": float(np.mean(sync_orders[-50:])),
        "expression_rate": expression_count / 200.0,
    }


def main():
    import matplotlib.pyplot as plt

    print(
        f"  Running personality sweep ({len(PERSONALITY_DIMS)} dims x "
        f"{len(SWEEP_VALUES)} values x {N_REPEATS} repeats)..."
    )

    # Collect data
    data = {}
    for dim in PERSONALITY_DIMS:
        data[dim] = {"energy": [], "sync": [], "expression": []}
        for val in SWEEP_VALUES:
            energies = []
            syncs = []
            expressions = []
            for rep in range(N_REPEATS):
                r = run_sweep_single(dim, float(val), seed=rep)
                energies.append(r["mean_energy"])
                syncs.append(r["mean_sync"])
                expressions.append(r["expression_rate"])
            data[dim]["energy"].append((float(val), np.mean(energies), np.std(energies)))
            data[dim]["sync"].append((float(val), np.mean(syncs), np.std(syncs)))
            data[dim]["expression"].append((float(val), np.mean(expressions), np.std(expressions)))
        print(f"    {dim}: done")

    # Figure: 3 rows (energy, sync, expression) x 5 cols (personality dims)
    fig, axes = plt.subplots(3, 5, figsize=(18, 10), sharex=True)
    colors = ["#E91E63", "#9C27B0", "#2196F3", "#4CAF50", "#FF9800"]
    metrics = ["energy", "sync", "expression"]
    ylabels = ["Mean Energy", "Sync Order r", "Expression Rate"]

    for col, (dim, color) in enumerate(zip(PERSONALITY_DIMS, colors)):
        for row, (metric, ylabel) in enumerate(zip(metrics, ylabels)):
            ax = axes[row, col]
            vals = data[dim][metric]
            x = [v[0] for v in vals]
            y = [v[1] for v in vals]
            err = [v[2] for v in vals]

            ax.errorbar(
                x, y, yerr=err, color=color, linewidth=2, capsize=3, marker="o", markersize=4
            )
            if row == 0:
                ax.set_title(dim.capitalize(), fontsize=10)
            if col == 0:
                ax.set_ylabel(ylabel, fontsize=9)
            if row == 2:
                ax.set_xlabel("Value", fontsize=9)

    fig.suptitle("Personality → Dynamics Response Surface (pro tier, 200 ticks)", fontsize=12)
    plt.tight_layout()
    save_figure(fig, "fig11_personality_modulation")
    plt.close(fig)


if __name__ == "__main__":
    main()
