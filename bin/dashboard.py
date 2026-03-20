#!/usr/bin/env python3
"""
DQ Dashboard — Web interface for DQIII8.
Exposes metrics, task execution, and real-time intent amplification.

Usage:
    python3 bin/dashboard.py                    # localhost:8080
    python3 bin/dashboard.py --host 0.0.0.0     # all interfaces (token required)
    python3 bin/dashboard.py --port 9090        # custom port
"""
import os
import sys
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
sys.path.insert(0, str(JARVIS / "bin"))

try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("FastAPI not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

from dashboard_security import get_or_create_dashboard_token, verify_token
from db import get_db

# ── Config ────────────────────────────────────────────────────────────────
HOST = os.environ.get("DQIII8_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DQIII8_DASHBOARD_PORT", "8080"))
REQUIRE_AUTH = HOST != "127.0.0.1"

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
    """Real-time intent amplification preview. Returns analysis without executing."""
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
            "error": "Intent Amplification not available",
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
    """Preview hierarchical routing for a given input (premium feature)."""
    body = await request.json()
    user_input = body.get("input", "")
    if not user_input:
        raise HTTPException(400, "input required")

    try:
        from hierarchical_router import classify_hierarchical
        result = classify_hierarchical(user_input)
        return result
    except ImportError:
        return {"error": "Hierarchical router not available (premium)"}


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
