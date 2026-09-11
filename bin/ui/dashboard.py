#!/usr/bin/env python3
"""
DQ Dashboard — Web interface for DQIII8.
Exposes metrics, task execution, and real-time task preview.

Usage:
    python3 bin/dashboard.py                    # localhost:8080
    python3 bin/dashboard.py --host 0.0.0.0     # all interfaces (token required)
    python3 bin/dashboard.py --port 9090        # custom port
"""

import asyncio
import json
import os
import sqlite3
import sys
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
CHAT_DB_PATH = ROOT_DIR / "database" / "dqiii8_knowledge.db"

# REGLA NIM (CLAUDE.md § REGLA NIM, .claude/rules/00_core_behavior.md): user
# directive since 2026-08-18, non-Anthropic providers are dormant, not
# eliminated. Reactivation needs a human probe + explicit user confirmation —
# an agent must never declare it live on its own, so this stays a manually
# toggled constant rather than something a live network probe could flip.
# Flip to False only when the user has explicitly lifted the directive.
NON_ANTHROPIC_DORMANT = True

for _d in [ROOT_DIR / "bin" / s for s in ["", "core", "agents", "monitoring", "tools", "ui"]]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

try:
    from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("FastAPI not installed. Run: pip install fastapi uvicorn python-multipart")
    sys.exit(1)

from dashboard_security import get_or_create_dashboard_token, verify_token
from db import get_db

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin.core.logging_config import get_logger as _get_logger
import human_hours
from model_map import DEFAULT_MODEL, resolve_model

log = _get_logger(__name__)
# ── Config ────────────────────────────────────────────────────────────────
HOST = os.environ.get("DQIII8_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DQIII8_DASHBOARD_PORT", "8080"))
# Always require the token, even on loopback (RT-001, red-team 2026-09-07): a
# shared multi-tenant box means "loopback-only" isn't a strong enough boundary
# on its own — any other local process (root or otherwise) could read
# operational telemetry from /api/health with zero defense-in-depth.
REQUIRE_AUTH = True


# ── Claude OAuth detection ────────────────────────────────────────────────


def detect_claude_oauth() -> dict:
    """Check if Claude Code CLI is installed and authenticated.

    Detection priority:
    1. Credential JSON files in ~/.claude/
    2. Active session files or history (strong signal of authenticated usage)
    3. Live CLI probe as last resort
    """
    claude_dir = Path.home() / ".claude"

    # 1) Check standard credential file locations
    for fname in ("credentials.json", "auth.json", ".credentials.json", ".auth.json"):
        f = claude_dir / fname
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if any(
                    data.get(k) for k in ("token", "access_token", "sessionKey", "claudeApiKey")
                ):
                    return {
                        "available": True,
                        "method": "oauth_file",
                        "plan": "Pro/Team",
                    }
            except Exception:
                pass  # Fail-open: failure must not break pipeline

    # 2) Check CLI is installed
    try:
        v = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        if v.returncode != 0:
            return {"available": False, "method": None, "plan": None}
        version_str = v.stdout.strip().split("\n")[0]
    except Exception:
        return {"available": False, "method": None, "plan": None}

    # 3) Strong signals: history.jsonl > 100 bytes OR sessions/ directory non-empty
    #    Both mean the CLI has been actively used → almost certainly authenticated
    history_file = claude_dir / "history.jsonl"
    has_history = history_file.exists() and history_file.stat().st_size > 100

    sessions_dir = claude_dir / "sessions"
    has_sessions = sessions_dir.is_dir() and any(True for _ in sessions_dir.iterdir())

    if has_history or has_sessions:
        return {
            "available": True,
            "method": "oauth_cli",
            "plan": "Pro/Team",
            "version": version_str,
        }

    # 4) Last resort: live test (slow, ~5-20s)
    try:
        r2 = subprocess.run(
            ["claude", "-p", "say ok"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if r2.returncode == 0:
            return {
                "available": True,
                "method": "oauth_cli",
                "plan": "Pro/Team",
                "version": version_str,
            }
    except Exception as _exc:
        log.warning("%s: %s", __name__, _exc)

    return {
        "available": False,
        "method": "installed_only",
        "plan": None,
        "version": version_str,
    }


def _mask_key(v: str) -> str:
    if not v or len(v) < 10:
        return ""
    return v[:4] + "••••" + v[-4:]


def _load_env_dict() -> dict:
    env_file = ROOT_DIR / ".env"
    result: dict = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _write_env_key(key: str, value: str) -> None:
    """Safely update or append a single key in .env."""
    env_file = ROOT_DIR / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    written = False
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            if stripped.partition("=")[0].strip() == key:
                output.append(f"{key}={value}")
                written = True
                continue
        output.append(line)
    if not written:
        output.append(f"{key}={value}")
    env_file.write_text("\n".join(output) + "\n", encoding="utf-8")
    env_file.chmod(0o600)


# Intent pattern → representative subtasks
_INTENT_SUBTASKS: dict[str, list[str]] = {
    "analyze": [
        "Data Collection",
        "Statistical Analysis",
        "Pattern Detection",
        "Report Generation",
    ],
    "generate": ["Requirements Analysis", "Draft Creation", "Review", "Finalization"],
    "optimize": [
        "Performance Profiling",
        "Bottleneck Identification",
        "Refactoring",
        "Benchmarking",
    ],
    "debug": [
        "Error Reproduction",
        "Root Cause Analysis",
        "Fix Implementation",
        "Regression Testing",
    ],
    "research": ["Source Discovery", "Data Extraction", "Analysis", "Synthesis"],
    "summarize": ["Content Parsing", "Key Points Extraction", "Summary Draft"],
    "compare": ["Criteria Definition", "Data Collection", "Analysis", "Recommendation"],
    "forecast": [
        "Historical Analysis",
        "Model Selection",
        "Projection",
        "Confidence Intervals",
    ],
    "explain": ["Concept Decomposition", "Examples", "Analogies", "Summary"],
    "transform": ["Source Parsing", "Mapping", "Transformation", "Validation"],
    "validate": ["Schema Check", "Business Rules", "Edge Cases", "Report"],
    "plan": [
        "Requirements Gathering",
        "Architecture Design",
        "Task Breakdown",
        "Timeline",
    ],
    "automate": ["Process Mapping", "Script Development", "Testing", "Deployment"],
    "report": ["Data Collection", "Analysis", "Visualization", "Executive Summary"],
}

# ── HTML templates (lazy-loaded on startup) ────────────────────────────────
DASHBOARD_HTML: str = ""
LOGIN_HTML: str = ""

DASHBOARD_HTML_PATH = ROOT_DIR / "bin" / "ui" / "dashboard.html"
LOGIN_HTML_PATH = ROOT_DIR / "bin" / "ui" / "login.html"

_LOGIN_FALLBACK = """<!DOCTYPE html><html><body style="background:#0a0a0f;color:#fff;font-family:monospace;display:flex;align-items:center;justify-content:center;min-height:100vh">
<form action="/" method="GET" style="text-align:center;gap:1rem;display:flex;flex-direction:column">
  <h1>DQ Dashboard</h1><p>Enter access token:</p>
  <input type="password" name="token" style="padding:.5rem;font-family:monospace;background:#1a1a2e;color:#fff;border:1px solid #333">
  <button type="submit" style="padding:.5rem 1rem;background:#2563eb;color:#fff;border:none;cursor:pointer">Login</button>
  <small>Token in: database/.dashboard_token</small>
</form></body></html>"""


def _load_html(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback


# ── Upload directory ───────────────────────────────────────────────────────
UPLOAD_DIR = ROOT_DIR / "uploads" / "chat"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".xlsx",
    ".xls",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".docx",
    ".pptx",
    # Removed: .py, .js, .ts, .html (executable content — use CLI for scripts)
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _extract_text(path: Path, suffix: str) -> str:
    """Best-effort text extraction from uploaded file."""
    if suffix in (".txt", ".md", ".json", ".csv", ".py", ".js"):
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:8000]
        except Exception:
            return ""
    if suffix == ".pdf":
        # Try pdftotext CLI first
        try:
            r = subprocess.run(
                ["pdftotext", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0 and r.stdout:
                return r.stdout[:8000]
        except FileNotFoundError:
            pass
        # Fallback: PyPDF2
        try:
            import PyPDF2  # type: ignore

            text = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages[:20]:
                    text.append(page.extract_text() or "")
            return "\n".join(text)[:8000]
        except Exception as _exc:
            log.warning("%s: %s", __name__, _exc)
        return "[PDF — text extraction unavailable; install pdftotext or PyPDF2]"
    if suffix in (".xlsx", ".xls"):
        try:
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            rows = []
            for sheet in wb.worksheets[:3]:
                for row in sheet.iter_rows(max_row=200, values_only=True):
                    rows.append("\t".join("" if v is None else str(v) for v in row))
            return "\n".join(rows)[:8000]
        except Exception:
            return "[Excel — install openpyxl for text extraction]"
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        return f"[Image file: {path.name}]"
    return ""


# ── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global DASHBOARD_HTML, LOGIN_HTML
    DASHBOARD_HTML = _load_html(
        DASHBOARD_HTML_PATH, "<h1>DQ Dashboard</h1><p>dashboard.html not found.</p>"
    )
    LOGIN_HTML = _load_html(LOGIN_HTML_PATH, _LOGIN_FALLBACK)

    token = get_or_create_dashboard_token()
    if REQUIRE_AUTH:
        print(f"\n  DQ Dashboard running on http://{HOST}:{PORT}")
        print(f"  Auth token: {token[:8]}...{token[-4:]}")
        print(f"  Access: http://{HOST}:{PORT}?token=<see token file>\n")
    else:
        print(f"\n  DQ Dashboard running on http://{HOST}:{PORT}")
        print(f"  Localhost mode — no auth required\n")
    yield


app = FastAPI(title="DQ Dashboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth dependency ───────────────────────────────────────────────────────
async def check_auth(request: Request) -> bool:
    """Require token auth when dashboard is exposed beyond localhost."""
    if not REQUIRE_AUTH:
        return True

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        token = request.cookies.get("dq_token", "")

    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return True


# ── API Endpoints ─────────────────────────────────────────────────────────


@app.get("/api/health")
async def health(auth: bool = Depends(check_auth)):
    """System health and aggregated metrics for the last 7 days."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    with get_db() as conn:
        sessions = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE date(start_time) >= ?", (week_ago,)
        ).fetchone()[0]

        actions = conn.execute(
            """
            SELECT COUNT(*) as total,
                   ROUND(AVG(success) * 100, 1) as success_rate
            FROM agent_actions WHERE date(timestamp) >= ?
        """,
            (week_ago,),
        ).fetchone()

        errors = conn.execute(
            """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN resolved = 1 THEN 1 ELSE 0 END) as resolved
            FROM error_log WHERE date(timestamp) >= ?
        """,
            (week_ago,),
        ).fetchone()

        tiers = conn.execute(
            """
            SELECT tier, COUNT(*) as count,
                   ROUND(SUM(estimated_cost_usd), 4) as cost
            FROM agent_actions WHERE date(timestamp) >= ?
            GROUP BY tier
        """,
            (week_ago,),
        ).fetchall()

        audit = conn.execute(
            "SELECT overall_score, timestamp FROM audit_reports ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()

    tier_data: dict = {}
    for row in tiers:
        t = str(row[0] or "unknown")
        tier_data[t] = {"count": row[1], "cost": row[2] or 0}

    total_errors = errors[0] if errors else 0
    resolved_errors = errors[1] if errors else 0

    return {
        "health_score": audit[0] if audit else None,
        "last_audit": audit[1] if audit else None,
        "sessions_7d": sessions,
        "actions_7d": actions[0] if actions else 0,
        "success_rate": actions[1] if actions else 0,
        "errors_open": (total_errors or 0) - (resolved_errors or 0),
        "errors_resolved": resolved_errors or 0,
        "tiers": tier_data,
    }


@app.get("/api/health/detail")
async def health_detail(metric: str, auth: bool = Depends(check_auth)):
    """Per-metric breakdown for the Overview inner menu. metric = health|actions|success."""
    if metric not in ("health", "actions", "success"):
        raise HTTPException(
            status_code=400, detail="metric must be one of: health, actions, success"
        )
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    with get_db() as conn:
        if metric == "health":
            rows = conn.execute(
                "SELECT overall_score, timestamp FROM audit_reports ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
            return {"recent_audits": [{"overall_score": r[0], "timestamp": r[1]} for r in rows]}

        if metric == "actions":
            by_day = conn.execute(
                """
                SELECT date(timestamp) as day, COUNT(*) as count
                FROM agent_actions WHERE date(timestamp) >= ?
                GROUP BY day ORDER BY day DESC
                """,
                (week_ago,),
            ).fetchall()
            by_agent = conn.execute(
                """
                SELECT agent_name, COUNT(*) as count
                FROM agent_actions WHERE date(timestamp) >= ?
                GROUP BY agent_name ORDER BY count DESC LIMIT 10
                """,
                (week_ago,),
            ).fetchall()
            return {
                "by_day": [{"day": r[0], "count": r[1]} for r in by_day],
                "by_agent": [{"agent": r[0] or "unknown", "count": r[1]} for r in by_agent],
            }

        by_tier = conn.execute(
            """
            SELECT tier, ROUND(AVG(success) * 100, 1) as success_rate, COUNT(*) as count
            FROM agent_actions WHERE date(timestamp) >= ?
            GROUP BY tier ORDER BY count DESC
            """,
            (week_ago,),
        ).fetchall()
        return {
            "by_tier": [
                {"tier": r[0] or "unknown", "success_rate": r[1] or 0, "count": r[2]}
                for r in by_tier
            ]
        }


@app.post("/api/human-hours/{action}")
async def human_hours_action(action: str, request: Request, auth: bool = Depends(check_auth)):
    """Start/stop a human_hours session for a project — dashboard-side alternative
    to the Telegram /hora inicio|fin command, same underlying table/logic."""
    if action not in ("inicio", "fin"):
        raise HTTPException(status_code=404, detail="action must be inicio or fin")
    body = await request.json()
    project = str(body.get("project") or "").strip()
    if not project:
        raise HTTPException(status_code=400, detail="project is required")
    if len(project) > 200:
        raise HTTPException(status_code=400, detail="project must be <= 200 characters")
    ok, msg = (
        human_hours.hora_inicio(project, source="manual")
        if action == "inicio"
        else human_hours.hora_fin(project)
    )
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    return {"message": msg}


@app.get("/api/sessions")
async def recent_sessions(limit: int = 20, auth: bool = Depends(check_auth)):
    """Recent sessions with derived status and action count."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT session_id, start_time, end_time,
                   CASE WHEN end_time IS NULL THEN 'active' ELSE 'ended' END as status,
                   (SELECT COUNT(*) FROM agent_actions WHERE session_id = s.session_id) as actions
            FROM sessions s
            ORDER BY start_time DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

    return [{"id": r[0], "start": r[1], "end": r[2], "status": r[3], "actions": r[4]} for r in rows]


@app.get("/api/tasks/recent")
async def recent_tasks(limit: int = 50, auth: bool = Depends(check_auth)):
    """Recent agent_actions records."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, agent_name, tier, success,
                   duration_ms, estimated_cost_usd, tokens_input, tokens_output
            FROM agent_actions
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

    return [
        {
            "timestamp": r[0],
            "agent": r[1],
            "tier": r[2],
            "success": bool(r[3]),
            "duration_ms": r[4],
            "cost": r[5],
            "tokens_in": r[6],
            "tokens_out": r[7],
        }
        for r in rows
    ]


def _heuristic_tasks(rows) -> list:
    """Fallback grouping for agent_actions rows with no agent_id (top-level session
    actions, or rows written before the Fase B migration): consecutive rows sharing
    (session_id, agent_name) belong to the same task unless a gap of more than 90s
    separates them. Approximate by design — see plan doc for why an exact FK isn't
    always available."""
    GAP_S = 90
    tasks: list = []
    cur: dict | None = None
    prev_ts: datetime | None = None
    for session_id, agent_name, tool_used, ts, success in rows:
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        new_group = (
            cur is None
            or cur["session_id"] != session_id
            or cur["skill"] != (agent_name or "unknown")
            or prev_ts is None
            or (ts_dt - prev_ts).total_seconds() > GAP_S
        )
        if new_group:
            cur = {
                "session_id": session_id,
                "skill": agent_name or "unknown",
                "model": resolve_model(agent_name),
                "tools": set(),
                "actions": 0,
                "success": True,
                "started_at": ts,
                "ended_at": ts,
                "exact": False,
            }
            tasks.append(cur)
        cur["tools"].add(tool_used or "?")
        cur["actions"] += 1
        cur["success"] = cur["success"] and bool(success)
        cur["ended_at"] = ts
        prev_ts = ts_dt
    return tasks


@app.get("/api/tasks/grouped")
async def grouped_tasks(limit: int = 20, auth: bool = Depends(check_auth)):
    """Recent work grouped by task (skill/agent invocation), not raw tool calls.

    Prefers an exact grouping via agent_registry (closed by SubagentStop, Fase B)
    when the schema migration has landed; falls back to the Fase A heuristic
    (session + 90s gap) for rows with no agent_id — top-level session actions, or
    data written before the migration. See ~/.claude/plans/parsed-swinging-donut.md.
    """
    window_start = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    tasks: list = []

    with get_db() as conn:
        try:
            registry_rows = conn.execute(
                """
                SELECT agent_id, agent_type, start_time, end_time
                FROM agent_registry
                WHERE end_time IS NOT NULL AND end_time >= ?
                """,
                (window_start,),
            ).fetchall()
            # Single aggregated query instead of one SELECT per agent_registry row
            # (was O(n) round-trips; measured ~2x slower than sibling endpoints at
            # only 3 rows — would scale linearly with subagent volume otherwise).
            action_rows = conn.execute(
                """
                SELECT agent_id, tool_used, success
                FROM agent_actions
                WHERE agent_id IN (SELECT agent_id FROM agent_registry WHERE end_time IS NOT NULL AND end_time >= ?)
                """,
                (window_start,),
            ).fetchall()
            actions_by_agent: dict = {}
            for agent_id, tool_used, success in action_rows:
                actions_by_agent.setdefault(agent_id, []).append((tool_used, success))

            for agent_id, agent_type, start_time, end_time in registry_rows:
                rows = actions_by_agent.get(agent_id, [])
                tasks.append(
                    {
                        "skill": agent_type or "unknown",
                        "model": resolve_model(agent_type),
                        "tools": sorted({t or "?" for t, _ in rows}),
                        "actions": len(rows),
                        "success": all(bool(s) for _, s in rows) if rows else True,
                        "started_at": start_time,
                        "ended_at": end_time,
                        "exact": True,
                    }
                )
            unheuristic_rows = conn.execute(
                """
                SELECT session_id, agent_name, tool_used, timestamp, success
                FROM agent_actions
                WHERE timestamp >= ? AND agent_id IS NULL
                ORDER BY session_id, timestamp
                """,
                (window_start,),
            ).fetchall()
        except sqlite3.OperationalError:
            # Fase B migration not applied yet (no agent_registry.end_time /
            # agent_actions.agent_id columns) — degrade to pure heuristic.
            unheuristic_rows = conn.execute(
                """
                SELECT session_id, agent_name, tool_used, timestamp, success
                FROM agent_actions
                WHERE timestamp >= ?
                ORDER BY session_id, timestamp
                """,
                (window_start,),
            ).fetchall()

    for t in _heuristic_tasks(unheuristic_rows):
        t.pop("session_id", None)
        tasks.append(t)

    tasks.sort(key=lambda t: t["ended_at"], reverse=True)
    return tasks[:limit]


@app.get("/api/production")
async def production_metrics(auth: bool = Depends(check_auth)):
    """Per-project agent-compute and human-hours metrics for the Produccion tab."""
    _my_projects = ROOT_DIR / "my-projects"
    known_projects = (
        {p.name for p in _my_projects.iterdir() if p.is_dir() and not p.name.startswith(".")}
        if _my_projects.is_dir()
        else set()
    )

    with get_db() as conn:
        agent_rows = conn.execute("""
            SELECT project,
                   COUNT(*) as actions,
                   SUM(CASE WHEN duration_ms IS NOT NULL THEN 1 ELSE 0 END) as duration_covered,
                   ROUND(SUM(estimated_cost_usd), 6) as cost_usd,
                   ROUND(AVG(success) * 100, 1) as success_rate
            FROM agent_actions
            WHERE project IS NOT NULL
            GROUP BY project
            """).fetchall()

        human_rows = conn.execute("""
            SELECT project,
                   SUM((julianday(COALESCE(ended_at, 'now')) - julianday(started_at)) * 1440) as minutes,
                   MAX(CASE WHEN ended_at IS NULL THEN 1 ELSE 0 END) as is_open
            FROM human_hours
            GROUP BY project
            """).fetchall()

    projects: dict = {}
    unrecognized_agent: list = []
    unrecognized_human: list = []

    for row in agent_rows:
        name = row[0]
        actions = row[1]
        covered_pct = round((row[2] / actions) * 100, 1) if actions else 0.0
        if name not in known_projects:
            unrecognized_agent.append(name)
        projects.setdefault(name, {})["agent"] = {
            "actions": actions,
            "duration_ms_covered_pct": covered_pct,
            "cost_usd": row[3] or 0.0,
            "success_rate": row[4] or 0.0,
        }

    for row in human_rows:
        name, minutes = row[0], row[1] or 0.0
        if name not in known_projects:
            unrecognized_human.append(name)
        projects.setdefault(name, {})["human"] = {
            "minutes": round(minutes, 1),
            "open": bool(row[2]),
        }

    return {
        "projects": projects,
        "unrecognized_human_projects": unrecognized_human,
        "unrecognized_agent_projects": unrecognized_agent,
        "known_projects": sorted(known_projects),
    }


@app.post("/api/amplify")
async def amplify_intent(request: Request, auth: bool = Depends(check_auth)):
    """Real-time prompt analysis preview. Returns analysis without executing."""
    body = await request.json()
    user_input = body.get("input", "")

    if not user_input:
        raise HTTPException(400, "input field required")

    try:
        from intent_amplifier import amplify

        result = amplify(user_input)

        domains = result.get("domains", [])
        top_domain = domains[0]["domain"] if domains else ""
        top_confidence = domains[0]["score"] if domains else 0
        all_scores = {d["domain"]: d["score"] for d in domains}

        intent = result.get("intent", "")
        subtasks = _INTENT_SUBTASKS.get(intent, [])

        return {
            "action": result.get("action", ""),
            "entity": result.get("entity", ""),
            "niche": result.get("niche", ""),
            "domain": top_domain,
            "confidence": round(top_confidence, 3),
            "all_scores": all_scores,
            "pattern": intent,
            "subtasks": subtasks,
            "tier": result.get("tier", 1),
            "knowledge_used": result.get("chunks_used", 0),
            "amplified_prompt": result.get("amplified", user_input),
            "amplified_prompt_length": len(result.get("amplified", user_input)),
        }
    except ImportError:
        return {
            "error": "Feature not available",
            "action": "",
            "entity": "",
            "niche": "",
            "domain": "",
            "confidence": 0,
            "all_scores": {},
            "pattern": "",
            "subtasks": [],
            "tier": 1,
            "knowledge_used": 0,
            "amplified_prompt": user_input,
            "amplified_prompt_length": len(user_input),
        }


@app.post("/api/route")
async def route_preview(request: Request, auth: bool = Depends(check_auth)):
    """Preview domain routing for a given input (premium feature)."""
    body = await request.json()
    user_input = body.get("input", "")
    if not user_input:
        raise HTTPException(400, "input required")

    try:
        from hierarchical_router import classify_hierarchical

        result = classify_hierarchical(user_input)
        return result
    except ImportError:
        return {"error": "Feature not available"}


@app.post("/api/task/execute")
async def execute_task(request: Request, auth: bool = Depends(check_auth)):
    """Execute a prompt through claude -p (OAuth CLI) — same mechanism as
    /api/chat's tier=claude branch, kept in sync with it."""
    body = await request.json()
    user_input = body.get("input", "")

    if not user_input:
        raise HTTPException(400, "input field required")

    if not detect_claude_oauth()["available"]:
        return {
            "output": None,
            "error": "Claude not available. Authenticate with Claude Code (claude /login).",
            "exit_code": -1,
        }

    try:
        # Two bugs fixed here (2026-09-04, both confirmed via a live
        # stress-test call before the fix):
        # 1. subprocess.run([...]) (a list, no shell=True) never goes through
        #    a shell, so shlex.quote()-ing user_input was wrong — it produced
        #    a literal-quote-wrapped string (shlex.quote builds a shell
        #    command *line*, not an argv element already isolated by the list
        #    form), which combined with a stray "run" positional that
        #    openrouter_wrapper.py's CLI never accepted, failed every call
        #    with "unrecognized arguments".
        # 2. Even after fixing (1), calling openrouter_wrapper.py without
        #    --force-provider anthropic walks its full multi-tier fallback
        #    chain (groq/nim/pollinations/...) — all dormant under REGLA NIM
        #    (00_core_behavior.md) — and fails outright with "all providers
        #    failed" before ever reaching Anthropic. REGLA NIM also flatly
        #    says not to invoke openrouter_wrapper.py outside an explicit
        #    reactivation probe. Switched to claude -p directly: the same
        #    mechanism /api/chat's tier=claude branch already uses.
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            user_input,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "DQIII8_ROOT": str(ROOT_DIR)},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        return {
            "output": stdout.decode("utf-8", errors="replace"),
            "error": stderr.decode("utf-8", errors="replace") if proc.returncode != 0 else None,
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"output": None, "error": "Task timed out (120s)", "exit_code": -1}


@app.get("/api/amplification/log")
async def amplification_log(limit: int = 20, auth: bool = Depends(check_auth)):
    """Recent amplification log entries."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT created_at, original_prompt, action_detected, entity_detected,
                   niche_detected, top_domain, intent_pattern, tier_selected, elapsed_ms
            FROM amplification_log
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

    return [
        {
            "timestamp": r[0],
            "input": r[1],
            "action": r[2],
            "entity": r[3],
            "niche": r[4],
            "domain": r[5],
            "pattern": r[6],
            "tier": r[7],
            "elapsed_ms": r[8],
        }
        for r in rows
    ]


@app.get("/api/subscription")
async def subscription_status(auth: bool = Depends(check_auth)):
    """Monthly budget and API cost tracking."""
    try:
        from subscription import get_status

        return get_status()
    except Exception as exc:
        return {"error": str(exc), "unlimited": True, "used_usd": 0.0, "budget_usd": 0}


# ── Chat endpoints ────────────────────────────────────────────────────────


@app.post("/api/chat")
async def chat_stream(request: Request, auth: bool = Depends(check_auth)):
    """Stream a chat response via SSE. Body: {message, session_id?, tier?}
    tier: auto | local | groq | claude
    """
    body = await request.json()
    message = body.get("message", "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())[:8]
    tier = body.get("tier", "auto")  # auto | local | groq | claude
    file_ids: list[str] = body.get("file_ids", [])

    if not message:
        raise HTTPException(400, "message required")

    # Prepend file contents to prompt
    if file_ids:
        file_ctx_parts: list[str] = []
        for fid in file_ids[:5]:
            # Find the file by scanning upload dir for matching file_id prefix
            matches = list(UPLOAD_DIR.glob(f"*_{fid}_*"))
            if matches:
                path = matches[0]
                suffix = path.suffix.lower()
                text = _extract_text(path, suffix)
                if text:
                    file_ctx_parts.append(f"[File: {path.name}]\n{text}\n[/File]")
        if file_ctx_parts:
            message = "\n\n".join(file_ctx_parts) + "\n\nUser question: " + message

    env = {**os.environ, "DQIII8_ROOT": str(ROOT_DIR)}
    # Merge .env values (so API keys are available even if not in process env)
    for k, v in _load_env_dict().items():
        env.setdefault(k, v)

    async def _generate():
        t_start = time.time()
        tier_used = tier
        full_text = ""
        claude_session_uuid: str | None = None
        claude_session_is_new = False
        try:
            if tier == "claude":
                # Priority 1: OAuth via claude -p CLI
                oauth = detect_claude_oauth()
                if oauth["available"]:
                    # Real multi-turn memory: resume the same underlying
                    # Claude Code session (--resume) instead of a stateless
                    # one-shot call, exactly like a terminal session. Falls
                    # back to a fresh session if the prior one was pruned/
                    # not found, rather than failing the turn outright.
                    claude_session_uuid = _get_claude_session_uuid(session_id)
                    args = ["claude", "-p"]
                    if claude_session_uuid:
                        args += ["--resume", claude_session_uuid]
                    else:
                        claude_session_uuid = str(uuid.uuid4())
                        claude_session_is_new = True
                        args += ["--session-id", claude_session_uuid]
                    args.append(message)

                    proc = await asyncio.create_subprocess_exec(
                        *args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )
                    stdout_bytes, stderr_bytes = await proc.communicate()
                    if proc.returncode != 0 and not claude_session_is_new:
                        # Prior session no longer resumable (pruned, corrupted,
                        # etc.) — retry once as a fresh session rather than
                        # surfacing an opaque failure for a normal chat turn.
                        claude_session_uuid = str(uuid.uuid4())
                        claude_session_is_new = True
                        proc = await asyncio.create_subprocess_exec(
                            "claude",
                            "-p",
                            "--session-id",
                            claude_session_uuid,
                            message,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env=env,
                        )
                        stdout_bytes, stderr_bytes = await proc.communicate()

                    full_text = stdout_bytes.decode("utf-8", errors="replace")
                    if full_text:
                        yield f"data: {json.dumps({'text': full_text})}\n\n"
                    await proc.wait()

                    if not full_text:
                        err_hint = (
                            stderr_bytes.decode("utf-8", errors="replace").strip()
                            or "No response from AI backend. Check API keys in Settings."
                        )
                        yield f"data: {json.dumps({'error': err_hint})}\n\n"
                        return

                    if claude_session_is_new:
                        _set_claude_session_uuid(session_id, claude_session_uuid)

                    elapsed_ms = int((time.time() - t_start) * 1000)
                    _persist_chat(session_id, message, full_text)
                    done_payload = {
                        "done": True,
                        "session_id": session_id,
                        "tier_used": "claude_oauth",
                        "elapsed_ms": elapsed_ms,
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    return
                elif env.get("ANTHROPIC_API_KEY"):
                    # Priority 2: ANTHROPIC_API_KEY via openrouter_wrapper
                    proc = await asyncio.create_subprocess_exec(
                        "python3",
                        str(ROOT_DIR / "bin" / "core" / "openrouter_wrapper.py"),
                        "--agent",
                        "research-analyst",
                        "--force-provider",
                        "anthropic",
                        message,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )
                    tier_used = "claude_api"
                else:
                    yield (f"data: {json.dumps({'error': 'Claude not available. '
                        'Authenticate with Claude Code (claude /login) or '
                        'add ANTHROPIC_API_KEY to Settings.'})}\n\n")
                    return

            elif tier == "groq":
                proc = await asyncio.create_subprocess_exec(
                    "python3",
                    str(ROOT_DIR / "bin" / "core" / "openrouter_wrapper.py"),
                    "--agent",
                    "research-analyst",
                    message,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
                tier_used = "groq"

            elif tier == "local":
                proc = await asyncio.create_subprocess_exec(
                    "python3",
                    str(ROOT_DIR / "bin" / "core" / "openrouter_wrapper.py"),
                    "--agent",
                    "python-specialist",
                    message,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
                tier_used = "local"

            else:  # auto
                proc = await asyncio.create_subprocess_exec(
                    "python3",
                    str(ROOT_DIR / "bin" / "core" / "openrouter_wrapper.py"),
                    "--agent",
                    "research-analyst",
                    message,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
                tier_used = "auto"

            while True:
                chunk = await proc.stdout.read(64)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                full_text += text
                yield f"data: {json.dumps({'text': text})}\n\n"

            await proc.wait()

            if not full_text:
                err_hint = "No response from AI backend. Check API keys in Settings."
                yield f"data: {json.dumps({'error': err_hint})}\n\n"
                return

            elapsed_ms = int((time.time() - t_start) * 1000)
            _persist_chat(session_id, message, full_text)
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'tier_used': tier_used, 'elapsed_ms': elapsed_ms})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


def _ensure_claude_session_column(conn: sqlite3.Connection) -> None:
    """Idempotent: chat_sessions predates this column, so ADD COLUMN (no
    IF NOT EXISTS support in SQLite) needs a try/except, not a migration —
    this table is dashboard-owned, created ad-hoc, not part of schema_v2.sql.
    """
    try:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN claude_session_id TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists


def _get_claude_session_uuid(session_id: str) -> str | None:
    """Look up the real Claude Code session UUID bound to this dashboard
    chat session, so replies can --resume it (true multi-turn memory,
    same mechanism an interactive terminal session uses) instead of each
    turn being a stateless one-shot call."""
    db = CHAT_DB_PATH
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db), timeout=3)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_sessions "
            "(session_id TEXT PRIMARY KEY, created_at TEXT)"
        )
        _ensure_claude_session_column(conn)
        row = conn.execute(
            "SELECT claude_session_id FROM chat_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception as exc:
        log.warning("%s: %s", __name__, exc)
        return None


def _set_claude_session_uuid(session_id: str, claude_session_uuid: str) -> None:
    db = CHAT_DB_PATH
    if not db.exists():
        return
    try:
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(db), timeout=3)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_sessions "
            "(session_id TEXT PRIMARY KEY, created_at TEXT)"
        )
        _ensure_claude_session_column(conn)
        conn.execute(
            "INSERT INTO chat_sessions (session_id, created_at, claude_session_id) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET claude_session_id = excluded.claude_session_id",
            (session_id, ts, claude_session_uuid),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.warning("%s: %s", __name__, exc)


def _persist_chat(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """Write chat turn to DB. Creates tables if missing (graceful on older schemas)."""
    db = CHAT_DB_PATH
    if not db.exists():
        return
    try:
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(db), timeout=3)
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
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) "
            "VALUES (?, 'user', ?, ?)",
            (session_id, user_msg[:2000], ts),
        )
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) "
            "VALUES (?, 'assistant', ?, ?)",
            (session_id, assistant_msg[:4000], ts),
        )
        conn.commit()
        conn.close()
    except Exception as _exc:
        log.warning("%s: %s", __name__, _exc)


@app.get("/api/chat/history")
async def chat_history(limit: int = 10, auth: bool = Depends(check_auth)):
    """Return last N sessions with first user message as preview."""
    db = CHAT_DB_PATH
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db), timeout=3)
        rows = conn.execute(
            """
            SELECT s.session_id, s.created_at,
                   (SELECT content FROM chat_messages
                    WHERE session_id = s.session_id AND role = 'user'
                    ORDER BY id LIMIT 1) as preview
            FROM chat_sessions s
            ORDER BY s.created_at DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()
        conn.close()
    except Exception:
        rows = []
    return [{"id": r[0], "created_at": r[1], "preview": (r[2] or "")[:60]} for r in rows]


@app.post("/api/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    auth: bool = Depends(check_auth),
):
    """Upload files for chat context. Returns list of {file_id, name, size, text_preview}."""
    if len(files) > 5:
        raise HTTPException(400, "Max 5 files per upload")

    results = []
    ts = int(time.time())
    for uf in files:
        suffix = Path(uf.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"File type {suffix!r} not allowed")

        data = await uf.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"{uf.filename}: exceeds 10MB limit")

        file_id = str(uuid.uuid4())[:8]
        safe_name = "".join(
            c if c.isalnum() or c in "._-" else "_" for c in (uf.filename or "file")
        )
        dest = UPLOAD_DIR / f"{ts}_{file_id}_{safe_name}"
        dest.write_bytes(data)

        text = _extract_text(dest, suffix)
        results.append(
            {
                "file_id": file_id,
                "name": uf.filename,
                "size": len(data),
                "path": str(dest),
                "text_preview": text[:300],
                "text_full": text,
            }
        )

    return results


@app.get("/api/chat/search")
async def search_chat(q: str = "", limit: int = 20, auth: bool = Depends(check_auth)):
    """Search chat sessions by content. Returns sessions matching the query."""
    if not q.strip():
        return []
    db = CHAT_DB_PATH
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db), timeout=3)
        rows = conn.execute(
            """
            SELECT DISTINCT s.session_id, s.created_at,
                (SELECT content FROM chat_messages
                 WHERE session_id = s.session_id AND role = 'user'
                 ORDER BY id LIMIT 1) as preview
            FROM chat_sessions s
            JOIN chat_messages m ON m.session_id = s.session_id
            WHERE m.content LIKE ?
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (f"%{q}%", limit),
        ).fetchall()
        conn.close()
    except Exception:
        rows = []
    return [{"id": r[0], "created_at": r[1], "preview": (r[2] or "")[:60]} for r in rows]


@app.post("/api/chat/{session_id}/delete")
async def delete_chat_session(session_id: str, auth: bool = Depends(check_auth)):
    """Delete a chat session and its messages."""
    db = CHAT_DB_PATH
    if not db.exists():
        return {"ok": False, "error": "DB not found"}
    try:
        conn = sqlite3.connect(str(db), timeout=3)
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/chat/{session_id}/messages")
async def chat_session_messages(session_id: str, auth: bool = Depends(check_auth)):
    """Return all messages for a given session."""
    db = CHAT_DB_PATH
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db), timeout=3)
        rows = conn.execute(
            "SELECT role, content, created_at FROM chat_messages "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        conn.close()
    except Exception:
        rows = []
    return [{"role": r[0], "content": r[1], "ts": r[2]} for r in rows]


@app.post("/api/tts")
async def text_to_speech(request: Request, auth: bool = Depends(check_auth)):
    """Convert text to speech using gTTS. Returns audio/mpeg stream."""
    data = await request.json()
    text = (data.get("text") or "").strip()[:500]
    if not text:
        raise HTTPException(400, "text field required")
    try:
        from gtts import gTTS
        import tempfile

        tts = gTTS(text=text, lang="en")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tts.save(tmp.name)
        return StreamingResponse(
            open(tmp.name, "rb"),
            media_type="audio/mpeg",
        )
    except ImportError:
        raise HTTPException(503, "gTTS not installed: pip install gTTS")
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Tiers / Settings endpoints ────────────────────────────────────────────

SETTINGS_HTML_PATH = ROOT_DIR / "bin" / "settings.html"

_SETTINGS_FALLBACK = """<!DOCTYPE html><html><body style="background:#0a0a0f;color:#fff;font-family:monospace;padding:2rem">
<h2>Settings</h2><p>settings.html not found.</p><a href="/" style="color:#60a5fa">Back</a></body></html>"""


@app.get("/api/tiers")
async def get_tiers(auth: bool = Depends(check_auth)):
    """Return available tiers with status and model info."""
    env = _load_env_dict()
    oauth = detect_claude_oauth()
    has_groq = bool(env.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY"))
    has_anthropic = bool(env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))

    _nim_setup = "Dormant (REGLA NIM): non-Anthropic providers off since 2026-08-18 — see CLAUDE.md"

    return {
        "tiers": [
            {
                "id": "auto",
                "label": "Auto",
                "description": "DQ picks the best tier per message",
                "available": not NON_ANTHROPIC_DORMANT,
                "cost": "free",
                "model": "llama-3.3-70b / qwen2.5-coder",
                "setup": _nim_setup if NON_ANTHROPIC_DORMANT else None,
            },
            {
                "id": "local",
                "label": "Local",
                "description": "Ollama — fully private, no internet",
                "available": not NON_ANTHROPIC_DORMANT,
                "cost": "free",
                "model": "qwen2.5-coder:7b",
                "setup": _nim_setup if NON_ANTHROPIC_DORMANT else None,
            },
            {
                "id": "groq",
                "label": "Groq",
                "description": "Fast cloud inference, free tier",
                "available": has_groq and not NON_ANTHROPIC_DORMANT,
                "cost": "free",
                "model": "llama-3.3-70b-versatile",
                "setup": (
                    _nim_setup
                    if NON_ANTHROPIC_DORMANT
                    else (None if has_groq else "Add GROQ_API_KEY in Settings")
                ),
            },
            {
                "id": "claude",
                "label": "Claude",
                "description": "Claude Sonnet via OAuth or API key",
                "available": oauth["available"] or has_anthropic,
                "cost": oauth["available"] and not has_anthropic and "$0 (Pro plan)" or "$3/Mtok",
                "model": "claude-sonnet-5",
                "method": (
                    oauth["method"]
                    if oauth["available"]
                    else ("api_key" if has_anthropic else None)
                ),
                "setup": (
                    None
                    if (oauth["available"] or has_anthropic)
                    else "Login with Claude Code or add ANTHROPIC_API_KEY"
                ),
            },
        ],
        "oauth": oauth,
    }


@app.get("/api/claude/status")
async def claude_status(auth: bool = Depends(check_auth)):
    """Lightweight Claude Code status for navbar indicator."""
    oauth = detect_claude_oauth()
    return {
        "available": oauth.get("available", False),
        "method": oauth.get("method"),
        "plan": oauth.get("plan"),
        "version": oauth.get("version"),
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings UI page."""
    if REQUIRE_AUTH:
        token = request.query_params.get("token", "") or request.cookies.get("dq_token", "")
        if not token or not verify_token(token):
            return HTMLResponse(content=LOGIN_HTML, status_code=401)
    html = _load_html(SETTINGS_HTML_PATH, _SETTINGS_FALLBACK)
    return HTMLResponse(content=html)


@app.get("/api/settings")
async def get_settings(auth: bool = Depends(check_auth)):
    """Return current settings (masked keys, tier config, OAuth status)."""
    env = _load_env_dict()
    oauth = detect_claude_oauth()
    return {
        "groq_key": _mask_key(env.get("GROQ_API_KEY", "")),
        "anthropic_key": _mask_key(env.get("ANTHROPIC_API_KEY", "")),
        "default_tier": env.get("DQ_DEFAULT_TIER", os.environ.get("DQ_DEFAULT_TIER", "auto")),
        "oauth": oauth,
        "tier_options": ["auto", "groq-only", "groq+ollama", "ollama-only"],
    }


@app.post("/api/settings")
async def update_settings(request: Request, auth: bool = Depends(check_auth)):
    """Update .env settings (GROQ_API_KEY, ANTHROPIC_API_KEY, DQ_DEFAULT_TIER)."""
    body = await request.json()
    allowed_keys = {"GROQ_API_KEY", "ANTHROPIC_API_KEY", "DQ_DEFAULT_TIER"}
    updated = []
    for key, value in body.items():
        if key not in allowed_keys:
            continue
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value:
            _write_env_key(key, value)
            updated.append(key)
    return {"updated": updated, "ok": True}


# ── HTML routes ───────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Main dashboard page."""
    if REQUIRE_AUTH:
        token = request.query_params.get("token", "") or request.cookies.get("dq_token", "")
        if not token or not verify_token(token):
            return HTMLResponse(content=LOGIN_HTML, status_code=401)
    return HTMLResponse(content=DASHBOARD_HTML)


# ── CLI entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DQ Dashboard")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    # Update module globals before uvicorn starts (lifespan reads them)
    HOST = args.host
    PORT = args.port
    REQUIRE_AUTH = True

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
