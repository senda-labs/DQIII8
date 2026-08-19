# /handover — Session Handover Note

> **SSOT: `.claude/skills/handover/SKILL.md`.** This command file is a pointer
> only — read the skill for the full procedure. It previously carried a second,
> divergent copy of the procedure; the skill's stop-and-ask flow
> (`AskUserQuestion` before writing anything, `bin/tools/handover.py`, local
> save, no commit, no push) is the correct behaviour for **this manual path**.
> That deleted copy was *not* pure fiction, as the 2026-08-18 fix wrongly
> assumed: `.claude/hooks/stop.py` §3 contains a second, automatic handover
> implementation that does `git add sessions/` → commit → `git push premium
> <current-branch>`, and §2b pushes the same way on every session close
> regardless — never `origin`, never a hardcoded branch. Both
> are described in `.claude/skills/handover/SKILL.md` §Two implementations and
> `.claude/rules/02_hooks_and_permissions.md`. "Never committed or pushed" is
> true of `/handover`, false of the hook.
