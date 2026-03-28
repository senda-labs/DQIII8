"""Autonomous orchestrator for Telegram /cc and /auto commands.

Runs Claude Code as an async subprocess with:
- Project detection from prompt keywords
- Progressive feedback via Telegram message editing
- File delivery on completion
- No fixed timeout — monitors until done
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
PROJECTS_DIR = DQIII8_ROOT / "my-projects"

# ── Project detection ─────────────────────────────────────────────────────────

# Keywords → project directory name
_PROJECT_KEYWORDS: dict[str, list[str]] = {
    "intl-reports": [
        "intl",
        "internacionalización",
        "internacionalizacion",
        "diagnóstico",
        "diagnostico",
        "anova",
        "ginard",
        "codima",
        "servifund",
        "plan de internacionalización",
        "plan internacionalización",
    ],
    "automatic-nutrition": [
        "nutrición",
        "nutricion",
        "dieta",
        "meal",
        "nutrition",
        "calories",
    ],
    "content-automation": [
        "vídeo",
        "video",
        "faceless",
        "tiktok",
        "subtítulos",
        "subtitulos",
        "cip",
        "content pipeline",
    ],
}


def detect_project(prompt: str) -> tuple[Path, str | None]:
    """Detect which project a prompt refers to.

    Returns (cwd, project_context) where:
      cwd: working directory for Claude Code
      project_context: PROJECT.md content (or None for root)
    """
    prompt_lower = prompt.lower()

    for project_name, keywords in _PROJECT_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                project_dir = PROJECTS_DIR / project_name
                if project_dir.is_dir():
                    project_md = project_dir / "PROJECT.md"
                    context = None
                    if project_md.exists():
                        context = project_md.read_text(encoding="utf-8")[:3000]
                    log.info("Detected project: %s (keyword: %s)", project_name, kw)
                    return project_dir, context

    return DQIII8_ROOT, None


# ── Async Claude runner with progress ─────────────────────────────────────────


async def run_claude_streaming(
    prompt: str,
    cwd: Path,
    system_prompt: str | None = None,
    model: str = "claude-sonnet-4-6",
    on_progress: object = None,
) -> tuple[bool, str, list[Path]]:
    """Run claude -p as async subprocess, stream progress updates.

    Args:
        prompt: The prompt to send
        cwd: Working directory
        system_prompt: Optional system prompt prepended
        model: Model to use
        on_progress: async callable(phase: str, elapsed: float) for updates

    Returns:
        (success, output_text, detected_file_paths)
    """
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "text",
        prompt,
    ]
    if system_prompt:
        cmd.insert(3, "--system-prompt")
        cmd.insert(4, system_prompt)

    env = dict(os.environ)
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    t0 = time.time()
    output_lines: list[str] = []
    last_update = t0

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )

        # Read stdout line by line
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=600)
            except asyncio.TimeoutError:
                log.warning("Claude stdout read timeout after 600s")
                break

            if not line:
                break

            decoded = line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(decoded)

            # Send progress update every 15s
            now = time.time()
            if on_progress and (now - last_update) >= 15:
                elapsed = now - t0
                phase = _detect_phase(output_lines)
                await on_progress(phase, elapsed)
                last_update = now

        await proc.wait()
        elapsed = time.time() - t0

        stderr = ""
        if proc.stderr:
            stderr = (await proc.stderr.read()).decode("utf-8", errors="replace")

        full_output = "\n".join(output_lines)
        success = proc.returncode == 0

        if not full_output.strip() and stderr:
            full_output = stderr[:2000]

        files = _detect_files(full_output, cwd)

        log.info(
            "Claude finished: success=%s, %d chars, %.1fs, %d files",
            success,
            len(full_output),
            elapsed,
            len(files),
        )
        return success, full_output, files

    except Exception as exc:
        elapsed = time.time() - t0
        log.error("Claude subprocess error after %.1fs: %s", elapsed, exc)
        return False, f"Error: {exc}", []


def _detect_phase(lines: list[str]) -> str:
    """Heuristic: detect current phase from output lines."""
    recent = "\n".join(lines[-20:]).lower()

    if "phase 5" in recent or "quality" in recent:
        return "Quality review"
    if "phase 4" in recent or "docx" in recent or "assembly" in recent:
        return "DOCX assembly"
    if "phase 3" in recent or "plan" in recent:
        return "Plan generation"
    if "phase 2" in recent or "diagnostic" in recent:
        return "Diagnostic writing"
    if "phase 1" in recent or "research" in recent or "crawl" in recent:
        return "Research"
    if "commit" in recent or "push" in recent:
        return "Git operations"
    if "test" in recent or "pytest" in recent:
        return "Running tests"
    if "install" in recent or "pip" in recent:
        return "Installing deps"

    return "Working..."


def _detect_files(output: str, cwd: Path) -> list[Path]:
    """Extract file paths from Claude output that exist on disk."""
    files: list[Path] = []
    seen: set[str] = set()

    patterns = [
        r"(?:Created|Wrote|Saved|Generated|Output).*?:\s*(.+\.(?:docx|pdf|png|xlsx|json|md))",
        r"(data/outputs/[^\s]+\.(?:docx|pdf|png))",
        r"(/[^\s]+\.(?:docx|pdf|png|xlsx))",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, output, re.IGNORECASE):
            path_str = match.group(1).strip().rstrip(".,;)")
            p = Path(path_str)
            if not p.is_absolute():
                p = cwd / path_str
            if p.exists() and str(p) not in seen:
                files.append(p)
                seen.add(str(p))

    return files


# ── Progress message formatter ────────────────────────────────────────────────


def format_progress(phase: str, elapsed: float, done: bool = False) -> str:
    """Format a progress update message."""
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    if done:
        return f"Completado en {time_str}."

    return f"[{time_str}] {phase}"


def format_summary(
    success: bool,
    output: str,
    files: list[Path],
    elapsed: float,
) -> str:
    """Format final summary message."""
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    status = "OK" if success else "ERROR"

    lines = [l.strip() for l in output.split("\n") if l.strip()]
    summary_lines = lines[-15:] if len(lines) > 15 else lines

    parts = [
        f"Status: {status} ({time_str})",
    ]

    if files:
        parts.append(f"Files: {len(files)}")
        for f in files[:5]:
            parts.append(f"  {f.name}")

    if summary_lines:
        summary = "\n".join(summary_lines)
        if len(summary) > 3000:
            summary = summary[:3000] + "..."
        parts.append(f"\n{summary}")

    return "\n".join(parts)
