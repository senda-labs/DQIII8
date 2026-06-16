#!/usr/bin/env python3
"""DQIII8 — Execution Plan Compiler.

Compiles a raw prompt into a structured execution plan:
  {plan_fases, pseudocódigo, audit_checklist, validation_tests, invariantes_flujo}

Pattern ported from intl-reports Orchestrator v4 (160 production reports):
  - phases-as-waves with explicit dependencies        (dag.py / scheduler.py)
  - audit checklist before declaring success          (qa gates / RIL)
  - max-2-retry then degraded, never silent           (ril.py MAX_RIL_RETRY_DEPTH)
  - phase separation: later phases consume only
    declared outputs of earlier phases                (phase_guard.py)
  - idempotency: same inputs → same plan, no side fx  (state.py fingerprint)

Zero LLM calls. Deterministic. ~0ms. Designed for Tier A/S prompts where
benchmarks (2026-03-25) proved generic RAG injection hurts but structured
execution scaffolding is the validated 70%-improvement pattern.
"""
from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhaseSpec:
    name: str           # e.g. "ROOT_CAUSE"
    goal: str           # one sentence, parametrized with {entity}
    depends_on: tuple   # names of prior phases (wave semantics)
    exit_criteria: str  # verifiable condition to leave the phase


@dataclass
class ExecutionPlan:
    intent_pattern: str
    plan_fases: list[PhaseSpec]
    pseudocodigo: str
    audit_checklist: list[str]
    validation_tests: list[str]
    invariantes_flujo: list[str]
    source_prompt: str
    confidence: float          # 0..1 — pattern-match certainty
    elapsed_ms: int = 0
    compiler_version: str = "1.1"

    def render(self) -> str:
        lines = [
            f"[EXECUTION PLAN — DQ compiler v{self.compiler_version} | "
            f"pattern: {self.intent_pattern} | confidence: {self.confidence:.2f}]",
            "",
            "FASES (execute in order; respect depends_on):",
        ]
        for i, ph in enumerate(self.plan_fases, 1):
            dep = f" (after: {', '.join(ph.depends_on)})" if ph.depends_on else ""
            lines.append(f"  {i}. {ph.name}{dep} — {ph.goal}")
            lines.append(f"     exit: {ph.exit_criteria}")
        lines += ["", "PSEUDOCÓDIGO:"]
        lines += ["  " + l for l in self.pseudocodigo.strip().splitlines()]
        lines += ["", "AUDIT CHECKLIST (verify each before declaring done):"]
        lines += [f"  [ ] {item}" for item in self.audit_checklist]
        lines += ["", "VALIDATION TESTS:"]
        lines += [f"  - {t}" for t in self.validation_tests]
        lines += ["", "INVARIANTES DE FLUJO (must hold at every step):"]
        lines += [f"  - {inv}" for inv in self.invariantes_flujo]
        return "\n".join(lines)


# ── Shared invariants (ported from Orchestrator v4) ──────────────────────────

_SHARED_INVARIANTS = [
    "Phase separation: a phase consumes ONLY declared outputs of earlier phases "
    "— never read ahead, never assume results of phases not yet run (phase_guard).",
    "Retry discipline: max 2 retries per failed check, then mark the unit "
    "degraded and surface it explicitly — never silent, never infinite (RIL).",
    "Failure isolation: a failure in one unit never aborts independent units.",
    "Idempotency: re-running a phase with identical inputs must be a no-op "
    "or produce byte-identical output (fingerprint).",
]

# ── Template definitions: 14 intent patterns ─────────────────────────────────
# Each value: phases (name, goal, depends_on, exit), pseudo, audit, validation, invariants.
# Goals/pseudo accept {entity} (detected entity or 'the target').

_T = {}

_T["plan"] = dict(
    phases=[
        ("SCOPE", "Pin down what {entity} must achieve and what is explicitly out of scope", (), "scope statement with ≥1 explicit exclusion"),
        ("DECOMPOSE", "Break the goal into independent, testable work units", ("SCOPE",), "each unit has a verifiable done-condition"),
        ("SEQUENCE", "Order units into waves by real dependency, maximize parallelism", ("DECOMPOSE",), "DAG with no cycles; parallel units identified"),
        ("RISK", "For each wave: what breaks it, blast radius, rollback", ("SEQUENCE",), "every high-risk unit has a mitigation"),
        ("DELIVER", "Emit the plan with exact paths, commands, expected outputs", ("RISK",), "another engineer could execute without questions"),
    ],
    pseudo="""scope = define(goal, exclusions)
units = decompose(scope)            # each unit: (action, done_condition)
waves = topo_sort(units)            # wave = units with no mutual deps
for wave in waves:
    annotate(wave, risk, rollback)
emit(plan)                          # paths + commands + expected output""",
    audit=[
        "Every requirement in the prompt maps to ≥1 work unit (coverage check).",
        "No unit says 'TBD', 'handle appropriately' or equivalent placeholder.",
        "Dependencies are real (data/code), not just thematic grouping.",
        "Rollback exists for every destructive step.",
    ],
    validation=[
        "Walk the DAG: no cycle, every depends_on names an earlier unit.",
        "Pick the riskiest unit and verify its done-condition is machine-checkable.",
    ],
    inv=["The plan never schedules a destructive action before its backup step."],
)

_T["debug"] = dict(
    phases=[
        ("REPRODUCE", "Trigger the failure in {entity} deterministically", (), "exact command + observed error captured"),
        ("ISOLATE", "Shrink to minimal failing input/code path", ("REPRODUCE",), "smallest repro identified"),
        ("ROOT_CAUSE", "Explain WHY it fails — mechanism, not symptom", ("ISOLATE",), "cause stated; symptom-patching rejected"),
        ("FIX", "Apply the minimal change that removes the cause", ("ROOT_CAUSE",), "diff touches only cause-related code"),
        ("VERIFY", "Re-run repro + regression suite", ("FIX",), "repro passes; no new failures"),
    ],
    pseudo="""repro = capture(command, error, env)
minimal = bisect(repro)
cause = explain(minimal)            # mechanism, with evidence
assert is_root_cause(cause), "patching a symptom is a plan failure"
fix = minimal_change(cause)
assert rerun(repro).passes and suite().passes""",
    audit=[
        "The bug was reproduced BEFORE any code was changed.",
        "Root cause is stated with evidence (log line, value, stack frame).",
        "The fix is minimal — no opportunistic refactors mixed in.",
        "A regression test exists that fails on the old code.",
    ],
    validation=[
        "Run the original repro command: must pass now.",
        "Run the full test suite: zero new failures.",
    ],
    inv=["Never declare fixed without re-running the original repro."],
)

_T["analyze"] = dict(
    phases=[
        ("FRAME", "State the question {entity} must answer and the decision it informs", (), "question + decision criterion written"),
        ("GATHER", "Collect the data/code/facts — primary sources only", ("FRAME",), "every datum has a source reference"),
        ("EXAMINE", "Quantify, segment, find the 2-3 signals that matter", ("GATHER",), "claims backed by numbers, not adjectives"),
        ("SYNTHESIZE", "Answer the framed question; state confidence and what would change it", ("EXAMINE",), "answer + confidence + falsifier"),
    ],
    pseudo="""q = frame(prompt)                  # question + decision it feeds
data = gather(primary_sources)
signals = examine(data)             # numbers, deltas, distributions
answer = synthesize(q, signals)
report(answer, confidence, falsifier)""",
    audit=[
        "Every quantitative claim traces to gathered data (no invented numbers).",
        "The analysis answers the framed question, not an adjacent easier one.",
        "Confidence level and its falsifier are explicit.",
        "Outliers/contradictory evidence are addressed, not dropped.",
    ],
    validation=[
        "Spot-check 2 numbers against their primary source.",
        "Re-read FRAME: does SYNTHESIZE answer exactly that question?",
    ],
    inv=["No conclusion may rest on data not collected in GATHER."],
)

_T["generate"] = dict(
    phases=[
        ("SPEC", "Fix format, audience, constraints and acceptance criteria for {entity}", (), "acceptance criteria listed"),
        ("DRAFT", "Produce the complete artifact — no placeholders", ("SPEC",), "artifact exists end-to-end"),
        ("REFINE", "Tighten against spec: cut filler, fix structure", ("DRAFT",), "every spec constraint satisfied"),
        ("VALIDATE", "Check acceptance criteria one by one", ("REFINE",), "all criteria pass or deviations justified"),
    ],
    pseudo="""spec = extract_constraints(prompt)   # format, length, audience, musts
draft = produce(spec)                # complete, runnable/readable
refined = tighten(draft, spec)
for c in spec.acceptance: assert check(refined, c)""",
    audit=[
        "Output contains zero placeholders (TBD/TODO/lorem/<...>).",
        "Format matches the requested one exactly (code runs, JSON parses, etc.).",
        "Length/structure constraints from the prompt are met.",
        "Nothing was added beyond what was asked (YAGNI).",
    ],
    validation=[
        "If code: execute it. If structured data: parse it. If prose: read top-to-bottom once.",
        "Diff the output against each explicit constraint in the prompt.",
    ],
    inv=["A draft with placeholders never advances past DRAFT."],
)

_T["report"] = dict(
    phases=[
        ("AUDIENCE", "Identify reader of {entity}, their decision, their time budget", (), "reader + decision named"),
        ("DATA", "Assemble verified figures; reconcile conflicting sources", ("AUDIENCE",), "single reconciled dataset"),
        ("STRUCTURE", "Executive summary → findings → evidence → next steps", ("DATA",), "outline approved against audience needs"),
        ("WRITE", "Write; every claim cites its datum", ("STRUCTURE",), "draft complete"),
        ("QA", "Audit numbers, names, dates; check internal consistency", ("WRITE",), "zero unverified claims"),
    ],
    pseudo="""reader = identify(audience)
data = reconcile(sources)            # conflicts resolved explicitly
outline = structure(reader, data)
doc = write(outline, cite=True)
qa(doc)                              # numbers, names, dates, consistency""",
    audit=[
        "Executive summary is self-sufficient (reader could stop there).",
        "Every figure in the report appears in the reconciled dataset.",
        "No section contradicts another (cross-section consistency).",
        "Next steps are actionable, owned, and dated.",
    ],
    validation=[
        "Cross-check 3 random figures against DATA phase output.",
        "Read only the summary: can the reader make their decision?",
    ],
    inv=["A number that appears in two sections must be identical in both."],
)

_T["refactor"] = dict(
    phases=[
        ("BASELINE", "Capture current behavior of {entity}: tests green, outputs recorded", (), "baseline artifacts saved"),
        ("CHARACTERIZE", "Add tests for any uncovered behavior you are about to touch", ("BASELINE",), "touched paths have coverage"),
        ("TRANSFORM", "Apply the refactor in small, individually-green steps", ("CHARACTERIZE",), "each step compiles + passes"),
        ("VERIFY_EQUIV", "Prove observable behavior unchanged", ("TRANSFORM",), "baseline outputs reproduced byte-identical"),
    ],
    pseudo="""baseline = run_suite(); record(outputs)
add_characterization_tests(touched_paths)
for step in small_steps(refactor):
    apply(step); assert run_suite().green
assert outputs_now == baseline.outputs""",
    audit=[
        "No behavior change is mixed into the refactor (pure restructure).",
        "Every commit/step in TRANSFORM left the suite green.",
        "Public interfaces kept signature-compatible or all callers updated.",
        "Dead code created by the refactor was removed.",
    ],
    validation=[
        "Full test suite green before and after.",
        "Diff review: zero logic changes, only structure.",
    ],
    inv=["Suite red → stop and revert the last step, never push through."],
)

_T["research"] = dict(
    phases=[
        ("QUESTION", "Decompose {entity} into 3-5 answerable sub-questions", (), "sub-questions listed"),
        ("SOURCES", "Locate primary sources per sub-question; rank reliability", ("QUESTION",), "≥2 independent sources per sub-question"),
        ("EXTRACT", "Pull claims with citations; quote, don't paraphrase numbers", ("SOURCES",), "claim table with source links"),
        ("TRIANGULATE", "Cross-check claims across sources; flag conflicts", ("EXTRACT",), "conflicts resolved or flagged"),
        ("SYNTHESIZE", "Answer the original question; separate fact from inference", ("TRIANGULATE",), "facts cited, inferences labeled"),
    ],
    pseudo="""subqs = decompose(question)
for sq in subqs:
    srcs = locate(sq, min_independent=2)
    claims += extract(srcs, cite=True)
verified = triangulate(claims)        # conflicts → flagged, not averaged
answer = synthesize(verified, label_inference=True)""",
    audit=[
        "Every factual claim carries a citation to a located source.",
        "Single-source claims are explicitly marked as such.",
        "Conflicting evidence is shown, not silently dropped.",
        "Inference is visually separated from sourced fact.",
    ],
    validation=[
        "Pick 2 claims, follow their citations, confirm wording matches.",
        "Count sources per sub-question: ≥2 or marked single-source.",
    ],
    inv=["Never average conflicting numbers — flag the conflict."],
)

_T["test"] = dict(
    phases=[
        ("SURFACE", "Enumerate the public contract of {entity}: inputs, outputs, errors", (), "contract table written"),
        ("CASES", "Design happy-path, edge, and failure cases per contract row", ("SURFACE",), "each contract row has ≥1 case of each kind"),
        ("IMPLEMENT", "Write the tests; each asserts ONE behavior", ("CASES",), "tests run, currently meaningful"),
        ("RUN", "Execute; confirm new tests can actually fail (mutate to check)", ("IMPLEMENT",), "tests proven non-vacuous"),
        ("COVER", "Check coverage of touched code; close gaps that matter", ("RUN",), "no critical path uncovered"),
    ],
    pseudo="""contract = enumerate_api(target)
cases = design(contract)             # happy + edge + failure each
tests = implement(cases, one_assert_focus=True)
assert all_fail_when_mutated(tests)  # vacuous test = plan failure
report(coverage(touched_paths))""",
    audit=[
        "Failure cases test real failure modes (exceptions, empty, overflow), not just happy path.",
        "Each test name states the behavior it pins.",
        "Tests are deterministic — no sleeps, no network, no order dependence.",
        "A deliberately broken implementation makes them fail.",
    ],
    validation=[
        "Run suite twice: identical results (determinism).",
        "Comment out one core line of the target: ≥1 test must fail.",
    ],
    inv=["A test that cannot fail is deleted, not kept for coverage optics."],
)

_T["deploy"] = dict(
    phases=[
        ("PREFLIGHT", "Verify {entity} green in CI, config/env complete, deps pinned", (), "preflight checklist all green"),
        ("ROLLBACK_PLAN", "Write the exact rollback commands BEFORE touching prod", ("PREFLIGHT",), "rollback tested or dry-run"),
        ("APPLY", "Deploy in smallest reversible increment", ("ROLLBACK_PLAN",), "deployment applied"),
        ("SMOKE", "Hit the real service: health endpoint + 1 critical user path", ("APPLY",), "real responses verified, not just logs"),
        ("MONITOR", "Watch error rate/latency for a defined window", ("SMOKE",), "window passed clean or rollback executed"),
    ],
    pseudo="""assert ci_green and env_complete and deps_pinned
rollback = write_and_dryrun(rollback_cmds)   # BEFORE apply
apply(smallest_increment)
assert smoke(real_endpoint).ok               # artifact, not logs
watch(metrics, window); if degraded: run(rollback)""",
    audit=[
        "Rollback commands existed and were dry-run before APPLY.",
        "Smoke test hit the deployed artifact, not a local copy.",
        "Secrets came from env, never from the deploy diff.",
        "The monitoring window was actually observed, not skipped.",
    ],
    validation=[
        "curl/health-check against the live service returns expected payload.",
        "Rollback dry-run exits 0.",
    ],
    inv=["No APPLY without a written, runnable rollback (zero-complacency)."],
)

_T["review"] = dict(
    phases=[
        ("CONTEXT", "Understand what {entity} claims to do and why", (), "intent of the change restated"),
        ("CORRECTNESS", "Hunt real bugs: logic, edge cases, races, resource leaks", ("CONTEXT",), "each suspicion verified in code, not guessed"),
        ("RISK_RANK", "Classify findings CRITICAL / SUGGESTION with file:line", ("CORRECTNESS",), "every finding located and ranked"),
        ("FEEDBACK", "Actionable comments: what, why, concrete fix", ("RISK_RANK",), "author can act without follow-up questions"),
    ],
    pseudo="""intent = restate(change)
findings = []
for path in changed_paths:
    findings += verify_suspicions(path)   # read the code, prove it
ranked = rank(findings, [CRITICAL, SUGGESTION], locate=True)
emit(ranked, with_concrete_fix=True)""",
    audit=[
        "Every CRITICAL finding includes file:line and a failing scenario.",
        "No style nitpicks ranked as CRITICAL.",
        "Praise-only review of non-trivial code = review failure; absence of findings is justified.",
        "Suggestions include the concrete replacement, not 'consider improving'.",
    ],
    validation=[
        "For each CRITICAL: write the 2-line repro scenario.",
        "Re-read findings as the author: is any comment ambiguous?",
    ],
    inv=["Findings are verified in the code, never speculated."],
)

_T["optimize"] = dict(
    phases=[
        ("MEASURE", "Baseline {entity} with a reproducible benchmark", (), "numbers recorded, variance known"),
        ("PROFILE", "Find where time/memory actually goes", ("MEASURE",), "top hotspot identified with data"),
        ("HYPOTHESIS", "State expected gain and why, BEFORE changing code", ("PROFILE",), "falsifiable prediction written"),
        ("CHANGE_ONE", "Apply exactly one optimization", ("HYPOTHESIS",), "single-variable change applied"),
        ("REMEASURE", "Same benchmark; accept only if gain ≥ predicted noise floor", ("CHANGE_ONE",), "gain confirmed or change reverted"),
    ],
    pseudo="""base = bench(n_runs=5)              # mean + variance
hot = profile()
pred = hypothesize(hot)             # 'X% because Y'
apply(one_change)
new = bench(n_runs=5)
accept if (base.mean - new.mean) > noise_floor else revert""",
    audit=[
        "Optimization targeted the measured hotspot, not intuition.",
        "Exactly one variable changed between measurements.",
        "Gain exceeds run-to-run variance (not noise).",
        "Correctness suite still green after the change.",
    ],
    validation=[
        "Re-run benchmark 5×: improvement persists across runs.",
        "Full test suite green.",
    ],
    inv=["No optimization is kept without a before/after measurement pair."],
)

_T["explain"] = dict(
    phases=[
        ("LEVEL_SET", "Identify the audience's starting knowledge for {entity}", (), "audience level fixed"),
        ("CORE_IDEA", "One-sentence essence before any detail", ("LEVEL_SET",), "summary sentence written"),
        ("MECHANISM", "How it works, step by step, no skipped leaps", ("CORE_IDEA",), "each step follows from the previous"),
        ("EXAMPLE", "One concrete, worked example with real values", ("MECHANISM",), "example computes/runs end-to-end"),
        ("LIMITS", "Where the concept breaks, common misconceptions", ("EXAMPLE",), "≥1 boundary + 1 misconception named"),
    ],
    pseudo="""level = audience(prompt)
emit(one_sentence_essence)
for step in mechanism: emit(step, no_leaps=True)
emit(worked_example(real_values))
emit(limits, misconceptions)""",
    audit=[
        "First sentence alone gives the gist.",
        "No step assumes knowledge above the fixed audience level.",
        "The example uses concrete numbers/code, not 'imagine some X'.",
        "At least one limitation or misconception is addressed.",
    ],
    validation=[
        "Recompute the worked example by hand: values check out.",
        "Strip everything but sentence 1: still a valid (if shallow) answer.",
    ],
    inv=["Accuracy beats simplicity: simplifications are flagged as such."],
)

_T["migrate"] = dict(
    phases=[
        ("INVENTORY", "Enumerate everything that moves: data, schemas, configs, callers of {entity}", (), "complete inventory with counts"),
        ("MAP", "Define old→new mapping incl. defaults for fields with no source", ("INVENTORY",), "every inventory item mapped or excluded with reason"),
        ("DUAL_RUN", "Run old and new side by side on real input", ("MAP",), "outputs comparable on real data"),
        ("CUTOVER", "Switch with a reversible step; keep old path readable", ("DUAL_RUN",), "new path live, old path frozen not deleted"),
        ("VERIFY_PARITY", "Compare counts/checksums old vs new", ("CUTOVER",), "row counts + spot checksums match"),
    ],
    pseudo="""inv = inventory(source)              # tables, files, callers, counts
mapping = define(inv, old→new)
old_out, new_out = dual_run(real_sample)
assert comparable(old_out, new_out)
cutover(reversible=True)             # old stays readable
assert counts(new) == counts(old) and checksums(sample) match""",
    audit=[
        "Row/record counts match between old and new (or delta explained).",
        "The old system is frozen readonly, not deleted, until parity holds.",
        "Every caller of the old path was found and repointed.",
        "Cutover is reversible with a documented command.",
    ],
    validation=[
        "SELECT COUNT(*) old vs new: equal.",
        "Checksum 3 random records across systems: identical.",
    ],
    inv=["Source data is never mutated during migration — copy, verify, then switch."],
)

_T["integrate"] = dict(
    phases=[
        ("CONTRACTS", "Pin both sides' interfaces: schemas, auth, rate limits, errors of {entity}", (), "contract doc for both directions"),
        ("ADAPTER", "Build the thinnest translation layer; no business logic inside", ("CONTRACTS",), "adapter passes contract examples"),
        ("FAILURE_MODES", "Decide behavior for: timeout, 4xx/5xx, malformed payload, partial success", ("ADAPTER",), "each failure has a coded response"),
        ("E2E_TEST", "Exercise the real integration path with real(istic) payloads", ("FAILURE_MODES",), "round-trip verified incl. one failure injection"),
    ],
    pseudo="""contract = pin(side_a, side_b)      # schema, auth, limits, errors
adapter = thin_translate(contract)   # no business logic
for f in [timeout, http_4xx, http_5xx, malformed, partial]:
    define(handler(f))               # retry? degrade? surface?
assert e2e(real_payload).ok and e2e(injected_failure).handled""",
    audit=[
        "Adapter contains translation only — business rules live outside it.",
        "Every failure mode has explicit, tested handling (no bare except).",
        "Credentials come from env vars, never the integration code.",
        "Rate limits of the external side are respected by design (backoff).",
    ],
    validation=[
        "E2E happy path with a real payload returns expected schema.",
        "Inject one timeout: system degrades as designed, no crash.",
    ],
    inv=["External calls always have a timeout and a coded failure path."],
)

PATTERNS: tuple = tuple(sorted(_T.keys()))
assert len(PATTERNS) == 14, f"expected 14 templates, got {len(PATTERNS)}"


# ── Pattern inference ─────────────────────────────────────────────────────────
# Own keyword table (compiler patterns ≠ amplifier intents). Spanish + English.

_PATTERN_KEYWORDS = {
    "plan":      ["planifica", "plan ", "diseña", "design", "architect", "roadmap", "estrategia"],
    "debug":     ["debug", "fix", "corrige", "arregla", "error", "falla", "bug", "crash", "traceback"],
    "analyze":   ["analiza", "analyze", "evalua", "assess", "examina", "compara", "compare", "estima", "forecast"],
    "generate":  ["genera", "generate", "crea", "create", "escribe", "write", "produce", "draft"],
    "report":    ["reporte", "report", "informe", "dashboard", "resumen ejecutivo", "executive"],
    "refactor":  ["refactor", "reestructura", "restructure", "limpia el codigo", "clean up", "simplifica"],
    "research":  ["investiga", "research", "busca", "find out", "discover", "estado del arte"],
    "test":      ["test", "prueba", "valida", "validate", "verifica", "verify", "cobertura", "coverage", "pytest"],
    "deploy":    ["deploy", "despliega", "release", "publica", "production", "produccion", "rollout", "systemd", "cron"],
    "review":    ["review", "revisa", "code review", "audita", "audit", "critica"],
    "optimize":  ["optimiza", "optimize", "mejora el rendimiento", "speed up", "acelera", "performance", "perf"],
    "explain":   ["explica", "explain", "describe", "clarifica", "define", "que es", "what is", "how does"],
    "migrate":   ["migra", "migrate", "convierte", "convert", "traduce", "translate", "port ", "porta", "mueve a"],
    "integrate": ["integra", "integrate", "conecta", "connect", "api de", "webhook", "third-party"],
}

# Amplifier intent id → compiler pattern (for callers passing intent_pattern through).
AMPLIFIER_INTENT_MAP = {
    "analyze": "analyze", "generate": "generate", "optimize": "optimize",
    "debug": "debug", "research": "research", "summarize": "explain",
    "compare": "analyze", "forecast": "analyze", "explain": "explain",
    "transform": "migrate", "validate": "test", "plan": "plan",
    "automate": "deploy", "report": "report",
}


def _norm(text: str) -> str:
    """Lowercase + strip diacritics so 'qué' matches keyword 'que' (v1.1 fix)."""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def _infer_pattern(prompt: str) -> tuple[str, float]:
    """Score keyword hits per pattern. Returns (pattern, confidence 0..1)."""
    p = _norm(prompt)
    best, best_score = "explain", 0
    for pattern, kws in _PATTERN_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in p)
        if score > best_score:
            best, best_score = pattern, score
    return best, round(min(1.0, best_score / 3.0), 3)


# Tokens that are imperative verbs / auxiliaries, never entities (v1.1 fix:
# Spanish/English prompts start with a capitalized verb — 'Analiza el…' must
# not yield entity='Analiza'). Includes every single-word pattern keyword.
_ENTITY_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "the", "a", "an",
    "can", "could", "would", "should", "please", "por", "favor", "haz",
    "hazme", "dame", "make", "do", "how", "what", "why", "when", "que",
} | {_norm(kw.strip()) for kws in _PATTERN_KEYWORDS.values() for kw in kws if " " not in kw.strip()}


def _detect_entity(prompt: str) -> str:
    """First capitalized/path-like token — same heuristic family as intent_amplifier."""
    for tok in prompt.split():
        clean = tok.strip(".,;:!?\"'()")
        if not clean:
            continue
        if "/" in clean or "." in clean[1:] or "_" in clean:
            return clean
        if clean[0].isupper() and len(clean) > 2 and _norm(clean) not in _ENTITY_STOPWORDS:
            return clean
    return "the target"


def dq_compile(prompt: str, intent_pattern: str | None = None) -> ExecutionPlan:
    """Compile a raw prompt into an ExecutionPlan.

    intent_pattern: force one of PATTERNS, or an amplifier intent id
    (mapped via AMPLIFIER_INTENT_MAP). None → infer from prompt.
    Raises ValueError on empty prompt or unknown forced pattern.
    """
    t0 = time.time()
    if not prompt or not prompt.strip():
        raise ValueError("dq_compile: empty prompt")

    if intent_pattern is not None:
        pattern = AMPLIFIER_INTENT_MAP.get(intent_pattern, intent_pattern)
        if pattern not in _T:
            raise ValueError(f"dq_compile: unknown intent_pattern {intent_pattern!r}")
        confidence = 1.0  # caller asserted it
    else:
        pattern, confidence = _infer_pattern(prompt)

    entity = _detect_entity(prompt)
    t = _T[pattern]
    fases = [
        PhaseSpec(name=n, goal=g.format(entity=entity), depends_on=tuple(d), exit_criteria=e)
        for (n, g, d, e) in t["phases"]
    ]
    return ExecutionPlan(
        intent_pattern=pattern,
        plan_fases=fases,
        pseudocodigo=t["pseudo"],
        audit_checklist=list(t["audit"]),
        validation_tests=list(t["validation"]),
        invariantes_flujo=list(t["inv"]) + _SHARED_INVARIANTS,
        source_prompt=prompt,
        confidence=confidence,
        elapsed_ms=int((time.time() - t0) * 1000),
    )
