# /handover — Session Handover Note

## Trigger
User writes `/handover` at the end of a work session.

## Behavior

Executes the handover script with a single call:

```bash
python3 bin/tools/handover.py
```

The script does everything without additional Claude tools:
- Collects modified files via `git diff --stat HEAD`
- Reads `projects/[project].md` for the next step
- Reads `tasks/lessons.md` (today's entries)
- Writes `sessions/YYYY-MM-DD_session.md`
- Updates `projects/[project].md` (section "Last session")
- `git add sessions/ projects/` → commit → push origin master

## Non-interactive invocation

```bash
python3 bin/tools/handover.py
```

## Notes
- If git push fails (network/auth), the .md file is saved locally — does not block
- Never include sensitive information (API keys, passwords) in the handover
- Variable `DQIII8_PROJECT` controls the active project (default: `dqiii8-core`)
