---
name: verification-loop
description: Use this skill after writing or modifying Python code. Runs a structured verification pipeline — format → lint → type → test → diff — and blocks progression if any phase fails.
origin: ECC/affaan-m (adaptado para JARVIS — Black + pytest + mypy)
status: APROBADA
---

# Verification Loop Skill

## When to Use

- After implementing any Python feature or fix
- Before creating a git commit
- After refactoring (`python-specialist` agent handoff)
- When `code-reviewer` returns critical findings

## Verification Phases

### Phase 1 — Format (Black)

```bash
cd /root/jarvis
black --check . 2>&1 | tail -10
```

If Black reports diffs → files are auto-fixed by PostToolUse hook.
Verify the fix ran: `git diff --stat`.

### Phase 2 — Lint (ruff, optional)

```bash
ruff check . --select E,W,F 2>&1 | head -30
```

Report all errors. Fix E and F codes before continuing; W codes are advisory.

### Phase 3 — Type Check (mypy, if installed)

```bash
python3 -m mypy bin/ .claude/hooks/ --ignore-missing-imports 2>&1 | head -30
```

Fix `error:` lines. `note:` lines are informational.

### Phase 4 — Test Suite (pytest)

```bash
cd /root/jarvis
python3 -m pytest tests/ -x -q 2>&1 | tail -30
```

- `-x`: stop on first failure
- All tests must pass before continuing
- If no `tests/` dir exists for the module, note it and continue

### Phase 5 — Security Scan

```bash
grep -rn "shell=True" .claude/ bin/ --include="*.py" | grep -v "#"
grep -rn "f\".*SELECT\|f'.*SELECT" . --include="*.py"
```

Both should return empty. If not — fix before committing.

### Phase 6 — Diff Review

```bash
git diff HEAD --stat
git diff HEAD -- '*.py' | head -80
```

Review: no accidental deletions, no debug statements, no hardcoded values.

## Output Format

After running all phases, report:

```
VERIFICATION LOOP
=================
Phase 1 Format:   PASS / FAIL (N files reformatted)
Phase 2 Lint:     PASS / FAIL (N errors)
Phase 3 Types:    PASS / SKIP / FAIL (N errors)
Phase 4 Tests:    PASS / FAIL (N failed / N passed)
Phase 5 Security: PASS / FAIL
Phase 6 Diff:     CLEAN / REVIEW (N lines)

RESULT: PROCEED / BLOCKED
Blocking issues: [list if any]
```

## Failure Protocol

- **Format FAIL**: Black PostToolUse hook should have fixed it. Re-run phase 1.
- **Lint FAIL**: Fix E/F errors in place. Do not commit with lint errors.
- **Test FAIL**: STOP. Fix failing tests before any commit.
- **Security FAIL**: STOP. Fix before any commit. Escalate if uncertain.

## Integration with Hooks

PostToolUse hook auto-runs Black after every Edit/Write.
This skill verifies the full pipeline beyond just formatting.

## Related

- `tdd-workflow` — write tests before running this skill
- `security-review` — deeper checklist for auth/secrets
- `/quality-gate` command — on-demand shortcut for phases 1-4
