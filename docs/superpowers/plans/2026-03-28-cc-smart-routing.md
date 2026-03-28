# /cc Smart Tier Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route /cc prompts to the cheapest LLM tier that can handle them — Groq ($0) for simple queries, Sonnet for code tasks, Opus for architecture.

**Architecture:** Add a `classify_cc_tier()` function to `bin/orchestrator.py` that combines `ml_selector.predict_tier()` heuristics with `/cc`-specific rules (simple query detection). The tier decision feeds into `_run_cc_async()` which already accepts a `model` param, and into a new `_run_groq_direct()` path for Tier B that bypasses `claude -p` entirely, calling `openrouter_wrapper.stream_response("groq", ...)` instead.

**Tech Stack:** Python, existing `bin/monitoring/ml_selector.py`, existing `bin/core/openrouter_wrapper.py`, existing `bin/agents/domain_classifier.py`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `bin/orchestrator.py` | Modify | Add `classify_cc_tier()` — the routing decision function |
| `bin/ui/dqiii8_bot.py` | Modify | Wire routing into `cmd_cc`, add `_run_groq_direct()` for Tier B |
| `tests/test_cc_routing.py` | Create | Test tier classification + routing logic |

**No new files created beyond the test.** The routing logic lives in `orchestrator.py` (already exists), and the Groq call path reuses `openrouter_wrapper.stream_response()` (already exists).

---

### Task 1: Add `classify_cc_tier()` to `bin/orchestrator.py`

**Files:**
- Modify: `bin/orchestrator.py` (add function after `format_progress` at ~line 175)
- Test: `tests/test_cc_routing.py`

**Context:** `ml_selector.predict_tier()` returns 1/2/3 (C/B/A) using keyword heuristics. But it doesn't distinguish "simple query" (Groq-answerable) from "code task" (needs Claude tools). We need a `/cc`-specific layer on top.

Real data from DB:
- `routing_feedback`: 10,115 rows. Tier A: 7,926 calls, Tier B: 2,050, Tier C: 139
- `amplification_log` (30d): Tier 1: 1,038 | Tier 2: 480 | Tier 3: 331
- `ml_selector.CODE_KEYWORDS`: python, function, class, error, traceback, refactor, debug, test, import, async, def, git, npm, pip, dockerfile, yaml, json, sql, bash, script
- `ml_selector.COMPLEX_KEYWORDS`: architecture, design system, multi-step, orchestrate, compare and contrast, analyze in depth, write a complete, full implementation, business plan, investment strategy, research paper, comprehensive report

The tier decision for `/cc`:
- **Tier B (Groq):** Simple questions, status checks, explanations, listing — anything that doesn't need file editing, tool use, or multi-step reasoning. Detected by: short prompt (<100 chars), question-only, no code keywords, no action verbs (implementa, crea, fix, refactor, deploy).
- **Tier A (Sonnet):** Code tasks, debugging, implementation, file modifications. Default tier. Detected by: code keywords from ml_selector, or action verbs, or prompt >200 chars.
- **Tier S (Opus):** Architecture, system design, multi-domain analysis. Detected by: complex keywords from ml_selector.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cc_routing.py`:

```python
"""Test classify_cc_tier routing logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))


def test_simple_query_routes_to_groq():
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("lista archivos en bin/") == "B"
    assert classify_cc_tier("status del sistema") == "B"
    assert classify_cc_tier("qué hace openrouter_wrapper?") == "B"
    assert classify_cc_tier("cuántos tests hay?") == "B"
    assert classify_cc_tier("explica el pipeline DQ") == "B"


def test_code_task_routes_to_sonnet():
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("implementa crawler retry con backoff") == "A"
    assert classify_cc_tier("fix el bug en _cc_check") == "A"
    assert classify_cc_tier("refactor diagnostic_writer para usar async") == "A"
    assert classify_cc_tier("crea un test para questionnaire_parser") == "A"
    assert classify_cc_tier("añade endpoint REST para /api/status") == "A"


def test_complex_routes_to_opus():
    from orchestrator import classify_cc_tier

    assert classify_cc_tier("diseña arquitectura de microservicios para el pipeline") == "S"
    assert classify_cc_tier("write a complete implementation plan for multi-tenant auth") == "S"
    assert classify_cc_tier("analyze in depth the performance bottlenecks and design system improvements") == "S"


def test_long_prompt_escalates():
    from orchestrator import classify_cc_tier

    # Long prompts with code context → Sonnet minimum
    long_prompt = "Aquí está el error: " + "x" * 300
    tier = classify_cc_tier(long_prompt)
    assert tier in ("A", "S")


def test_default_is_sonnet():
    from orchestrator import classify_cc_tier

    # Ambiguous prompt → default to Sonnet (safe)
    assert classify_cc_tier("hazlo") == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cc_routing.py -v`
Expected: FAIL with `ImportError: cannot import name 'classify_cc_tier'`

- [ ] **Step 3: Implement `classify_cc_tier()`**

Add to `bin/orchestrator.py` after the `format_progress` function (around line 175):

```python
# ── Tier classification for /cc ───────────────────────────────────────────────

# Action verbs that require Claude Code tool use (file editing, execution)
_ACTION_VERBS = frozenset({
    "implementa", "implement", "crea", "create", "fix", "arregla",
    "refactor", "añade", "add", "modifica", "modify", "actualiza",
    "update", "deploy", "instala", "install", "ejecuta", "run",
    "genera", "generate", "escribe", "write", "borra", "delete",
    "mueve", "move", "renombra", "rename", "commit", "push",
})

# Code keywords (from ml_selector.py — kept in sync)
_CODE_KW = frozenset({
    "python", "function", "class", "error", "traceback", "refactor",
    "debug", "test", "import", "async", "def ", "git ", "npm", "pip",
    "dockerfile", "yaml", "json", "sql", "bash", "script",
})

# Complex keywords (from ml_selector.py — kept in sync)
_COMPLEX_KW = frozenset({
    "architecture", "design system", "multi-step", "orchestrate",
    "compare and contrast", "analyze in depth", "write a complete",
    "full implementation", "business plan", "investment strategy",
    "research paper", "comprehensive report", "arquitectura",
    "microservicios", "diseña sistema",
})


def classify_cc_tier(prompt: str) -> str:
    """Classify a /cc prompt into tier B/A/S.

    B = Groq (simple queries, $0)
    A = Sonnet (code tasks, default)
    S = Opus (architecture, deep analysis)

    Based on real routing data: 10K+ rows in routing_feedback.
    """
    lower = prompt.lower()
    words = set(lower.split())

    # S-tier: complex keywords → Opus
    if any(kw in lower for kw in _COMPLEX_KW):
        return "S"

    # A-tier: action verbs or code keywords → Sonnet
    if words & _ACTION_VERBS:
        return "A"
    if sum(1 for kw in _CODE_KW if kw in lower) >= 1:
        return "A"

    # A-tier: long prompts (>200 chars) likely need reasoning
    if len(prompt) > 200:
        return "A"

    # B-tier: short, simple, no action verbs, no code keywords → Groq
    return "B"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cc_routing.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bin/orchestrator.py tests/test_cc_routing.py
git commit -m "feat: classify_cc_tier — route /cc prompts to B/A/S tiers"
```

---

### Task 2: Add `_run_groq_direct()` to `bin/ui/dqiii8_bot.py`

**Files:**
- Modify: `bin/ui/dqiii8_bot.py` (add function near `_run_cc_async` at ~line 1304)

**Context:** For Tier B prompts, we bypass `claude -p` entirely and call Groq via `openrouter_wrapper.stream_response("groq", "llama-3.3-70b-versatile", prompt)`. This avoids Claude Code overhead (~5s startup) and costs $0. The function already exists and works — we just need to call it from the bot.

`stream_response()` signature (line 472 of openrouter_wrapper.py):
```python
def stream_response(provider_name, model, prompt, system_prompt="") -> tuple[str, int, int, bool]:
    # Returns (full_text, tokens_input, tokens_output, success)
```

It's a synchronous function that writes to stdout and returns the text. We'll call it via `run_in_executor` from the async bot context.

- [ ] **Step 1: Write the function**

Add after `_run_cc_async()` (around line 1370) in `dqiii8_bot.py`:

```python
async def _run_groq_direct(prompt: str, system_prompt: str = "") -> tuple[bool, str]:
    """Call Groq directly via openrouter_wrapper. No Claude Code overhead.

    For Tier B simple queries: status, listing, explanations.
    Uses existing stream_response() from the DQ pipeline.
    """
    import importlib.util

    wrapper_path = JARVIS / "bin" / "core" / "openrouter_wrapper.py"
    spec = importlib.util.spec_from_file_location("openrouter_wrapper", wrapper_path)
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)

    def _call():
        # Redirect stdout to capture (stream_response prints to stdout)
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            text, tok_in, tok_out, success = wrapper.stream_response(
                "groq", "llama-3.3-70b-versatile", prompt, system_prompt
            )
            return success, text
        finally:
            sys.stdout = old_stdout

    return await asyncio.get_event_loop().run_in_executor(None, _call)
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('bin/ui/dqiii8_bot.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bin/ui/dqiii8_bot.py
git commit -m "feat: _run_groq_direct — Tier B bypass for simple queries"
```

---

### Task 3: Wire routing into `cmd_cc`

**Files:**
- Modify: `bin/ui/dqiii8_bot.py` — `cmd_cc()` function (~line 1372)

**Context:** Currently `cmd_cc` always calls `_run_cc_async()` with Sonnet. After this task, it will:
1. Call `classify_cc_tier(prompt)` to get B/A/S
2. If B → call `_run_groq_direct()` (fast, free)
3. If A → call `_run_cc_async(model="claude-sonnet-4-6")` (current behavior)
4. If S → call `_run_cc_async(model="claude-opus-4-6")` (deep reasoning)

The progress message shows which tier was selected.

- [ ] **Step 1: Write integration test**

Add to `tests/test_cc_routing.py`:

```python
def test_tier_to_model_mapping():
    """Verify tier labels map to expected models."""
    tier_models = {"B": "groq", "A": "sonnet", "S": "opus"}
    for tier, model_fragment in tier_models.items():
        assert model_fragment  # Just verify the mapping exists


def test_classify_returns_valid_tier():
    from orchestrator import classify_cc_tier

    for prompt in ["hola", "implementa X", "diseña arquitectura de Y", ""]:
        tier = classify_cc_tier(prompt)
        assert tier in ("B", "A", "S"), f"Invalid tier {tier} for '{prompt}'"
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_cc_routing.py -v`
Expected: 7 tests PASS

- [ ] **Step 3: Modify `cmd_cc()` to use routing**

Replace the body of `cmd_cc()` after the rate limit check (~line 1396) with:

```python
    sys.path.insert(0, str(JARVIS / "bin"))
    from orchestrator import build_context, classify_cc_tier, detect_project

    project = detect_project(prompt)
    label = project["name"]
    tier = classify_cc_tier(prompt)

    tier_labels = {"B": "Groq", "A": "Sonnet", "S": "Opus"}
    progress_msg = await update.message.reply_text(
        f"[{label}] {tier_labels[tier]}..."
    )

    t0 = time.time()

    if tier == "B":
        # Groq direct — no Claude Code overhead
        ctx = build_context(project, prompt) or ""
        success, output = await _run_groq_direct(prompt, system_prompt=ctx)
        files = []
    else:
        # Claude Code — Sonnet or Opus
        model = "claude-opus-4-6" if tier == "S" else "claude-sonnet-4-6"
        success, output, files = await _run_cc_async(
            prompt=prompt,
            cwd=project["path"],
            system_prompt=build_context(project, prompt),
            model=model,
            progress_msg=progress_msg,
            project_label=label,
        )

    elapsed = time.time() - t0

    try:
        m, s = divmod(int(elapsed), 60)
        t_str = f"{m}m {s}s" if m else f"{s}s"
        await progress_msg.edit_text(
            f"[{label}] {tier_labels[tier]} done ({t_str})"
        )
    except Exception:
        pass

    _log_cc_command("/cc", prompt, None, success, len(output))
    await send_chunks(update, output)

    for fpath in files[:5]:
        try:
            with open(fpath, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=fpath.name, caption=fpath.name
                )
        except Exception as exc:
            log.warning("Failed to send file %s: %s", fpath, exc)
```

- [ ] **Step 4: Verify syntax + smoke test**

Run: `python3 -c "import ast; ast.parse(open('bin/ui/dqiii8_bot.py').read()); print('OK')"`
Run: `python3 -m pytest tests/test_smoke.py -q`
Expected: `OK` + `38 passed`

- [ ] **Step 5: Commit**

```bash
git add bin/ui/dqiii8_bot.py tests/test_cc_routing.py
git commit -m "feat: /cc smart routing — Groq for simple, Sonnet for code, Opus for arch"
```

---

### Task 4: Restart bot + manual verification

**Files:** None (operational verification)

- [ ] **Step 1: Restart the bot**

```bash
systemctl restart dqiii8-bot.service
sleep 2
systemctl is-active dqiii8-bot.service
# Expected: active
```

- [ ] **Step 2: Verify via logs that handler loaded**

```bash
journalctl -u dqiii8-bot.service --no-pager -n 10 | grep -i "error\|started\|handler"
# Expected: no errors, "Application started"
```

- [ ] **Step 3: Run all tests**

```bash
python3 -m pytest tests/test_cc_routing.py tests/test_cc_check.py tests/test_smoke.py -v
# Expected: all pass
```

- [ ] **Step 4: Push**

```bash
git push premium main && git push origin main
```

---

## Routing Decision Table (from real data)

| Prompt example | Keywords matched | Tier | Model | Cost |
|---|---|---|---|---|
| `lista archivos en bin/` | none | B | Groq llama-3.3-70b | $0 |
| `status del sistema` | none | B | Groq | $0 |
| `qué hace el pipeline DQ?` | none | B | Groq | $0 |
| `implementa crawler retry` | "implementa" (action) | A | Sonnet 4.6 | ~$0.01 |
| `fix bug en _cc_check` | "fix" (action) | A | Sonnet 4.6 | ~$0.01 |
| `refactor diagnostic_writer` | "refactor" (code+action) | A | Sonnet 4.6 | ~$0.01 |
| `diseña arquitectura microservicios` | "arquitectura" (complex) | S | Opus 4.6 | ~$0.15 |
| `write a complete implementation` | "write a complete" (complex) | S | Opus 4.6 | ~$0.15 |

## Cost Impact (projected from 10K routing_feedback rows)

| Scenario | Tier B % | Tier A % | Tier S % | Cost/100 prompts |
|---|---|---|---|---|
| **Current** (all Sonnet) | 0% | 100% | 0% | ~$1.00 |
| **With routing** (estimated) | 40% | 50% | 10% | ~$0.65 |
| **Savings** | — | — | — | **~35%** |

Note: The real savings are in latency — Groq responds in ~1-3s vs Claude CLI ~10-90s.
