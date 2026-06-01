"""Experiment 7: Harmonic Identity — Restoring Force.

Validates: "Hodge Laplacian null-space extraction preserves personality across perturbations"
Protocol: Build identity over 500 ticks, apply perturbation, measure recovery. 10 repeats.
Output: Identity norm over time, perturbation recovery curve.
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

    identity_norms = []
    state_norms = []

    # Phase 1: Build identity (500 ticks of consistent input)
    for i in range(500):
        text = POSITIVE_TEXTS[i % len(POSITIVE_TEXTS)]
        now = base_time + i * 60.0
        process_text(spine, text, now=now)
        identity_norms.append(float(np.linalg.norm(field._harmonic_identity)))
        state_norms.append(float(field._last_energy))

    identity_before_perturbation = np.array(field._harmonic_identity)
    norm_before = float(np.linalg.norm(identity_before_perturbation))

    # Phase 2: Perturbation (200 ticks of extreme stress)
    for i in range(200):
        text = STRESS_TEXTS[i % len(STRESS_TEXTS)]
        now = base_time + (500 + i) * 60.0
        process_text(spine, text, now=now)
        identity_norms.append(float(np.linalg.norm(field._harmonic_identity)))
        state_norms.append(float(field._last_energy))

    identity_after_perturbation = np.array(field._harmonic_identity)
    perturbation_drift = float(
        np.linalg.norm(identity_after_perturbation - identity_before_perturbation)
    )

    # Phase 3: Recovery (300 ticks of neutral input)
    for i in range(300):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        now = base_time + (700 + i) * 60.0
        process_text(spine, text, now=now)
        identity_norms.append(float(np.linalg.norm(field._harmonic_identity)))
        state_norms.append(float(field._last_energy))

    identity_final = np.array(field._harmonic_identity)
    recovery_distance = float(np.linalg.norm(identity_final - identity_before_perturbation))

    return {
        "identity_norms": identity_norms,
        "state_norms": state_norms,
        "norm_before": norm_before,
        "perturbation_drift": perturbation_drift,
        "recovery_distance": recovery_distance,
        "recovery_ratio": 1.0 - (recovery_distance / max(perturbation_drift, 1e-8)),
    }


def main():
    import matplotlib.pyplot as plt

    print(f"  Running harmonic identity experiment ({N_REPEATS} repeats x 1000 ticks)...")
    all_results = []
    for rep in range(N_REPEATS):
        result = run_single(seed=rep)
        all_results.append(result)

    # Stats
    print_stats("Identity norm (pre-perturbation)", [r["norm_before"] for r in all_results])
    print_stats("Perturbation drift", [r["perturbation_drift"] for r in all_results])
    print_stats("Recovery distance", [r["recovery_distance"] for r in all_results])
    print_stats("Recovery ratio", [r["recovery_ratio"] for r in all_results])

    # Figure
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4))

    # Identity norm over time
    norms_mean = np.mean([r["identity_norms"] for r in all_results], axis=0)
    norms_std = np.std([r["identity_norms"] for r in all_results], axis=0)
    x = np.arange(len(norms_mean))
    ax1.plot(x, norms_mean, color="#673AB7", linewidth=1.5)
    ax1.fill_between(x, norms_mean - norms_std, norms_mean + norms_std, color="#673AB7", alpha=0.2)
    ax1.axvline(500, color="red", linestyle="--", label="Perturbation")
    ax1.axvline(700, color="green", linestyle="--", label="Recovery")
    ax1.set_xlabel("Tick")
    ax1.set_ylabel("Identity Norm ||h||")
    ax1.set_title("Harmonic Identity Evolution")
    ax1.legend(fontsize=8)

    # Recovery ratio
    recovery_ratios = [r["recovery_ratio"] for r in all_results]
    ax2.hist(recovery_ratios, bins=10, color="#4CAF50", alpha=0.7, edgecolor="white")
    ax2.axvline(
        np.mean(recovery_ratios),
        color="red",
        linestyle="--",
        label=f"Mean={np.mean(recovery_ratios):.2f}",
    )
    ax2.set_xlabel("Recovery Ratio")
    ax2.set_ylabel("Count")
    ax2.set_title("Identity Recovery After Perturbation")
    ax2.legend()

    # Perturbation vs recovery scatter
    drifts = [r["perturbation_drift"] for r in all_results]
    recoveries = [r["recovery_distance"] for r in all_results]
    ax3.scatter(drifts, recoveries, color="#FF5722", s=60, alpha=0.7)
    max_val = max(max(drifts), max(recoveries)) * 1.1
    ax3.plot([0, max_val], [0, max_val], "k--", alpha=0.3, label="No recovery")
    ax3.set_xlabel("Perturbation Drift")
    ax3.set_ylabel("Final Distance from Pre-perturbation")
    ax3.set_title("Restoring Force Effectiveness")
    ax3.legend()

    plt.tight_layout()
    save_figure(fig, "fig08_harmonic_identity")
    plt.close(fig)


if __name__ == "__main__":
    main()
