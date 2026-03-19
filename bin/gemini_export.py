"""
gemini_export.py — Exports pipeline context for Gemini Pro audit.
Usage: python3 gemini_export.py [module] [--metric X] [--question "..."]
Generates a structured .md ready to paste into Gemini Pro.
Modules: full | script | audio | video | subtitles
"""

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
PROJ = Path(os.environ.get("CONTENT_PROJECT_ROOT", str(JARVIS)))
OUT_DIR = JARVIS / "tasks" / "gemini_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def export_last_errors(n: int = 5) -> str:
    conn = sqlite3.connect(DB)
    errors = conn.execute(
        """
        SELECT created_at, objective_id, error_type,
               error_message, file, line, resolved
        FROM loop_errors
        ORDER BY id DESC LIMIT ?
        """,
        (n,),
    ).fetchall()
    conn.close()
    if not errors:
        return "No recent errors in loop_errors.\n"
    lines = ["## Latest pipeline errors\n"]
    for e in errors:
        lines.append(
            f"**[{e[0]}]** `{e[2]}` in objective `{e[1]}`\n"
            f"```\n{e[3]}\n```\n"
            f"File: `{e[4]}:{e[5]}` | Resolved: {'✅' if e[6] else '❌'}\n"
        )
    return "\n".join(lines)


def export_code_snippet(file_path: str, func_name: str = None) -> str:
    # FIX 2: full files up to 8000 chars, functions without limit
    p = Path(file_path)
    if not p.exists():
        return f"File not found: {file_path}\n"
    content = p.read_text(encoding="utf-8")
    if func_name:
        lines = content.split("\n")
        start = next(
            (
                i
                for i, l in enumerate(lines)
                if f"def {func_name}" in l or f"class {func_name}" in l
            ),
            None,
        )
        if start is not None:
            snippet = []
            indent = len(lines[start]) - len(lines[start].lstrip())
            for l in lines[start:]:
                stripped = l.lstrip()
                if (
                    stripped
                    and len(l) - len(stripped) <= indent
                    and snippet
                    and (stripped.startswith("def ") or stripped.startswith("class "))
                ):
                    break
                snippet.append(l)
            return f"```python\n# {p.name} — def {func_name}\n" f"{''.join(snippet)}\n```\n"
    return f"```python\n# {p.name}\n{content[:8000]}\n```\n"


def export_pipeline_metrics() -> str:
    conn = sqlite3.connect(DB)
    videos = conn.execute("""
        SELECT topic, mode, language, duration_s,
               file_size_mb, renderer_used, pipeline_ms,
               telegram_sent, approved
        FROM video_outputs ORDER BY id DESC LIMIT 5
        """).fetchall()
    objectives = conn.execute("""
        SELECT objective_id, description, status, result
        FROM loop_objectives ORDER BY id DESC LIMIT 10
        """).fetchall()
    conn.close()

    lines = ["## Pipeline metrics\n", "### Latest videos\n"]
    for v in videos:
        approved = "✅" if v[8] == 1 else ("❌" if v[8] == 0 else "⏳ pending")
        lines.append(
            f"- **{v[0][:60]}**\n"
            f"  Mode: `{v[1]}` | Lang: `{v[2]}` | {v[3]}s | "
            f"{v[5]} | {v[6] // 1000 if v[6] else '?'}s render | "
            f"Approved: {approved}\n"
        )
    lines.append("\n### Loop objectives\n")
    for o in objectives:
        icon = "✅" if o[2] == "done" else ("❌" if o[2] == "failed" else "⏳")
        lines.append(f"{icon} **[{o[0]}]** {o[1][:80]}\n")
        if o[3]:
            lines.append(f"   → {o[3][:100]}\n")
    return "\n".join(lines)


def generate_gemini_report(
    module: str = "full",
    include_errors: bool = True,
    code_files: list = None,
    question: str = None,  # FIX 1: parameter added
    metric: str = "virality",  # FIX 1: parameter added
) -> str:
    """
    Generates structured report for Gemini Pro.
    module:  'full' | 'audio' | 'video' | 'script' | 'subtitles'
    metric:  'virality' | 'performance' | 'architecture'
    question: specific question for the auditor (optional)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    sections = []

    # Header — FIX 1: uses metric and question
    sections.append(
        f"# DQIII8 — Report for Gemini Pro Audit\n"
        f"**Timestamp:** {timestamp}\n"
        f"**Module:** {module}\n"
        f"**Success metric:** {metric}\n"
        f"**Specific question:** {question or 'General audit'}\n\n---\n"
    )

    # Tech stack
    sections.append(
        "## Tech stack\n"
        "- **VPS:** Ubuntu 24.04 | 8GB RAM | 4 CPUs | 100GB NVMe\n"
        "- **Pipeline:** Python + MoviePy + ElevenLabs + FFmpeg\n"
        "- **Models:** Groq (LLaMA 3.3 70b) + ElevenLabs TTS + Claude API\n"
        "- **DB:** SQLite jarvis_metrics.db\n"
        f"- **Repo:** {PROJ}/\n\n---\n"
    )

    sections.append(export_pipeline_metrics())
    sections.append("\n---\n")

    if include_errors:
        sections.append(export_last_errors())
        sections.append("\n---\n")

    MODULE_FILES = {
        "script": ["backend/services/script_service.py"],
        "audio": [
            "backend/services/sound_design.py",
            "scripts/pipeline/audio.py",
        ],
        "video": ["scripts/pipeline/renderer.py"],
        "subtitles": ["backend/services/netflix_subtitle_generator.py"],
        "full": [
            "backend/services/script_service.py",
            "scripts/pipeline/renderer.py",
            "backend/services/netflix_subtitle_generator.py",
        ],
    }
    files_to_export = code_files or MODULE_FILES.get(module, [])

    sections.append("## Relevant code\n")
    for f in files_to_export:
        sections.append(f"### `{f}`\n")
        sections.append(export_code_snippet(str(PROJ / f)))

    # Footer — FIX 1: uses question and metric
    sections.append(
        f"---\n## Question for the auditor\n\n"
        f"We are optimizing for: **{metric}**\n\n"
        + (
            question
            or (
                "Review the full pipeline and identify:\n"
                "1. Potential FFmpeg/OpenCV/NumPy failures before execution\n"
                "2. Performance bottlenecks\n"
                "3. Quality gaps to reach viral standard (1M views)\n"
                "Be specific with line numbers and concrete functions."
            )
        )
        + "\n"
    )

    report = "\n".join(sections)
    out_path = OUT_DIR / f"gemini_{module}_{timestamp}.md"
    out_path.write_text(report, encoding="utf-8")

    # Exact format that the Telegram handler looks for (FIX 3 dependency):
    print(f"✅ Report generated: {out_path}")
    print(f"   Size: {len(report)} chars")
    print(f"\nFirst 300 chars:")
    print(report[:300])
    return str(out_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate audit report for Gemini Pro")
    parser.add_argument(
        "module",
        nargs="?",
        default="full",
        choices=["full", "audio", "video", "script", "subtitles"],
    )
    parser.add_argument(
        "--metric",
        default="virality",
        choices=["virality", "performance", "architecture"],
    )
    parser.add_argument("--question", default=None)
    parser.add_argument("--no-errors", action="store_true", default=False)
    args = parser.parse_args()

    generate_gemini_report(
        module=args.module,
        include_errors=not args.no_errors,
        question=args.question,
        metric=args.metric,
    )
