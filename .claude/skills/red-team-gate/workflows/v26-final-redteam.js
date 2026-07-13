export const meta = {
  name: 'v260-final-redteam',
  description: 'Adversarial review of the full v2.6.0 affect-dynamics implementation diff, fable5 final verdict',
  phases: [
    { title: 'Review', detail: '5 adversarial lenses over the diff' },
    { title: 'Verify', detail: 'adversarially verify each finding' },
    { title: 'Judge', detail: 'fable5 synthesis + verdict' },
  ],
}

const REPO = 'G:/SylannEngine'
const BASE = 'bdf967b'  // last pre-v2.6 commit (T1 slice-2); v2.6 work is BASE..HEAD

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          claim: { type: 'string', description: 'the defect, one sentence' },
          failure_scenario: { type: 'string', description: 'concrete inputs/flags -> wrong behavior' },
        },
        required: ['severity', 'file', 'claim', 'failure_scenario'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'UNCERTAIN'] },
    severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
    reasoning: { type: 'string' },
    fix_hint: { type: 'string' },
  },
  required: ['verdict', 'severity', 'reasoning'],
}

const CONTEXT = `Repo ${REPO}, branch feat/v26-affect-dynamics. The v2.6.0 affect-dynamics
work is the commit range ${BASE}..HEAD (10 commits: docs upgrade-path, then Phase-0,
T1-completion, T-Persist, T4, T2, T3, T3-silence, T6, T5). Read the plan at
docs/design/v26-upgrade-path.md for the intended contract.

KEY DESIGN CLAIMS TO ATTACK (do not take on faith — verify against code):
- Every stage ships behind a DEFAULT-OFF config flag; with all flags off the engine is
  claimed BYTE-IDENTICAL to baseline (778 tests green). Flags: affect_dynamics_enabled
  (T1 shadow), affect_v26_takeover (T3, writes base + silence drive + label-in-fragment),
  affect_slowchannel_enabled (T5 personality drift).
- E == ScarredState.base is tanh (-1,1); E-law math assumes [0,1]; a Phase-0 adapter
  bridges them. decay is affine-equivariant (remap Phi_eq only); saturating_update is NOT.
- T3 decay-at-TOP-of-step (before event evolution); takeover writes base, fail-closed to
  legacy hand-rules on error.
- T5 slow channel: poignancy leaky bucket -> reflection -> anchor-rebound macro drift,
  committed atomically (snapshot ring BEFORE mutate, restore on failure); TraitMemory.anchor
  is immutable; drift bounded by the existing tick cap.
- T-Persist: feedback() no longer zeroes _last_step_time (behavior change on legacy path);
  cold-load hoisted via asyncio.to_thread.

Useful commands: \`cd ${REPO} && git diff ${BASE}..HEAD -- <path>\`, \`git log --oneline ${BASE}..HEAD\`.
Read the actual source in sylanne_core/compute/. Focus on REAL defects with a concrete
failure scenario, not style. Return [] if a lens finds nothing real.`

const LENSES = [
  {
    key: 'byte-identical',
    prompt: `${CONTEXT}\n\nLENS: FLAG-GATING / BYTE-IDENTICAL. Attack the claim that every OFF path is
byte-identical to baseline. Hunt for: any v2.6 code that mutates state / changes output even when
its flag is off; to_dict keys added unconditionally (snapshot format drift); the _e_ver bump and
_affect_decay call in ScarredState.step() running when affect is off; TraitMemory.anchor added to
to_dict for EVERYONE (is that truly harmless?); the silence_drive added to the bifurcation max()
(is max(...,0.0)==max(...) actually guaranteed — are all other drives provably >=0?); the
feedback() _last_step_time fix (a REAL behavior change — is it correct and are there callers that
relied on the old zeroing?). Cite file:line. Read scar_algebra.py, personality.py,
resonance_integration.py, prompt_surface.py, kernel.py.`,
  },
  {
    key: 'elaw-math',
    prompt: `${CONTEXT}\n\nLENS: E-LAW MATH / DOMAIN. Attack the numerical correctness. Verify:
to_unit_interval/from_unit_interval are truly inverse and bounded; the decay affine-equivariance
shortcut (remap Phi_eq only, keep base native) is EXACTLY equal to full round-trip — or find an
input where it diverges; saturating_update MUST round-trip (find a case where the code skips it);
T3 takeover decay-at-top ordering vs the MLP/PEL event evolution (does decaying base then MLP-ing
it double-process or erase the event? is that the intended hybrid or a bug?); half_lives/equilibrium
are fed the right frames; NaN/inf handling. Read affect_dynamics.py, affect_projection.py,
scar_algebra.py (_affect_decay, apply_affect_takeover, apply_affect_appraisal_shadow).`,
  },
  {
    key: 'slowchannel-atomicity',
    prompt: `${CONTEXT}\n\nLENS: SLOW-CHANNEL ATOMICITY / IRREVERSIBILITY (Gate C). Attack slow_channel.py
+ personality.py. Verify: the ring snapshot is taken BEFORE any mutation and the restore on failure
is complete (does compute_embodiment_drift mutate anything the snapshot doesn't capture — e.g.
OscillationDetector freeze state, DriftAttribution records, _drift_tick? are those left corrupted
after a rollback?); TraitMemory.from_dict restore is faithful (fast_ema/slow_ema/set_point/anchor);
anchor is truly immutable (never written after __init__); the drift is bounded by the cap; the
appraisal->trait map + reflection constants can't produce runaway/NaN; poignancy retained-for-retry
after failure doesn't cause an infinite re-fire loop. Read slow_channel.py, personality.py
(TraitMemory, compute_embodiment_drift), resonance_integration.py/_drift_embodiment.`,
  },
  {
    key: 'threading',
    prompt: `${CONTEXT}\n\nLENS: THREADING / PERSISTENCE / RESTORE. Verify the flags reach every place
they must and survive restore. Trace affect_enabled / affect_takeover / affect_slowchannel from
SylanneConfig -> engine._build_host -> SylanneAlphaHost -> AlphaRuntime (all 5 boot/restore calls)
-> AlphaKernel.boot/restore -> spine ctor -> (VoidScarEngine ->) ScarredState / SlowChannel. Find
any dropped kwarg, any restore path (from_dict / _restore_pel_after_scar) that forgets to re-supply
affect params or the takeover/slowchannel flag, any __slots__ missing a new attribute (AttributeError
risk), any snapshot round-trip that loses e_last_wall_ts/e_ver/anchor. Read engine.py, host.py,
runtime.py, kernel.py, computation_spine.py, resonance_integration.py, void_scar_engine.py,
scar_algebra.py.`,
  },
  {
    key: 'test-adequacy',
    prompt: `${CONTEXT}\n\nLENS: TEST ADEQUACY. Attack the tests (tests/test_affect_*.py + the fixed
test_axiom_conformance expression-decay test). Find: tests that assert something vacuous or trivially
true; claims in commit messages / the plan that NO test actually covers (e.g. is "fail-closed to
hand-rules on takeover error" really exercised end-to-end? is the decay-at-top ORDERING tested? is
the byte-identical-when-off claim tested by an actual golden/parity comparison or just "no crash"?);
parity tests that would pass even if the shadow DID leak into base; missing coverage for restore/
persistence of the new fields. Read all tests/test_affect_*.py and the source they cover.`,
  },
]

phase('Review')
const reviewed = await parallel(
  LENSES.map((L) => () =>
    agent(L.prompt, { label: `review:${L.key}`, phase: 'Review', schema: FINDINGS_SCHEMA, model: 'sonnet', effort: 'high' })
      .then((r) => ({ lens: L.key, findings: (r && r.findings) || [] }))
  )
)

const allFindings = reviewed.filter(Boolean).flatMap((r) => (r.findings || []).map((f) => ({ ...f, lens: r.lens })))
log(`Review surfaced ${allFindings.length} candidate findings across ${reviewed.length} lenses`)

phase('Verify')
const verified = await parallel(
  allFindings.map((f) => () =>
    agent(
      `${CONTEXT}\n\nAdversarially VERIFY this finding against the real code. Try hard to REFUTE it\n` +
      `(is the claimed failure actually reachable given the flag gating and fail-closed guards?).\n` +
      `Read the cited file:line and surrounding context.\n\nLENS: ${f.lens}\nSEVERITY(claimed): ${f.severity}\n` +
      `FILE: ${f.file}:${f.line || '?'}\nCLAIM: ${f.claim}\nSCENARIO: ${f.failure_scenario}`,
      { label: `verify:${f.lens}:${(f.file || '').split('/').pop()}`, phase: 'Verify', schema: VERDICT_SCHEMA, model: 'sonnet', effort: 'high' }
    ).then((v) => ({ ...f, verdict: v }))
  )
)
const survivors = verified.filter(Boolean).filter((f) => f.verdict && f.verdict.verdict === 'CONFIRMED')
log(`${survivors.length}/${allFindings.length} findings CONFIRMED after adversarial verification`)

phase('Judge')
const judge = await agent(
  `${CONTEXT}\n\nYou are the FINAL adversarial judge for the v2.6.0 affect-dynamics implementation.\n` +
  `Below are the findings that survived independent adversarial verification. Assess the OVERALL\n` +
  `implementation quality and correctness. Produce: (1) a ranked list of the genuine must-fix issues\n` +
  `(blocker/major only) with the single most important one first, each with a one-line fix; (2) a\n` +
  `crisp overall verdict — is the v2.6.0 plan faithfully and correctly implemented, safe to keep on\n` +
  `the branch (all flags default-off), and what (if anything) MUST be fixed before anyone flips a\n` +
  `flag on. Be direct; do not rubber-stamp; if the survivors are all minor/nits, say the\n` +
  `implementation is sound and say so plainly.\n\n` +
  `SURVIVING FINDINGS (JSON):\n${JSON.stringify(survivors, null, 2)}\n\n` +
  `ALL RAW FINDINGS COUNT: ${allFindings.length}; CONFIRMED: ${survivors.length}.`,
  { label: 'judge:fable5-final', phase: 'Judge', model: 'fable', effort: 'high' }
)

return {
  counts: { raw: allFindings.length, confirmed: survivors.length },
  survivors: survivors.map((f) => ({ severity: f.verdict.severity, lens: f.lens, file: f.file, line: f.line, claim: f.claim, fix: f.verdict.fix_hint })),
  verdict: judge,
}
