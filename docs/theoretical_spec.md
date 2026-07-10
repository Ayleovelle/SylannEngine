> **Note**: This document describes the theoretical computation standard (axioms, algebra, conformance levels). For the SDK API specification (method signatures, Surface schema), see [SPEC.md](../SPEC.md). For the integration guide, see [AGENT_GUIDE.md](../AGENT_GUIDE.md).

# Sylanne Affective Computation Standard — Draft Specification v0.2

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
| **neuroticism** | dissipation rate, void detection | High → more sensitive, emotions linger longer |
| **openness** | Hebbian learning rate (PEL-Core, opt-in), residual decay | High → faster learning, stronger inter-module influence |
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
Frozen as of v2.5 — it is kept as the Level-0 baseline and receives correctness
fixes only; new engine features land in the Resonance Field path, not here.

#### Resonance Field (v2, `ResonanceSpine`)
```
All 7 modules inject → Resonance Field (single deterministic mean-field coherence pass) → Expression emerges
```
Adaptive, self-organizing over successive ticks. Suitable for rich affective interaction.

Key properties of the resonance model:
- **42 directed coupling channels** (`n_modules × (n_modules - 1)` with `n_modules = 7`, fixed across all tiers) — tier differences show up in per-module vector width (emotion/stalk/d_model dims: 8/16/128 for lite/pro/max), not in channel count
- **Use-dependent plasticity**: opt-in via PEL-Core (three-factor Hebbian + BCM, default off); the always-on fusion core itself performs a single deterministic mean-field coherence pass with no channel-level learning
- **Single-pass convergence**: modules combine into a mean-field resonance state (not an iterative multi-round settling loop)
- **Expression as bifurcation**: expression fires when the system escapes an attractor
- **Harmonic identity**: topological invariants persist across perturbations (the "soul")

#### On Kuramoto (retired)

Prior to v2.5, the resonance field ran an iterative six-mechanism core (Kuramoto
phase coupling + Hopfield attractor dynamics + active-inference free-energy
minimization + harmonic identity + echo-state reservoir + simplicial
higher-order coupling), settling to convergence over repeated rounds per tick.
Benchmarking showed the default (lite) tier phase-locked to an input-insensitive
fixed point with no objective function driving it (steady-state sync
0.9991±0.0001, 0% convergence variance) — the iteration bought no behavior it
could be held accountable for, so the whole loop, including the Kuramoto phase
model, was deleted. The current fusion core (`deterministic_fusion.py`) is a
**single-pass deterministic mean-field coherence computation**, not an
iterative synchronization process. Its `sync_order` output is a mean-field
coherence proxy in `[0, 1]` — how aligned each module's state is to the
population mean — carried over in name and shape from the old Kuramoto order
parameter for interface compatibility, but it is no longer a phase order
parameter over oscillator phases; there is no phase variable left in the
system.

#### On Φ / integrated information (approximation, not IIT)

`EmergenceTracker.phi` (`sylanne_core/compute/emergence.py`) reports a value
called `phi` as an emergence diagnostic. This is **not** a computation of
Integrated Information Theory's Φ — full IIT Φ requires an intractable search
over system bipartitions and is NP-hard for anything but toy systems. What is
actually computed is a two-component heuristic: spatial correlation across
module-state pairs, combined with a temporal-coherence term (whole-system
prediction error vs. sum of independently-modeled parts), combined via
`sqrt(spatial * (spatial + temporal / 2))`. It is inspired by IIT's
"integration beyond the sum of parts" intuition but makes no partition-search
claim and should not be read as a legitimate Φ estimate in the IIT sense —
treat it as a bounded emergence/coherence indicator, not an IIT citation.

### 11.2 Choosing a Computation Model

| Criterion | Sequential (v1) | Resonance (v2) |
|-----------|----------------|----------------|
| Determinism | Bit-exact | Bit-exact (single deterministic pass, no iteration) |
| Latency | O(1) per layer | O(1) per resonance (one coherence pass) |
| Emergent behavior | None | Cross-tick attractor dynamics, phase-transition expression |
| Memory | Stateless between calls | Attractor landscape + reservoir |
| Personality expression | Parameter-driven | Topology-driven (harmonic identity) |
| Best for | Embedded, real-time, testing | Rich dialogue, long-term interaction |

Performance tiers map to both models. Coupling channel count is fixed at 42
(`n_modules × (n_modules - 1)`, `n_modules = 7`) across all tiers; what scales
per tier is per-module vector width and backend:
- `lite` mode: 42 channels, 8-dim vectors, pure Python, ≥5 concurrent sessions
- `pro` mode: 42 channels, 16-dim vectors, numpy, ≥15 concurrent sessions
- `max` mode: 42 channels, 128-dim vectors, numpy, ≥30 concurrent sessions

### 11.3 Platform Requirements and Performance

All tiers run on CPU. A GPU/torch execution path was explored but removed in
v2.5 (no tier requires or benefits from a GPU). `force_backend` is accepted and
validated, and is written into `DimensionProfile.backend`, but that field has
no reader anywhere in the current engine wiring (the HGT module's numpy-
acceleration flag is hardcoded from a local `_HAS_NUMPY` check, not read from
the profile) — so the parameter has no observable effect on computation today.
The parameter position is kept because downstream plugins pass
`force_backend="python"` explicitly at construction time.

| Tier | Latency (p50) | Min Platform | Typical Deployment |
|------|---------------|--------------|-------------------|
| lite | ~5ms | Any CPU, 64MB RAM | Raspberry Pi, mobile, serverless |
| pro | ~40ms | 2 cores, 256MB, numpy | Desktop, cloud VM |
| max | ~50ms | 4 cores, 1GB+, numpy | Research, multi-agent simulation |

**Throughput:** lite ~200 msg/s, pro ~25 msg/s, max ~20 msg/s.

**Memory per session:** lite ~8KB, pro ~25KB, max ~60KB.

**Choosing a tier:**
- If your latency budget is ≥5ms and you want minimal dependencies → `lite`
- If you want richer per-module state and have numpy → `pro`
- If you need the largest per-module vector width for research-scale multi-agent sessions → `max`
- If you need <5ms deterministic and don't need the resonance model at all → use `ComputationSpine` (sequential, ~1ms)

## 12. Versioning and Stability

- Operator semantics are version-pinned (like ONNX opsets)
- Once an axiom is published, it is never weakened (Unicode stability guarantee)
- New axioms may be added in minor versions but never remove existing guarantees
- Breaking changes require a new major version with explicit migration path

**Changelog**: v0.1 → v0.2 adds §13 (Affect-Dynamics E-Law — axioms AD1–AD8,
normative operators, AD-L1/L2/L3 conformance with golden reference vectors, and
the PEL-Core interaction/retirement position). No existing axiom or level was
changed.

## 13. Affect-Dynamics E-Law (opt-in Level 1 extension)

Normative specification of the dual-speed affect dynamics ("E-law", design
codename v26) implemented by the reference engine on its 8-dim emotion core.
The full derivation with proofs lives in
[docs/design/affect-dynamics-derivation.md](design/affect-dynamics-derivation.md)
(theorem/proof-grade internal draft, cleared an independent math red-team);
this chapter states the **normative contract** an implementation must satisfy.
All of §13 is **opt-in**: three configuration flags, all default **off**; with
all flags off, behavior and persisted state are byte-identical to a pre-§13
implementation (verified against the reference implementation with seeded
RNG — note the verification methodology REQUIRES seeding the global `random`
module in addition to `PYTHONHASHSEED=0`, or unrelated exploration noise
dominates any comparison).

### 13.1 Gates

| Flag | Gate | Contract |
|---|---|---|
| `affect_dynamics_enabled` | A (shadow) | E-law computes a parallel shadow E for diagnostics only. MUST NOT write the authoritative state, MUST NOT reach the prompt/output contract, MUST keep observable behavior byte-identical. |
| `affect_takeover` | B (authority) | E-law owns inter-turn wall-clock decay of the authoritative E (applied BEFORE event evolution — settle-then-evolve) and the per-turn semantic appraisal update (replacing legacy hand-rules). Requires Gate A. MUST fail closed to the legacy path on any E-law error within a turn. Mutually exclusive with PEL-Core (§13.5). |
| `affect_plasticity_enabled` | B+ (learning) | Per-dim gains G become learned state via delta-rule with projection (AD8). Requires Gate B. Learned state persists; the lagged quality feedback MUST be consumed before the current turn's own activity updates the eligibility trace. |

### 13.2 Axioms (AD1–AD8)

A conforming E-law implementation MUST satisfy (unit frame `u in [0,1]^8` with
an affine adapter to the native storage frame; dim order = the reference
`_DIM_NAMES`):

- **AD1 (Bounded state)** Every E-law operator maps the invariant set K=[0,1]^8
  (native [-1,1]^8) into itself, for any finite composition in any order.
  Boundary contracts MUST be code-enforced at restore/entry points (a bare
  convex combination does not self-heal out-of-range input). [Thm 4]
- **AD2 (Saturating semantics)** The appraisal update uses multiplicative
  headroom factors: positive increments scale by (1-u), negative by u; the
  increment vanishes at the boundaries. The boundary is reached in one step iff
  G·|a| = 1; otherwise approach is asymptotic. [Thm 1]
- **AD3 (Wall-clock decay)** Between turns, E decays toward a personality-and-
  relationship equilibrium Phi_eq with per-dim half-lives; the decay is the
  exact flow of a linear ODE — contraction, no overshoot, order-preserving.
  Phi_eq MUST be clamped into an interior band (reference: [0.15, 0.85]) so no
  equilibrium sits on a corner. [Thm 2]
- **AD4 (Scar-coupled stickiness, capped)** Wound history may slow per-dim
  decay by a multiplicative stickiness factor that MUST be capped (reference:
  x3) and MUST self-heal as wounds fade — the decay rate has a strictly
  positive floor for any wound history ("never freezes"). Trait inputs to the
  half-life map MUST be domain-clamped at the E-law boundary. [Thm 3]
- **AD5 (Fail-closed semantics)** Any error inside an E-law step MUST leave the
  authoritative state driven by the legacy path for that turn — never a stale
  or partial E-law write.
- **AD6 (Slow-channel bounded drift)** Personality macro-drift, if implemented,
  MUST keep traits inside an invariant ball around an immutable anchor and be
  non-increasing outside it, for ANY quality-gate sequence in [0,1]. Reversion
  toward the anchor MAY be quality-gated (the reference gates BOTH the push and
  the reversion term — reversion stalls under sustained zero quality; this is a
  disclosed semantic, not a defect). [Thm 5]
- **AD7 (Hysteretic labeling)** Any categorical label derived from E MUST use a
  deadband: reversing a label change requires crossing the quantization
  boundary by a margin theta_h. The anti-chatter turn bound is a calibration-
  regime guarantee, not an unconditional one (a maximal silence-decay plus a
  maximal opposite appraisal CAN reverse in consecutive turns — by design; real
  extreme events should switch immediately). [Prop 7]
- **AD8 (Projection-invariant plasticity)** Learned gains MUST pass through a
  projection onto [eps,1] (eps>0) on every update. Safety is carried entirely
  by the projection: Thm 1–4 hold verbatim for ANY projected gain sequence, so
  no learning signal — wrong, noisy, or adversarial — can break AD1–AD4.
  [Lemma 6; this is an invariance audit, not a control-theoretic separation
  theorem — see the derivation's demotion note]

### 13.3 Normative Operators

| Operator | Contract | Anchor |
|---|---|---|
| `equilibrium(T, R)` | Phi_eq in [0.15,0.85]^8; monotone in the documented trait directions | AD3 / Thm 2 |
| `half_lives(T, scarload)` | h_i = h_base·g_i(T)·min(1+sigma·L_i, S_bar); g bounded via trait clamp | AD4 / Thm 3 |
| `decay(u0, u_eq, h, dt)` | exact exponential flow; dt<=0/NaN => identity; NO internal clamp (caller enforces AD1 at entry) | AD3 / Thm 2 |
| `saturating_update(u, a, G)` | AD2 semantics; NOT affine-equivariant — native-frame callers MUST round-trip through the unit frame | AD2 / Note 1.2 |
| `project_appraisal(v, a, w, intent)` | 3 scalars + intent class -> a in [-1,1]^8; non-finite inputs sanitized | design §3.1 |
| `plasticity_step(G, q, q_hat, phi)` | G' = Proj_[eps,1](G + alpha·delta·phi); bounded under adversarial q | AD8 / Lemma 6 |
| `eligibility_update(phi, a)` | phi' = clamp01(gamma·phi + abs(a)); credit only to recently-active dims | Note 6.2 |
| `contagion_blend(u, m, kappa)` | convex, defensively clamped; kappa derived as a personality function, never a flat config scalar | derivation §8 |

### 13.4 Conformance (AD-L1 / AD-L2 / AD-L3)

> AD-L1/L2/L3 are an **independent axis** from the §6 Level 0/1/2 conformance
> ladder — "AD-L1" means golden-vector pure-function equivalence, not "standard
> Level 1". §13 as a whole is an opt-in extension adjacent to Level 1; it is
> not required for any §6 Level.

- **AD-L1 — pure-function equivalence (MUST for any §13 implementation)**:
  reproduce the golden reference vectors below to within 1e-9 per component.
- **AD-L2 — dynamics equivalence (SHOULD)**: given the same event/appraisal/
  wall-clock sequence, the authoritative E trajectory under Gate B matches the
  reference to within 1e-6 per component over 100 turns.
- **AD-L3 — full-pipeline gating (MUST for the reference engine lineage)**:
  all-flags-off is byte-identical (behavior AND persisted snapshots) to the
  pre-§13 baseline; each gate's contract in §13.1 holds under its flag.

Golden reference vectors (traits T* = {warmth_bias .6, perception_acuity .7,
curiosity .7, expression_drive_trait .6, relational_gravity .7,
sovereignty_guard .8, inner_order .6}; locked by
`tests/test_conformance_vectors.py`):

```
equilibrium(T*, 0.5) = [0.52, 0.40, 0.55, 0.35, 0.50, 0.28, 0.48, 0.52]
equilibrium(T*, 0.9) = [0.64, 0.40, 0.55, 0.35, 0.50, 0.28, 0.48, 0.52]
half_lives(T*, zeros) = [5400, 1800, 3600, 3780, 2400, 3000, 1500, 7200] (s)
half_lives(T*, twos)  = 3.0 x the above (sticky cap engaged)
gain_vector(T*)       = [0.50, 0.50, 0.50, 0.61, 0.50, 0.50, 0.58, 0.50]
decay(e0*, eq*, h*, 1800s) = [0.266015831685, 0.6, 0.55, 0.314056332564,
                              0.470269822125, 0.260207381338,
                              0.488705505633, 0.587271713220]
project_appraisal(0.6, 0.7, 0.2, "撒娇") = [0.54, 0.40, 0.60, -0.156,
                              0.084, 0.0, 0.38, 0.024]  (class "coax")
saturating_update(e0*, a*, G*) = [0.416, 0.84, 0.685, 0.271452,
                              0.4731, 0.25, 0.6102, 0.6048]
plasticity_step([0.5]^8, q=0.9, q_hat=0.5, phi*) = [0.5002, 0.5001, 0.5,
                              0.50005, 0.5002, 0.5, 0.50015, 0.50002]
  with e0* = [0.20, 0.80, 0.55, 0.30, 0.45, 0.25, 0.50, 0.60]
       phi* = [1.0, 0.5, 0.0, 0.25, 1.0, 0.0, 0.75, 0.1]
```

Constants (alpha=0.0005, gamma=0.6, beta=0.1, eps=0.05, sigma=1, S_bar=3,
h_base, Phi_eq coefficients) are **calibration priors** version-pinned with
this spec revision (§12 opset discipline): a conforming implementation matches
these vectors for THIS spec version; a future revision may re-pin them with a
changelog entry, never silently.

### 13.5 PEL-Core: Interaction and Retirement Position

PEL-Core (v2.5, `pel_core_enabled`, default off) and the E-law takeover BOTH
claim authority over the 8-dim core's base evolution. The standard's position:

1. **Mutual exclusion is normative**: `affect_takeover` + `pel_core_enabled`
   MUST be rejected at configuration time (the reference raises ValueError),
   and an implementation MUST additionally keep the E-law takeover inert if a
   PEL core is somehow active (belt at the state layer) — otherwise the PEL
   readout silently overwrites the E-law's decay every tick and the takeover
   contract is false while appearing enabled.
2. **Honest status**: PEL remains an opt-in experiment. Its production-liveness
   witnesses (precision spread, anchor drift) ship in diagnostics; it has NOT
   cleared a behavioral-calibration gate, and the known structural finding that
   the legacy MLP main-step image (not Phi_eq, not PEL mu) dominates the
   observed resting mood applies to the hybrid wiring as a whole (see
   docs/design/affect-calibration-memo.md, D1).
3. **Retirement path**: if the E-law full-takeover slice (memo D1 option b —
   silence ticks become decay-only and event semantics enter via projection
   instead of the MLP) is adopted and clears its own shadow-parity + red-team
   gates, PEL-Core retires in the following minor version: the flag remains
   accepted-and-ignored for one deprecation cycle (config warning), snapshot
   "pel" sub-keys are ignored on restore (already migration-safe), and the
   module is deleted the version after. Retreat MUST be announced in the
   changelog — silence is not a retirement mechanism (the failure mode this
   clause exists to prevent).
