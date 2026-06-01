"""Run all SylannEngine v2 experiments and generate figures.

Usage:
    python run_all.py          # run all experiments
    python run_all.py 1 3 5    # run specific experiments by number
"""

from __future__ import annotations

import importlib
import sys
import time

EXPERIMENTS = [
    "exp01_convergence",
    "exp02_tier_comparison",
    "exp03_plasticity",
    "exp04_kuramoto_sync",
    "exp05_hopfield_attractor",
    "exp06_expression_bifurcation",
    "exp07_harmonic_identity",
    "exp08_phi_emergence",
    "exp09_stability",
    "exp10_personality_modulation",
    "exp11_tier_hotswitch",
]


def main():
    if len(sys.argv) > 1:
        indices = [int(x) - 1 for x in sys.argv[1:]]
        selected = [EXPERIMENTS[i] for i in indices if 0 <= i < len(EXPERIMENTS)]
    else:
        selected = EXPERIMENTS

    print(f"Running {len(selected)} experiments...\n")
    total_start = time.time()

    for name in selected:
        print(f"{'=' * 60}")
        print(f"  {name}")
        print(f"{'=' * 60}")
        start = time.time()
        try:
            mod = importlib.import_module(name)
            mod.main()
            elapsed = time.time() - start
            print(f"  DONE in {elapsed:.1f}s\n")
        except Exception as e:
            elapsed = time.time() - start
            print(f"  FAILED after {elapsed:.1f}s: {e}\n")
            import traceback
            traceback.print_exc()

    total = time.time() - total_start
    print(f"\nAll experiments completed in {total:.1f}s")
    print(f"Figures saved to: experiments/figures/")


if __name__ == "__main__":
    main()
