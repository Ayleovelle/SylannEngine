> ⚠️ **Historical document**: This describes the iterative resonance field
> architecture (six mechanisms: Kuramoto phase coupling, Hopfield attractors,
> free-energy minimization, harmonic identity, echo-state reservoir, simplicial
> higher-order coupling) and the GPU/torch path for the `max` tier, both
> removed prior to v2.5 (commit `29b402a`). It is kept for historical reference
> only and does not describe the current engine. For the current architecture,
> see [theoretical_spec.md](theoretical_spec.md) and [SPEC.md](../SPEC.md).

```mermaid
---
title: "SylannEngine MAX Tier — Resonance Field Computation Flow"
---
flowchart TB
    %% Input
    INPUT["📥 Input Text + Timestamp + Assessment"]

    %% Module Computation (Parallel)
    subgraph MODULES["Phase 1: Module Injection (Parallel)"]
        direction LR
        M0["M0: HDC Encoder<br/>text → 2048-bit hypervector<br/>→ compress to 32-dim"]
        M1["M1: Predictive Coding<br/>surprise = gate.surprise(h)<br/>→ 32-dim gate signal"]
        M2["M2: VoidScar Engine<br/>emotion state evolution<br/>→ 32-dim emotion vector"]
        M3["M3: Relational Sheaf<br/>cross-relational propagation<br/>→ 32-dim sheaf signal"]
        M4["M4: HGT Decision<br/>multi-head attention fusion<br/>→ 32-dim decision vector"]
        M5["M5: Autopoietic Boundary<br/>perturb + self-repair<br/>→ 32-dim boundary signal"]
        M6["M6: Phase Transition<br/>expression drive<br/>→ 32-dim expression signal"]
    end

    %% Resonance Field
    subgraph FIELD["Phase 2: Resonance Field (Iterative, max 20 iterations)"]
        direction TB
        
        subgraph TOPOLOGY["Simplicial Complex Δ⁶ — 441 Directed Channels"]
            direction LR
            T1["1-simplices<br/>42 pairwise"]
            T2["2-simplices<br/>105 three-body"]
            T3["3-simplices<br/>140 four-body"]
            T4["4-simplices<br/>105 five-body"]
            T5["5-simplices<br/>42 six-body"]
            T6["6-simplex<br/>7 global"]
        end

        subgraph ITERATION["Per-Iteration Pipeline"]
            direction TB
            S1["1. Coupling Dynamics Step<br/>Hebbian plasticity update (441 weights)<br/>Higher-order Kuramoto sync (K₁+K₂+K₃)<br/>Free energy minimization"]
            S2["2. Signal Propagation<br/>Pairwise: w_ij · cos(θ_i-θ_j) · x_j<br/>Higher-order: γ · w_σ · Π tanh(x̄_src) · avg(x_src)"]
            S3["3. Hopfield Attractor Pull<br/>E = -½ Σ(X·ξ_μ)²<br/>Pull toward stored patterns (≤20)"]
            S4["4. Harmonic Identity Restoring<br/>Δx += 0.03 · (h_identity - x)<br/>Soul resists perturbation"]
            S5["5. Reservoir Memory Injection<br/>Δx += 0.05 · r[i mod 64]<br/>Temporal context from past"]
            S6["6. Global Broadcast (GWT)<br/>Winner-take-all competition<br/>Winning module broadcasts to all"]
            S7["7. Activation + Dissipation<br/>x = tanh(x) · 0.98<br/>Bounded + energy loss"]
            S8{"Converged?<br/>max|Δx| < ε"}
        end

        S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8
        S8 -->|No, iter < 20| S1
        S8 -->|Yes or iter = 20| POST
    end

    %% Post-resonance
    subgraph POST["Phase 3: Post-Resonance"]
        direction TB
        P1["Update Harmonic Identity<br/>h_id = 0.95·h_id + 0.05·harmonics<br/>(norm capped at 32)"]
        P2["Store Attractor (if novel)<br/>Normalize + store if dist > 0.15"]
        P3["Emergence Tracking<br/>Φ (integration) + χ (criticality)<br/>+ attractor basin + temporal narrative"]
    end

    %% Expression Decision
    subgraph EXPR["Phase 4: Expression Bifurcation (OR-gate)"]
        direction TB
        E1["Trigger 1: Surprise<br/>1.5 × surprise"]
        E2["Trigger 2: Novelty<br/>attractor_distance × 3"]
        E3["Trigger 3: Ignition<br/>Δ(sync_order) × 5"]
        E4["Trigger 4: Raw Drive<br/>(|M6| - avg) × 2"]
        EMAX["drive = max(T1,T2,T3,T4)<br/>× meaning_gate(Φ)"]
        EVETO["HGT Inhibition<br/>d[3] > 0.75 → ×0.2"]
        EDECISION{"drive > threshold?"}
        EXPRESS["✅ EXPRESS"]
        HOLD["⏸️ HOLD"]
    end

    %% Feedback
    subgraph FEEDBACK["Feedback Loop (on response outcome)"]
        direction LR
        F1["accepted → Hebbian boost (all channels +0.3)"]
        F2["rejected → Hebbian suppress (all channels 0.0)"]
        F3["ignored → Hebbian minimal (all channels +0.05)"]
    end

    %% Connections
    INPUT --> MODULES
    M0 & M1 & M2 & M3 & M4 & M5 & M6 --> FIELD
    TOPOLOGY -.->|"shapes"| ITERATION
    POST --> EXPR
    E1 & E2 & E3 & E4 --> EMAX --> EVETO --> EDECISION
    EDECISION -->|Yes| EXPRESS
    EDECISION -->|No| HOLD
    EXPRESS --> FEEDBACK
    FEEDBACK -.->|"modulates plasticity"| TOPOLOGY

    %% Styling
    classDef module fill:#1a1a2e,stroke:#16213e,color:#e94560
    classDef field fill:#0f3460,stroke:#533483,color:#e94560
    classDef expr fill:#1a1a2e,stroke:#e94560,color:#fff
    class M0,M1,M2,M3,M4,M5,M6 module
    class S1,S2,S3,S4,S5,S6,S7 field
    class E1,E2,E3,E4,EMAX expr
```

---

## Timing Breakdown (MAX tier, single `process()` call)

```
Phase 1: Module Injection     ~5ms   (7 modules compute in sequence)
Phase 2: Resonance Field     ~40ms   (20 iterations × 441 channels)
  ├─ Coupling dynamics        ~15ms   (Hebbian + Kuramoto + FreeEnergy)
  ├─ Pairwise propagation     ~10ms   (42 channels × 32 dims)
  ├─ Higher-order propagation  ~12ms   (399 channels, AND-gate products)
  ├─ Hopfield + Identity + Reservoir ~2ms
  └─ Activation + convergence  ~1ms
Phase 3: Post-resonance       ~3ms   (harmonics + attractor + emergence)
Phase 4: Expression decision   ~1ms   (OR-gate + threshold)
─────────────────────────────────────
Total                         ~50ms   (CPU, pure Python)
                               <5ms   (GPU, torch batched)
```

## Data Flow Summary

```
Text ──→ [7 Modules] ──inject──→ [Resonance Field: 224-dim state]
                                         │
                                    ┌────┴────┐
                                    │ 20 iter │ ← 441 channels × Hebbian weights
                                    │ converge│ ← Kuramoto phase sync
                                    │         │ ← Hopfield attractors (≤20)
                                    │         │ ← Harmonic identity (soul)
                                    │         │ ← Echo reservoir (memory)
                                    └────┬────┘
                                         │
                              ┌──────────┼──────────┐
                              ▼          ▼          ▼
                         Expression   Emergence   Plasticity
                         (bifurcation) (Φ, χ)    (use→strengthen)
```
