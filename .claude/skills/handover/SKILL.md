---
name: handover
description: Generate a session handover note at the end of a work session. The manual /handover path saves to sessions/ locally only, never committing or pushing — stop.py's separate automatic path does commit and push (see §Two implementations). Suggested after long sessions (50+ turns).
command: /handover
allowed-tools: [Bash, AskUserQuestion, Edit]
user-invocable: true
auto-invoke:
  - when: "Session has 50+ turns OR user signals end of session"
    action: "Suggest /handover to preserve session state before context loss"
---

# /handover — Session Handover Note

## Trigger
User writes `/handover` at the end of a work session.

## Behavior

### Step 1 — Verify system state

Run these checks from `$DQIII8_ROOT` and note the results:

```bash
cd /root/dqiii8
git status --short
git log --oneline -5
python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -1
ls tasks/pending_*.md 2>/dev/null || echo "(no pending tasks)"
```

### Step 2 — Ask user for next steps

Use `AskUserQuestion` to ask the user before saving anything:

> "¿Cuáles son los próximos pasos para la siguiente sesión?"

Offer 4 options based on what you observed in Step 1 (infer from context),
plus "Auto" as fallback.

**If user selects "Auto" or provides no answer:**
Infer next steps from:
1. `ls tasks/pending_*.md` — incomplete task files
2. `git log --oneline -10` — look for feat:/fix: commits that mention open issues or TODOs
3. `cat my-projects/*/.dq-project.json 2>/dev/null` — check `next_step` fields
4. Uncommitted changes in `git status --short` — unfinished work
5. Fall back to: "Continuar desde el último estado del proyecto activo"

### Step 3 — Run the handover script

```bash
cd /root/dqiii8
python3 bin/tools/handover.py
```

El script añade automáticamente una sección `## Operador` derivada del
usuario Linux real (`plglobal-isabel` → Isabel Vinagre, `plglobal-mario` →
Mario Cabeza, `root` → Iker) — no requiere preguntar quién opera la sesión.

The script generates `sessions/YYYY-MM-DD_session_N.md` locally. `sessions/` is gitignored — a file written by *this* path is never committed or pushed.

### Step 4 — Inject real next steps

Find the generated file:

```bash
ls -t /root/dqiii8/sessions/*.md | head -1
```

Use `Edit` to replace the `## Next steps` section content with the actual
steps collected in Step 2. Format each step as a bullet:

```markdown
## Next steps
- [step 1 exactly as provided/inferred]
- [step 2]
- ...
```

Do NOT invent steps. Only write what the user confirmed or what was clearly
inferred from system state.

### Step 5 — Confirm

Output:
```
[HANDOVER] Saved locally · sessions/YYYY-MM-DD_session_N.md
Next steps: [N items]
```

## Two implementations (read before claiming "no push")

The handover feature exists **twice**, with different triggers, filenames and git behaviour.
Nothing else in the corpus may state one and imply the other.

| | Manual — this skill | Automatic — `.claude/hooks/stop.py` §3 |
|---|---|---|
| Trigger | user types `/handover`; suggested after ~50 turns | session ≥15 min old (`_duration_min >= 15`, measured from the first `agent_actions` row), on every `Stop`/`SubagentStop` |
| Writer | `bin/tools/handover.py` (no git code at all) | inline in the hook |
| Filename | `sessions/YYYY-MM-DD_session_N.md` (N from 1) | `sessions/YYYY-MM-DD_session.md`, then `_2`, `_3`, … |
| Asks first | yes (`AskUserQuestion`) | no |
| Git | none — local-only artifact | `git add sessions/` → `git commit -m "session handover {date}"` → `git push premium <current-branch>`, capped at one per calendar day |

Independently of the handover block, `stop.py` §2 auto-commits `tasks/lessons.md` and
`projects/*.md`, and §2b then runs an **unconditional, ungated `git push premium
<current-branch>` on every session and subagent close** — never `origin` (public, must stay
vanilla) and never a hardcoded branch name. So "the handover note is never pushed" describes
the manual path only; the hook layer pushes regardless of which path ran, though on `main`
specifically the push is currently rejected non-fast-forward (a known divergence from the
`premium` remote's `main` branch, unresolved as of 2026-08-19).
SSOT for the automatic behaviour is `stop.py`; see `.claude/rules/02_hooks_and_permissions.md`.

## Notes
- NEVER invent next steps that weren't verified in system state or confirmed by user
- `sessions/` is gitignored, so a note written by *this* skill is never committed or pushed — a local-only artifact (the hook's `git add sessions/` is a no-op for the same reason; its commit/push carries whatever §2 staged)
- Never include sensitive information (API keys, passwords) in the handover
- The active project is resolved via `bin/core/project_context.py::resolve_project()` (DB-backed SSOT, default: `dqiii8-core`) — not an env var
