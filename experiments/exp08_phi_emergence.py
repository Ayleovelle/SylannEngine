"""Experiment 8: Phi (Integrated Information) and Expression Correlation.

Validates: "Phi gates meaningfulness: meaning_gate = 0.3 + phi * 0.7"
Protocol: Run 1000 ticks, collect (Phi, expression_drive) pairs. Compute correlation.
Output: Scatter plot of Phi vs expression drive, Pearson/Spearman correlation.
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
    base_time = 1_000_000.0 + seed * 100_000

    phi_values = []
    drive_values = []
    expressed = []

    # Mix of different input types for variance
    all_texts = SAMPLE_TEXTS * 40 + STRESS_TEXTS * 40 + POSITIVE_TEXTS * 40
    np.random.seed(seed)
    np.random.shuffle(all_texts)
    texts = all_texts[:1000]

    for i, text in enumerate(texts):
        now = base_time + i * 60.0
        result = process_text(spine, text, now=now)
        resonance = result.get("resonance", {})
        phi = resonance.get("phi", 0.0)
        drive = spine._expression_drive
        phi_values.append(phi)
        drive_values.append(drive)
        expressed.append(result.get("should_express", False))

    return {
        "phi": phi_values,
        "drive": drive_values,
        "expressed": expressed,
    }


def main():
    import matplotlib.pyplot as plt

    print(f"  Running Phi-expression experiment ({N_REPEATS} repeats x 1000 ticks)...")
    all_results = []
    correlations_pearson = []
    correlations_spearman = []

    for rep in range(N_REPEATS):
        result = run_single(seed=rep)
        all_results.append(result)

        phi = np.array(result["phi"])
        drive = np.array(result["drive"])

        # Filter out zero-phi (cold start)
        mask = phi > 0
        if mask.sum() > 10:
            try:
                from scipy.stats import pearsonr, spearmanr
                r_p, _ = pearsonr(phi[mask], drive[mask])
                r_s, _ = spearmanr(phi[mask], drive[mask])
            except ImportError:
                # Fallback: numpy correlation
                r_p = float(np.corrcoef(phi[mask], drive[mask])[0, 1])
                r_s = r_p  # approximate
            correlations_pearson.append(r_p)
            correlations_spearman.append(r_s)

    print_stats("Pearson r(Phi, drive)", correlations_pearson)
    print_stats("Spearman rho(Phi, drive)", correlations_spearman)

    # Filter NaN values for plotting
    correlations_pearson = [x for x in correlations_pearson if not np.isnan(x)]
    correlations_spearman = [x for x in correlations_spearman if not np.isnan(x)]

    # Figure
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4))

    # Scatter: Phi vs drive (first repeat)
    phi = np.array(all_results[0]["phi"])
    drive = np.array(all_results[0]["drive"])
    expressed = np.array(all_results[0]["expressed"])

    ax1.scatter(phi[~expressed], drive[~expressed], s=8, alpha=0.3,
                color="#9E9E9E", label="No expression")
    ax1.scatter(phi[expressed], drive[expressed], s=20, alpha=0.7,
                color="#F44336", label="Expression fired")
    ax1.set_xlabel("Phi (Integrated Information)")
    ax1.set_ylabel("Expression Drive")
    ax1.set_title("Phi vs Expression Drive")
    ax1.legend(fontsize=8)

    # Meaning gate visualization
    phi_range = np.linspace(0, 1, 100)
    meaning_gate = 0.3 + phi_range * 0.7
    ax2.plot(phi_range, meaning_gate, color="#2196F3", linewidth=2)
    ax2.fill_between(phi_range, 0, meaning_gate, color="#2196F3", alpha=0.1)
    ax2.set_xlabel("Phi")
    ax2.set_ylabel("Meaning Gate (0.3 + 0.7*Phi)")
    ax2.set_title("Phi as Noise Suppression Gate")
    ax2.set_ylim(0, 1.1)

    # Correlation distribution
    if correlations_pearson:
        ax3.hist(correlations_pearson, bins=max(2, len(correlations_pearson) // 2),
                 color="#4CAF50", alpha=0.7, edgecolor="white", label="Pearson")
    if correlations_spearman:
        ax3.hist(correlations_spearman, bins=max(2, len(correlations_spearman) // 2),
                 color="#FF9800", alpha=0.5, edgecolor="white", label="Spearman")
    ax3.axvline(0, color="gray", linestyle="--")
    ax3.set_xlabel("Correlation Coefficient")
    ax3.set_ylabel("Count")
    ax3.set_title(f"Phi-Drive Correlation (n={N_REPEATS})")
    ax3.legend()

    plt.tight_layout()
    save_figure(fig, "fig09_phi_emergence")
    plt.close(fig)


if __name__ == "__main__":
    main()
