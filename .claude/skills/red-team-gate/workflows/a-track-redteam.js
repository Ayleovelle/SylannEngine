export const meta = {
  name: 'a-track-redteam',
  description: 'Adversarial review of A-track diff: assessor intent (A.1), delta-rule plasticity (A.2), calibration harness/memo (A.4)',
  phases: [{ title: 'Attack' }],
}

const FINDINGS = {
  type: 'object', additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['SOUND', 'SOUND_WITH_FIXES', 'BROKEN'] },
    findings: { type: 'array', maxItems: 8, items: {
      type: 'object', additionalProperties: false,
      properties: {
        severity: { type: 'string', enum: ['fatal', 'major', 'minor', 'nit'] },
        target: { type: 'string' },
        claim: { type: 'string' },
        attack: { type: 'string', description: 'Concrete reproduction / counterexample, verified against real code where possible' },
        fix: { type: 'string' },
      },
      required: ['severity', 'target', 'claim', 'attack'],
    }},
  },
  required: ['verdict', 'findings'],
}

const COMMON = `Repo G:\\SylannEngine, branch feat/v26-affect-dynamics. The A-track landed in commits f3f6a0a (A.1 assessor intent), 326da76 (A.2 delta-rule gain plasticity), e19ab12 (A.4 harness+memo). Run \`git show <sha>\` to see each diff. Your job is to BREAK the work, not admire it. Default to skepticism; verify every attack against the REAL code (run python snippets / pytest where useful; PYTHONHASHSEED=0). Report only findings you could verify or make highly concrete. Include exact file:line. Return findings via StructuredOutput.`

const LENSES = [
  { key: 'a1-gating', prompt: `${COMMON}
LENS: A.1 intent gating & semantics. Attack surfaces:
1. Byte-parity claims: with want_intent=False is the LLM prompt and output key-set REALLY byte-identical to pre-A.1? Any path where intent leaks under Gate A only (affect_dynamics_enabled=True, affect_takeover=False)? Check engine._assess gating, spine apply_assessment paths, submit()/process() entry points, cached assessment reuse (computation_spine cache_key), host.on_request(assessment=...) caller-supplied dicts.
2. _sanitize_intent: whitelist bypasses (labels embedded in junk like "不生气", negations misclassified — "别生气" contains 生气!), length cap, non-str.
3. _fallback_intent runs affect_projection.classify_intent on the USER's raw text — semantic misattribution risks: user ASKING "你生气了吗" classified as anger intent? user quoting? Is that acceptable for a coarse fallback (confidence 0.3) or a real bug?
4. The 7-label vocabulary vs project_appraisal.INTENT_CLASSES keyword lists and the legacy hand-rules (exact-match 撒娇/生气): does every emitted label actually hit the intended class in BOTH consumers? Does 施压 hit "press"? check keyword lists.` },
  { key: 'a2-math-wiring', prompt: `${COMMON}
LENS: A.2 plasticity math & wiring. Attack surfaces:
1. plasticity_step/eligibility_update/quality_baseline_update: bounds under adversarial inputs, alpha semantics, order of baseline update vs delta (does q_ema update use pre- or post-step baseline; double-update per turn?).
2. Timing/credit semantics: dialogue_quality is LAGGED feedback (turn N+1 carries quality about turn N). phi is updated at takeover time of THIS turn. When quality for turn N arrives at N+1, phi already leaked (gamma=0.6) AND absorbed turn N+1's own |a| BEFORE or AFTER the quality step? Trace the exact call order in ResonanceSpine.process: assessment path (_apply_assessment_to_engine -> apply_affect_takeover -> phi update) vs dialogue_quality hook — which runs first in one process() call? Does turn N+1's activity contaminate turn N's credit?
3. Gating: any path where learning happens with plasticity off / takeover off / PEL on? set_affect_params preserving learned gain — is that right when personality LEGITIMATELY changes tiers? _effective_gain fallback when plasticity flips off after learning: does stale learned gain leak?
4. Persistence: byte-parity of snapshots when plasticity off; restore clamp correctness; e_ver/affect_gain interplay; what happens when n_dims != 8 (pro/max) — lists sized n_dims vs N_DIMS=8 mismatch in _affect_phi init ([0.0]*n_dims) vs eligibility_update (N_DIMS)?
5. Config threading: verify all 5 runtime call sites + kernel boot/restore + both spines actually pass affect_plasticity (grep).` },
  { key: 'flags-off-parity', prompt: `${COMMON}
LENS: flags-off byte-identity for the WHOLE A-track diff. The branch's headline claim: all flags default False => byte-identical behavior AND byte-identical persisted snapshots. Attack:
1. Construct a deterministic driver (random.seed(0), PYTHONHASHSEED=0) at pre-A-track commit c49b2f9 (git worktree) vs HEAD, all flags off: snapshot JSON must be byte-identical. Actually run this comparison.
2. Prompt parity: engine._assess with default config must send the EXACT pre-A.1 system prompt (assert string equality against the old constant from git show c49b2f9:sylanne_core/assessor.py).
3. Any new dict keys / state fields that leak into snapshots or Surface with flags off (affect_gain, intent, etc.).` },
  { key: 'harness-memo-honesty', prompt: `${COMMON}
LENS: A.4 harness methodology & memo honesty (docs/design/affect-calibration-memo.md, experiments/exp02_warmth_calibration.py). Attack:
1. The D1 headline finding: "a single zero-event step drags base to the MLP attractor (+0.166 tension/+0.242 repair) and h priors are invisible overnight". Reproduce it. Is the harness methodology sound: does _fight timing make sense (steps at 60s apart advancing _e_last_wall_ts), does scenario_overnight measure what it claims, is the h_scale monkeypatch actually effective (or does it silently not propagate — check whether half_lives reads _H_BASE_MIN at call time), is comparing against equilibrium(traits, 0.5) the right reference?
2. Scars formed during _fight: wound_risk=0.75 > threshold 0.7? Does the fight actually inject wounds via apply_affect_takeover (NO — wound injection lives in the spine assessor path, not in apply_affect_takeover!) — so does the harness UNDERSTATE scar stickiness effects, and is the memo honest about that?
3. The memo's numeric claims vs harness output — any mismatch or cherry-pick. Are D2/D3 options factually accurate about the code (R hardcoded 0.5 everywhere; normalize_personality never backfills Sylanne-Six; drift_sylanne_traits zero call sites)?` },
]

phase('Attack')
const results = await parallel(LENSES.map(l => () =>
  agent(l.prompt, { label: `attack:${l.key}`, model: 'sonnet', effort: 'high', schema: FINDINGS })))
const out = {}
LENSES.forEach((l, i) => { out[l.key] = results[i] })
return out