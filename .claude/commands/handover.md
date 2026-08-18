# /handover — Session Handover Note

> **SSOT: `.claude/skills/handover/SKILL.md`.** This command file is a pointer
> only — read the skill for the full procedure. It previously carried a second,
> divergent copy that told the agent to `git add sessions/ projects/` → commit →
> `push origin master`. That was wrong twice over: `bin/tools/handover.py` has no
> commit or push code at all, and `sessions/` is gitignored (`.gitignore:10`), so
> the note is a local-only artifact. It also contradicted
> `.claude/rules_db/git-safety.md` and the core "destructive / irreversible
> actions → STOP, notify, wait" rule by pushing to `master` unattended. The
> skill's stop-and-ask flow (`AskUserQuestion` before writing anything, local
> save, no push) is the correct behaviour. Resolved 2026-08-18 (F6).
