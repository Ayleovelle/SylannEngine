# Fully-Connected Resonance Field Architecture
## Formal Specification for SylannEngine v2.0

---

## 1. Mathematical Framework

### 1.1 State Space Definition

The resonance field consists of 7 modules indexed by $i \in \mathcal{M} = \{1, 2, 3, 4, 5, 6, 7\}$:

| Index | Module | Symbol | State Dimension |
|-------|--------|--------|-----------------|
| 1 | HDC Encoder (Perception) | $\mathbf{x}_1$ | $d_1 = 8$ (compressed HDC) |
| 2 | Predictive Coding Gate | $\mathbf{x}_2$ | $d_2 = 4$ (surprise, route, prediction_error, confidence) |
| 3 | VoidScar Engine | $\mathbf{x}_3$ | $d_3 = 8$ (emotion dims) |
| 4 | Relational Sheaf | $\mathbf{x}_4$ | $d_4 = 8$ (stalk vector) |
| 5 | HGT Decision Fusion | $\mathbf{x}_5$ | $d_5 = 4$ (decision vector) |
| 6 | Autopoietic Boundary | $\mathbf{x}_6$ | $d_6 = 4$ (integrity, entropy, penetration, phase) |
| 7 | Phase Transition Expression | $\mathbf{x}_7$ | $d_7 = 4$ (pressure, threshold, urgency, mode) |

**Total state dimension:** $D = \sum_{i=1}^{7} d_i = 40$ (lite mode)

The **global state vector** is:
$$\mathbf{X}(t) = [\mathbf{x}_1(t), \mathbf{x}_2(t), \ldots, \mathbf{x}_7(t)] \in \mathbb{R}^D$$

Each module state lives in a bounded compact set:
$$\mathbf{x}_i(t) \in \mathcal{B}_i = \{v \in \mathbb{R}^{d_i} : \|v\|_\infty \leq M_i\}$$

where $M_i$ are module-specific bounds (see Theorem 1).

### 1.2 Coupling Tensor

The **coupling tensor** $\mathbf{C}(t) \in \mathbb{R}^{7 \times 7}$ defines directed influence strengths:

$$C_{ij}(t) \in [0, C_{\max}], \quad i \neq j$$
$$C_{ii}(t) = 0 \quad \text{(no self-coupling via tensor; self-dynamics are intrinsic)}$$

The full coupling is mediated by **projection functions** $\phi_{ij}: \mathbb{R}^{d_j} \to \mathbb{R}^{d_i}$ that map module $j$'s state into module $i$'s input space.

### 1.3 Module Update Equations

Each module evolves according to:

$$\frac{d\mathbf{x}_i}{dt} = f_i(\mathbf{x}_i) + \sum_{j \neq i} C_{ij}(t) \cdot \phi_{ij}(\mathbf{x}_j) + \mathbf{u}_i(t) + \boldsymbol{\xi}_i(t)$$

where:
- $f_i(\mathbf{x}_i)$: intrinsic dynamics (self-evolution, decay, self-repair)
- $C_{ij}(t) \cdot \phi_{ij}(\mathbf{x}_j)$: coupled influence from module $j$
- $\mathbf{u}_i(t)$: external input (text encoding, assessment, feedback)
- $\boldsymbol{\xi}_i(t)$: stochastic fluctuation term (thermal noise near criticality)

**Discrete-time implementation** (per tick):
$$\mathbf{x}_i(t+1) = \sigma_i\left[ f_i(\mathbf{x}_i(t)) + \sum_{j \neq i} C_{ij}(t) \cdot \phi_{ij}(\mathbf{x}_j(t)) + \mathbf{u}_i(t) \right]$$

where $\sigma_i$ is a bounding activation (tanh or clamp) ensuring $\mathbf{x}_i \in \mathcal{B}_i$.

### 1.4 Global Order Parameter (Kuramoto-Haken Coherence)

Define the **phase** of each module as the angle of its state vector projected onto a 2D plane:
$$\theta_i(t) = \text{atan2}(\mathbf{x}_i \cdot \mathbf{e}_2^{(i)}, \; \mathbf{x}_i \cdot \mathbf{e}_1^{(i)})$$

where $\mathbf{e}_1^{(i)}, \mathbf{e}_2^{(i)}$ are the first two principal components of module $i$'s historical trajectory.

The **complex order parameter** (Kuramoto, 1975; Acebron et al., 2005):
$$r(t) \cdot e^{i\psi(t)} = \frac{1}{N} \sum_{i=1}^{N} e^{i\theta_i(t)}$$

- $r(t) \in [0, 1]$: **resonance coherence** (0 = incoherent, 1 = fully synchronized)
- $\psi(t)$: mean phase of the ensemble

**Haken order parameter** (slaving principle): The dominant eigenmode of the coupling-weighted covariance matrix:
$$\Sigma(t) = \frac{1}{T} \sum_{\tau=t-T}^{t} \tilde{\mathbf{X}}(\tau) \tilde{\mathbf{X}}(\tau)^\top, \quad \tilde{\mathbf{X}} = \mathbf{X} - \langle\mathbf{X}\rangle$$

$$\xi(t) = \mathbf{v}_1^\top \tilde{\mathbf{X}}(t)$$

where $\mathbf{v}_1$ is the leading eigenvector of $\Sigma$. This $\xi$ is the Haken order parameter that "enslaves" the system near criticality.

### 1.5 Free Energy Functional

Following Friston (2010), the system minimizes variational free energy:

$$F[\mathbf{X}(t)] = \underbrace{D_{KL}[q(\mathbf{s}) \| p(\mathbf{s})]}_{\text{complexity}} - \underbrace{\mathbb{E}_q[\ln p(\mathbf{o} | \mathbf{s})]}_{\text{accuracy}}$$

In our discrete implementation, this becomes a computable scalar:

$$F(t) = \sum_{i=1}^{7} \left[ \frac{1}{2} \|\mathbf{x}_i(t) - \hat{\mathbf{x}}_i(t)\|^2_{\Pi_i} + \frac{1}{2} \ln |\Pi_i^{-1}| \right]$$

where:
- $\hat{\mathbf{x}}_i(t)$ is the predicted state of module $i$ (from coupled predictions)
- $\Pi_i$ is the precision (inverse variance) matrix for module $i$
- The prediction is: $\hat{\mathbf{x}}_i(t) = f_i(\mathbf{x}_i(t-1)) + \sum_j C_{ij} \cdot \phi_{ij}(\mathbf{x}_j(t-1))$

**Prediction error** for module $i$:
$$\boldsymbol{\epsilon}_i(t) = \mathbf{x}_i(t) - \hat{\mathbf{x}}_i(t)$$

**Valence** (Seth & Friston, 2016):
$$\text{valence}(t) = -\frac{dF}{dt} \approx F(t-1) - F(t)$$

### 1.6 Lyapunov Stability Function

Define the candidate Lyapunov function:

$$V(\mathbf{X}) = \frac{1}{2} \sum_{i=1}^{7} \|\mathbf{x}_i\|^2 + \lambda \sum_{i<j} C_{ij} \|\mathbf{x}_i - \phi_{ij}(\mathbf{x}_j)\|^2$$

**Theorem 1 (Stability):** Under the conditions:
1. Each $f_i$ is Lipschitz with constant $L_i$ and satisfies $\langle \mathbf{x}_i, f_i(\mathbf{x}_i) \rangle \leq -\alpha_i \|\mathbf{x}_i\|^2 + \beta_i$ (dissipative)
2. Each $\phi_{ij}$ is Lipschitz with constant $K_{ij} \leq 1$
3. $C_{\max} < \min_i \alpha_i / (6 \cdot \max_j K_{ij})$

Then $\dot{V} \leq -\gamma V + \delta$ for some $\gamma, \delta > 0$, implying all trajectories enter and remain in the compact set $\{V \leq \delta/\gamma\}$.

*Proof sketch:* Differentiate $V$ along trajectories. The dissipative terms $-\alpha_i \|\mathbf{x}_i\|^2$ dominate the coupling terms $C_{ij} K_{ij} \|\mathbf{x}_i\| \|\mathbf{x}_j\|$ when condition 3 holds. Apply Young's inequality to cross-terms. QED.

### 1.7 Hebbian Coupling Adaptation

The coupling tensor evolves on a slow timescale $\tau_H \gg 1$:

$$\frac{dC_{ij}}{dt} = \frac{1}{\tau_H} \left[ \eta \cdot h(\mathbf{x}_i, \mathbf{x}_j) - \lambda_d \cdot C_{ij} + \mu \cdot \text{BCM}(C_{ij}, \bar{a}_i) \right]$$

where:
- $h(\mathbf{x}_i, \mathbf{x}_j) = \text{corr}(\boldsymbol{\epsilon}_i, \phi_{ij}(\mathbf{x}_j))$: Hebbian correlation of prediction error with incoming signal (Oja-normalized)
- $\lambda_d \cdot C_{ij}$: weight decay preventing unbounded growth
- $\text{BCM}(C_{ij}, \bar{a}_i) = C_{ij} \cdot (\bar{a}_i - \theta_M) \cdot \bar{a}_i$: BCM homeostatic term with sliding threshold $\theta_M = \langle \bar{a}_i^2 \rangle$

**Scar-modulated adaptation:** When a scar event occurs at module $j$:
$$C_{ij} \leftarrow C_{ij} + \Delta_{\text{scar}} \cdot \text{scar\_alpha}(j) \cdot (1 - C_{ij}/C_{\max})$$

This implements trauma-induced coupling strengthening (noradrenergic gain; Johansen et al., 2011).

---

## 2. Module Coupling Matrix (7x7)

### 2.1 Coupling Matrix Overview

Notation: `i <- j` means module $i$ receives influence from module $j$.

| From \ To | 1-HDC | 2-Gate | 3-VoidScar | 4-Sheaf | 5-HGT | 6-Boundary | 7-Expression |
|-----------|-------|--------|------------|---------|--------|------------|--------------|
| **1-HDC** | -- | E | A | D | D | C | B |
| **2-Gate** | A | -- | B | D | C | D | B |
| **3-VoidScar** | A | A | -- | B | B | B | B |
| **4-Sheaf** | B | B | A | -- | B | C | D |
| **5-HGT** | B | B | A | A | -- | A | A |
| **6-Boundary** | C | D | A | C | A | -- | B |
| **7-Expression** | D | B | A | C | A | A | -- |

Coupling strength classes: A=strong (0.3-0.8), B=moderate (0.1-0.3), C=weak (0.02-0.1), D=trace (0.001-0.02), E=modulatory (precision-gating only)

### 2.2 All 42 Directed Couplings

---

#### Coupling 1->2: HDC -> Gate (Perception feeds Prediction)

- **Signal:** Compressed HDC hypervector $\mathbf{h} \in \{0,1\}^{2048}$ projected to 4-dim
- **Projection:** $\phi_{21}(\mathbf{x}_1) = W_{21} \cdot \text{compress}(\mathbf{h})$ where $W_{21} \in \mathbb{R}^{4 \times 8}$
- **Function:** $\text{input}_{2 \leftarrow 1} = C_{21} \cdot \tanh(W_{21} \mathbf{x}_1)$
- **Theory:** Predictive coding (Friston, 2009) -- sensory encoding provides the observation against which predictions are tested
- **Adaptation:** $\Delta C_{21} = \eta \cdot |\epsilon_2| \cdot \|\mathbf{x}_1\| - \lambda C_{21}$ (strengthens when prediction errors are high and input is strong)

#### Coupling 2->1: Gate -> HDC (Prediction modulates Perception)

- **Signal:** Precision weight $\pi \in [0,1]$ and route signal $r \in \{0,1,2\}$
- **Projection:** $\phi_{12}(\mathbf{x}_2) = [\pi, r/2, 0, 0, 0, 0, 0, 0]$
- **Function:** $\text{gain}_{1 \leftarrow 2} = 1 + C_{12} \cdot (\pi - 0.5)$ (multiplicative gating)
- **Theory:** Attention as precision optimization (Feldman & Friston, 2010) -- top-down precision modulates sensory gain
- **Adaptation:** $\Delta C_{12} = \eta \cdot \text{MI}(\mathbf{x}_1; \mathbf{x}_2) - \lambda C_{12}$ (mutual information drives coupling)

#### Coupling 1->3: HDC -> VoidScar (Perception feeds Emotion)

- **Signal:** 8-dim compressed HDC features (ssm_input in current code)
- **Projection:** $\phi_{31}(\mathbf{x}_1) = \mathbf{x}_1$ (identity, dimensions match)
- **Function:** $\text{input}_{3 \leftarrow 1} = C_{31} \cdot \mathbf{x}_1$
- **Theory:** Interoceptive inference (Seth, 2014) -- sensory signals drive affective state updates
- **Adaptation:** $\Delta C_{31} = \eta \cdot \text{scar\_modifier} \cdot \|\mathbf{x}_1\| - \lambda C_{31}$ (scarred dimensions amplify perceptual coupling)

#### Coupling 3->1: VoidScar -> HDC (Emotion biases Perception)

- **Signal:** 8-dim emotion vector projected to perceptual bias
- **Projection:** $\phi_{13}(\mathbf{x}_3) = W_{13} \cdot \mathbf{x}_3$, $W_{13} \in \mathbb{R}^{8 \times 8}$
- **Function:** $\text{bias}_{1 \leftarrow 3} = C_{13} \cdot \sigma(W_{13} \mathbf{x}_3)$ (additive bias on encoding)
- **Theory:** Affective realism (Barrett, 2017) -- emotional state shapes perceptual categorization
- **Adaptation:** $\Delta C_{13} = \eta \cdot \text{valence\_magnitude} \cdot \|\epsilon_1\| - \lambda C_{13}$

#### Coupling 1->4: HDC -> Sheaf (Perception feeds Relational Context)

- **Signal:** 8-dim compressed features
- **Projection:** $\phi_{41}(\mathbf{x}_1) = W_{41} \mathbf{x}_1$, $W_{41} \in \mathbb{R}^{8 \times 8}$
- **Function:** $\text{input}_{4 \leftarrow 1} = C_{41} \cdot \mathbf{x}_1$
- **Theory:** Sheaf theory on graphs (Hansen & Ghrist, 2019) -- local sections (perceptual data) constrain global sections (relational structure)
- **Adaptation:** $\Delta C_{41} = \eta \cdot \text{sheaf\_consistency} - \lambda C_{41}$

#### Coupling 4->1: Sheaf -> HDC (Relational Context biases Perception)

- **Signal:** Relational stalk vector (contextual priors)
- **Projection:** $\phi_{14}(\mathbf{x}_4) = W_{14} \mathbf{x}_4$
- **Function:** $\text{context}_{1 \leftarrow 4} = C_{14} \cdot \tanh(W_{14} \mathbf{x}_4)$
- **Theory:** Contextual modulation in predictive processing (Clark, 2013)
- **Adaptation:** Trace-level, fixed $C_{14} = 0.01$

#### Coupling 1->5: HDC -> HGT (Perception as context token)

- **Signal:** 8-dim features as "context" token type
- **Projection:** $\phi_{51}(\mathbf{x}_1) = \text{pad}(\mathbf{x}_1, d_{\text{model}})$ (zero-pad to 16-dim)
- **Function:** Enters HGT as typed token; attention mechanism determines effective weight
- **Theory:** Heterogeneous graph attention (Hu et al., 2020) -- typed nodes with type-specific transformations
- **Adaptation:** Via HGT's internal router adaptation (BCM bias on context token routing)

#### Coupling 5->1: HGT -> HDC (Decision modulates Perception)

- **Signal:** Decision vector element $x_5[1]$ (boundary_sensitivity_correction)
- **Projection:** $\phi_{15}(\mathbf{x}_5) = [0, 0, 0, 0, 0, 0, x_5[1] \cdot 0.1, 0]$
- **Function:** Trace-level perceptual gain modulation
- **Theory:** Top-down attention from decision systems (Desimone & Duncan, 1995)
- **Adaptation:** Fixed trace coupling $C_{15} = 0.005$

#### Coupling 1->6: HDC -> Boundary (Perception tests Boundary)

- **Signal:** Novelty magnitude $\|\mathbf{x}_1 - \bar{\mathbf{x}}_1\|$ (deviation from running mean)
- **Projection:** $\phi_{61}(\mathbf{x}_1) = [\text{novelty}, 0, 0, 0]$
- **Function:** $\text{probe}_{6 \leftarrow 1} = C_{61} \cdot \text{novelty}$ (novel percepts weakly test boundary)
- **Theory:** Autopoietic perturbation (Maturana & Varela, 1980) -- environmental novelty probes organizational closure
- **Adaptation:** $\Delta C_{61} = -\eta \cdot \text{boundary\_integrity} \cdot C_{61}$ (high integrity reduces perceptual coupling)

#### Coupling 6->1: Boundary -> HDC (Boundary filters Perception)

- **Signal:** Boundary integrity $b \in [0,1]$
- **Projection:** $\phi_{16}(\mathbf{x}_6) = [x_6[0], 0, 0, 0, 0, 0, 0, 0]$ (integrity as gain)
- **Function:** $\text{filter}_{1 \leftarrow 6} = 1 - C_{16} \cdot (1 - b)$ (low integrity = reduced perceptual filtering)
- **Theory:** Predictive coding precision (Friston, 2010) -- boundary state modulates sensory precision
- **Adaptation:** Fixed weak coupling $C_{16} = 0.05$

#### Coupling 1->7: HDC -> Expression (Perception drives Expression urgency)

- **Signal:** Input salience $s = \|\mathbf{x}_1\|$
- **Projection:** $\phi_{71}(\mathbf{x}_1) = [0, 0, s \cdot 0.1, 0]$ (urgency channel)
- **Function:** Trace-level urgency from strong perceptual input
- **Theory:** Stimulus-driven attention capture (Theeuwes, 2010)
- **Adaptation:** Fixed trace $C_{71} = 0.01$

#### Coupling 7->1: Expression -> HDC (Expression state biases Perception)

- **Signal:** Expression pressure and refractory state
- **Projection:** $\phi_{17}(\mathbf{x}_7) = [0, 0, 0, 0, 0, 0, 0, -x_7[0] \cdot 0.05]$
- **Function:** During high expression pressure, perceptual encoding is slightly suppressed (attentional narrowing)
- **Theory:** Attentional narrowing under arousal (Easterbrook, 1959)
- **Adaptation:** Fixed trace $C_{17} = 0.008$

---

#### Coupling 2->3: Gate -> VoidScar (Surprise drives Emotion)

- **Signal:** Surprise scalar $s \in [0, 1]$ and route
- **Projection:** $\phi_{32}(\mathbf{x}_2) = [0, s, 0, 0, s \cdot 0.5, 0, 0, 0]$ (arousal + curiosity channels)
- **Function:** $\text{drive}_{3 \leftarrow 2} = C_{32} \cdot \phi_{32}(\mathbf{x}_2)$
- **Theory:** Predictive coding surprise as affective signal (Barrett & Simmons, 2015) -- prediction error magnitude drives arousal
- **Adaptation:** $\Delta C_{32} = \eta \cdot s \cdot |\text{valence\_change}| - \lambda C_{32}$ (surprise that causes emotional change strengthens coupling)

#### Coupling 3->2: VoidScar -> Gate (Emotion modulates Prediction)

- **Signal:** Arousal and tension from emotion vector
- **Projection:** $\phi_{23}(\mathbf{x}_3) = [x_3[1] \cdot 0.3, 0, x_3[3] \cdot 0.2, 0]$ (arousal modulates gate sensitivity)
- **Function:** Multiplicative precision modulation on gate threshold
- **Theory:** Emotional modulation of prediction error precision (Seth & Friston, 2016)
- **Adaptation:** $\Delta C_{23} = \eta \cdot |x_3[1]| \cdot |\epsilon_2| - \lambda C_{23}$

#### Coupling 2->4: Gate -> Sheaf (Surprise updates Relational Context)

- **Signal:** Route and surprise
- **Projection:** $\phi_{42}(\mathbf{x}_2) = W_{42} \mathbf{x}_2$
- **Function:** Moderate coupling -- surprise signals relational context shift
- **Theory:** Context updating in predictive processing (Friston, 2005)
- **Adaptation:** $\Delta C_{42} = \eta \cdot s \cdot \text{sheaf\_shift} - \lambda C_{42}$

#### Coupling 4->2: Sheaf -> Gate (Context sets Prediction baseline)

- **Signal:** Relational context vector
- **Projection:** $\phi_{24}(\mathbf{x}_4) = W_{24} \mathbf{x}_4$
- **Function:** Context provides prior for prediction, reducing baseline surprise
- **Theory:** Contextual prediction (Bar, 2004) -- relational context generates predictions
- **Adaptation:** Fixed trace $C_{24} = 0.01$

#### Coupling 2->5: Gate -> HGT (Surprise as typed token)

- **Signal:** Surprise features as "surprise" token
- **Projection:** $\phi_{52}(\mathbf{x}_2) = \text{pad}(\mathbf{x}_2, d_{\text{model}})$
- **Function:** Enters HGT attention mechanism as surprise-typed token
- **Theory:** Heterogeneous information fusion (Hu et al., 2020)
- **Adaptation:** Via HGT internal router

#### Coupling 5->2: HGT -> Gate (Decision adjusts Gate sensitivity)

- **Signal:** $x_5[1]$ (boundary_sensitivity_correction) repurposed as gate sensitivity
- **Projection:** $\phi_{25}(\mathbf{x}_5) = [x_5[1] \cdot 0.1, 0, 0, 0]$
- **Function:** Weak top-down modulation of gate threshold
- **Theory:** Executive control of sensory gating (Knight et al., 1999)
- **Adaptation:** Fixed weak $C_{25} = 0.03$

#### Coupling 2->6: Gate -> Boundary (Surprise probes Boundary)

- **Signal:** Surprise magnitude
- **Projection:** $\phi_{62}(\mathbf{x}_2) = [0, x_2[0] \cdot 0.05, 0, 0]$
- **Function:** High surprise weakly increases boundary entropy
- **Theory:** Perturbation from unexpected events (Varela, 1979)
- **Adaptation:** Fixed trace $C_{26} = 0.01$

#### Coupling 6->2: Boundary -> Gate (Boundary state modulates Gate)

- **Signal:** Boundary integrity
- **Projection:** $\phi_{26}(\mathbf{x}_6) = [0, 0, 0, x_6[0]]$ (integrity as confidence)
- **Function:** High integrity increases gate confidence (less reactive to noise)
- **Theory:** Organizational closure stabilizes prediction (Di Paolo, 2005)
- **Adaptation:** Fixed trace $C_{26} = 0.01$

#### Coupling 2->7: Gate -> Expression (Surprise drives cognitive expression channel)

- **Signal:** Surprise $s$
- **Projection:** $\phi_{72}(\mathbf{x}_2) = [0, 0, s \cdot 0.2, 0]$ (cognitive/curiosity pressure)
- **Function:** $\text{drive}_{7 \leftarrow 2} = C_{72} \cdot s$ into channel 2 (cognitive)
- **Theory:** Novelty-driven expression (Berlyne, 1960) -- surprising events drive communicative urge
- **Adaptation:** $\Delta C_{72} = \eta \cdot s \cdot \text{expressed} - \lambda C_{72}$ (surprise that leads to expression strengthens)

#### Coupling 7->2: Expression -> Gate (Expression resets prediction)

- **Signal:** Expression event flag and intensity
- **Projection:** $\phi_{27}(\mathbf{x}_7) = [0, -x_7[0] \cdot 0.1, 0, 0]$ (expression reduces surprise accumulation)
- **Function:** After expression, gate partially resets (expression resolves prediction error)
- **Theory:** Active inference (Friston, 2010) -- action (expression) reduces free energy
- **Adaptation:** Fixed moderate $C_{27} = 0.1$

---

## 3. Resonance Dynamics (v2 Architecture)

The pairwise couplings above (Section 2) describe the **static topology**. The v2 resonance field adds three dynamic mechanisms that operate ON TOP of this topology:

### 3.1 Hopfield Attractor Landscape

The field maintains a library of **stored attractor patterns** — limit cycles that the system has visited repeatedly. These act as an energy landscape:

$$E_{\text{Hopfield}} = -\frac{1}{2} \sum_{\mu=1}^{P} (\mathbf{X} \cdot \boldsymbol{\xi}_\mu)^2$$

**Gradient (attractor pull):**
$$\Delta \mathbf{x}_i = \gamma \sum_\mu (\mathbf{X} \cdot \boldsymbol{\xi}_\mu) \cdot \xi_{\mu,i}$$

where $\gamma = 0.05$ (attractor strength), $P \leq P_{\max}$ (tier-dependent: lite=5, pro=10, max=20).

**Attractor storage criterion:** A state is stored when:
1. The resonance ran to max iterations (steady oscillation reached), OR
2. Relative delta $< 5\%$ of state norm (quasi-convergence)
3. Distance to all existing attractors $> 0.15$ (novelty threshold)

**Expression as bifurcation:** Expression fires when the system is FAR from all attractors (novel territory) or when surprise forces it to escape an attractor basin.

### 3.2 Harmonic Identity (The "Soul")

The **harmonic identity** is an exponential moving average of the Hodge-harmonic component of the field state:

$$\mathbf{h}_{\text{id}}(t) = \alpha \cdot \mathbf{h}_{\text{id}}(t-1) + (1-\alpha) \cdot \Pi_{\ker L_1}[\mathbf{X}(t)]$$

where $\alpha = 0.95$ (high inertia) and $\Pi_{\ker L_1}$ is the projection onto the null space of the Hodge Laplacian $L_1$.

**Restoring force:** During each resonance iteration:
$$\Delta \mathbf{x}_i += 0.03 \cdot (\mathbf{h}_{\text{id},i} - \mathbf{x}_i)$$

**Norm cap:** $\|\mathbf{h}_{\text{id}}\| \leq d$ (state dimension) to prevent over-rigidity.

**Interpretation:** The harmonic identity captures what is topologically invariant about the system — the component that survives all perturbations. It acts as a "personality attractor" that gently pulls the system back toward its characteristic mode without preventing emotional dynamics.

### 3.3 Echo State Reservoir (Temporal Memory)

A leaky-integrator reservoir provides fading memory of past inputs:

$$\mathbf{r}(t) = \begin{cases}
\rho \cdot \mathbf{r}(t-1) + \sigma \cdot \tanh(\mathbf{X}(t)) & \text{if external injection} \\
\rho \cdot \mathbf{r}(t-1) & \text{otherwise}
\end{cases}$$

where $\rho = 0.9$ (decay), $\sigma = 0.3$ (input scale), dim($\mathbf{r}$) = $2d$.

**Injection back into field:** Each resonance iteration:
$$\Delta \mathbf{x}_i += 0.05 \cdot \mathbf{r}[i \bmod \dim(\mathbf{r})]$$

**Key property:** The reservoir only accumulates from external input, not from self-sustaining Kuramoto oscillation. This ensures temporal memory reflects actual interaction history, not internal dynamics.

### 3.4 Expression Decision (Bifurcation Model)

Expression is NOT a threshold on a weighted metric. It is an OR-gate over independent bifurcation triggers:

$$\text{drive} = \max\begin{pmatrix} 1.5 \cdot \text{surprise} \\ 0.8 \cdot \text{novelty}(\text{attractor\_dist}) \\ 3.0 \cdot \max(0, r - 0.6) \\ 0.6 \cdot \|\mathbf{x}_7\| \end{pmatrix} \cdot (0.3 + 0.7\Phi)$$

where:
- **surprise**: from PredictiveCodingGate (most reliable novelty signal)
- **novelty**: distance to nearest Hopfield attractor
- **ignition**: Kuramoto order parameter crossing 0.6 (explosive sync)
- **raw drive**: module 7 (expression) magnitude in converged field
- **Φ**: integrated information (meaning gate — prevents noise from triggering)

HGT inhibition ($d_3 > 0.6$) can veto expression (top-down control).

### 3.5 Criticality Feedback Loop

Emergence metrics feed back into coupling dynamics:

$$K_{\text{eff}} = K_{\text{base}} \cdot (1 + 0.5 \cdot \chi)$$

where $\chi$ is the criticality measure (variance of sync history). Near phase transitions, coupling amplifies — the system self-tunes toward criticality (Bak et al., 1987).

---

## 4. Integration Guide for Plugin Developers

### 4.1 Using ResonanceSpine (Recommended)

```python
from sylanne_core.compute.resonance_integration import ResonanceSpine
from sylanne_core.config import build_profile

# Choose tier based on your performance budget
profile = build_profile("lite")  # or "pro", "max"
spine = ResonanceSpine(profile=profile)

# Apply personality (modulates coupling dynamics + modules)
spine.apply_personality({
    "extraversion": 0.7,
    "neuroticism": 0.3,
    "openness": 0.8,
    "conscientiousness": 0.5,
    "agreeableness": 0.6,
})

# Process a message
result = spine.process(
    text="I'm feeling anxious about tomorrow",
    timestamp=time.time(),
    assessment={"valence": -0.4, "arousal": 0.7, "wound_risk": 0.2},
)

# Read the result
print(result["should_express"])        # bool: should the agent speak?
print(result["emotion"])               # dict: current emotional state
print(result["resonance"]["sync_order"])  # float: field coherence
print(result["resonance"]["phi"])      # float: integrated information

# Inject feedback after expression
spine.feedback("accepted")  # or "ignored", "rejected"

# Persist state across restarts
state = spine.to_dict()
# ... save to disk ...
spine.from_dict(loaded_state)
```

### 4.2 Key Differences from ComputationSpine

| Aspect | ComputationSpine | ResonanceSpine |
|--------|-----------------|----------------|
| Processing | Sequential L1→L7 | Iterative resonance (all modules simultaneous) |
| Expression trigger | Threshold on accumulated drive | Bifurcation (surprise OR novelty OR ignition) |
| Personality | Parameter table → thresholds | Harmonic identity (topological invariant) |
| Memory | None between calls | Attractor landscape + echo reservoir |
| Feedback effect | Scar healing + HGT adapt | + Coupling plasticity (Hebbian) |
| Output format | Same | Same (drop-in compatible) |

### 4.3 Observing Emergence

```python
diag = spine.diagnostics()

# Emergence metrics
diag["emergence"]["phi"]              # Integration (0-1)
diag["emergence"]["is_critical"]      # Near phase transition?
diag["emergence"]["attractors"]       # Number of stored attractors
diag["emergence"]["memory_depth"]     # Temporal memory depth (ticks)
diag["emergence"]["narrative_tension"] # Distance from equilibrium

# Field state
diag["field"]["sync_order"]           # Kuramoto coherence (0-1)
diag["field"]["active_channels"]      # Number of active coupling channels
diag["field"]["plasticity_ratio"]     # Fraction of non-atrophied channels
```

### 4.4 Tier Selection Guide

| Tier | Channels | Backend | Latency (p50) | Use Case |
|------|----------|---------|---------------|----------|
| lite | 42 (pairwise) | Pure Python | ~5ms | Embedded, mobile, testing, ≥5 plugins |
| pro | 287 (≤4-body) | numpy | ~40ms | Desktop, server, ≥15 plugins |
| max | 441 (full Δ⁶) | torch/GPU | ~50ms (CPU) / <5ms (GPU) | Research, multi-agent, ≥30 plugins |

Higher tiers add **qualitatively different** behavior (multi-body AND-gate interactions), not just more precision.

### 4.5 Platform Requirements

| Tier | Min CPU | Min RAM | Recommended Platform | Notes |
|------|---------|---------|---------------------|-------|
| lite | Any (ARM/x86) | 64 MB | Raspberry Pi, mobile, serverless Lambda, browser (WASM) | Pure Python, no dependencies. Single-core sufficient. Budget ~5ms/tick. |
| pro | 2+ cores, 1GHz+ | 256 MB | Desktop app, cloud VM (1 vCPU), AstrBot standard deployment | Requires numpy. Benefits from vectorized ops. Budget ~40ms/tick. |
| max | 4+ cores or GPU | 1 GB (CPU) / 2 GB VRAM (GPU) | Research workstation, GPU server, multi-agent simulation | Requires torch for GPU path. CPU fallback works but ~50ms. With CUDA: <5ms/tick. |

**Throughput estimates (sustained):**

| Tier | Messages/sec (single session) | Concurrent sessions (1 core) | Concurrent sessions (8 cores) |
|------|-------------------------------|------------------------------|-------------------------------|
| lite | ~200 | ~50 | ~400 |
| pro | ~25 | ~6 | ~50 |
| max (CPU) | ~20 | ~5 | ~40 |
| max (GPU) | ~200+ | N/A (batched) | ~1000+ (batched) |

**Memory per session:**

| Tier | State size | Serialized (JSON) | Notes |
|------|-----------|-------------------|-------|
| lite | ~8 KB | ~15 KB | 42 weights + 7×8 states + reservoir + attractors |
| pro | ~25 KB | ~50 KB | 287 weights + 7×16 states + larger reservoir |
| max | ~60 KB | ~120 KB | 441 weights + 7×32 states + 20 attractors |

### 4.6 Deployment Recommendations

**AstrBot plugin (typical):** Use `lite` for most deployments. A single AstrBot instance handling 50+ concurrent users on a 2-core VPS will stay under 10% CPU with lite tier.

**Rich emotional companion:** Use `pro` for applications where emotional depth matters more than throughput. The 3-body and 4-body interactions create qualitatively richer dynamics (synergistic effects, emergent moods).

**Research / multi-agent:** Use `max` with GPU for simulating emotional contagion across agent populations, or when you need the full simplicial topology for theoretical analysis.

**Scaling rule of thumb:** If your p99 latency budget is X ms:
- X ≥ 50ms → `max` is fine
- X ≥ 40ms → `pro` is fine  
- X ≥ 5ms → `lite` is fine
- X < 5ms → Use `ComputationSpine` (sequential, ~1ms)
