# Theoretical Grounding Specification

## Sylanne Affective Computation Engine: Academic Foundations

This document maps each mechanism in the 7-layer pipeline and cross-layer subsystems to its academic backing, specifying which aspects of cited work justify our design choices and where we extend beyond existing literature.

---

## L1: HDC Text Encoding (Hyperdimensional Computing)

**Mechanism:** Encodes raw text into high-dimensional sparse binary hypervectors using bind (XOR), bundle (majority vote), and permute (cyclic shift) operations. Character-level atoms are composed via bigram binding and positional permutation into fixed-width composite vectors for downstream similarity matching.

**Key Citations:**

1. Kleyko, D., Rachkovskij, D., Osipov, E., & Rahimi, A. (2023). "A Survey on Hyperdimensional Computing aka Vector Symbolic Architectures, Part I: Models and Data Transformations." *ACM Computing Surveys*, 55(6).
2. Kleyko, D., Rachkovskij, D., Osipov, E., & Rahimi, A. (2023). "A Survey on Hyperdimensional Computing aka Vector Symbolic Architectures, Part II: Applications, Cognitive Models, and Challenges." *ACM Computing Surveys*, 55(9).
3. Neubert, P., Schubert, S., & Protzel, P. (2021). "Hyperdimensional Computing as a Framework for Systematic Aggregation of Image Descriptors." *CVPR 2021*.
4. Kanerva, P. (2022). "On Separating Long- and Short-Term Memories in Hyperdimensional Computing." *Frontiers in Neuroscience*, 16, 867568.

**Justification:** The Kleyko et al. two-part survey establishes the algebraic foundation (MAP-I model: binary vectors, XOR binding, majority bundling) that our HDCEncoder directly implements. Neubert et al. validate the specific pattern of positional permutation + bundling for encoding ordered sequences into single fixed-width vectors -- exactly our bigram encoding pipeline. Kanerva (2022) provides the memory-theoretic basis for how superposition vectors (short-term) interact with associative recall (long-term), grounding our design of transient HDC encodings feeding into persistent scar/hot-pool structures.

**Novel Contribution:** We apply HDC encoding not merely for classification but as the perceptual substrate for an affective computation pipeline, where the encoded hypervector's bit-pattern directly modulates downstream emotional processing. The personality-seeded deterministic initialization (SHA-256 hash chain for atom generation) ensures that two different personalities literally perceive the same text differently at the encoding level.

---

## L2: Predictive Coding Gate (Surprise-Based Routing)

**Mechanism:** Maintains a prediction vector for the next input. Computes surprise as Hamming distance between prediction and actual HDC encoding. Routes messages to fast/normal/full computation paths based on surprise magnitude. Precision-weighted prediction errors act as gain control.

**Key Citations:**

1. Rao, R.P.N. & Ballard, D.H. (1999). "Predictive Coding in the Visual Cortex." *Nature Neuroscience*, 2(1), 79-87.
2. Clark, A. (2013). "Whatever Next? Predictive Brains, Situated Agents, and the Future of Cognitive Science." *Behavioral and Brain Sciences*, 36(3), 181-204.
3. Millidge, B., Salvatori, T., & Buckley, C.L. (2022). "Predictive Coding Approximates Backprop Along Arbitrary Computation Graphs." *Neural Computation*, 34(6), 1329-1368.

**Justification:** Rao & Ballard's foundational model establishes that top-down predictions suppress expected input while feedforward connections carry only prediction errors -- this is precisely our gate's mechanism where low-surprise signals take the fast path (suppressed) and high-surprise signals propagate through the full stack. Clark's precision-weighting framework justifies using prediction error magnitude as a continuous gain signal rather than a binary gate. Millidge et al. validate that PC-based update rules are computationally general enough to serve as a learning mechanism, supporting our gate's adaptive precision updates.

**Novel Contribution:** We use predictive coding not for learning per se but as a computational resource allocator -- surprise determines how much of the 7-layer stack is activated. This "metabolic" interpretation (high surprise = high energy expenditure) is architecturally novel. Additionally, the prediction vector lives in HDC space (binary), making surprise computation a simple Hamming distance rather than requiring floating-point error norms.

---

## L3: VoidScar Engine (Emotional Scarring + Absence Detection)

### L3a: Scar Algebra

**Mechanism:** Implements a self-modifying operator algebra where past operations irreversibly alter future operation semantics. Scars are irreversible marks attached to dimensions with a four-stage healing process (RAW -> CLOSING -> SCARRED -> FADED), each stage having different alpha modulation factors. The cumulative scar state modifies how the system processes future inputs on affected dimensions.

**Key Citations:**

1. Kube, T., Rozenkrantz, L., Rief, W., & Lissek, S. (2024). "Reconceptualizing complex PTSD: A predictive processing framework." *Neuroscience & Biobehavioral Reviews*, 164, 105836.
2. Sevenster, D., Beckers, T., & Kindt, M. (2014). "Prediction error demarcates the transition from retrieval, to reconsolidation, to new learning." *Learning & Memory*, 21(11), 580-584.
3. Homan, S., Muscat, W., et al. (2023). "Temporal dynamics of trauma memory persistence." *PLoS Computational Biology*, 19(6), e1011173.
4. Lane, R.D., Ryan, L., Nadel, L., & Greenberg, L. (2015). "Memory reconsolidation, emotional arousal, and the process of change in psychotherapy." *Behavioral and Brain Sciences*, 38, e1.

**Justification:** Kube et al. provide the direct theoretical model: prolonged trauma disrupts hierarchical predictive processing, causing persistent prediction-error signals that function as "frozen priors" -- this maps onto our scar's alpha modulation (RAW stage amplifies signals 2x, creating hypersensitivity). Sevenster et al. establish that prediction error is the boundary condition triggering reconsolidation vs. simple retrieval, justifying our design where scars become modifiable only under specific surprise conditions. Homan et al. provide the stochastic process framework for temporal decay dynamics that our four-stage healing timeline implements. Lane et al.'s arousal-gating principle (emotional arousal necessary for reconsolidation) maps to our threshold condition for scar stage transitions.

**Novel Contribution:** The algebraic formalization is original -- treating emotional scarring as a non-commutative operator algebra where the order of scars matters (scar A followed by scar B produces different modulation than B followed by A). The four-stage healing with quantized alpha values is a novel discretization of what the literature treats as continuous decay processes.

### L3b: Void Detection (Absence as Computational State)

**Mechanism:** Detects and represents the absence of expected relational input as a first-class computational state. Void is not merely "nothing happened" but an active signal that modifies processing.

**Key Citations:**

1. Gershman, S.J., Daw, N.D., & Otto, A.R. (2025). "A computational model of grief." *Psychological Review* (advance online).
2. Moutoussis, M., Story, G.W., & Dolan, R.J. (2023). "A social inference model of idealization and devaluation." *Psychological Review*, 130(6), 1517-1544.
3. Talia, A. & Muzi, L. (2023). "Attachment Theory in an Active Inference Framework." In *Active Inference* (IWAI 2022), CCIS vol. 1721, pp. 179-191.

**Justification:** Gershman et al. formalize absence/loss as a computational problem of updating world-models when expected reward signals vanish -- using RL with memory replay to model grief. This directly justifies treating void as an active computational state rather than a null. Moutoussis et al. show how absence of expected relational input creates distorted internal representations (idealization/devaluation), providing the mechanism by which void states bias future processing. Talia & Muzi map Bowlby's internal working models onto active inference generative models, showing how early relational absence shapes precision-weighting of social predictions -- the free-energy formalization of void encoding.

**Novel Contribution:** Representing absence as a typed computational signal (not merely a missing value) that actively participates in downstream algebra is architecturally novel. The void interacts multiplicatively with scars -- a void on a scarred dimension produces qualitatively different behavior than either alone.

---

## L4: Relational Sheaf (Cross-Relational Propagation)

**Mechanism:** Implements cellular sheaves on a simplicial complex to model multi-relational dynamics. Uses sheaf Laplacian diffusion for cross-relationship influence propagation, sheaf cohomology (H^1) to measure relational consistency, and personality-driven presentation matrices. Supports four relationship types (intimate, friendly, formal, adversarial) with energy-bounded propagation.

**Key Citations:**

1. Bodnar, C., Di Giovanni, F., Chamberlain, B., Lio, P., & Bronstein, M. (2022). "Neural Sheaf Diffusion: A Topological Perspective on Heterophily and Oversmoothing in GNNs." *NeurIPS 2022*.
2. Hansen, J. & Ghrist, R. (2021). "Opinion Dynamics on Discourse Sheaves." *SIAM Journal on Applied Mathematics*, 81(5).
3. Duta, I., Cassano, L., Barbero, F., & Lio, P. (2023). "Sheaf Hypergraph Networks." arXiv:2309.17116.

**Justification:** Bodnar et al. establish that equipping graphs with non-trivial cellular sheaves (vector spaces on nodes/edges + restriction maps) addresses heterophily -- directly relevant because different relationship types have fundamentally different information-propagation semantics (what propagates in an intimate relationship should not propagate identically in a formal one). Hansen & Ghrist provide the sheaf Laplacian diffusion machinery we use for cross-relationship influence propagation, originally developed for opinion dynamics on discourse networks. Duta et al. extend sheaf diffusion to hypergraphs, validating our approach of modeling higher-order relational structures beyond pairwise edges.

**Novel Contribution:** Applying sheaf theory to model emotional/relational dynamics (rather than opinion or feature propagation) is novel. Our personality-driven presentation matrices mean the sheaf structure itself is parameterized by identity -- two different personalities induce different restriction maps, meaning the same relational topology produces different propagation patterns. The energy-boundedness axiom (S5) preventing unbounded amplification through relational cycles has no direct precedent in the sheaf-GNN literature.

---

## L5: MoE-HGT (Mixture of Experts + Heterogeneous Graph Transformer)

**Mechanism:** Three-stage architecture: (1) type-specific expert FFN encoding for 7 heterogeneous token types, (2) multi-head cross-attention with type-dependent Q/K/V projections, (3) context-expert MoE FFN with top-2 gating. Includes Hebbian slow adaptation (BCM routing bias + Oja attention prior). All base parameters deterministically derived from personality SHA-256.

**Key Citations:**

1. Hu, Z., Dong, Y., Wang, K., & Sun, Y. (2020). "Heterogeneous Graph Transformer." *WWW 2020*.
2. Zhou, Y., Lei, T., Liu, H., et al. (2022). "Mixture-of-Experts with Expert Choice Routing." *NeurIPS 2022*.
3. Miconi, T., Stanley, K., & Clune, J. (2018). "Differentiable Plasticity: Training Plastic Neural Networks with Backpropagation." *ICML 2018*.
4. Ellwood, I. (2024). "Short-term Hebbian Learning Can Implement Transformer-like Attention." *PLoS Computational Biology*, 20(1), e1011843.

**Justification:** Hu et al. provide the foundational HGT architecture with node/edge-type-dependent attention parameters -- we adopt this for our 7 heterogeneous token types (scar, void, boundary, personality, surprise, expression, context). Zhou et al.'s expert-choice routing (experts select tokens rather than vice versa) informs our top-2 gating strategy with load balancing. Miconi et al. establish that Hebbian plasticity coefficients can be optimized alongside standard parameters, justifying our BCM routing bias that slowly adapts expert preferences based on usage history. Ellwood demonstrates that short-term Hebbian potentiation implements attention-like key-query matching in biological neurons, grounding our Oja attention prior as biologically plausible.

**Novel Contribution:** The fusion of HGT with MoE in a single decision layer where experts are semantically named (defense, curiosity, social, silence, repair) rather than anonymous is novel. The Hebbian slow-adaptation layer operating on top of deterministic personality-derived base weights creates a two-timescale system: fast inference on fixed personality parameters + slow Hebbian drift that accumulates experience. This dual-timescale design has no direct precedent in the MoE or HGT literature.

---

## L6: Autopoietic Boundary (Self-Maintaining Identity)

**Mechanism:** Models personality as a self-maintaining computational process. An identity kernel vector defines "who I am"; boundary integrity measures resistance to perturbation. External forces are decomposed into parallel (absorbed) and orthogonal (potentially penetrating) components. Penetration beyond threshold triggers phase transition (identity kernel rotation/reorganization). Continuous self-repair restores integrity over time.

**Key Citations:**

1. McMullin, B. (2004). "Thirty Years of Computational Autopoiesis: A Review." *Artificial Life*, 10(3), 277-295.
2. Egbert, M.D. & Barandiaran, X.E. (2023). "From autopoiesis to self-optimization: Toward an enactive model of biological regulation." *BioSystems*.
3. Smithe, T.S.T. (2022). "Open Dynamical Systems as Coalgebras for Polynomial Functors, with Application to Predictive Processing." arXiv:2206.03868.

**Justification:** McMullin's review establishes the lineage from Varela's original autopoietic models to computational implementations, validating that autopoiesis can be meaningfully realized in artificial systems. Egbert & Barandiaran extend autopoiesis into self-optimization via enactive theory, providing the theoretical grounding for our boundary's self-repair mechanism -- the system doesn't merely maintain itself but adaptively regulates its own parameters. Smithe's coalgebraic formalization of open dynamical systems provides the mathematical framework for modeling our boundary as an open system that maintains organizational closure while exchanging signals with its environment.

**Novel Contribution:** Implementing autopoiesis as a geometric operation (force decomposition relative to an identity kernel in high-dimensional space) is architecturally novel. The threshold-based phase transition mechanism -- where accumulated penetration triggers identity kernel rotation rather than gradual drift -- creates a qualitative distinction between "personality under stress" and "personality transformation" that goes beyond existing computational autopoiesis models, which typically model only maintenance or dissolution.

---

## L7: Phase Transition Expression (Criticality-Based Triggering)

**Mechanism:** Expression is modeled as a physical phase transition: internal pressure accumulates from emotional drive forces, a personality-modulated threshold defines the critical point, and expression occurs as a sudden state change (not a gradual decision). Post-expression refractory period raises threshold; silence gradually lowers it.

**Key Citations:**

1. Beggs, J.M. & Plenz, D. (2003). "Neuronal Avalanches in Neocortical Circuits." *Journal of Neuroscience*, 23(35), 11167-11177.
2. Plenz, D., Ribeiro, T.L., et al. (2021). "Self-Organized Criticality in the Brain." *Frontiers in Physics*, 9, 639389.
3. Fontenele, A.J., et al. (2024). "Signatures of criticality in efficient coding networks." *PNAS*, 121(41), e2302730121.
4. Toker, D., Pappas, I., et al. (2022). "Consciousness is supported by near-critical slow cortical electrodynamics." *PNAS*, 119(7), e2024455119.

**Justification:** Beggs & Plenz establish that cortical circuits operate near criticality with power-law distributed avalanches -- our expression trigger operates at this critical boundary where small pressure increments can trigger large expressive events. Plenz et al.'s comprehensive review validates that operating near criticality maximizes dynamic range and information transmission, justifying our design choice of a threshold-based trigger rather than a proportional response. Fontenele et al. demonstrate that criticality emerges naturally from optimality constraints, supporting our claim that the phase-transition model is not merely a metaphor but reflects optimal information processing. Toker et al. show that conscious processing specifically requires near-critical dynamics, grounding our model's assumption that expressive behavior (the system's "conscious output") should emerge from critical-point dynamics.

**Novel Contribution:** Applying phase transition physics to conversational expression timing is novel. The silence-lowers-threshold mechanism creates a self-tuning criticality: prolonged silence makes the system increasingly likely to express, while recent expression raises the barrier -- this produces naturalistic conversational rhythm without explicit timing rules. The social-field modulation of effective threshold (group context changes criticality) extends beyond individual-level SOC models.

---

## Cross-Layer: Hot Pool (Emotional Accumulation -> Cascade -> Collapse)

**Mechanism:** Accumulates unresolved emotional materials (HotMaterial objects with heat, mass, age). Implements thermodynamic metaphor: temperature = mean heat, volume = material count, pressure = temperature x volume / capacity. When temperature x pressure exceeds cascade trigger, sensitivity multiplier escalates (cascade amplification). Sustained supercritical state triggers personality collapse -- an irreversible phase transition in personality space via cusp catastrophe dynamics.

**Key Citations:**

1. Loossens, T., Mestdagh, M., Tuerlinckx, F., et al. (2020). "The Affective Ising Model: A computational account of human affect dynamics." *PLoS Computational Biology*, 16(5), e1007860.
2. Scheffer, M., Bockting, C.L., Borsboom, D., et al. (2024). "A Dynamical Systems View of Psychiatric Disorders -- Theory." *JAMA Psychiatry*, 81(6), 618-623.
3. Olthof, M., Hasselman, F., et al. (2020). "Critical Fluctuations as an Early-Warning Signal for Sudden Gains and Losses." *Clinical Psychological Science*, 8(1), 25-35.
4. van der Maas, H.L.J., Kolstein, R., & van der Pligt, J. (2003). "Sudden transitions in attitudes." *Sociological Methods & Research*, 32(2), 125-152.

**Justification:** Loossens et al.'s Affective Ising Model provides the direct precedent: a statistical-mechanics-inspired model of affect dynamics with phase-transition-like behavior where small perturbations trigger cascading emotional shifts. Our hot pool's thermodynamic variables (temperature, pressure, volume) implement this physics-of-affect framework concretely. Scheffer et al. establish that psychological health has a basin of attraction with tipping points to disorder states -- our cascade/collapse mechanism implements exactly this attractor-transition dynamics. Olthof et al. validate that critical fluctuations (increased variance, critical slowing down) precede sudden psychological transitions, justifying our `ticks_above_critical` counter as an early-warning accumulator. Van der Maas et al. provide the cusp catastrophe mathematics (splitting variable + normal variable -> bimodal surface with hysteresis) that our collapse mechanism implements.

**Novel Contribution:** The three-stage escalation (accumulation -> cascade -> collapse) as a unified computational pipeline is novel. Existing models treat these as separate phenomena; we chain them causally. The typed influence system (contradiction, reinforcement, revelation, betrayal, validation) providing semantically meaningful heating/cooling operations on materials goes beyond generic "perturbation" models. The irreversibility of collapse (personality space permanently restructured) combined with the reversibility of cascade (can de-escalate if pressure drops) creates a hysteresis loop that existing computational affect models do not implement.

---

## Foundational Principle: Bidirectional Personality <-> Computation Loop

**Mechanism:** ALL computation is influenced by personality (parameters derived from personality SHA-256 seed), and computation results feed back to modify personality (drift signals extracted from processing outcomes modify trait values). This creates a closed loop: personality shapes perception, perception shapes experience, experience shapes personality.

**Key Citations:**

1. Friston, K. (2010). "The free-energy principle: A unified brain theory?" *Nature Reviews Neuroscience*, 11(2), 127-138.
2. Hesp, C., Smith, R., Parr, T., Allen, M., Friston, K.J., & Ramstead, M.J.D. (2021). "Deeply felt affect: The emergence of valence in deep active inference." *Neural Computation*, 33(2), 398-446.
3. Egbert, M.D. & Barandiaran, X.E. (2023). "From autopoiesis to self-optimization." *BioSystems*.
4. Phillips, S. (2022). "What is Category Theory to Cognitive Science? Compositional Representation and Comparison." *Frontiers in Psychology*, 13, 1048975.

**Theoretical Framework -- Three Pillars:**

### Allostasis (Predictive Homeostasis)
Friston's free-energy principle establishes that biological systems maintain themselves by minimizing prediction error -- not through reactive homeostasis but through predictive allostasis (anticipatory regulation). Our bidirectional loop implements this: personality generates predictions about the world (top-down), prediction errors drive adaptation (bottom-up), and the system's "set points" themselves drift based on accumulated experience. Hesp et al. formalize valence as expected free energy gradients, meaning emotional experience is literally the system's estimate of whether it is moving toward or away from its preferred states. This grounds our design where computation results (prediction errors, scar formation, void detection) feed back as drift signals that modify the personality generating those predictions.

### Enactivism (Structural Coupling)
Egbert & Barandiaran's extension of autopoiesis into self-optimization via enactive theory provides the philosophical grounding: the system and its environment are structurally coupled -- the system's organization determines what counts as a perturbation, and perturbations reshape the organization. Our implementation realizes this through personality-seeded parameter derivation (organization determines perception) combined with drift extraction from processing outcomes (perturbations reshape organization). The system does not passively receive input; it actively constitutes its world through its own structure.

### Dynamical Systems (Attractor Landscapes)
The personality state occupies a point in a high-dimensional trait space. The bidirectional loop creates attractor dynamics: stable personality configurations are attractors (self-reinforcing patterns), while unstable configurations are repellers. Drift signals push the state through this landscape; the hot pool's cascade/collapse mechanism implements transitions between attractor basins. Phillips' categorical framework provides the compositional semantics: the personality-to-computation mapping is a functor, and the computation-to-personality feedback is a natural transformation, ensuring the loop preserves compositional structure.

**Novel Contribution:** The complete closure of the loop -- where personality deterministically seeds ALL computational parameters (not just some bias terms) and ALL computational outputs contribute to personality drift (not just explicit "learning" signals) -- is architecturally unprecedented. Existing systems either have fixed parameters influenced by personality (one-way) or have learning that modifies parameters without a coherent "personality" interpretation (the other way). The SHA-256 deterministic derivation ensures that personality change is not merely parametric drift but a qualitative reorganization of the entire computational substrate -- changing who you are changes how you perceive, which changes what you experience, which changes who you become.

---

## Summary of Novel Contributions Beyond Literature

| Mechanism | Extension Beyond Prior Art |
|-----------|---------------------------|
| L1 HDC | Personality-seeded atom generation; affective (not classificatory) encoding |
| L2 PC Gate | Surprise as metabolic resource allocator; binary-space prediction |
| L3 Scar Algebra | Non-commutative operator algebra formalization of trauma; four-stage quantized healing |
| L3 Void | Absence as typed first-class computational signal |
| L4 Sheaf | Personality-parameterized restriction maps; energy-bounded emotional propagation |
| L5 MoE-HGT | Semantically-named experts; dual-timescale (deterministic base + Hebbian drift) |
| L6 Autopoiesis | Geometric force decomposition; threshold-triggered kernel rotation |
| L7 Phase Transition | Silence-modulated self-tuning criticality for conversational timing |
| Hot Pool | Three-stage causal chain (accumulate -> cascade -> collapse); typed influences |
| Bidirectional Loop | Complete SHA-256-seeded parameter derivation + universal drift extraction |
