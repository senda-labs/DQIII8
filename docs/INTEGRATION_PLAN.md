# DQIII8 — Integration Plan: OMC + Marketplace + Feature Adoption

> **Purpose:** This document is a complete, self-contained execution plan.
> Claude Code reads it once and executes ALL blocks in sequence.
> Each block has verification steps. If verification fails, fix before proceeding.
> If a block requires manual user action, ASK and WAIT.

---

## Pre-flight

Before starting, verify system health:

```bash
python3 -m pytest tests/ -q          # Expected: 142 passed
systemctl is-active dqiii8-bot        # Expected: active
claude --version                      # Expected: 2.1.86+
ollama list                           # Expected: bge-m3, qwen2.5-coder:7b
```

If any check fails, fix it before proceeding. Do NOT skip.

Read CLAUDE.md and RULE before starting any work.

---

## BLOCK 1: Install OMC as Claude Code Plugin (30 min)

### 1.1 Install OMC

This requires an interactive Claude Code session. ASK THE USER to run these
commands manually inside Claude Code (not bash):

```
/plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode
/plugin install oh-my-claudecode
/oh-my-claudecode:omc-setup
```

WAIT for user confirmation that OMC is installed.

### 1.2 Update settings template

After user confirms OMC is installed, update the settings template so future
installations include OMC:

```python
import json
path = "config/claude_settings_template.json"
s = json.load(open(path))
s["enabledPlugins"]["oh-my-claudecode"] = True
json.dump(s, open(path, "w"), indent=2)
```

### 1.3 Update install.sh

Add OMC plugin installation step to install.sh. Find the Claude Code section
and add after the settings copy:

```bash
# Install OMC plugin (if Claude Code is available)
if command -v claude &>/dev/null; then
    echo "  Installing oh-my-claudecode plugin..."
    claude -p "Run: /plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode && /plugin install oh-my-claudecode" 2>/dev/null || true
fi
```

### 1.4 Verify Block 1

```bash
# Check OMC is in settings
python3 -c "
import json
s = json.load(open('config/claude_settings_template.json'))
assert 'oh-my-claudecode' in str(s.get('enabledPlugins', {})), 'OMC not in template'
print('Block 1 OK: OMC in settings template')
"
```

Commit: `feat: integrate OMC plugin + update settings template`
Push to premium and origin.

---

## BLOCK 2: Complete Ecomode Routing in /cc (45 min)

### 2.1 Review current state

Read the existing smart routing plan if it exists:
```bash
cat docs/superpowers/plans/2026-03-28-cc-smart-routing.md 2>/dev/null
```

Read the current classify_cc_tier in bin/orchestrator.py.
Read the current cmd_cc handler in bin/ui/dqiii8_bot.py.

### 2.2 Implement routing logic

The routing for /cc must follow this logic:

```
QUESTION (no execution needed):
  Keywords: que, como, explica, describe, por que, what, how, explain, why
  AND no action verbs: ejecuta, crea, implementa, fix, test, deploy, commit
  -> Route to Qwen via openrouter_wrapper WITH context injection
  -> Context = CLAUDE.md + PROJECT.md of detected project
  -> Response time: 1-3s, cost: $0

EXECUTION (needs filesystem/bash access):
  Everything else
  -> Route to Sonnet via claude -p
  -> Response time: 10-90s

OPUS ESCALATION (never by default):
  Only triggered by plan-gate rule (.claude/rules/dqiii8-plan-gate.md)
  When Sonnet produces a poor plan, Opus subagent reviews
```

### 2.3 Implementation

In bin/orchestrator.py, add or update classify_cc_tier():

```python
_QUESTION_KEYWORDS = frozenset({
    "que", "como", "explica", "describe", "por que", "cual",
    "what", "how", "explain", "why", "which", "tell me",
    "dime", "cuentame", "define", "significa",
})

_EXECUTION_KEYWORDS = frozenset({
    "ejecuta", "crea", "implementa", "fix", "test", "deploy",
    "commit", "push", "instala", "configura", "lanza", "genera",
    "build", "run", "create", "install", "setup", "refactor",
    "delete", "remove", "update", "migrate", "lista", "list",
    "cuenta", "count", "verifica", "check", "audit",
})

def classify_cc_tier(prompt: str) -> str:
    """Classify prompt for /cc routing.
    
    Returns: "qwen" for questions, "sonnet" for execution tasks.
    Opus is never returned here - handled by plan-gate rule.
    """
    words = set(_normalize(prompt.lower()).split())
    
    has_question = bool(words & _QUESTION_KEYWORDS)
    has_execution = bool(words & _EXECUTION_KEYWORDS)
    
    # Execution keywords win over question keywords
    if has_execution:
        return "sonnet"
    
    # Pure questions go to Qwen (with context injection)
    if has_question and not has_execution:
        return "qwen"
    
    # Long prompts (>50 words) likely need execution
    if len(words) > 50:
        return "sonnet"
    
    # Default: Sonnet (safe fallback)
    return "sonnet"
```

### 2.4 Update cmd_cc to use routing

In bin/ui/dqiii8_bot.py, update cmd_cc:

- If tier == "qwen": call openrouter_wrapper.stream_response() with
  system_prompt containing CLAUDE.md + PROJECT.md content. Send response
  directly as text. No subprocess needed. Label as "[project] Qwen done (Xs)".

- If tier == "sonnet": use existing _run_cc_async() flow unchanged.
  Label as "[project] Sonnet done (Xs)".

### 2.5 Test routing

```python
# Test cases
from orchestrator import classify_cc_tier
assert classify_cc_tier("que hace el pipeline de intl-reports") == "qwen"
assert classify_cc_tier("explica como funciona el DQ enricher") == "qwen"
assert classify_cc_tier("ejecuta los tests") == "sonnet"
assert classify_cc_tier("implementa retry en el crawler") == "sonnet"
assert classify_cc_tier("lista los archivos de intl-reports") == "sonnet"
assert classify_cc_tier("hola") == "sonnet"  # default safe
```

Add these as tests/test_cc_routing.py (update existing file).

### 2.6 Verify Block 2

```bash
python3 -m pytest tests/test_cc_routing.py -v
python3 -m pytest tests/ -q  # All 142+ pass
```

Test from Telegram:
- `/cc que hace el pipeline de intl-reports` -> should use Qwen, fast
- `/cc ejecuta los tests de smoke` -> should use Sonnet

Commit: `feat: ecomode routing — Qwen for questions, Sonnet for execution`
Push to premium and origin.

---

## BLOCK 3: Ultrapilot for intl-reports (1 hour)

### 3.1 Evaluate feasibility

Before implementing, evaluate:

1. Does intl-reports have independent sections that can run in parallel?
   Read my-projects/intl-reports/PROJECT.md
   Read agents/diagnostic_writer.py — are the 6 areas independent?
   Read agents/plan_writer.py — are the 9 sections independent?

2. Can tmux be used to launch parallel Claude Code workers on this VPS?
   Check: tmux is installed, RAM allows 2-3 workers (each ~300MB)

3. What is the expected speedup vs complexity tradeoff?
   Current: 6 areas sequential (3s each) = 18s
   Parallel: 6 areas in 2 batches of 3 = 6s
   Speedup: 3x but only on the Groq calls (already fast)
   
   The bottleneck is Sonnet calls (conclusions + strategy = 200s).
   Parallelizing Groq calls saves 12s out of 246s total = 5% speedup.

4. SELF-EVALUATE: Is this worth implementing now?
   If the speedup is <10%, document why and skip to Block 4.
   If >10%, implement using asyncio.gather() for Groq calls
   (NOT tmux workers — that adds complexity for minimal gain).

### 3.2 If implementing

The simplest parallelization: use asyncio.gather() in diagnostic_writer.py
to run 6 area calls simultaneously instead of sequentially.

```python
# In diagnostic_writer.py
# BEFORE (sequential):
for area in areas:
    result = await call_writer(prompt, tier="B")

# AFTER (parallel):
tasks = [call_writer(prompt, tier="B") for area in areas]
results = await asyncio.gather(*tasks)
```

Same for plan_writer.py — 9 Groq sections in parallel.

### 3.3 Verify Block 3

Run intl-reports pipeline for GINARD and compare timing:
- Before: 246s total
- After: should be ~230s (Groq sections parallel)

If difference is <10s, revert and document "not worth complexity".

Commit: `perf: parallelize Groq calls in diagnostic and plan writers`

---

## BLOCK 4: Ralph Verification Loop for /auto (45 min)

### 4.1 Concept

When /auto finishes, before sending "Done", verify the work:

1. Run tests: `python3 -m pytest tests/ -q`
2. Check git status: any uncommitted changes?
3. If tests fail or there are issues, re-run Claude Code with the error
4. Maximum 2 retry loops, then report regardless

### 4.2 Implementation

In bin/ui/dqiii8_bot.py, update cmd_auto after _run_cc_async returns:

```python
# After first execution
if success:
    # Ralph verification: run tests
    verify_proc = await asyncio.create_subprocess_exec(
        "python3", "-m", "pytest", "tests/test_smoke.py", "-q",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project["path"]),
    )
    v_stdout, v_stderr = await verify_proc.communicate()
    
    if verify_proc.returncode != 0:
        # Tests failed after /auto — retry once
        await progress_msg.edit_text(f"[AUTO/{label}] Verifying... tests failed, retrying")
        retry_prompt = f"Tests failed after your changes. Fix them:\n{v_stdout.decode()[:2000]}"
        success2, output2, files2 = await _run_cc_async(
            prompt=retry_prompt, cwd=project["path"],
            system_prompt=sys_prompt,
            progress_msg=progress_msg,
            project_label=f"AUTO/{label}",
        )
        files.extend(files2)
```

### 4.3 Verify Block 4

Test from Telegram:
```
/auto introduce un bug intencional en un test, luego arreglalo
```

Should see: execution -> verification -> retry -> fixed.

Commit: `feat: Ralph verification loop in /auto — retry on test failure`

---

## BLOCK 5: Deep Interview for Vague Prompts (30 min)

### 5.1 Concept

When /cc receives a vague prompt (<15 words, no specific keywords),
instead of executing immediately, ask 2-3 clarifying questions.

### 5.2 Implementation

In bin/ui/dqiii8_bot.py cmd_cc, after detect_project:

```python
# Check if prompt is vague
words = prompt.split()
if len(words) < 15 and not any(w in prompt.lower() for w in _EXECUTION_KEYWORDS):
    project = detect_project(prompt)
    if project["name"] == "dqiii8":  # No specific project detected
        await update.message.reply_text(
            "Tu prompt es amplio. Para darte la mejor respuesta:\n"
            "1. Que proyecto quieres trabajar?\n"
            "2. Que resultado esperas?\n"
            "3. Hay restricciones especificas?\n\n"
            "O reformula con mas detalle y vuelve a enviar /cc"
        )
        return
```

### 5.3 Self-evaluate

IMPORTANT: Evaluate if this is annoying vs helpful.
If users have to reformulate every time, it adds friction.
Only trigger for VERY vague prompts (< 8 words AND no project detected).
Adjust the threshold after testing.

### 5.4 Verify Block 5

Test from Telegram:
- `/cc hazlo` -> should ask clarifying questions
- `/cc ejecuta pipeline GINARD` -> should NOT ask, execute directly

Commit: `feat: deep interview for vague /cc prompts`

---

## BLOCK 6: DQIII8 as Claude Code Plugin (design only)

### 6.1 Evaluate

This is a DESIGN block, not implementation. Evaluate:

1. What would DQIII8 offer as a plugin that OMC doesn't?
   - DQ knowledge enrichment pipeline
   - Domain classification with local embeddings
   - Knowledge base management (index, search, enrich)
   - Project detection from prompt keywords

2. What's the minimum viable plugin?
   - Skills: /dqiii8:audit, /dqiii8:checkpoint, /dqiii8:enrich
   - Hooks: PermissionAnalyzer, session tracking
   - Agents: 9 specialists via subagent delegation

3. Technical requirements:
   - Claude Code plugins are Node.js/TypeScript
   - DQIII8 is Python — need a bridge
   - Option A: TypeScript wrapper that calls Python scripts
   - Option B: MCP server in Python that exposes DQ functions
   - Option B is cleaner — use the existing sqlite MCP pattern

4. For users without Claude subscription:
   - DQIII8 standalone works with Groq+Ollama (free)
   - The plugin adds Claude Code integration on top
   - install.sh handles standalone, plugin handles Claude Code users

### 6.2 Output

Write a design document to docs/DQIII8_PLUGIN_DESIGN.md with:
- Plugin manifest structure
- MCP server approach for Python bridge
- Skills to export
- Hooks to export
- Minimum viable feature set
- Timeline estimate

Do NOT implement. Design only.

Commit: `docs: DQIII8 plugin design for Claude Code marketplace`

---

## BLOCK 7: Team/Swarm Mode (evaluate only)

### 7.1 Self-evaluate

Check if Claude Code supports Agent Teams:

```bash
claude --help 2>&1 | grep -i team
echo $CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
```

If Teams is not available or experimental:
- Document current status
- List what we would use it for (parallel diagnostic sections, etc.)
- Note: asyncio.gather() from Block 3 covers 80% of the use case
- SKIP implementation, add to next checkpoint as future work

If Teams IS available:
- Design a team configuration for intl-reports
- 3 workers: researcher, diagnostic_writer, plan_writer
- Shared state via SQLite (already have anova_reports.db)
- Implement as /auto --team flag

### 7.2 Output

Add findings to checkpoint. No code changes unless Teams is GA.

---

## Post-flight

After ALL blocks complete:

1. Run full test suite:
```bash
python3 -m pytest tests/ -q
```
Expected: 142+ passed, 0 failed, 0 skipped, 0 xfailed

2. Update checkpoint:
```bash
# Generate new checkpoint
python3 -m pytest tests/ -q > /tmp/test_results.txt
# Create docs/CHECKPOINT_2026-03-29.md with current state
# Delete old checkpoint
```

3. Run /audit and report score

4. Commit everything:
```
git add -A
git commit -m "integration: OMC plugin + ecomode routing + ralph verification + deep interview"
git push premium main
git push origin main
```

5. Send Telegram notification with summary of all changes

---

## RULES

- NEVER skip verification steps
- If a block fails verification, FIX before moving to next block
- If a block requires manual user action, ASK and WAIT
- Blocks marked "evaluate only" should produce a document, not code
- Self-evaluation sections: be honest about cost/benefit
- Maximum 1 Opus escalation per block (plan-gate rule)
- Commit after EACH block, not at the end
- Push to BOTH premium and origin after each commit
