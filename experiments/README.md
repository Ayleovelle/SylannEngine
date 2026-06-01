# SylannEngine v2 Experiments

Experimental validation of the resonance field architecture claims.

## Requirements

```bash
pip install numpy matplotlib scipy
```

## Running

```bash
# All experiments (takes ~30-60 minutes)
python run_all.py

# Specific experiments by number
python run_all.py 1 3 5

# Individual experiment
python exp01_convergence.py
```

## Experiments

| # | Name | Validates |
|---|------|-----------|
| 1 | Convergence | Tier-specific iteration bounds |
| 2 | Tier Comparison | Performance and dynamics differences |
| 3 | Plasticity | Hebbian LTP/LTD + homeostatic scaling |
| 4 | Kuramoto Sync | Explosive synchronization via higher-order coupling |
| 5 | Hopfield Attractor | Emotional memory + expression as escape |
| 6 | Expression Bifurcation | OR-gate: any single trigger suffices |
| 7 | Harmonic Identity | Restoring force preserves personality |
| 8 | Phi Emergence | Integrated information correlates with expression |
| 9 | Stability | 1500 ticks, no NaN/Inf, bounded energy |
| 10 | Personality Modulation | 7 dimensions fully determine dynamics |
| 11 | Tier Hot-Switch | Lossless state migration across tiers |

## Output

Figures are saved to `figures/` as both PDF (for LaTeX) and PNG (for preview).

## Parameters

- **Repeats:** 10 per experiment (configurable in `utils.py`)
- **Ticks:** 1000+ per run
- **Statistical tests:** Mann-Whitney U, Wilcoxon signed-rank (requires scipy)
