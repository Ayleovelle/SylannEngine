export const meta = {
  name: 'derivation-math-redteam',
  description: 'Adversarial verification of the E-law derivation: attack every theorem, proof, constant, and code-correspondence claim',
  phases: [{ title: 'Attack' }],
}

const SCHEMA = {
  type: 'object',
  required: ['verdict', 'findings'],
  properties: {
    verdict: { type: 'string', enum: ['SOUND', 'SOUND_WITH_FIXES', 'BROKEN'], description: 'overall for your assigned scope' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'target', 'claim', 'attack'],
        properties: {
          severity: { type: 'string', enum: ['fatal', 'major', 'minor', 'nit'] },
          target: { type: 'string', description: 'theorem/lemma/prop/section attacked, e.g. "Thm 5"' },
          claim: { type: 'string', description: 'what the derivation asserts' },
          attack: { type: 'string', description: 'the hole: counterexample, gap in proof, wrong constant, mismatch with code — be concrete, with numbers/file:line where possible' },
          fix: { type: 'string', description: 'minimal repair if you see one' },
        },
      },
    },
  },
}

const DOC = 'G:\\SylannEngine\\docs\\design\\affect-dynamics-derivation.md'
const CTX = `Read ${DOC} in full first. It is a paper-grade derivation for the affect-dynamics E-law in repo G:\\SylannEngine (package sylanne_core, branch feat/v26-affect-dynamics). Your job is to BREAK it, not to admire it. Default to skepticism: try numeric counterexamples, edge cases (u on boundaries, dt=0, G=1, a=+-1, rho->0/1, empty scars), and check every constant against the actual code. If a proof step is hand-wavy, say exactly which inequality fails or is unjustified. Your final message must be ONLY the structured output.`

phase('Attack')
const attackers = [
  {
    key: 'fast-channel',
    prompt: `${CTX}
SCOPE: Theorems 1, 2, Lemma 2.1, Prop 7, and section 8 (saturating update, decay, affine equivariance, hysteresis bound, contagion). Attack lines: (1) Thm 1 case split — does a_i+*a_i-=0 actually hold for the CODE's implementation (read sylanne_core/compute/affect_dynamics.py saturating_update — note it sanitizes non-finite a to 0 and clamps output; does the clamp hide a violation or is it redundant given the theorem?); (2) tightness claim in Note 1.1 — verify the escape counterexample; (3) Thm 2 — is beta in (0,1] or (0,1) for dt>0, and does the code's dt<=0 guard match the theorem's domain; is "no overshoot" exactly right when u0=ubar? (4) Lemma 2.1 — verify affine-equivariance algebraically AND against the property test tests/test_affect_domain_adapter.py; does the argument require coefficients summing to 1, and do they? (5) Prop 7 — is the "2*theta_h band" argument actually correct for the CODE's resolve_label (read affect_output_contract.py: hysteresis compares margin-to-nearest-boundary, NOT distance traveled — construct a scenario with the 1/3 and 2/3 cuts where the stated turn-separation bound fails, e.g. oscillation between margins just under theta_h on both sides of a boundary, or level jumps of 2). Also check the s-bar step-bound claim: is per-turn displacement really bounded by G_max + (1-beta_min)?`,
  },
  {
    key: 'slow-channel',
    prompt: `${CTX}
SCOPE: Theorems 3, 5, Notes 5.1/5.2 (scar stickiness, drift radius, two-timescale tracking). Attack lines: (1) Thm 3 — the g_i(T) bound [0.3,2.0]: read affect_dynamics.py half_lives and verify g_max=2.0 and h_base_max; is the k-lower-bound formula right? Does the PROOF's comparison-principle step hold when h changes discontinuously between turns (piecewise-constant k(t))? (2) Thm 5 — the recursion: read sylanne_core/compute/slow_channel.py and personality.py compute_embodiment_drift: is the ACTUAL update T + eta*q*u - rho*(T-A), or does compute_embodiment_drift apply caps/homeostatic-resistance/oscillation-freeze that change the recursion (making the theorem model a DIFFERENT system than the code)? Check the claimed constants eta=0.30 rho=0.20 against the code. Is the limsup bound eta*Q/rho derived correctly (check the geometric-series step)? Is the claim "from T0=A, ||e_n|| < eta*Q/rho for all finite n" exactly right or off by the (1-(1-rho)^n) factor direction? (3) Note 5.1 — the admission that clamp dominates: given clamp [0.05,0.95] and anchor at 0.5, radius 0.45 vs eta*Q/rho=1.5*Q — for what Q does the theorem bind at all? Is the theorem vacuous in practice? (4) Note 5.2 — Phi_eq Lipschitz row-sum <=0.5: recompute from equilibrium() coefficients in affect_dynamics.py (e.g. warmth row: 0.30*rel + 0.20*warmth_bias — but rel is NOT a trait; does mixing T and R into one Lipschitz claim conflate two arguments?).`,
  },
  {
    key: 'composition-and-plasticity',
    prompt: `${CTX}
SCOPE: Theorem 4, Theorem 6, Notes 6.1/6.2, assumptions A1-A7, and section 11 open holes. Attack lines: (1) Thm 4 — "any finite composition preserves K": trace the actual write paths in scar_algebra.py (_affect_decay, apply_affect_takeover, the PEL-affine wound branch math.tanh(base+0.3*modulated), the legacy MLP branch) and check whether every write really lands in the claimed invariant set. CRITICAL: does _affect_decay clamp base before decaying, or does it feed raw possibly-out-of-range base (restored snapshot with base=1.5) into decay — and does decay preserve boundedness for u0 OUTSIDE [0,1]? Thm 2's convexity argument needs u0 in [0,1]! Construct the counterexample if it exists. (2) Thm 6 — "proofs of Thm 1-4 only use G in (0,1]": verify by re-reading each proof; does Thm 3 use G at all? Would a learned-G path bypass validate_gain in apply_affect_takeover? (3) Note 6.1 timescale ordering "k*interval >> alpha >> drift-effect": is this ordering dimensionally well-formed (k has 1/seconds, alpha is dimensionless per-turn)? Propose the dimensionally correct statement. (4) A1-A7: any assumption the code violates TODAY? (5) Section 10 table — spot-check 3 rows for real file/test existence.`,
  },
  {
    key: 'positioning-honesty',
    prompt: `${CTX}
SCOPE: Section 9 (positioning & named contributions C1-C3), section 0 stance assumptions, and the document's overall claims discipline. Attack lines: (1) C1 "no counterpart in named systems" — is the claim scoped honestly ("in the systems surveyed" vs implying exhaustive novelty)? Is there any system YOU know — computational trauma/PTSD models, mood-inertia literature, psychology's affect-dynamics field (Kuppens' DynAffect, emotional-inertia attractor models) — that couples decay time-constants to accumulated state history or provides the same math? Must the doc cite psych affect dynamics (the FIELD is literally called affect dynamics) to be honest? (2) C2 — bounded-drift claim vs OU processes: an OU process with clamped state trivially has bounded excursions; is Thm 5 genuinely more than "discrete OU with bounded input has bounded excursion", and should C2 be downgraded to an engineering-contract claim rather than a theory contribution? (3) C3 — is a "separation theorem" that amounts to "the safety proof never referenced the learned parameter beyond its projected domain" a THEOREM or a design observation; how would a serious venue reviewer react to the naming? (4) The doc's title says paper-grade: list what an actual reviewer would still demand (related-work coverage, empirical validation, baselines) so the self-description stays honest. Suggest precise wording downgrades where claims exceed evidence.`,
  },
]

const results = await parallel(attackers.map(a => () =>
  agent(a.prompt, { label: `attack:${a.key}`, phase: 'Attack', schema: SCHEMA, model: 'sonnet', effort: 'high' })
    .then(r => ({ attacker: a.key, ...r }))
))
return { attacks: results.filter(Boolean) }