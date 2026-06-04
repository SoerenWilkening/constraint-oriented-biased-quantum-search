// CBQS core-change gate (see CLAUDE.md §3).
//
// Vets + verifies a change to faithfulness-critical code:
//   oracle accounting (SearchLib.c ctg, model.h::qtg_applications),
//   PRNG/seeding (solver_ctx.c, prng.c),
//   branching/bias math (Branching.h, solver_ctx.c setters),
//   phase transitions (SearchLib.c stage machine, solver.c CSearch_*).
//
// Lean gate: one proposer (test-first plan) -> one adversarial reviewer (refute) -> verifier
// (build + targeted tests + the relevant sanitizer). Auto-escalates to a 3+1 blind-proposer panel
// for REDESIGNS (phase machinery, PRNG architecture, oracle-cost model).
//
// Invoke:
//   Workflow({ name: "core-change", args: {
//     task: "what you are changing and why",
//     files: ["cbqs/src/SearchLib.c", ...],   // files you intend to touch
//     northstarSection: "§11",                 // optional: the NORTHSTAR section this serves
//     diffReady: false                         // true once a diff exists in the working tree
//   }})

export const meta = {
  name: 'core-change',
  description: 'Vet + verify a change to CBQS faithfulness-critical code: test-first plan, adversarial refutation against the §1/§2 invariants, sanitizer + regression-baseline gate; escalates to 3+1 for redesigns.',
  whenToUse: 'Before/while changing oracle accounting, PRNG/seeding, branching/bias math, or phase transitions. Pass args={task, files, northstarSection?, diffReady?}.',
  phases: [
    { title: 'Propose', detail: 'test-first plan + at-risk invariants/baselines + exact gate commands' },
    { title: 'Refute', detail: 'adversarial review; may escalate to a 3+1 blind panel for redesigns' },
    { title: 'Verify', detail: 'if a diff exists: build + targeted tests + relevant sanitizer' },
  ],
}

const A = args || {}
const task = A.task || 'UNSPECIFIED core change'
const files = Array.isArray(A.files) ? A.files : []
const nsSection = A.northstarSection || '(unspecified — find it in NORTHSTAR.md)'
const diffReady = A.diffReady === true

const CHARTER = `Read CLAUDE.md (the Operating Charter) and NORTHSTAR.md first.
The non-negotiable invariants (CLAUDE.md §1): quantum-faithfulness / A/B-priced levers; oracle accounting
is sacred (the shared mod->qtg_applications is racy — model.h:28 int, unlocked += at SearchLib.c:179);
no uniform-greedy collapse (score best-of-portfolio, never mean); Phase-1 feature allow-list; scale-invariance
(radius r, bias=n/r-2; enabling branching_weights silently rescales the radius via shared factor_sum in
Branching.h:88-109); no per-candidate recompilation; value must end up clamped to (eps,1-eps).
Hotspots to respect (CLAUDE.md §5): M vs local m_tot reset (SearchLib.c:221); portfolio collapse
(prng_seed_thread(master,0) at solver_ctx.c:535; worker loop Model.pyx:780-783 uses '_'); dead look-ahead
term (diffcount always 0); phase-machine coupling (stage/search_function/active_stats move together);
feasibility/EQUAL sign accounting (solver.c:387-390,510-517); Eq.29 c2/c3 swap + MAXIMIZE=-1 sign.
Regression baselines NOT to break silently (CLAUDE.md §8): BranchingFunction(i,0,0,0)==6/7 at bias=5;
eq29 RHS 5032863(c3)/5040079(c2); single-worker determinism; history schema migration touches
SearchLib.pyx:170 + test_concurrent_history.py + test_diagnostics_py.py + result.py together.`

const PLAN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['summary', 'failing_test_first', 'edits', 'invariants_at_risk', 'baselines_touched', 'gate_commands', 'is_redesign'],
  properties: {
    summary: { type: 'string' },
    failing_test_first: {
      type: 'object', additionalProperties: false, required: ['path', 'asserts'],
      properties: { path: { type: 'string' }, asserts: { type: 'string', description: 'the known-correct value/behavior it pins' } },
    },
    edits: {
      type: 'array',
      items: { type: 'object', additionalProperties: false, required: ['file', 'change'],
        properties: { file: { type: 'string' }, change: { type: 'string' } } },
    },
    invariants_at_risk: { type: 'array', items: { type: 'string', description: 'which CLAUDE.md §1/§2 rule this could violate, and the mitigation' } },
    baselines_touched: { type: 'array', items: { type: 'string', description: 'which §8 baseline this affects and the files that must change together' } },
    gate_commands: { type: 'array', items: { type: 'string', description: 'exact build/test/sanitizer commands to run, selected for the touched files' } },
    is_redesign: { type: 'boolean', description: 'true if this reworks the phase machinery, PRNG architecture, or oracle-cost model' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['verdict', 'is_redesign', 'faithfulness_ok', 'threading_ok', 'sign_feasibility_ok', 'phase_consistency_ok', 'baseline_ok', 'test_first_ok', 'must_fix', 'rationale'],
  properties: {
    verdict: { type: 'string', enum: ['sound', 'needs-fixes', 'reject'] },
    is_redesign: { type: 'boolean' },
    faithfulness_ok: { type: 'boolean' },
    threading_ok: { type: 'boolean' },
    sign_feasibility_ok: { type: 'boolean' },
    phase_consistency_ok: { type: 'boolean' },
    baseline_ok: { type: 'boolean' },
    test_first_ok: { type: 'boolean' },
    must_fix: { type: 'array', items: { type: 'string' } },
    rationale: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ran', 'build_ok', 'tests_ok', 'sanitizer_ok', 'commands_run', 'failures', 'summary'],
  properties: {
    ran: { type: 'boolean' },
    build_ok: { type: 'boolean' },
    tests_ok: { type: 'boolean' },
    sanitizer_ok: { type: 'boolean' },
    commands_run: { type: 'array', items: { type: 'string' } },
    failures: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
}

// ---- Phase 1: Propose (test-first) ----
phase('Propose')
const plan = await agent(
  `${CHARTER}

CORE CHANGE: ${task}
Files intended to touch: ${files.join(', ') || '(infer from the task)'}
Serves NORTHSTAR ${nsSection}.

Produce a TEST-FIRST implementation plan. Open the real files and verify behavior before proposing.
- The FAILING test to write first, and the known-correct value/behavior it pins (not "runs without errors").
- The minimal edits (file + what changes).
- Which §1/§2 invariants this could violate and how you avoid it.
- Which §8 regression baselines it touches and every file that must change in the same commit.
- The exact build/test/sanitizer commands to run, chosen for the touched files (C core -> full ctest + TSan
  if threading/seeding, ASan if memory; Cython callback arity -> rebuild; Python harness -> pytest).
- is_redesign = true ONLY if this reworks the phase machinery, PRNG architecture, or oracle-cost model.`,
  { schema: PLAN_SCHEMA, phase: 'Propose', label: 'propose' }
)

// ---- Phase 2: Refute (adversarial) ----
phase('Refute')
let review = await agent(
  `${CHARTER}

A proposer submitted this plan for the core change "${task}":
${JSON.stringify(plan, null, 2)}

You are an adversarial reviewer. Try to REFUTE it. Open the cited files and check, concretely:
- Faithfulness: is every lever still QTG-implementable + A/B-priced? No free relabel? No banned features?
- Threading: does it touch shared model_t state? Is the oracle counter still correct + race-free under workers?
- Sign/feasibility: objective sign (MAXIMIZE=-1), EQUAL/inequality violation accounting — any silent flip?
- Phase consistency: do stage/search_function/active_stats still move together?
- Baselines: does it change a §8 baseline without updating ALL co-dependent files? Is the failing test genuinely
  known-correct (e.g. pins 6/7, or the eq29 RHS), not just "no error"?
- Is the failing test actually written FIRST?
Default to skepticism: if a risk is plausible and unrefuted, mark the relevant *_ok false and add a must_fix.
Set is_redesign true if this really reworks phase machinery / PRNG architecture / oracle-cost model.`,
  { schema: REVIEW_SCHEMA, phase: 'Refute', label: 'refute' }
)

// ---- Escalation: 3+1 blind panel for redesigns ----
if (plan.is_redesign || review.is_redesign) {
  log('Redesign detected — escalating to a 3+1 blind-proposer panel.')
  const blind = await parallel([0, 1].map(i => () =>
    agent(
      `${CHARTER}

REDESIGN TASK: ${task} (serves NORTHSTAR ${nsSection}).
Independently design this from scratch. Do NOT assume any particular approach is correct.
Produce a complete test-first plan that honors every §1 invariant. You are proposer #${i} and cannot see
the other proposers' work.`,
      { schema: PLAN_SCHEMA, phase: 'Refute', label: `redesign-proposer-${i}` }
    )
  ))
  const candidates = [plan, ...blind.filter(Boolean)]
  review = await agent(
    `${CHARTER}

Three independent redesign proposals for "${task}":
${JSON.stringify(candidates, null, 2)}

You are the orchestrator/judge. Pick the soundest, graft the best ideas from the others, and return a single
consolidated verdict + must_fix list against the §1/§2 invariants and §8 baselines. Be specific about which
proposal you take as the base and why.`,
    { schema: REVIEW_SCHEMA, phase: 'Refute', label: 'judge' }
  )
}

// ---- Phase 3: Verify (only if a diff exists) ----
phase('Verify')
let verify = null
if (diffReady) {
  verify = await agent(
    `${CHARTER}

A diff for "${task}" exists in the working tree. Run the gate and report results.
Run, in order, the gate_commands from the plan (and any you judge necessary for the touched files):
${(plan.gate_commands || []).map(c => '  - ' + c).join('\n') || '  (none specified — derive from CLAUDE.md §7 for the touched files)'}
Build the package/tests, run the FULL local C suite (no -R filter) if C changed, the matching sanitizer
(TSan for threading/seeding, ASan for memory), and the relevant pytest files. Report exact pass/fail with
the failing output; do not declare success on a skipped test (e.g. eq29 RHS skips without CBQS_BENCHMARKS_DIR).`,
    { schema: VERIFY_SCHEMA, phase: 'Verify', label: 'verify' }
  )
} else {
  log('diffReady=false — no diff to verify yet. The implementer runs plan.gate_commands after writing the change.')
}

return { task, plan, review, verify }
