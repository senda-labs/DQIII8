#!/usr/bin/env python3
"""
DQIII8 — Gemini Pro Code Reviewer via Aider
Detects unreviewed .py files and runs an efficiency audit.
Saves report in database/audit_reports/ and registers it in the DB.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import logging
log = logging.getLogger(__name__)
JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = JARVIS / "database" / "dqiii8.db"
REPORTS_DIR = JARVIS / "database" / "audit_reports"
AIDER_PROMPT = """\
You are a senior-level Python code reviewer. Analyze the file efficiently:

1. **Potential bugs**: logic errors, race conditions, unhandled exceptions.
2. **Efficiency**: expensive operations, N+1 queries, unnecessary memory usage.
3. **Readability**: confusing names, overly long functions, obsolete comments.
4. **Security**: command injection, unsanitized paths, exposed credentials.

Respond ONLY with valid JSON (no markdown):
{
  "file": "<name>",
  "score": <0.0-1.0>,
  "issues": [{"severity": "high|medium|low", "line": <n|null>, "description": "<text>"}],
  "recommendations": ["<concrete action>"]
}
"""


def load_env() -> None:
    env_path = JARVIS / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() and key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()


def get_unreviewed_files() -> list[Path]:
    """Returns .py files modified since the last review registered in the DB."""
    reviewed: set[str] = set()

    if DB.exists():
        try:
            conn = sqlite3.connect(str(DB), timeout=5)
            rows = conn.execute(
                "SELECT top_error_keywords FROM audit_reports "
                "WHERE top_error_keywords IS NOT NULL ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
            conn.close()
            for (raw,) in rows:
                if raw and raw.startswith("["):
                    reviewed.update(json.loads(raw))
        except Exception as _exc:
            log.warning('%s: %s', __name__, _exc)

    # .py files modified in git (staged + unstaged + untracked)
    result = subprocess.run(
        ["git", "-C", str(JARVIS), "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    candidates: list[Path] = []
    for name in result.stdout.splitlines():
        if name.endswith(".py"):
            p = JARVIS / name
            if p.exists() and p.name not in reviewed:
                candidates.append(p)

    # Also include tracked files with unstaged changes
    result2 = subprocess.run(
        ["git", "-C", str(JARVIS), "diff", "--name-only"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    for name in result2.stdout.splitlines():
        if name.endswith(".py"):
            p = JARVIS / name
            if p.exists() and p not in candidates and p.name not in reviewed:
                candidates.append(p)

    return candidates


def run_review(files: list[Path]) -> list[dict]:
    """Runs aider on each file and parses the JSON response."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[gemini-review] ERROR: GEMINI_API_KEY not configured in .env", file=sys.stderr)
        sys.exit(1)

    results = []
    for f in files:
        print(f"[gemini-review] Reviewing {f.name} ...", flush=True)
        try:
            proc = subprocess.run(
                [
                    "aider",
                    "--model", "gemini/gemini-2.0-flash",
                    "--no-git",
                    "--yes",
                    "--no-auto-commits",
                    "--message", AIDER_PROMPT,
                    str(f),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "GEMINI_API_KEY": api_key},
            )
            output = proc.stdout + proc.stderr
            # Extract first JSON block from the output
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                try:
                    parsed = json.loads(output[json_start:json_end])
                    parsed["file"] = f.name
                    results.append(parsed)
                except json.JSONDecodeError as je:
                    results.append({
                        "file": f.name,
                        "score": None,
                        "issues": [],
                        "recommendations": [f"JSON parse error: {je}"],
                        "raw": output[:500],
                    })
            else:
                results.append({
                    "file": f.name,
                    "score": None,
                    "issues": [],
                    "recommendations": ["Could not parse Gemini response"],
                    "raw": output[:500],
                })
        except subprocess.TimeoutExpired:
            results.append({
                "file": f.name,
                "score": None,
                "issues": [],
                "recommendations": ["Timeout while reviewing the file"],
            })
        except Exception as e:
            results.append({
                "file": f.name,
                "score": None,
                "issues": [],
                "recommendations": [f"Error: {e}"],
            })
    return results


def save_report(files: list[Path], results: list[dict]) -> Path:
    """Saves .md report in audit_reports/ and registers it in the DB."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"gemini_review_{ts}.md"

    valid_scores = [r["score"] for r in results if r.get("score") is not None]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else None
    avg_score_display = f"{avg_score:.2f}" if avg_score is not None else "N/A"

    lines = [
        f"# Gemini Code Review — {now.strftime('%Y-%m-%d %H:%M')}",
        f"\n**Global score:** {avg_score_display}  |  **Files reviewed:** {len(results)}\n",
    ]
    for r in results:
        lines.append(f"\n## {r['file']}  (score: {r.get('score', '?')})")
        issues = r.get("issues", [])
        if issues:
            lines.append("\n### Issues")
            for issue in issues:
                sev = issue.get("severity", "?").upper()
                ln = issue.get("line")
                desc = issue.get("description", "")
                loc = f" (l.{ln})" if ln else ""
                lines.append(f"- [{sev}]{loc} {desc}")
        recs = r.get("recommendations", [])
        if recs:
            lines.append("\n### Recommendations")
            for rec in recs:
                lines.append(f"- {rec}")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[gemini-review] Report saved: {report_path}")

    # Register in DB only if there is a valid score
    if DB.exists() and avg_score is not None:
        try:
            conn = sqlite3.connect(str(DB), timeout=5)
            conn.execute(
                """INSERT INTO audit_reports
                   (timestamp, global_success_rate, top_error_keywords,
                    worst_agent, recommendations, overall_score)
                   VALUES (?,?,?,?,?,?)""",
                (
                    now.isoformat(),
                    1.0,
                    json.dumps([f.name for f in files]),
                    None,
                    json.dumps([r.get("recommendations", []) for r in results]),
                    avg_score,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[gemini-review] DB skip: {e}", file=sys.stderr)
    elif avg_score is None:
        print("[gemini-review] Invalid score (all fallbacks) — skipping INSERT into DB")

    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Pro code reviewer via Aider")
    parser.add_argument("--check-only", action="store_true",
                        help="Only report how many files are pending (without reviewing)")
    parser.add_argument("files", nargs="*", help="Specific files to review")
    args = parser.parse_args()

    if args.check_only:
        files = get_unreviewed_files()
        print(f"{len(files)} files pending review")
        sys.exit(0)

    load_env()

    if args.files:
        files = [Path(f) for f in args.files if Path(f).exists()]
    else:
        files = get_unreviewed_files()

    if not files:
        print("[gemini-review] No .py files pending review.")
        sys.exit(0)

    print(f"[gemini-review] Reviewing {len(files)} file(s) with Gemini 2.0 Flash...")
    results = run_review(files)
    report = save_report(files, results)

    # Git add + push so it reaches Obsidian
    try:
        subprocess.run(
            ["git", "-C", str(JARVIS), "add", str(report)],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", str(JARVIS), "commit", "-m",
             f"chore(review): gemini review {datetime.now().strftime('%Y-%m-%d')}"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", str(JARVIS), "push", "origin", "master"],
            capture_output=True, timeout=30
        )
        print("[gemini-review] Report pushed to Obsidian.")
    except Exception as e:
        print(f"[gemini-review] Git push skip: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
