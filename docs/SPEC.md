# Sylanne Affective Computation Standard — Draft Specification v0.1

## 1. Purpose

Sylanne defines a **universal computation standard for affective state machines**. It specifies:
- A finite algebra of operations on bounded affective values
- Deterministic state transitions given identical inputs
- Layered conformance levels (Core / Standard / Extended)
- A serialization format for cross-platform interchange

Sylanne is to affective computing what IEEE 754 is to floating point: implementations may differ internally, but observable behavior is identical.

## 2. Design Principles (Lessons from Prior Standards)

| Principle | Source |
|-----------|--------|
| Deterministic algebra — same inputs produce same outputs everywhere | IEEE 754 |
| Stability guarantee — once defined, semantics never change | Unicode |
| Separate representation from interpretation | MIDI |
| Falsifiable conformance via test suite | Vulkan/OpenGL |
| Extensible operator sets without breaking existing consumers | ONNX |
| Define operations, not just labels (anti-EmotionML) | W3C EmotionML failure |
| No unverifiable mental-state semantics | FIPA ACL failure |

## 3. Core Axioms

Every conforming implementation MUST satisfy these axioms:

### A1. Boundedness
All affective values are bounded in their declared ranges. No operation produces out-of-range values.

```
∀t: state(t) ∈ [lower_bound, upper_bound]
```

### A2. Determinism
Given identical initial state and identical stimulus sequence, the output sequence is identical.

```
state₀ = state₀' ∧ stimulus_seq = stimulus_seq' → output_seq = output_seq'
```

### A3. Lipschitz Continuity (Bounded Delta)
No single stimulus can cause unbounded state change. There exists a constant L such that:

```
|state(t+1) - state(t)| ≤ L · |stimulus(t)|
```

### A4. Convergence (Lyapunov Stability)
Without external stimuli, the system converges to a stable attractor (resting state).

```
∀ε>0, ∃T: t>T ∧ no_stimulus_after(T) → |state(t) - attractor| < ε
```

### A5. Compositionality (Functorial)
Affective operations compose associatively. If F and G are valid state transformations:

```
(F ∘ G)(state) = F(G(state))
```

Third-party extensions that satisfy the functor laws inherit all system guarantees.

### A6. Irreversibility of Trauma (Scar Monotonicity)
Scars (permanent state modifications from significant events) are monotonically non-decreasing in count. Individual scar intensity may decay, but scars are never deleted.

```
|scars(t+1)| ≥ |scars(t)|
```

### A7. Personality-Computation Coupling (Bidirectional Functor)
Personality parameters modulate computation, AND computation results feed back to personality drift. This bidirectional coupling is the core identity of the system.

```
computation = F(personality, stimulus)
personality' = G(personality, computation)
```

#### Personality → Computation Mapping (v2 Resonance Field)

Every tunable parameter in the resonance field derives from personality traits:

| Trait | Controls | Effect |
|-------|----------|--------|
| **extraversion** | expression threshold, Hopfield pull strength | High → speaks easily, stronger habitual patterns |
| **neuroticism** | free energy precision, dissipation rate, void detection | High → more sensitive, emotions linger longer |
| **openness** | Kuramoto coupling (K₁,K₂,K₃), Hebbian learning rate, residual decay | High → faster learning, stronger inter-module influence |
| **conscientiousness** | Hebbian decay rate, identity inertia | High → stable connections, consistent personality |
| **agreeableness** | broadcast threshold | High → easier global ignition (more responsive) |
| **patience** | max attractors, silence urgency | High → richer emotional memory, slower pressure buildup |
| **sovereignty_guard** | identity norm cap, boundary phase threshold | High → stronger sense of self, harder to perturb |

This mapping ensures that personality is not a label but a **structural parameter** that shapes the topology of the computation itself.

## 4. Mathematical Foundation

### Primary: Category Theory
- **Functors** map between personality space and computation space, preserving structure
- **Natural transformations** formalize drift as morphisms between functors
- **Adjunctions** capture perception-action as free/forgetful pairs
- Third-party extensions are new functors; if they satisfy the laws, guarantees propagate

### Secondary: Dynamical Systems Theory
- **Lyapunov functions** prove personality doesn't diverge (Axiom A4)
- **Attractors** formalize resting states with semantic meaning
- **Bifurcation theory** handles phase transitions (calm → agitated)
- Immediately implementable — every language has ODE solvers

### Derived: Sheaf Theory (from L4)
The sheaf condition (local consistency implies global consistency) is a special case of categorical limits plus Lyapunov boundedness on each local patch.

## 5. Data Model

### 5.1 Stimulus (Input)

```
struct Stimulus {
    valence: f32          // [-1.0, 1.0] — negative to positive
    arousal: f32          // [0.0, 1.0] — calm to activated
    dominance: f32        // [0.0, 1.0] — submissive to dominant
    magnitude: f32        // [0.0, 1.0] — event significance
    timestamp: u64        // monotonic, milliseconds
    tag: optional<string> // opaque label for downstream use
}
```

### 5.2 EmotionState (Output)

```
struct EmotionState {
    primary: EmotionVector    // current dominant state
    mood: EmotionVector       // slow-moving baseline
    delta: EmotionVector      // change from previous state
    confidence: f32           // [0.0, 1.0]
    epoch: u64                // state version counter
}

struct EmotionVector {
    valence: f32     // [-1.0, 1.0]
    arousal: f32     // [0.0, 1.0]
    dominance: f32   // [0.0, 1.0]
}
```

### 5.3 Personality (Configuration)

```
struct Personality {
    traits: map<string, f32>  // all values in [0.0, 1.0]
    // Minimum required traits for Layer 0 conformance:
    // openness, warmth, assertiveness, stability, sensitivity
}
```

### 5.4 Scar (Persistent State)

```
struct Scar {
    dimension: u32            // which affective dimension is affected
    intensity: f32            // [0.0, 1.0], may decay but never deleted
    created_at: u64           // timestamp of formation
    source_tag: string        // what caused it
}
```

## 6. Conformance Levels

### Level 0 — Core (MUST implement)

| Requirement | Description |
|-------------|-------------|
| `init(config) → Instance` | Create a new affective state machine |
| `process(instance, stimulus) → EmotionState` | The single mandatory operation |
| `reset(instance)` | Return to initial state |
| Axioms A1-A4 | Boundedness, determinism, Lipschitz, convergence |
| O(1) memory | No unbounded history accumulation |
| Embeddable | No heap allocation after init, no clock dependency |

**Left unspecified at Level 0:**
- Internal state representation (SCAR, neural, lookup table — all valid)
- How valence/arousal/dominance interact to produce transitions
- Interpolation curves between states
- Serialization format
- Threading model

### Level 1 — Standard (SHOULD implement)

Adds to Level 0:
- Personality configuration (trait vector modulates computation)
- Text-to-stimulus bridge (NLP → PAD mapping)
- State serialization/deserialization (JSON format)
- Emotion label mapping (categorical from dimensional)
- Event history with configurable window
- Mood drift parameters
- Axioms A5-A7 (compositionality, irreversibility, bidirectional coupling)

### Level 2 — Extended (MAY implement)

Adds to Level 1:
- GPU-batched multi-agent processing (`process_batch`)
- Emotional contagion graphs (multi-agent influence)
- Expression mapping profiles (blend shapes, motor commands)
- Real-time constraints with deadline specification
- Hot-pool kernel scheduling (thermodynamic accumulation)
- Longitudinal analytics and audit logging
- Phase transition expression triggers
- Multi-round attention fusion

## 7. Algebraic Operations

The standard defines these operations on affective values:

| Operation | Signature | Semantics |
|-----------|-----------|-----------|
| `blend(a, b, α)` | `(EV, EV, f32) → EV` | Linear interpolation, α ∈ [0,1] |
| `decay(a, rate, dt)` | `(EV, f32, f32) → EV` | Exponential decay toward attractor |
| `project(a, dim)` | `(EV, Dim) → f32` | Extract single dimension |
| `threshold(a, t)` | `(EV, f32) → bool` | Magnitude exceeds threshold |
| `normalize(a)` | `(EV) → EV` | Clamp to valid range (idempotent) |
| `distance(a, b)` | `(EV, EV) → f32` | Fisher metric on affective manifold |
| `drift(p, computation)` | `(Personality, Computation) → Personality` | Bidirectional feedback |

Properties that MUST hold:
- `blend` is commutative: `blend(a, b, 0.5) = blend(b, a, 0.5)`
- `normalize` is idempotent: `normalize(normalize(x)) = normalize(x)`
- `decay` converges: `lim(t→∞) decay(a, rate, t) = attractor`
- `distance` satisfies triangle inequality

## 8. Serialization Format

Conforming implementations at Level 1+ MUST support JSON interchange:

```json
{
  "sylanne_version": "1.0",
  "schema_version": 1,
  "session_key": "string",
  "personality": {"openness": 0.7, "warmth": 0.8, ...},
  "state": {
    "primary": {"valence": 0.3, "arousal": 0.5, "dominance": 0.4},
    "mood": {"valence": 0.1, "arousal": 0.3, "dominance": 0.5},
    "epoch": 142
  },
  "scars": [...],
  "metadata": {}
}
```

## 9. Influence Protocol (Level 2)

External systems inject influences into the affective state machine:

```
struct Influence {
    source: string            // identifier of the influence source
    type: enum {              // semantic category
        ENVIRONMENTAL,        // ambient context change
        SOCIAL,               // from another agent
        PHYSIOLOGICAL,        // embodiment signal
        COGNITIVE,            // internal reappraisal
        EXTERNAL              // plugin/API injection
    }
    intensity: f32            // [0.0, 1.0]
    target_dimension: string  // optional: which dimension to affect
    payload: map<string, any> // opaque extension data
}
```

## 10. Compliance Testing

A conformance test suite verifies:
1. **Boundedness**: Fuzz all inputs, verify outputs never exceed declared ranges
2. **Determinism**: Replay identical stimulus sequences, verify bit-identical outputs
3. **Convergence**: After stimulus removal, verify state approaches attractor within T ticks
4. **Lipschitz**: Verify no single stimulus causes delta > L * magnitude
5. **Scar monotonicity**: Verify scar count never decreases
6. **Normalize idempotency**: Verify double-normalize equals single-normalize
7. **Blend commutativity**: Verify blend(a,b,0.5) = blend(b,a,0.5)

## 11. Reference Implementation

The SylannEngine SDK (`sylanne_core`) is the reference implementation:
- **Level 0**: `ComputationSpine.process()` — sequential 7-layer pipeline (legacy)
- **Level 0 (v2)**: `ResonanceSpine.process()` — simplicial resonance field (recommended)
- **Level 1**: `AlphaKernel` with personality, persistence, text bridge
- **Level 2**: `SylanneAlphaHost` with hot pool, multi-round attention, phase transitions

### 11.1 Computation Models

Sylanne supports two computation models. Both satisfy all axioms (A1-A7).

#### Sequential Pipeline (v1, `ComputationSpine`)
```
L1(HDC) → L2(Gate) → L3(VoidScar) → L4(Sheaf) → L5(HGT) → L6(Boundary) → L7(Expression)
```
Deterministic, predictable, easy to debug. Suitable for constrained environments.

#### Resonance Field (v2, `ResonanceSpine`)
```
All 7 modules inject → Resonance Field (iterative convergence) → Expression emerges
```
Emergent, adaptive, self-organizing. Suitable for rich affective interaction.

Key properties of the resonance model:
- **42 directed coupling channels** (lite) / **287** (pro) / **441** (max)
- **Use-dependent plasticity**: channels strengthen with use, atrophy without (Hebb 1949)
- **Iterative convergence**: modules resonate until field stabilizes
- **Expression as bifurcation**: expression fires when the system escapes an attractor
- **Harmonic identity**: topological invariants persist across perturbations (the "soul")

### 11.2 Choosing a Computation Model

| Criterion | Sequential (v1) | Resonance (v2) |
|-----------|----------------|----------------|
| Determinism | Bit-exact | Convergent (within ε) |
| Latency | O(1) per layer | O(max_iter) per resonance |
| Emergent behavior | None | Synchronization, phase transitions |
| Memory | Stateless between calls | Attractor landscape + reservoir |
| Personality expression | Parameter-driven | Topology-driven (harmonic identity) |
| Best for | Embedded, real-time, testing | Rich dialogue, long-term interaction |

Performance tiers map to both models:
- `lite` mode: 42 channels, pure Python, ≥5 concurrent plugins
- `pro` mode: 287 channels, numpy, ≥15 concurrent plugins
- `max` mode: 441 channels, GPU/torch, ≥30 concurrent plugins

### 11.3 Platform Requirements and Performance

| Tier | Latency (p50) | Min Platform | Typical Deployment |
|------|---------------|--------------|-------------------|
| lite | ~5ms | Any CPU, 64MB RAM | Raspberry Pi, mobile, serverless, AstrBot default |
| pro | ~40ms | 2 cores, 256MB, numpy | Desktop, cloud VM, AstrBot pro |
| max | ~50ms CPU / <5ms GPU | 4 cores or GPU, 1GB+ | Research, multi-agent simulation |

**Throughput:** lite ~200 msg/s, pro ~25 msg/s, max(GPU) ~200+ msg/s batched.

**Memory per session:** lite ~8KB, pro ~25KB, max ~60KB.

**Choosing a tier:**
- If your latency budget is ≥5ms and you want minimal dependencies → `lite`
- If you want emergent multi-body dynamics and have numpy → `pro`
- If you need full simplicial topology or GPU batching → `max`
- If you need <5ms deterministic → use `ComputationSpine` (sequential, ~1ms)

## 12. Versioning and Stability

- Operator semantics are version-pinned (like ONNX opsets)
- Once an axiom is published, it is never weakened (Unicode stability guarantee)
- New axioms may be added in minor versions but never remove existing guarantees
- Breaking changes require a new major version with explicit migration path
