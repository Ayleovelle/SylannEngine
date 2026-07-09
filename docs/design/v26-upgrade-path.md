# v2.6.0 Affect-Dynamics — Definitive Upgrade Path (Implementation Contract)

Canonical repo `G:/SylannEngine`, package `sylanne_core`, branch `feat/v26-affect-dynamics`. Grounded against real `file:line`; folds every red-team BLOCKER/MAJOR. ⚠ marks a surviving attack + required fix.


> **Provenance / 复核戳**：本文由 canonical 落地对账 workflow 产出（9 子系统各自 grounding + 独立红队 + 合成），
> 主循环已亲手复核三条承重更正：(1) `base` 值域 tanh **(-1,1)** 非 [0,1]（`scar_algebra.py:391,397`；PEL 路径 :514）；
> (2) canonical **无** `fragment.py`/`integration.py`，渲染在 `prompt_surface.py` 且为无条件拼接（无预算/无驱逐）；
> (3) `_DEFAULT_SPINE = ResonanceSpine`（`kernel.py:50`），`ComputationSpine` 仅测试/实验用。
> 配套原契约：`docs/design/v26-affect-dynamics-design.md`。本文**更正**其 §0.5 未覆盖的 fork-drift
> （§2.1 E 值域 / §5 记忆库 / §6.2 fragment / §4.2 dialogue.py，见下方对账表）。
> 日期 2026-07-10 · 分支 `feat/v26-affect-dynamics` · **未 commit，待你审阅**。

---

## 0. BASELINE — what is already done

**Committed (pure functions, ZERO wiring):**
- `sylanne_core/compute/affect_projection.py` (T1 slice-1, `48d93ce`): `project_appraisal(v,a,w,intent)→a_k[8]`, intent normalizer, NaN/inf sanitize. Tests `tests/test_affect_projection.py`.
- `sylanne_core/compute/affect_dynamics.py` (T1 slice-2, `bdf967b`): `decay` (half-life lerp to Φ_eq), `saturating_update`, `equilibrium`/`half_lives`/`gain_vector`, `validate_gain`/`validate_scalar_params`. Tests `tests/test_affect_dynamics.py`.
- Audit verdict: **formulas/signs/clamps/dim-order/trait-keys all correct vs design §2.2/§3.1/§3.3/§8.** No bugs in the pure math. **Zero call sites** outside their own tests.

**Not wired (unchanged):** `ScarredState.step()` legacy timestamp healing; both assessor write-points; no `(E,last_ts,ver)` persistence; no output-contract/fragment change; no memory coupling; no slow-channel/drift; `SylanneConfig` has no new fields; `observe()` still reads old base.

**E IS `ScarredState.base`** — 8-dim, order `_DIM_NAMES` = `(warmth,arousal,valence,tension,curiosity,repair_pressure,expression_drive,boundary_firmness)` @ `void_scar_engine.py:256-265`; class @ `scar_algebra.py:113`; read via `observe()` @ `void_scar_engine.py:267` → `scar_algebra.py:627`. **Single source. Upgrade in place. Never a parallel EState.**

### Reconcile verdict on design §0.5 canonical mapping

| Design claim | Status | Correction (grounded) |
|---|---|---|
| E = `ScarredState.base`, dim order, `observe()` single read | ✅ matches | — |
| §0.5 pt2 decay "replaces" timestamp healing @ `scar_algebra.py:556-563` | ⚠ **drifted** | That block is inside `if heal:` (line 550) and only advances **scar STAGE**, never touches `base`. It is a *different* mechanism sharing only `_last_step_time`. Do not conflate; do not double-clock. |
| **E ∈ [0,1]^8** (design §2.1, T1 code assumes) | ❌ **WRONG** | `base` is tanh-bounded **(-1,1)** (`scar_algebra.py:391-397` `_evolve_base`; `pel_core.py:240`; valence goes negative `resonance_integration.py:650`). **Domain-adapter is a hard T1 prerequisite** (Phase 0 below). |
| §2.1 "async KV `host.load` prefetch / put_kv/get_kv" | ❌ **WRONG** | No KV store, no async in this layer. `host.py:96-102`/`runtime.py:56-101` are synchronous file IO. Reinterpret as `asyncio.to_thread` hoist of the one blocking cold-load. |
| §3.4 assessor race needs new CAS | ⚠ **drifted** | Per-session `asyncio.Lock` (`engine.py:830-833`) + scalar-only assessment across the pre-lock await already close the RMW race. Real residual gap = timestamp monotonicity in `step()`. |
| §4.2 `s`(self_score) @ `dialogue.py:189` | ❌ **WRONG** | `dialogue.py`/`turn_runner.py` do not exist. `s` = host-supplied `dialogue_quality` threaded `kernel.py:265-279 → spine.process → personality.py:65-66,251-266`. |
| §5 memory recall "reserved emotion slot" (`memory-recall-humanlike-redesign`) | ❌ **WRONG/MISSING** | That note lives under **downstream plugin** `G--Sylanne-next`. Canonical has **no per-item scored long-term memory store** (`body.py:258` = signal counts; `shadow_memory.py` = advisory, non-persistent). Nothing to wire. |
| §6.2 fragment salience/`_pack_within_budget` eviction; `fragment.py`/`integration.py` | ❌ **WRONG** | Those files **never existed** in canonical (any branch, any commit). `render_prompt_fragment` (`prompt_surface.py:110-126`) is unconditional string concat — no budget, no eviction. §6.2 failure mode cannot occur here. |
| §0.5 pt4 `pad_interop.py`/`contagion.py` cross-fed / out of scope | ✅ matches | `contagion.py` is dead 3-dim DeGroot. **But** `Surface.pad.label` (`adapter.py:175-229`→`pad_interop.py:424-463`→`types.py:175-186`) is an **already-live, already-broken** categorical labeler — reconcile before T2 Gate B. |
| §0.5 pt5 G/κ/μ/ρ → `SylanneConfig` typed fields | ⚠ drifted | `validate_gain`/`validate_scalar_params` already shipped as standalone funcs (reuse, don't duplicate). κ/μ are **personality functions**, not flat config scalars (design attack #7 already resolved). |
| ResonanceSpine is live default | ✅ matches | `kernel.py:47-53` `_DEFAULT_SPINE=ResonanceSpine`; `ComputationSpine` is test/experiment-only. Any fix that only touches ComputationSpine reaches **0% of production**. |

---

## 1. PHASE 0 — shared prerequisite (blocks T1-completion, T3)

**Scope:** add the [0,1]↔(-1,1) domain adapter that all E-law wiring needs. Without it, feeding raw `base` into `decay`/`saturating_update` (which assume [0,1]) is semantically wrong and Gate-A shadow telemetry measures noise.

- **Touch** `sylanne_core/compute/affect_dynamics.py`: add pure `to_unit_interval(base)=[(x+1)/2…]`, `from_unit_interval(e)=[2x-1…]`.
- **Note (proven exact):** `decay` is an affine lerp ⇒ affine-equivariant, so `[2y-1 for y in decay(to_unit(base),to_unit(Φ_eq),h,dt)] == decay(base, 2Φ_eq-1, h, dt)` — remap Φ_eq only, or round-trip base; both exact. **`saturating_update` is NOT affine-equivariant** (hard-codes 0/1 bounds) — it MUST use `to_unit_interval`/`from_unit_interval`, never the shortcut.
- **Tests:** round-trip identity + boundedness for x∈[-1,1]; affine-equivariance property test for `decay`.
- **Gate A.** Rollback: delete funcs (no callers).

---

## 2. STAGED PATH (dependency chain, respects §11)

### T1-COMPLETION — E-law shadow (decay + appraisal + persistence + config flag)
**Gate A (shadow — MUST NOT write `base`).**

**Scope:** activate the committed pure functions as a *parallel shadow* computed & logged, plus persistence triple + enable flag. No `base` mutation, no prompt entry, no drift.

**Insertion points:**
- `scar_algebra.py:ScarredState.__slots__/__init__` — add `_affect_enabled:bool=False`, `_affect_traits:dict`, `_relationship:float=0.5`, `_affect_shadow_base:list|None=None`, `_e_last_wall_ts:float`, `_e_ver:int`.
- `scar_algebra.py:ScarredState.step()` — inside existing `if timestamp>0 and self._last_step_time>0:`, when `_affect_enabled`, compute `dt_secs=timestamp-_last_step_time` **once** (shared with the untouched scar bonus-tick loop), remap Φ_eq via Phase-0 adapter, write result to **`_affect_shadow_base`** and `logger.debug` — ⚠ **BLOCKER (e-core #1): never assign `self.base`.** Gate A is shadow-only per design.md:272-274.
- `scar_algebra.py:ScarredState.to_dict/from_dict` (690-749) — add `ver`/`e_last_wall_ts` via `.get(key,default)` idiom (precedent `last_step_time` @708/737). **Do NOT persist traits/relationship/shadow_base** (re-supplied via `apply_personality` on restore, mirrors PEL must-fix #3).
- `scar_algebra.py` — new `set_affect_params(traits, relationship=0.5)` mirroring `set_pel_priors` (270-282).
- `computation_spine.py:apply_personality` (~403) + `resonance_integration.py:apply_personality` (~262) + restore mirrors (`computation_spine.py:1239`, `resonance_integration.py:313`) — call `set_affect_params`.
- Both assessor write-points — append shadow appraisal (see below), computed into `_last_affect_shadow` only.
  - `computation_spine.py:apply_assessment` (526-580): after unchanged rules.
  - `resonance_integration.py:_apply_assessment_to_engine` (599-668): inside existing `if direct_affect:` guard (646), keep `_cached_observe=None` (668) firing.
  - ⚠ **MAJOR (assessor #4):** add `_last_affect_shadow` to **both `__slots__` tuples** + init `None`, else first tick `AttributeError`.
  - ⚠ **BLOCKER (t1-audit #1):** wrap every shadow call in `try/except Exception: log; continue`. Write-points (`computation_spine.py:787`, `resonance_integration.py:439-440`) are unguarded on the live per-turn path; a bug in trait plumbing / out-of-range gain crashes the turn. Add fail-safe test (malformed traits + bad gain → no escape, old path intact).
- `config.py:SylanneConfig` (~257) — add `affect_dynamics_enabled:bool=False` (mirror `pel_core_enabled` docstring 226-230). No range check.
- `engine.py` (~844) → `kernel.py`/`void_scar_engine.py:104-120`/`host.py`/`runtime.py` — thread `affect_enabled` 1:1 like `pel_enabled`. ⚠ **open dep:** confirm `SylanneConfig` actually reaches `ScarredState`'s owner (verified path: `engine.py:842-844 pel_core_enabled → VoidScarEngine pel_enabled`).
- host.load prefetch → **use `asyncio.to_thread`, not "async KV"** (see T-Persist).

**In-place / anti-shadow-E:** shadow value is *diagnostic only*; the authoritative E remains the single `base`. This is not a parallel-E core — it is a comparison buffer that is discarded, never read by `observe()`.

**Zero-behavior-change proof:** `affect_dynamics_enabled=False` ⇒ new branches never execute ⇒ `step()`/write-points byte-identical (golden snapshot before/after). With flag True, `base` still never written ⇒ `observe()` bit-identical (parity test, fixed seed). Full ≥355 suite green both flag states.

**Tests:** golden byte-identical (flag off); shadow populated+finite (flag on) but `base` unchanged; `to_dict/from_dict` round-trip w/ old snapshot (missing keys → defaults); domain-adapter reuse; fail-safe exception isolation; ⚠ **MAJOR (assessor #3):** assert `equilibrium()` on real live personality — `warmth_bias`/`curiosity`/`sovereignty_guard` are Sylanne-Six keys **not populated** by `normalize_personality` (`personality.py:727-747` only maps Big-Five via `_LEGACY_MAP`); they fall back to 0.5 forever. **Required fix:** either wire `drift_sylanne_traits()` (`personality.py:614`, currently zero call sites) into the live tick, or add `_LEGACY_MAP`-style alias fallback in `affect_dynamics._trait`, or get explicit sign-off that warmth/curiosity/boundary equilibrium is pinned to 0.5 for T1.

**Rollback:** flip `affect_dynamics_enabled` False / revert field; no persisted trait state; old snapshots load (only additive defaulted keys).

**Blast radius:** `void_scar_engine.py:299 expression_drive()` reads `base[6]`; `computation_spine.py:1146-1164`/`resonance_integration.py:1142-1151 pad_project()`; `hgt.py:971-997 build_tokens_from_spine` (`base[dim_i]` → attention/MoE, called `computation_spine.py:832`/`resonance_integration.py:465`) — ⚠ **MAJOR (assessor #1):** all read raw `base`; **inert at Gate A** (base unwritten) but become live blast at T3. `observe()`/`_cached_observe` cache contract unchanged.

---

### T-PERSIST — concurrency & cold-load (parallelizable with T1-completion, own PR)
**Gate A.**

**Scope:** `_e_ver` monotonic field (dormant), cold-load hoist, timestamp-monotonicity guard.

**Insertion points:**
- `_e_ver` increment in `step()` on `base` mutation; `to_dict/from_dict` lazy default.
- `engine.py:_get_or_create_host` (835-846) — hoist blocking `SylanneAlphaHost(...)`→`AlphaRuntime.load()` (`host.py:96-102`, sync `read_text`+`json.loads`) off event loop via `asyncio.to_thread`. ⚠ **MINOR (persist #4):** drop the "double-checked insert" — per-session `asyncio.Lock` already serializes; state what future refactor it guards or omit.
- ⚠ **BLOCKER (persist #1/#2):** the proposed monotonicity guard on `_last_step_time` was justified against the wrong sites. The guarded block is inside `if heal:` (`scar_algebra.py:550`); the two cited sites (`computation_spine.py:552`,`resonance_integration.py:631`) pass `heal=False` and never reach it. **Real callers:** `void_scar_engine.py:204` (main, `heal=True`, real ts) and `void_scar_engine.py:351 feedback()` (`heal=True`, **`timestamp=0.0` hardcoded**). A bare `timestamp>=_last_step_time` guard changes `feedback()`'s `_last_step_time` zeroing → flips next real step's bonus-heal eligibility (exercised by `tests/test_expression_policy_saddle.py:197-208`). **Required fix:** special-case `timestamp<=0` as "no time signal, leave `_last_step_time` untouched" (correct pre-existing-bug fix, documented as intentional), OR scope the `>=` guard to the real-timestamp main-step path only. Add before/after `_last_step_time` regression test across `process()→feedback()→process()`.
- ⚠ **MINOR (persist #3):** periodic flush fsync (`host.py:174-216`→`runtime.py:110-123`, every ~8 ticks/5s) still blocks hot path — either add to open-risks explicitly or extend `asyncio.to_thread` to `_flush()`. Do not claim "hot path is zero-IO".

**Blast radius (corrected — 6 step() sites, not 2):** `void_scar_engine.py:197`(wound,heal=F), `:204`(main,heal=T), `:351`(feedback,heal=T,ts=0); `computation_spine.py:552`, `resonance_integration.py:631` (both heal=F). Persistence chain `ScarredState.to_dict`→`VoidScarEngine.to_dict:354`→spine.to_dict→`AlphaKernel.snapshot:348`→`AlphaRuntime.save_snapshot`.

**Note:** cross-process multi-writer is an **accepted non-goal** (`engine.py:661-667`). `ver` lands dormant; do NOT build file-CAS.

**Zero-behavior-change:** additive `ver` unread; guard unreachable on monotonic traffic *after* the feedback fix. Two separate commits (ver / hoist+guard). Rollback = git revert, no migration.

---

### T2 — output-contract label (shadow diagnostic)
**Gate A.**

**Scope:** categorical emotion label from E via LUT + hysteresis, surfaced in **diagnostics only**. **No PINNED/eviction work** — that mechanism does not exist in canonical (§6.2 WRONG).

**Insertion points:**
- New pure `sylanne_core/compute/affect_output_contract.py`: `quantize`, `EMOTION_LUT`, `HysteresisState`, `resolve_label(e_key,prev,θ_h)` (cross-bucket-with-margin). Zero callers first (mirror T1 posture).
- `prompt_surface.py:render_diagnostics` (~244-302) — add ONE key `affect_label_shadow` from `kernel._computation_emotion_overlay()` (`kernel.py:615-622`, reads `observe()`). **Do not touch** `render_prompt_fragment` (27) or `render_host_payload` (174).
- ⚠ **MAJOR (output #1):** `AlphaKernel` is `@dataclass(slots=True)` (`kernel.py:98-99`) with **no `__init__`**. Declare hysteresis as a real field `_affect_label_state: Any = field(default=None, repr=False)` next to `_affect_debt` (`:133`); decide `restore()` reset (mirror `:191-198`). Ad-hoc `self.x=` raises `AttributeError`.
- ⚠ **MAJOR (output #2):** reconcile with **already-live** `Surface.pad.label` (`adapter.py:175-229`→`pad_interop.py:424-463`→`types.py:175-186`, re-exported `__init__.py:39,59`, reached via `engine.py:560/574/1033`). It is positionally cross-fed (E dims → Plutchik-8 W-rows) and **already wrong in production** (design §0.5 pt4 rules it out of scope). Add to blast radius + a reconcile note; **before T2 Gate B, explicit decision:** `resolve_label` supersedes / deprecates / coexists with `pad.label`. Do not ship a second disagreeing labeler silently.
- ⚠ **open risk:** hysteresis must mutate ≤once per real tick; `kernel.surface()` can be polled off-tick (WebUI). Guard on `kernel.turns`.
- ⚠ **open risk:** §6.1 never names which 4 of 8 dims are the LUT key — product/writer sign-off before authoring the ~24-word vocab.

**Blast radius:** `render_diagnostics` sole in-repo reader = `kernel.py:344 surface()['diagnostics']`; ⚠ **MINOR (output #3):** also propagates via `kernel.tick()["surface"]` (`:234/:313`) → `host.py:184-200` on every request (additive key, no existing key touched). `adapter.py:26-51 to_surface()` does NOT read `diagnostics` (SDK path unaffected — assert with a Surface-equality test).

**ZBC:** structural — additive dict key can't reach `prompt_fragment`. Golden byte-identical `render_prompt_fragment`/`render_host_payload['prompt_fragment']`; deep-equal pre-existing diagnostics keys. Rollback: revert 2 additive commits.

---

### T3 — E-core takeover + warmth calibration
**Gate B (takeover). Depends on: T1-completion, Phase 0.**

**Scope:** E-law becomes authoritative — write `base` in place; replace intent hand-rules with saturating-update; decay at read-time.

**Insertion points:**
- `scar_algebra.py:step()` — ⚠ **BLOCKER (e-core #2):** move decay application to the **TOP** of `step()` (operate on prior-call `base` before this call's event evolution `_evolve_base`/PEL @501-521), so wall-clock settle precedes event write-back (design §9:321/324). Inserting decay *after* event evolution erases a fresh message's response after silence (2h gap → arousal ×0.0625) and is the double-decay taboo (design.md:19). Behind `affect_dynamics_enabled` (now promoted off shadow).
- `computation_spine.py:565-576` + `resonance_integration.py:648-656` — replace intent/nudge stamps with `base[:] = from_unit_interval(saturating_update(to_unit_interval(base), a_k, gain))` behind `affect_v26_takeover`. Wound inject (`547-552`/`625-631`) and void-pressure untouched (→T5).
- ⚠ **MAJOR (assessor #2 — fail-closed):** on `validate_gain`/shadow-calc exception during takeover, **fall through to OLD hand-rule branch for that tick** — never assign undefined/stale `_last_affect_shadow` into `base` (read same-tick by `observe()` @`resonance_integration.py:441`). Add Gate-B test: `gain_vector` raises mid-tick → `base` == old-rules output (not stale, not crash).
- `affect_dynamics.equilibrium`/`half_lives`/`gain_vector` — promote priors to `SylanneConfig` overrides **only if** calibration needs runtime tuning (`affect_gain_base`, `affect_half_life_base_minutes`, validated by `validate_gain`/new `validate_half_lives`). Signature change `equilibrium(traits, relationship, eq_domain=None)` co-designed with config field shape (tuple[8], `_DIM_NAMES`-aligned). Φ_eq domain `[0.15,0.85]` stays a code constant (anti-absorbing-state invariant).

**In-place / anti-double-clock:** decay + event-evolution both mutate the single `base`, sequenced read-then-write, `dt_secs` computed once. Scar-stage bonus-tick loop (`556-563`) is orthogonal, unchanged.

**ZBC obligation:** this is an **intended behavior change** — not "zero". Gate-A shadow diff (from T1) must run N rounds first, diffing `observe()` **and** `expression_drive()` (`:299`) **and** `pad_project()` **and** `hgt build_tokens` (`hgt.py:971`) before promotion. Migration test documents old-vs-new deltas at historical fixed points (`w>0.7`, `v<-0.5/>0.5`, intent `撒娇`/`生气`, `arousal>0.7`).

**Gate:** B. Warmth behavioral calibration (§7) is the acceptance bar.

**Rollback:** flip `affect_v26_takeover` False → old rules resume mutating same `base` (valid (-1,1)); no snapshot corruption.

**Blast radius (now LIVE):** `observe()`, `expression_drive()`, `pad_project`, `hgt.py:971-997` attention/MoE routing, phase-transition urgency. Document HGT routing shift explicitly.

---

### T3-SILENCE — wall-clock silence (folded into T3 window)
**Gate A→B.**

**Scope:** replace `phase_transition.py` tick-counter with true wall-clock silence; feed the **live** ResonanceSpine expression path.

**Insertion points:**
- `phase_transition.py:PhaseTransitionExpression` — add `_last_activity_ts`, `mark_activity(now)`, `wall_silence_seconds(now)` (pure, **uncapped** — do NOT reuse the `[0.1,10.0]`-clamped dt at `computation_spine.py:662`/`resonance_integration.py:396`), `classify_silence_texture` wrapper activating dead `void_calculus.SilenceTexture.classify` (`void_calculus.py:21`).
- ⚠ **MAJOR (silence — structural):** `kernel.py:47-53` makes ResonanceSpine sole live spine; it **never calls** `PhaseTransitionExpression.accumulate/should_express/express`. Scope **must** extend into `resonance_integration.py:_update_expression` (701-799) / `express` (801-812) — add `silence_drive` as 4th OR-gate in `bifurcation_drive max(...)` (Gate B). Wiring only `phase_transition.py` reaches 0% of production.
- ⚠ **MAJOR (silence — dead urgency line):** `phase_transition.py:242` (the one genuine `silence_duration` reader) is itself unreachable — `kernel.tick()` never calls `.express()`, and no `_build_result` exposes `urgency` (`computation_spine.py:1429-1440`, `resonance_integration.py:951-974`). Swapping it changes nothing observable. **Either** deprioritize it, **or** add `kernel.tick()`/`_build_result` surfacing as explicit new blast radius.
- ⚠ **MAJOR (silence — vacuous test):** `tests/test_axiom_conformance.py:490-509` is tautological (`state()` has no `drive`/`accumulator` key → `.get(...,0.0)` always 0.0 → `0.0<=0.01` always true). **Fix the test** (assert on `pressure`/`silence_duration`) as part of this commit; do not count it as pre-existing equivalence coverage.
- ⚠ **MINOR:** `computation_spine.py:650 silence_lowers_threshold(dt=1.0)` hardcoded on skip path — note residual gap for future idle-ticker (deferred past 2.6.0, design:366).
- **Ordering hazard:** read `wall_silence_seconds(now)` **then** `mark_activity(now)` — dedicated ordering test.
- **Persistence:** consume T1's `_e_last_wall_ts` rather than growing a 2nd wall clock (sequencing dep on T1-completion).

**Note:** "single clock" is because kernel holds one spine per instance (`kernel.py:124`), not a shared object — each spine has its own `PhaseTransitionExpression`.

**Rollback:** Gate A additive methods (git revert). Gate B behind `wall_clock_silence_enabled:bool=False`.

---

### T4 — memory coupling (primitives only)
**Gate B. Depends on: T3.**

**Scope:** ship reusable pure math **only**; **no store to wire into** (§5 WRONG — canonical has no scored memory store).

**Insertion points:**
- New `sylanne_core/compute/memory_coupling.py` (or in `affect_dynamics.py`): `emotion_match(e_now,m_e)` (cosine, near-zero→0.0, wrong-length→ValueError), `contagion_blend(e,m_e,kappa)` (convex combo, bounded [0,1]^8).
- ⚠ **MAJOR (memory #1):** do **NOT** add flat `kappa:float` to `SylanneConfig` — κ is a **personality function** (design attack #7, headline principle line 32). `contagion_blend` takes an explicit `kappa` **argument**; when needed, add `kappa(traits)` alongside `equilibrium`/`gain_vector`, bound-checked via `validate_scalar_params`. Defer any config field.

**Blast radius:** none (zero call sites). **Organizational risk = PRIMARY open:** T4-as-designed needs a memory store that doesn't exist — flag-and-defer; do NOT wire downstream plugin's `MemoryItem` (SDK-not-stable rule).

**Rollback:** delete module (no callers).

---

### T5 — slow channel / drift (poignancy → reflection → macro-drift)
**Gate C (authority — irreversible memory writes). Depends on: T3.**

**Scope:** π leaky bucket, wall-clock reflection cooldown, fail-closed trigger, anchor-rebound trait drift, versioned rollback ring. **Host at `AlphaKernel`** (single choke point `kernel.py:284 _update_affect_debt`), not duplicated per spine.

**Insertion points:**
- `affect_dynamics.py` — pure `poignancy_update`, `poignancy_magnitude`, `reflection_ready`, `scarload_decay` (the §2.2 self-heal hook — `half_lives` @114-132 only *reads* scarload, nothing decays it), `q_dc`, `drift_step`, `validate_slowchannel_params`.
- `personality.py:TraitMemory` (119-179) — add **immutable `anchor`** slot (from `initial`), distinct from adaptive `set_point` (`:172-173` chases `value`). ⚠ **open risk:** wiring `anchor`→`set_point` reintroduces the z-gate "adaptive baseline chases signal" failure the design killed. `to_dict/from_dict` `.get('anchor', value)`.
- `personality.py:compute_embodiment_drift` (466-563) — additive `macro_deltas=None` param, merged into `pending` (503/537) **before** cap-scale (539-549), bypassing per-signal homeostatic resistance (520-526) so ρ isn't double-counted. Single write path preserved (cap/OscillationDetector/DriftAttribution/`TraitMemory.update`).
- `computation_spine.py:apply_assessment:547-552` + `resonance_integration.py:_apply_assessment_to_engine:625-631` — gate inline wound-inject behind `_slowchannel_active:bool=False`; when True skip inline, defer to kernel.
- `kernel.py:AlphaKernel` — `_update_slowchannel(assessment, now)` beside `_update_affect_debt`; new fields (dataclass `field(...)`, per output #1) `_poignancy`, `_pending_wound_mass`, `_reflection_count`, `_last_reflection_wall`, `_slowchannel_ring:deque(maxlen=5)`. Public `reflection_status()`, `commit_reflection(dialogue_quality_ema, s_ref, now)`.
- ⚠ **BLOCKER (drift #1 — atomicity):** `commit_reflection` mutates scar_state (irreversible) then later clears buffer. **Required:** pop/clear `_pending_wound_mass` into a local **before** `scar_state.step(...)`, wrap in `try/except` that self-restores from the ring snapshot on any post-mutation failure. Test: force raise inside `apply_macro_drift` → wound mass NOT re-replayed next commit.
- ⚠ **MAJOR (drift #2 — batching not equivalent):** single consolidated `wound_vec` at commit ≠ N live-paced `step()` calls (nonlinear `_evolve_base` `scar_algebra.py:511-521`; intervening main-steps skipped). "Zero-behavior-change" proven only for degenerate N=1. **Required:** either replay N individual `step(wound_i,…,heal=False)` in order, OR call it a reviewed behavior change with a non-degenerate N=3–5 vs live-paced test asserting bounded divergence + explicit sign-off. Not byte-identity.
- ⚠ **MAJOR (drift #3 — pin heal):** commit-time replay MUST pass `heal=False, timestamp=0.0` (matching `computation_spine.py:552`/`resonance_integration.py:631`). Omitting → `heal=True` default increments `_tick` (`scar_algebra.py:486`) + runs healing bonus. Test: replay does not advance `_tick`.
- ⚠ **MINOR (drift #4):** Γ-coupling wound path `void_scar_engine.py:191-198` fires every tick regardless of `_slowchannel_active`, feeding the same circuit breaker (`scar_algebra.py:537-545`) the batched replay lands on. Add to blast radius + breaker adversarial pass.
- ⚠ **MINOR (drift #5):** kernel mutating `engine.scar_state` is a **new layering decision** (kernel bypassing spine write-encapsulation), not the read-only `observe()` precedent. State plainly in PR.
- ⚠ **open (config dead-field trap):** `config.py:251 tick_drift_cap` is validated-but-never-read (`compute_embodiment_drift` uses module constant `_TICK_DRIFT_CAP=0.05` @`personality.py:61`). Every new field (`reflection_theta`, `reflection_cooldown_seconds`, `drift_eta`, `drift_rho`, appraisal weights) needs a **dedicated wiring test**, not just `__post_init__` range check — this is the warmth-0.005 dead-link failure mode.
- ⚠ **erratum:** `u` (drift direction unit vector) has no spec formula (§4.2/§8 prose only) — sign-off before impl.

**Fail-closed:** π/buffer mutated only inside `commit_reflection`'s guaranteed-atomic final step; host that never calls it (budget denied) leaves state untouched. **No LLM-budget mechanism exists in canonical** — engine exposes trigger/commit contract; budget-gating stays host responsibility.

**Rollback:** `_slowchannel_active=False` = today's inline behavior; state rollback = `AlphaKernel.restore(ring[i])` (existing classmethod `kernel.py:160-199`), survives restart via snapshot.

---

### T6 — output-contract Gate B splice (label into fragment)
**Gate B. Depends on: T2, T3.**

**Scope:** splice `resolve_label` output into the real `render_prompt_fragment` string. In canonical this is just "append label segment to the always-included list" (no eviction — §6.2 WRONG). Behind config flag. `affect_hysteresis_band`, `affect_fragment_floor_chars` added as representation-layer constants (config fields, no trait-function wrapping). Requires the T2 `pad.label` reconciliation decision resolved first.

---

## 3. RISK REGISTER (cross-cutting)

| Hazard | Where it bites | Owner stage | Guard |
|---|---|---|---|
| **Shadow-E (nobody reads it)** | any parallel E store; T1 shadow buffer never promoted; silence fix only touching test-only ComputationSpine; label diverging from live `pad.label` | T1-completion, T3, T3-Silence, T2 | Upgrade `base` in place; `observe()` single read; silence scope MUST reach `resonance_integration._update_expression`; reconcile `pad.label` |
| **Double-clock / double-decay** | decay after event-evolution (e-core #2); scar bonus-tick vs base decay sharing `_last_step_time` | T3 | decay at TOP of `step()`, one `dt_secs`, scar-stage loop untouched |
| **Fail-open on red-line (drift/memory)** | `commit_reflection` non-atomic (drift #1); Gate-B takeover writing stale/undefined base on gain failure (assessor #2); unguarded shadow crashing turn (t1-audit #1) | T5, T3, T1-completion | consume-then-mutate + ring self-restore; fall through to old rules; try/except log-continue |
| **Batching ≠ live pacing** | consolidated wound replay over nonlinear base (drift #2); wrong `heal=` (drift #3) | T5 | N-individual replay OR documented bounded-divergence sign-off; pin `heal=False,ts=0.0` |
| **Fragment eviction** | §6.2 premise (WRONG — no budget system) | T2/T6 | append-only; do not build PINNED floor in canonical |
| **Assessor async race / timestamp non-monotonic** | `feedback()` ts=0.0 zeroing (persist #1); RMW already lock-closed | T-Persist | special-case `timestamp<=0`; do not build CAS |
| **Config domain / dead-field** | κ as flat scalar (memory #1); `tick_drift_cap` validated-never-read pattern | T4, T5, T-Config | κ=personality function; per-field wiring test |
| **Domain [0,1] vs (-1,1)** | `base` is tanh; T1 code assumes [0,1] | Phase 0 (blocks T1/T3) | `to_unit_interval`/`from_unit_interval`; `saturating_update` MUST adapt (not affine-equivariant) |
| **Personality traits not populated** | Sylanne-Six keys → 0.5 forever (assessor #3) | T1-completion | wire `drift_sylanne_traits` / alias fallback / sign-off |
| **Slots dataclass** | `AlphaKernel` no `__init__` (output #1); spine `__slots__` (assessor #4) | T2, T1-completion | declare fields; extend `__slots__` |

---

## 4. SCOPE FENCES (explicit)

- **Downstream plugin migration DEFERRED** — SDK-not-stable rule (`feedback_no_premature_downstream`). Do NOT wire canonical into the vendored `G--Sylanne-next` fork, `MemoryItem`, or `fragment.py`/`integration.py` (which exist only downstream). §5 memory store and §6.2 eviction are downstream-only concepts.
- **DeterministicFusion retirement is 2.7, NOT 2.6** — out of scope this path.
- **Per-stage: own branch → PR into `next-gen`, NEVER `main`.** Each stage independently revertible.
- **No push / no merge / no tag / no PyPI until user explicitly says go** (`feedback_no_merge_without_go`). CI-green ≠ authorization.
- **Ruff E/F/W/I/UP/B/SIM line-100 py310 + mypy strict + `asyncio_mode=auto`** on every touched file; full ≥355 suite green (re-confirm actual count via `pytest --collect-only`) as the acceptance bar at every gate.
- **Gate discipline:** A = compute+log+visualize, no body write / no prompt / no persisted drift, N-round parallel diff. B = takeover behind flag, warmth calibration passed. C = irreversible authority, fail-closed + rollback ring mandatory.
