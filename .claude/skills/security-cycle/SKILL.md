---
name: security-cycle
description: Run iterative red-team/blue-team cycles until the codebase is hardened. Each cycle runs /red-team, then /blue-team, then /red-team again to verify fixes hold. Stops when red-team finds 0 CRITICAL and 0 HIGH findings.
command: /security-cycle
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
user-invocable: true
disable-model-invocation: true
---

# /security-cycle — Iterative Security Hardening

Run red-team → blue-team → red-team cycles until the code is a bunker.

## Usage

```
/security-cycle                     # Full cycle on current project
/security-cycle --max-iterations 5  # Limit iterations
/security-cycle $ARGUMENTS          # Cycle on specific path
```

## Pipeline

### Iteration N:

1. Run `/red-team` → generates red-team report at `tasks/audit/red-team-{date}-{N}.md`
2. Count CRITICAL + HIGH findings in the report
3. If 0: **STOP** — code is hardened
4. If > 0: Run `/blue-team` → fixes findings, generates `tasks/audit/blue-team-{date}-{N}.md`
5. Run `/red-team` again → verify fixes hold + find new issues
6. Repeat until CRITICAL + HIGH = 0 or max iterations reached (default: 10)

### Stopping criteria

- **SUCCESS**: Red-team finds 0 CRITICAL and 0 HIGH findings
- **MAX ITERATIONS**: Limit reached — generate final report with remaining risks documented
- **NO PROGRESS**: Two consecutive red-team reports with identical findings — stop, flag for manual review

### After all iterations:

Generate: `tasks/audit/security-cycle-{date}.md`

```markdown
# Security Cycle Report — {date}

## Iterations: {N}

| Iteration | Critical | High | Medium | Low | Fixed |
|-----------|----------|------|--------|-----|-------|
| 1 (red)   | 3        | 5    | 12     | 8   | —     |
| 1 (blue)  | —        | —    | —      | —   | 8 fixed |
| 2 (red)   | 0        | 1    | 9      | 6   | —     |
| 2 (blue)  | —        | —    | —      | —   | 1 fixed |
| 3 (final) | 0        | 0    | 7      | 4   | HARDENED |

## Final Security Score: {score}/100
## Vibe-Coding Patterns Fixed: {N}
## Kill Chains Eliminated: {N}
## Total Fixes Applied: {N}
```

## Notes

- Max 10 iterations by default (prevent infinite loops)
- MEDIUM and LOW findings are documented but do not block completion
- Each iteration generates separate red/blue reports for full audit trail
- The security-cycle report is the master summary
- After completion, commit all reports: `git add tasks/audit/ && git commit -m "security: cycle {date} — {N} iterations, {score}/100"`
