#!/usr/bin/env python3
"""
DQ Interactive Chat — multi-turn terminal session.

Usage:
    dq --chat
    python3 bin/interactive_chat.py

Commands inside chat:
    /exit  /quit    End session and save
    /clear          Clear the screen and history
    /status         Show system health score
    /audit          Run local health auditor
    /tier           Show current routing tier
    /help           List commands
"""

import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"

# ── ANSI helpers ──────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
BLUE   = "\033[94m"
GREEN  = "\033[92m"
GRAY   = "\033[90m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def _clear_screen() -> None:
    # ANSI: clear screen + move cursor home (no shell injection risk)
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _render_md(text: str) -> str:
    """Minimal markdown → ANSI: bold, inline code, code blocks."""
    # Code blocks
    def _code_block(m: re.Match) -> str:
        lines = m.group(1).strip().splitlines()
        bar = _c(GRAY, "─" * 44)
        content = "\n".join(_c(CYAN, "  " + line) for line in lines)
        return f"\n{bar}\n{content}\n{bar}"
    text = re.sub(r"```(?:\w*\n)?(.*?)```", _code_block, text, flags=re.DOTALL)

    # Inline code
    text = re.sub(r"`([^`]+)`", lambda m: _c(CYAN, m.group(1)), text)

    # Bold
    text = re.sub(
        r"\*\*(.+?)\*\*|__(.+?)__",
        lambda m: _c(BOLD, m.group(1) or m.group(2)),
        text,
    )

    # Italic
    text = re.sub(r"\*(.+?)\*", lambda m: _c(DIM, m.group(1)), text)

    return text


# ── DB helpers ────────────────────────────────────────────────────────────────

def _save_session(session_id: str, turns: list[dict]) -> None:
    if not DB.exists() or not turns:
        return
    try:
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(DB), timeout=3)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_sessions "
            "(session_id TEXT PRIMARY KEY, created_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_messages "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, "
            "role TEXT, content TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO chat_sessions (session_id, created_at) VALUES (?, ?)",
            (session_id, ts),
        )
        for turn in turns:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, turn["role"], turn["content"][:4000], ts),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _get_health_score() -> str:
    if not DB.exists():
        return "N/A"
    try:
        conn = sqlite3.connect(str(DB), timeout=2)
        row = conn.execute(
            "SELECT overall_score FROM audit_reports ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return f"{row[0]:.0f}/100" if row else "N/A"
    except Exception:
        return "N/A"


def _get_active_tier() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "Sonnet (Tier 3)"
    if os.environ.get("GROQ_API_KEY"):
        return "Groq (Tier 2)"
    return "Ollama (Tier 1 local)"


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(prompt: str, history: list[dict]) -> str:
    """Send the current turn to openrouter_wrapper.py, including short history."""
    if history:
        ctx_lines = []
        for turn in history[-6:]:  # last 3 exchanges
            prefix = "User" if turn["role"] == "user" else "Assistant"
            ctx_lines.append(f"{prefix}: {turn['content'][:300]}")
        full_prompt = (
            "Previous conversation:\n"
            + "\n".join(ctx_lines)
            + "\n\nUser: "
            + prompt
        )
    else:
        full_prompt = prompt

    env = {**os.environ, "JARVIS_ROOT": str(JARVIS)}

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(JARVIS / "bin" / "openrouter_wrapper.py"),
                "--agent", "research-analyst",
                full_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            encoding="utf-8",
        )
        return (result.stdout or "").strip() or "(no response)"
    except subprocess.TimeoutExpired:
        return "[Timeout — no response after 120s]"
    except Exception as exc:
        return f"[Error: {exc}]"


# ── Internal command handlers ─────────────────────────────────────────────────

def _cmd_status() -> str:
    score = _get_health_score()
    tier  = _get_active_tier()
    return f"Health: {score}  |  Tier: {tier}"


def _cmd_audit() -> str:
    try:
        result = subprocess.run(
            [sys.executable, str(JARVIS / "bin" / "auditor_local.py")],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        return (result.stdout or result.stderr or "(no output)").strip()
    except Exception as exc:
        return f"Audit error: {exc}"


def _cmd_help() -> str:
    return (
        "  /exit  /quit  — end session\n"
        "  /clear         — clear screen and history\n"
        "  /status        — health score and active tier\n"
        "  /audit         — run local health auditor\n"
        "  /tier          — show routing tier\n"
        "  /help          — show this help"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Load .env
    env_file = JARVIS / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    session_id = str(uuid.uuid4())[:8]
    history: list[dict] = []
    turns_saved: list[dict] = []

    _clear_screen()
    print(_c(BOLD, "╔══════════════════════════════╗"))
    print(_c(BOLD, "║   DQ Interactive Chat        ║"))
    print(_c(BOLD, "╚══════════════════════════════╝"))
    print(_c(GRAY, f"  Session {session_id}  |  {_get_active_tier()}"))
    print(_c(GRAY,  "  Type /exit to quit, /help for commands"))
    print()

    while True:
        try:
            user_input = input(_c(BOLD + BLUE, "You") + " › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("/exit", "/quit"):
            break

        if cmd == "/clear":
            history.clear()
            turns_saved.clear()
            _clear_screen()
            print(_c(GRAY, "  History cleared."))
            continue

        if cmd == "/status":
            print(_c(GREEN, "  " + _cmd_status()))
            continue

        if cmd == "/audit":
            print(_c(GRAY, "  Running audit..."))
            print(_render_md(_cmd_audit()))
            continue

        if cmd == "/tier":
            print(_c(GREEN, "  " + _get_active_tier()))
            continue

        if cmd == "/help":
            print(_c(GRAY, _cmd_help()))
            continue

        # LLM call
        print(_c(BOLD + CYAN, "DQ") + "  › ", end="", flush=True)
        t0 = time.time()
        response = _call_llm(user_input, history)
        elapsed = time.time() - t0

        print(_render_md(response))
        print(_c(GRAY, f"     [{elapsed:.1f}s]"))
        print()

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        turns_saved.extend([
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response},
        ])

    # Save session on exit
    _save_session(session_id, turns_saved)
    print()
    print(_c(GRAY, f"  Session {session_id} saved. Goodbye!"))


if __name__ == "__main__":
    main()
