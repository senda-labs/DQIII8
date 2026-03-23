#!/usr/bin/env python3
"""
DQIII8 — Handover script
Generates sessions/YYYY-MM-DD_session.md, updates projects/[project].md,
and runs git commit+push. Non-interactive — designed for 'claude -p /handover'.
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
NOW = datetime.now()
DATE = NOW.strftime("%Y-%m-%d")
TIME = NOW.strftime("%H:%M")

# ── 1. Modified files via git diff ───────────────────────────────
diff = subprocess.run(
    ["git", "-C", str(JARVIS), "diff", "--stat", "HEAD"],
    capture_output=True, text=True, timeout=10
)
files = [
    line.split("|")[0].strip()
    for line in diff.stdout.splitlines()
    if "|" in line and not line.strip().startswith("Bin")
]

# ── 2. Active project ─────────────────────────────────────────────
project = os.environ.get("JARVIS_PROJECT", "jarvis-core")

# ── 3. Next step from projects/[project].md ───────────────────────
next_step = f"See projects/{project}.md"
pm = JARVIS / "projects" / f"{project}.md"
if pm.exists():
    lines = pm.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if any(k in line for k in ("Próximo paso", "Proximo paso", "Next step")):
            for j in range(i + 1, min(i + 4, len(lines))):
                t = lines[j].strip().lstrip("-").lstrip("*").strip()
                if t:
                    next_step = t
                    break
            break

# ── 4. Recent lessons (today) ─────────────────────────────────────
lessons_today = []
lessons_file = JARVIS / "tasks" / "lessons.md"
if lessons_file.exists():
    for line in lessons_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"[{DATE}]"):
            lessons_today.append(f"- {line.strip()}")

lessons_block = "\n".join(lessons_today) if lessons_today else "- (none this session)"

# ── 5. Write sessions/YYYY-MM-DD_session.md ───────────────────────
sessions_dir = JARVIS / "sessions"
sessions_dir.mkdir(exist_ok=True)

session_path = sessions_dir / f"{DATE}_session.md"
idx = 2
while session_path.exists():
    session_path = sessions_dir / f"{DATE}_session_{idx}.md"
    idx += 1

files_block = "\n".join(f"- `{f}`" for f in files[:20]) or "- (no pending changes)"

content = f"""---
date: {DATE}
time: {TIME}
project: {project}
agent_used: claude-sonnet-4-6
---

# Session {DATE}

## What we did
- Manual handover session — {project}
- (See modified files below for details)

## Modified files
{files_block}

## Next step
{next_step}

## Lessons learned
{lessons_block}
"""

session_path.write_text(content, encoding="utf-8")
print(f"[HANDOVER] Session saved in {session_path.relative_to(JARVIS)}")

# ── 6. Update projects/[project].md ───────────────────────────────
if pm.exists():
    text = pm.read_text(encoding="utf-8")
    marker = "**Last session:**"
    new_line = f"**Last session:** {DATE} — manual handover"
    if marker in text:
        lines = text.splitlines()
        updated = [new_line if marker in l else l for l in lines]
        pm.write_text("\n".join(updated) + "\n", encoding="utf-8")
    else:
        pm.write_text(text.rstrip() + f"\n\n{new_line}\n", encoding="utf-8")

# ── 7. Git add + commit + push ────────────────────────────────────
add_targets = [str(sessions_dir)]
if pm.exists():
    add_targets.append(str(pm))

subprocess.run(
    ["git", "-C", str(JARVIS), "add"] + add_targets,
    capture_output=True, timeout=10
)

commit = subprocess.run(
    ["git", "-C", str(JARVIS), "commit", "-m", f"session handover {DATE}"],
    capture_output=True, text=True, timeout=10
)

if commit.returncode == 0:
    push = subprocess.run(
        ["git", "-C", str(JARVIS), "push", "origin", "master"],
        capture_output=True, text=True, timeout=20
    )
    if push.returncode == 0:
        print(f"[HANDOVER] Push OK -> origin/master")
    else:
        print(f"[HANDOVER] Push failed (network/auth) — file saved locally")
        print(push.stderr.strip()[:200])
else:
    if "nothing to commit" in commit.stdout:
        print("[HANDOVER] No new changes to commit")
    else:
        print(f"[HANDOVER] Commit failed: {commit.stderr.strip()[:200]}")

print(f"[HANDOVER] Complete — {session_path.name}")
