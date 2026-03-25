---
name: handover
description: Generate a session handover note at the end of a work session. Saves to sessions/, updates project status, commits and pushes. Auto-invoked after long sessions (50+ turns).
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

The script generates `sessions/YYYY-MM-DD_session_N.md`, commits, and pushes.

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

### Step 5 — Commit the enriched file

```bash
cd /root/dqiii8
git add sessions/
git commit -m "docs: add real next steps to handover $(date +%Y-%m-%d)"
git push origin main
```

### Step 6 — Confirm

Output:
```
[HANDOVER] Saved · sessions/YYYY-MM-DD_session_N.md
Next steps: [N items]
```

## Notes
- NEVER invent next steps that weren't verified in system state or confirmed by user
- If git push fails (network/auth), the .md file is saved locally — does not block
- Never include sensitive information (API keys, passwords) in the handover
- Variable `DQIII8_PROJECT` controls the active project (default: `dqiii8-core`)
