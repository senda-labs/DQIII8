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
from datetime import datetime, timedelta
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
sys.path.insert(0, str(JARVIS / "bin"))

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

# ── Config ────────────────────────────────────────────────────────────────
HOST = os.environ.get("DQIII8_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DQIII8_DASHBOARD_PORT", "8080"))
REQUIRE_AUTH = HOST != "127.0.0.1"


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
                if any(data.get(k) for k in ("token", "access_token", "sessionKey", "claudeApiKey")):
                    return {"available": True, "method": "oauth_file", "plan": "Pro/Team"}
            except Exception:
                pass

    # 2) Check CLI is installed
    try:
        v = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5
        )
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
            capture_output=True, text=True, timeout=20,
        )
        if r2.returncode == 0:
            return {
                "available": True,
                "method": "oauth_cli",
                "plan": "Pro/Team",
                "version": version_str,
            }
    except Exception:
        pass

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
    env_file = JARVIS / ".env"
    result: dict = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _write_env_key(key: str, value: str) -> None:
    """Safely update or append a single key in .env."""
    env_file = JARVIS / ".env"
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
    "analyze":   ["Data Collection", "Statistical Analysis", "Pattern Detection", "Report Generation"],
    "generate":  ["Requirements Analysis", "Draft Creation", "Review", "Finalization"],
    "optimize":  ["Performance Profiling", "Bottleneck Identification", "Refactoring", "Benchmarking"],
    "debug":     ["Error Reproduction", "Root Cause Analysis", "Fix Implementation", "Regression Testing"],
    "research":  ["Source Discovery", "Data Extraction", "Analysis", "Synthesis"],
    "summarize": ["Content Parsing", "Key Points Extraction", "Summary Draft"],
    "compare":   ["Criteria Definition", "Data Collection", "Analysis", "Recommendation"],
    "forecast":  ["Historical Analysis", "Model Selection", "Projection", "Confidence Intervals"],
    "explain":   ["Concept Decomposition", "Examples", "Analogies", "Summary"],
    "transform": ["Source Parsing", "Mapping", "Transformation", "Validation"],
    "validate":  ["Schema Check", "Business Rules", "Edge Cases", "Report"],
    "plan":      ["Requirements Gathering", "Architecture Design", "Task Breakdown", "Timeline"],
    "automate":  ["Process Mapping", "Script Development", "Testing", "Deployment"],
    "report":    ["Data Collection", "Analysis", "Visualization", "Executive Summary"],
}

# ── HTML templates (lazy-loaded on startup) ────────────────────────────────
DASHBOARD_HTML: str = ""
LOGIN_HTML: str = ""

DASHBOARD_HTML_PATH = JARVIS / "bin" / "dashboard.html"
LOGIN_HTML_PATH = JARVIS / "bin" / "login.html"

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
UPLOAD_DIR = JARVIS / "uploads" / "chat"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".pdf", ".md", ".txt", ".json", ".csv", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _extract_text(path: Path, suffix: str) -> str:
    """Best-effort text extraction from uploaded file."""
    if suffix in (".txt", ".md", ".json", ".csv"):
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:8000]
        except Exception:
            return ""
    if suffix == ".pdf":
        # Try pdftotext CLI first
        try:
            r = subprocess.run(
                ["pdftotext", str(path), "-"],
                capture_output=True, text=True, timeout=30,
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
        except Exception:
            pass
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
    DASHBOARD_HTML = _load_html(DASHBOARD_HTML_PATH, "<h1>DQ Dashboard</h1><p>dashboard.html not found.</p>")
    LOGIN_HTML = _load_html(LOGIN_HTML_PATH, _LOGIN_FALLBACK)

    token = get_or_create_dashboard_token()
    if REQUIRE_AUTH:
        print(f"\n  DQ Dashboard running on http://{HOST}:{PORT}")
        print(f"  Auth token: {token}")
        print(f"  Access: http://{HOST}:{PORT}?token={token}\n")
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
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    with get_db() as conn:
        sessions = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE date(start_time) >= ?", (week_ago,)
        ).fetchone()[0]

        actions = conn.execute("""
            SELECT COUNT(*) as total,
                   ROUND(AVG(success) * 100, 1) as success_rate
            FROM agent_actions WHERE date(timestamp) >= ?
        """, (week_ago,)).fetchone()

        errors = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN resolved = 1 THEN 1 ELSE 0 END) as resolved
            FROM error_log WHERE date(timestamp) >= ?
        """, (week_ago,)).fetchone()

        tiers = conn.execute("""
            SELECT tier, COUNT(*) as count,
                   ROUND(SUM(estimated_cost_usd), 4) as cost
            FROM agent_actions WHERE date(timestamp) >= ?
            GROUP BY tier
        """, (week_ago,)).fetchall()

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


@app.get("/api/sessions")
async def recent_sessions(limit: int = 20, auth: bool = Depends(check_auth)):
    """Recent sessions with derived status and action count."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT session_id, start_time, end_time,
                   CASE WHEN end_time IS NULL THEN 'active' ELSE 'ended' END as status,
                   (SELECT COUNT(*) FROM agent_actions WHERE session_id = s.session_id) as actions
            FROM sessions s
            ORDER BY start_time DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {"id": r[0], "start": r[1], "end": r[2], "status": r[3], "actions": r[4]}
        for r in rows
    ]


@app.get("/api/tasks/recent")
async def recent_tasks(limit: int = 50, auth: bool = Depends(check_auth)):
    """Recent agent_actions records."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT timestamp, agent_name, tier, success,
                   duration_ms, estimated_cost_usd, tokens_input, tokens_output
            FROM agent_actions
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {
            "timestamp": r[0], "agent": r[1], "tier": r[2],
            "success": bool(r[3]), "duration_ms": r[4],
            "cost": r[5], "tokens_in": r[6], "tokens_out": r[7],
        }
        for r in rows
    ]


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
    """Execute a prompt through the openrouter_wrapper pipeline."""
    body = await request.json()
    user_input = body.get("input", "")

    if not user_input:
        raise HTTPException(400, "input field required")

    try:
        result = subprocess.run(
            ["python3", str(JARVIS / "bin" / "openrouter_wrapper.py"), "run", user_input],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "JARVIS_ROOT": str(JARVIS)},
        )
        return {
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"output": None, "error": "Task timed out (120s)", "exit_code": -1}


@app.get("/api/amplification/log")
async def amplification_log(limit: int = 20, auth: bool = Depends(check_auth)):
    """Recent amplification log entries."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT created_at, original_prompt, action_detected, entity_detected,
                   niche_detected, top_domain, intent_pattern, tier_selected, elapsed_ms
            FROM amplification_log
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {
            "timestamp": r[0], "input": r[1], "action": r[2],
            "entity": r[3], "niche": r[4], "domain": r[5],
            "pattern": r[6], "tier": r[7], "elapsed_ms": r[8],
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

    env = {**os.environ, "JARVIS_ROOT": str(JARVIS)}
    # Merge .env values (so API keys are available even if not in process env)
    for k, v in _load_env_dict().items():
        env.setdefault(k, v)

    async def _generate():
        t_start = time.time()
        tier_used = tier
        full_text = ""
        try:
            if tier == "claude":
                # Priority 1: OAuth via claude -p CLI
                oauth = detect_claude_oauth()
                if oauth["available"]:
                    proc = await asyncio.create_subprocess_exec(
                        "claude", "-p", message,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        env=env,
                    )
                    tier_used = "claude_oauth"
                elif env.get("ANTHROPIC_API_KEY"):
                    # Priority 2: ANTHROPIC_API_KEY via openrouter_wrapper
                    proc = await asyncio.create_subprocess_exec(
                        "python3",
                        str(JARVIS / "bin" / "openrouter_wrapper.py"),
                        "--agent", "research-analyst",
                        "--force-provider", "anthropic",
                        message,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        env=env,
                    )
                    tier_used = "claude_api"
                else:
                    yield (
                        f"data: {json.dumps({'error': 'Claude not available. '
                        'Authenticate with Claude Code (claude /login) or '
                        'add ANTHROPIC_API_KEY to Settings.'})}\n\n"
                    )
                    return

            elif tier == "groq":
                proc = await asyncio.create_subprocess_exec(
                    "python3",
                    str(JARVIS / "bin" / "openrouter_wrapper.py"),
                    "--agent", "research-analyst",
                    message,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
                tier_used = "groq"

            elif tier == "local":
                proc = await asyncio.create_subprocess_exec(
                    "python3",
                    str(JARVIS / "bin" / "openrouter_wrapper.py"),
                    "--agent", "python-specialist",
                    message,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
                tier_used = "local"

            else:  # auto
                proc = await asyncio.create_subprocess_exec(
                    "python3",
                    str(JARVIS / "bin" / "openrouter_wrapper.py"),
                    "--agent", "research-analyst",
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

            elapsed_ms = int((time.time() - t_start) * 1000)
            _persist_chat(session_id, message, full_text)
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'tier_used': tier_used, 'elapsed_ms': elapsed_ms})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


def _persist_chat(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """Write chat turn to DB. Creates tables if missing (graceful on older schemas)."""
    db = JARVIS / "database" / "jarvis_metrics.db"
    if not db.exists():
        return
    try:
        ts = datetime.utcnow().isoformat()
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
    except Exception:
        pass


@app.get("/api/chat/history")
async def chat_history(limit: int = 10, auth: bool = Depends(check_auth)):
    """Return last N sessions with first user message as preview."""
    db = JARVIS / "database" / "jarvis_metrics.db"
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db), timeout=3)
        rows = conn.execute("""
            SELECT s.session_id, s.created_at,
                   (SELECT content FROM chat_messages
                    WHERE session_id = s.session_id AND role = 'user'
                    ORDER BY id LIMIT 1) as preview
            FROM chat_sessions s
            ORDER BY s.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
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
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in (uf.filename or "file"))
        dest = UPLOAD_DIR / f"{ts}_{file_id}_{safe_name}"
        dest.write_bytes(data)

        text = _extract_text(dest, suffix)
        results.append({
            "file_id": file_id,
            "name": uf.filename,
            "size": len(data),
            "path": str(dest),
            "text_preview": text[:300],
            "text_full": text,
        })

    return results


@app.get("/api/chat/search")
async def search_chat(q: str = "", limit: int = 20, auth: bool = Depends(check_auth)):
    """Search chat sessions by content. Returns sessions matching the query."""
    if not q.strip():
        return []
    db = JARVIS / "database" / "jarvis_metrics.db"
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


@app.get("/api/chat/{session_id}/messages")
async def chat_session_messages(session_id: str, auth: bool = Depends(check_auth)):
    """Return all messages for a given session."""
    db = JARVIS / "database" / "jarvis_metrics.db"
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


# ── Tiers / Settings endpoints ────────────────────────────────────────────

SETTINGS_HTML_PATH = JARVIS / "bin" / "settings.html"

_SETTINGS_FALLBACK = """<!DOCTYPE html><html><body style="background:#0a0a0f;color:#fff;font-family:monospace;padding:2rem">
<h2>Settings</h2><p>settings.html not found.</p><a href="/" style="color:#60a5fa">Back</a></body></html>"""


@app.get("/api/tiers")
async def get_tiers(auth: bool = Depends(check_auth)):
    """Return available tiers with status and model info."""
    env = _load_env_dict()
    oauth = detect_claude_oauth()
    has_groq = bool(env.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY"))
    has_anthropic = bool(env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))

    return {
        "tiers": [
            {
                "id": "auto",
                "label": "Auto",
                "description": "DQ picks the best tier per message",
                "available": True,
                "cost": "free",
                "model": "llama-3.3-70b / qwen2.5-coder",
            },
            {
                "id": "local",
                "label": "Local",
                "description": "Ollama — fully private, no internet",
                "available": True,
                "cost": "free",
                "model": "qwen2.5-coder:7b",
            },
            {
                "id": "groq",
                "label": "Groq",
                "description": "Fast cloud inference, free tier",
                "available": has_groq,
                "cost": "free",
                "model": "llama-3.3-70b-versatile",
                "setup": None if has_groq else "Add GROQ_API_KEY in Settings",
            },
            {
                "id": "claude",
                "label": "Claude",
                "description": "Claude Sonnet via OAuth or API key",
                "available": oauth["available"] or has_anthropic,
                "cost": oauth["available"] and not has_anthropic and "$0 (Pro plan)" or "$3/Mtok",
                "model": "claude-sonnet-4-6",
                "method": oauth["method"] if oauth["available"] else ("api_key" if has_anthropic else None),
                "setup": None if (oauth["available"] or has_anthropic) else "Login with Claude Code or add ANTHROPIC_API_KEY",
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
    REQUIRE_AUTH = HOST != "127.0.0.1"

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
