"""
DQIII8 Telegram Bot — full mobile terminal.
Requires: python-telegram-bot>=20, JARVIS_BOT_TOKEN in .env
"""

import asyncio
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).parent))
from voice_handler import transcribe_audio, synthesize_speech

# ── Paths ──────────────────────────────────────────────────────────────────────
JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
LOG_FILE = JARVIS / "database" / "audit_reports" / "jarvis_bot.log"
QUEUE_DIR = JARVIS / "objectives" / "queue"
REFERENCE_IMAGE_PATH = JARVIS / "tasks" / "reference_image.jpg"

# ── Configuration ──────────────────────────────────────────────────────────────
load_dotenv(JARVIS / ".env")
BOT_TOKEN = os.getenv("DQIII8_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN", "")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # empty = no restriction

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("jarvis_bot")

# ── Global app reference (set in main()) ───────────────────────────────────────
APP: Application = None  # type: ignore[assignment]

# ── Active tasks state ──────────────────────────────────────────────────────────
# {task_id: {start_time, description, chat_id, proc, monitor: asyncio.Task}}
ACTIVE_TASKS: dict[str, dict] = {}

# ── Pending satisfaction responses ──────────────────────────────────────────────
# {pending_key: {session_id, model_used, task_type, task_description, duration_ms,
#                technical_success, tier_used}}
PENDING_SATISFACTION: dict[str, dict] = {}

ACTION_VERBS_RE = re.compile(
    r"\b(arregla|crea|refactoriza|implementa|añade|ejecuta|"
    r"fix|create|implement|update|deploy)\b",
    re.IGNORECASE,
)

# ── Voice settings ───────────────────────────────────────────────────────────────
VOICE_RESPONSES_ENABLED = False  # toggle with /voice on|off


# ── Utilidades base ─────────────────────────────────────────────────────────────
def authorized(update: Update) -> bool:
    if not ALLOWED_CHAT_ID:
        return True
    return str(update.effective_chat.id) == ALLOWED_CHAT_ID


def db_query(sql: str, params: tuple = ()) -> list:
    try:
        conn = sqlite3.connect(DB)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows
    except Exception as exc:
        log.error("DB error: %s", exc)
        return []


async def send_chunks(update: Update, text: str) -> None:
    """Splits long messages into 4000-char chunks."""
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        await update.message.reply_text(text[i : i + chunk_size])


def run_cmd(cmd: list[str], timeout: int = 120) -> str:
    """Runs a subprocess and returns combined stdout+stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(JARVIS),
            encoding="utf-8",
        )
        return (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Timeout: process took too long."
    except Exception as exc:
        return f"Error executing: {exc}"


def _load_env_dict() -> dict:
    """os.environ + .env as dict for subprocesses."""
    env = dict(os.environ)
    env_file = JARVIS / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


# ── Model satisfaction ───────────────────────────────────────────────────────────


def _infer_task_type(description: str) -> str:
    d = description.lower()
    if any(k in d for k in ("video", "tts", "subtitle", "pipeline", "ffmpeg", "reels", "content")):
        return "pipeline"
    if any(
        k in d
        for k in ("chapter", "scene", "novel", "narrative", "creative", "writing")
    ):
        return "writing"
    if any(k in d for k in ("review", "analiz", "research", "audit", "investiga", "explain")):
        return "analysis"
    if any(
        k in d
        for k in (
            "python",
            "refactor",
            "debug",
            "fix",
            "test",
            "commit",
            "bug",
            "script",
            "code",
            "codigo",
        )
    ):
        return "code"
    return "research"


def _log_satisfaction(
    session_id: str,
    model_used: str,
    task_type: str,
    task_description: str,
    duration_ms: int,
    technical_success: int,
    tier_used: str,
    user_satisfaction: int | None = None,
) -> None:
    try:
        conn = sqlite3.connect(str(DB), timeout=2)
        conn.execute(
            "INSERT INTO model_satisfaction "
            "(session_id, model_used, task_type, task_description, "
            "duration_ms, technical_success, user_satisfaction, tier_used) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                model_used,
                task_type,
                task_description[:100],
                duration_ms,
                technical_success,
                user_satisfaction,
                tier_used,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.error("Error logging satisfaction: %s", exc)


# ── Task execution (asyncio subprocess) ─────────────────────────────────────────
async def _run_task(task_id: str, description: str, chat_id: str) -> None:
    """
    Runs claude -p in an asyncio subprocess.
    Sends update every 30s if still running.
    Sends full result when done.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--add-dir",
            str(JARVIS),
            "-p",
            description,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(JARVIS),
        )
        if task_id in ACTIVE_TASKS:
            ACTIVE_TASKS[task_id]["proc"] = proc

        # communicate() collects all output; shield() prevents wait_for
        # from cancelling it on each iteration of the 30s loop
        communicate_task = asyncio.create_task(proc.communicate())
        start = time.time()

        while not communicate_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(communicate_task), timeout=30.0)
            except asyncio.TimeoutError:
                elapsed = int(time.time() - start)
                await APP.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏳ `{task_id}` trabajando... ({elapsed}s)",
                    parse_mode="Markdown",
                )
                if elapsed >= 300:
                    proc.terminate()
                    break

        if communicate_task.done():
            stdout, stderr = communicate_task.result()
            output = (stdout or b"").decode("utf-8").strip()
            if not output:
                output = (stderr or b"").decode("utf-8").strip() or "(no response)"
        else:
            output = "Task forcibly terminated (300s timeout)."

    except Exception as exc:
        output = f"Error launching claude: {exc}"
    finally:
        task_info = ACTIVE_TASKS.pop(task_id, {})
        task_start = task_info.get("start_time", time.time())
        duration_ms = int((time.time() - task_start) * 1000)

    # Send result in chunks if long
    chunks = [output[i : i + 3800] for i in range(0, max(len(output), 1), 3800)]
    for i, chunk in enumerate(chunks):
        prefix = f"✅ `{task_id}`:\n" if i == 0 else f"`{task_id}` (cont.):\n"
        await APP.bot.send_message(
            chat_id=chat_id,
            text=f"{prefix}```\n{chunk}\n```",
            parse_mode="Markdown",
        )
    log.info("Task completed: %s (%d chars)", task_id, len(output))

    # Satisfaction prompt with inline buttons
    technical_success = 0 if output.startswith("Error") or "Timeout" in output else 1
    task_type = _infer_task_type(description)
    pending_key = f"sat_{task_id}"
    PENDING_SATISFACTION[pending_key] = {
        "session_id": task_id,
        "model_used": "claude-sonnet-4-6",
        "task_type": task_type,
        "task_description": description[:100],
        "duration_ms": duration_ms,
        "technical_success": technical_success,
        "tier_used": "tier3",
    }
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👍", callback_data=f"sat:1:{pending_key}"),
                InlineKeyboardButton("👎", callback_data=f"sat:0:{pending_key}"),
            ]
        ]
    )
    await APP.bot.send_message(
        chat_id=chat_id,
        text=f"_{description[:60]}_ — was it useful?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_satisfaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra la respuesta 👍/👎 y actualiza model_satisfaction."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[0] != "sat":
        return
    rating = int(parts[1])
    key = parts[2]
    record = PENDING_SATISFACTION.pop(key, None)
    if not record:
        await query.edit_message_text("(ya registrado)")
        return
    _log_satisfaction(**record, user_satisfaction=rating)
    emoji = "👍" if rating else "👎"
    await query.edit_message_text(f"{emoji} Registrado.")
    log.info("Satisfaction: %s | %s | rating=%d", key, record.get("task_type"), rating)


async def _spawn_task(update: Update, description: str) -> str:
    """Registers the task and launches _run_task in background. Returns task_id."""
    task_id = f"t{int(time.time()) % 100000}"
    chat_id = str(update.effective_chat.id)

    ACTIVE_TASKS[task_id] = {
        "start_time": time.time(),
        "description": description[:100],
        "chat_id": chat_id,
        "proc": None,
    }

    monitor = asyncio.create_task(_run_task(task_id, description, chat_id))
    ACTIVE_TASKS[task_id]["monitor"] = monitor

    log.info("Task spawned: %s | %s", task_id, description[:60])
    return task_id


# ── Task handlers ───────────────────────────────────────────────────────────────
async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "Usage: `/task [task description]`", parse_mode="Markdown"
        )
        return
    task_id = await _spawn_task(update, description)
    await update.message.reply_text(
        f"🚀 `{task_id}` launched\n_{description[:80]}_\n\n"
        f"I'll notify you with the result. Update every 30s if it takes long.",
        parse_mode="Markdown",
    )
    log.info("/task: %s | %s", task_id, description[:60])


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    if not ACTIVE_TASKS:
        await update.message.reply_text("No active tasks.")
        return
    now = time.time()
    lines = ["*Active tasks:*\n"]
    for tid, info in ACTIVE_TASKS.items():
        elapsed = int(now - info["start_time"])
        m, s = divmod(elapsed, 60)
        proc = info.get("proc")
        alive = "🟢" if (proc and proc.returncode is None) else "🟡"
        lines.append(f"{alive} `{tid}` — {m}m{s}s\n" f"   _{info['description'][:60]}_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_output(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/output [task_id]`", parse_mode="Markdown")
        return
    task_id = context.args[0]
    if task_id not in ACTIVE_TASKS:
        await update.message.reply_text(f"Task `{task_id}` not found.", parse_mode="Markdown")
        return
    info = ACTIVE_TASKS[task_id]
    elapsed = int(time.time() - info["start_time"])
    proc = info.get("proc")
    status = "in progress" if (proc and proc.returncode is None) else "finishing"
    await update.message.reply_text(
        f"`{task_id}` — {status} ({elapsed}s)\n"
        f"_{info['description'][:80]}_\n\n"
        f"Full result will be sent when done.",
        parse_mode="Markdown",
    )


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/kill [task_id]`", parse_mode="Markdown")
        return
    task_id = context.args[0]
    if task_id not in ACTIVE_TASKS:
        await update.message.reply_text(f"Task `{task_id}` not found.", parse_mode="Markdown")
        return
    proc = ACTIVE_TASKS[task_id].get("proc")
    if proc and proc.returncode is None:
        proc.terminate()
    monitor = ACTIVE_TASKS[task_id].get("monitor")
    if monitor and not monitor.done():
        monitor.cancel()
    ACTIVE_TASKS.pop(task_id, None)
    await update.message.reply_text(f"💀 `{task_id}` eliminado.", parse_mode="Markdown")
    log.info("/kill: %s", task_id)


async def cmd_reply_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "Tasks run with `claude -p` (non-interactive).\n"
        "For interaction use `/task` with complete instructions.",
        parse_mode="Markdown",
    )


# ── Existing handlers ───────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    chat_id = update.effective_chat.id
    text = (
        f"*DQIII8 Bot — mobile terminal*\n\n"
        f"Chat ID: `{chat_id}`\n\n"
        "*DQ tasks (tier-routed):*\n"
        "/dq [prompt] — runs through DQ tier router\n\n"
        "*Claude Code tasks:*\n"
        "/task [desc] — launches claude -p in background\n"
        "/tasks — list active tasks\n"
        "/output [id] — task status\n"
        "/kill [id] — cancel task\n\n"
        "*System:*\n"
        "/status — active objectives in DB\n"
        "/score — latest scoring snapshot\n"
        "/logs — last 20 log lines\n"
        "/audit — local health audit (offline)\n"
        "/run [name.md] — runs jal\\_run.py\n\n"
        "Free message: action verb or \\>15 words → automatic /task.\n"
        "Otherwise → quick response.\n\n"
        "*Voice:*\n"
        "Send a voice note → auto-transcribe via Groq Whisper → execute\n"
        "/voice on|off — toggle audio responses"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    log.info("/start from chat_id=%s", chat_id)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args
    project = args[0] if args else "math-image-generator"

    try:
        conn = sqlite3.connect(DB)
        ranking = conn.execute("SELECT * FROM tier_ranking WHERE model_tier='tier3'").fetchone()
        metrics = conn.execute(
            """
            SELECT renderer, lines_of_code, cpu_seconds,
                   memory_peak_mb, ssim_score, passes_tests
            FROM code_metrics
            WHERE project=?
            ORDER BY timestamp DESC LIMIT 5
            """,
            (project,),
        ).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) FROM objectives WHERE project=? AND status='pending'",
            (project,),
        ).fetchone()[0]
        conn.close()

        renderers_text = (
            "\n".join(
                [
                    f"  {'✅' if r[5] else '⚠️'} {r[0]}: "
                    f"{r[1]} LOC | {r[2]:.1f}s | "
                    f"SSIM {f'{r[4]:.3f}' if r[4] else 'N/A'}"
                    for r in metrics
                ]
            )
            if metrics
            else "  No data yet"
        )
        score = ranking[8] if ranking else 0
        await update.message.reply_text(
            f"📊 *Estado — {project}*\n\n"
            f"Score: {score}/100\n"
            f"Objetivos pending: {pending}\n\n"
            f"*Renderers:*\n{renderers_text}",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
    log.info("/status project=%s", project)


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    rows = db_query("""
        SELECT s.objective_id, s.attempt, s.evaluated_at, s.score_raw,
               s.score_final, s.converges, s.steps_completed, s.steps_total
        FROM jal_scoring_snapshots s
        ORDER BY s.evaluated_at DESC
        LIMIT 1
        """)
    if not rows:
        await update.message.reply_text("No scoring snapshots yet.")
        return
    obj_id, attempt, evaluated_at, score_raw, score_final, converges, steps_done, steps_total = (
        rows[0]
    )
    converge_str = "[OK] Converge" if converges else "[~] Sin convergencia"
    text = (
        f"*Ultimo scoring snapshot:*\n\n"
        f"Objetivo: `{obj_id}`\n"
        f"Intento: {attempt}\n"
        f"Evaluado: {evaluated_at}\n"
        f"Score raw: {score_raw:.3f}\n"
        f"Score final: {score_final:.3f}\n"
        f"Steps: {steps_done}/{steps_total}\n"
        f"Convergencia: {converge_str}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    log.info("/score queried")


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        tail = "\n".join(lines[-20:]) if lines else "(empty log)"
    except FileNotFoundError:
        tail = "(not yet created)"
    await send_chunks(update, f"*Bot log (last 20 lines):*\n```\n{tail}\n```")
    log.info("/logs queried")


async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text("Running local health audit...")
    log.info("/audit started")
    output = run_cmd(["python3", "bin/auditor_local.py"], timeout=60)
    await send_chunks(update, f"*DQ Health Audit:*\n```\n{output[:3800]}\n```")
    log.info("/audit completed")


async def cmd_dq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /dq [prompt]
    Runs a prompt through bin/j.sh (full tier routing) in background.
    Example: /dq refactor bin/dashboard.py to add dark mode
    """
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    description = " ".join(context.args).strip() if context.args else ""
    if not description:
        await update.message.reply_text(
            "Usage: `/dq [prompt]`\nExample: `/dq explain what Risk Parity means`",
            parse_mode="Markdown",
        )
        return
    task_id = await _spawn_task(update, description)
    await update.message.reply_text(
        f"🚀 `{task_id}` via DQ router\n_{description[:80]}_",
        parse_mode="Markdown",
    )
    log.info("/dq: %s | %s", task_id, description[:60])


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args
    if not args:
        queue_files = sorted(QUEUE_DIR.glob("*.md")) if QUEUE_DIR.exists() else []
        if not queue_files:
            await update.message.reply_text("Queue empty. Use `/run name.md` to execute.")
            return
        names = "\n".join(f"- `{f.name}`" for f in queue_files)
        await update.message.reply_text(
            f"*Objectives in queue:*\n{names}\n\nUse `/run name.md` to execute.",
            parse_mode="Markdown",
        )
        return
    target = args[0]
    if not target.endswith(".md"):
        target += ".md"
    await update.message.reply_text(
        f"Ejecutando jal\\_run.py con `{target}`...", parse_mode="Markdown"
    )
    log.info("/run target=%s", target)
    output = run_cmd(["python3", "bin/jal_run.py", target], timeout=300)
    await send_chunks(update, f"*Resultado /run {target}:*\n```\n{output[:3800]}\n```")
    log.info("/run completado target=%s", target)


async def cmd_loop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /loop [project] [cycles] [tier]
    Lanza OrchestratorLoop en background (asyncio.create_task) y notifica al terminar.
    El bot sigue respondiendo mientras el loop corre.
    Ejemplos: /loop math-image-generator 3 tier3
              /loop math-image-generator
    """
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return

    args = context.args
    project = args[0] if args else "math-image-generator"
    cycles = args[1] if len(args) > 1 else "5"
    tier = args[2] if len(args) > 2 else "tier3"

    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"🚀 *OrchestratorLoop* lanzado en background\n"
        f"Proyecto: `{project}` | Ciclos: `{cycles}` | Tier: `{tier}`\n"
        f"_I'll notify you when done. You can close the chat._",
        parse_mode="Markdown",
    )
    log.info("/loop project=%s cycles=%s tier=%s", project, cycles, tier)

    async def _run_and_notify() -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3",
                str(JARVIS / "bin" / "orchestrator_loop.py"),
                "--project",
                project,
                "--cycles",
                cycles,
                "--tier",
                tier,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(JARVIS),
                env={**os.environ, "JARVIS_MODE": "autonomous"},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=7200)
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"*Loop completado — {project}*\n```\n{output[-3000:]}\n```",
                parse_mode="Markdown",
            )
        except asyncio.TimeoutError:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ *Loop timeout* (>2h) — {project}\nVerifica el VPS manualmente.",
                parse_mode="Markdown",
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ *Loop error* — {project}\n`{str(e)[:200]}`",
                parse_mode="Markdown",
            )

    asyncio.create_task(_run_and_notify())


async def cmd_images(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /images [project]
    Sends the latest generated images from the project.
    """
    if not authorized(update):
        return

    args = context.args
    project = args[0] if args else "math-image-generator"
    output_dir = Path(f"/root/{project}/output")

    if not output_dir.exists():
        await update.message.reply_text(f"No images in {project} yet.")
        return

    png_files = sorted(
        output_dir.glob("*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:5]

    if not png_files:
        await update.message.reply_text("No generated images.")
        return

    await update.message.reply_text(
        f"📸 Sending {len(png_files)} images from `{project}`...",
        parse_mode="Markdown",
    )

    for png in png_files:
        try:
            with open(png, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption=f"`{png.stem}`\n_{project}_",
                    parse_mode="Markdown",
                )
        except Exception as e:
            await update.message.reply_text(f"Error sending {png.name}: {e}")

    log.info("/images project=%s count=%d", project, len(png_files))


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Saves the sent photo as a reference image when the caption
    contains 'reference' or '/reference'.
    Usage: send a photo with caption 'reference' or '/reference'
    """
    if not authorized(update):
        return
    caption = (update.message.caption or "").strip().lower()
    if "reference" not in caption:
        return

    photo = update.message.photo[-1]  # highest resolution available
    file = await context.bot.get_file(photo.file_id)
    await file.download_to_drive(str(REFERENCE_IMAGE_PATH))

    await update.message.reply_text(
        f"Reference image saved.\n"
        f"The next `/loop` will use it as a visual criterion.\n"
        f"To launch: `/loop math-image-generator 5 tier3`",
        parse_mode="Markdown",
    )
    log.info("Reference image saved to %s", REFERENCE_IMAGE_PATH)


async def _download_telegram_file(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> str:
    """Download a Telegram file to tmp/ and return its local path."""
    tmp_dir = JARVIS / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tg_file = await context.bot.get_file(file_id)
    local_path = str(tmp_dir / f"tg_voice_{file_id}.ogg")
    await tg_file.download_to_drive(local_path)
    return local_path


async def _send_voice_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Synthesize text and send as voice message. Cleans up temp file after sending."""
    audio_path = synthesize_speech(text[:500])
    if not audio_path or not Path(audio_path).exists():
        return
    try:
        with open(audio_path, "rb") as audio:
            await context.bot.send_voice(
                chat_id=update.effective_chat.id,
                voice=audio,
            )
    except Exception as e:
        log.warning("send_voice failed: %s", e)
    finally:
        Path(audio_path).unlink(missing_ok=True)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive a Telegram voice/audio message, transcribe via Groq Whisper, and execute as task."""
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    file_id = voice.file_id
    await update.message.reply_text("Transcribing...")

    audio_path = await _download_telegram_file(context, file_id)
    try:
        text = transcribe_audio(audio_path)
    finally:
        Path(audio_path).unlink(missing_ok=True)

    if not text or text.startswith("[Error"):
        await update.message.reply_text(f"Could not transcribe: {text}")
        return

    await update.message.reply_text(
        f"*Heard:* {text}", parse_mode="Markdown"
    )
    log.info("Voice transcription: %s", text[:80])

    word_count = len(text.split())
    is_action = bool(ACTION_VERBS_RE.search(text)) or word_count > 15

    if is_action:
        task_id = await _spawn_task(update, text)
        await update.message.reply_text(
            f"Launched `{task_id}`\n_{text[:80]}_",
            parse_mode="Markdown",
        )
        log.info("Voice → task: %s | %s", task_id, text[:60])
    else:
        await update.message.reply_text("Processing...")
        prompt = (
            "You are DQIII8, an AI orchestration system. "
            f"Respond concisely and technically:\n\n{text}"
        )
        result = subprocess.run(
            [
                "python3",
                str(JARVIS / "bin" / "openrouter_wrapper.py"),
                "--model",
                "stepfun/step-3.5-flash:free",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(JARVIS),
            timeout=60,
            env=_load_env_dict(),
        )
        output = result.stdout.strip() or "(no response)"
        await send_chunks(update, output)

        if VOICE_RESPONSES_ENABLED:
            await _send_voice_reply(update, context, output)

        log.info("Voice quick response sent (%d chars)", len(output))


async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/voice on|off — toggle audio responses."""
    global VOICE_RESPONSES_ENABLED
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    arg = (context.args[0] if context.args else "").lower()
    if arg == "on":
        VOICE_RESPONSES_ENABLED = True
        await update.message.reply_text("Voice responses enabled. I'll reply with audio.")
    elif arg == "off":
        VOICE_RESPONSES_ENABLED = False
        await update.message.reply_text("Voice responses disabled. Text only.")
    else:
        state = "on" if VOICE_RESPONSES_ENABLED else "off"
        await update.message.reply_text(
            f"Voice responses: *{state}*\nUse `/voice on` or `/voice off`.",
            parse_mode="Markdown",
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    user_msg = (update.message.text or "").strip()
    if not user_msg:
        return

    word_count = len(user_msg.split())
    is_action = bool(ACTION_VERBS_RE.search(user_msg)) or word_count > 15

    if is_action:
        task_id = await _spawn_task(update, user_msg)
        await update.message.reply_text(
            f"🚀 `{task_id}` launched\n_{user_msg[:80]}_",
            parse_mode="Markdown",
        )
        log.info("Message → task: %s | %s", task_id, user_msg[:60])
        return

    # Quick response via OpenRouter (no claude CLI)
    await update.message.reply_text("Processing...")
    log.info("Quick message: %s", user_msg[:80])
    prompt = (
        "You are DQIII8, an AI orchestration system. "
        f"Respond concisely and technically:\n\n{user_msg}"
    )
    result = subprocess.run(
        [
            "python3",
            str(JARVIS / "bin" / "openrouter_wrapper.py"),
            "--model",
            "stepfun/step-3.5-flash:free",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        cwd=str(JARVIS),
        timeout=60,
        env=_load_env_dict(),
    )
    output = result.stdout.strip() or "(no response)"
    await send_chunks(update, output)
    log.info("Quick response sent (%d chars)", len(output))


# ── Block 4: Auto-improvement + Sleep Mode commands ──────────────────────────────


async def cmd_research_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows research_items state by status."""
    conn = sqlite3.connect(str(DB), timeout=5)
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM research_items GROUP BY status ORDER BY COUNT(*) DESC"
    ).fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("No research items yet.")
        return
    lines = ["*Research Items:*"]
    for status, count in rows:
        lines.append(f"• {status}: {count}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_sandbox_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs sandbox_tester.py --process-queue in background."""
    await update.message.reply_text("[DQIII8] Launching sandbox tester...")
    result = subprocess.run(
        [sys.executable, str(JARVIS / "bin" / "sandbox_tester.py"), "--process-queue"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(JARVIS),
    )
    output = (result.stdout + result.stderr).strip()[-800:] or "(no output)"
    await send_chunks(update, output)


async def _handle_integrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marks a research item as INTEGRADO. Usage: /integrar_<id>"""
    text = update.message.text or ""
    m = re.match(r"/integrar[_\s]+(\d+)", text)
    if not m:
        await update.message.reply_text("Usage: /integrar_<id>")
        return
    item_id = int(m.group(1))
    conn = sqlite3.connect(str(DB), timeout=5)
    conn.execute("UPDATE research_items SET status='INTEGRADO' WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"[DQIII8] Item {item_id} marked as INTEGRADO.")


async def _handle_rechazar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marks a research item as RECHAZADO. Usage: /rechazar_<id>"""
    text = update.message.text or ""
    m = re.match(r"/rechazar[_\s]+(\d+)", text)
    if not m:
        await update.message.reply_text("Usage: /rechazar_<id>")
        return
    item_id = int(m.group(1))
    conn = sqlite3.connect(str(DB), timeout=5)
    conn.execute("UPDATE research_items SET status='RECHAZADO_MANUAL' WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"[DQIII8] Item {item_id} rejected.")


async def _handle_aprobar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approves a Sleep Mode permission request. Usage: /aprobar_<id>"""
    text = update.message.text or ""
    m = re.match(r"/aprobar[_\s]+([0-9a-f]+)", text)
    if not m:
        await update.message.reply_text("Usage: /aprobar_<id>")
        return
    perm_id = m.group(1)
    perm_file = Path(f"/tmp/jarvis_perm_{perm_id}.json")
    perm_file.write_text('{"decision":"allow","reason":"user approved"}', encoding="utf-8")
    await update.message.reply_text(f"[DQIII8] Permission {perm_id} APPROVED.")


async def _handle_denegar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Denies a Sleep Mode permission request. Usage: /denegar_<id>"""
    text = update.message.text or ""
    m = re.match(r"/denegar[_\s]+([0-9a-f]+)", text)
    if not m:
        await update.message.reply_text("Usage: /denegar_<id>")
        return
    perm_id = m.group(1)
    perm_file = Path(f"/tmp/jarvis_perm_{perm_id}.json")
    perm_file.write_text('{"decision":"deny","reason":"user denied"}', encoding="utf-8")
    await update.message.reply_text(f"[DQIII8] Permission {perm_id} DENIED.")


async def cmd_stop_autonomous(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Writes stop flag to halt the next autonomous session."""
    if not authorized(update):
        await update.message.reply_text("Unauthorized.")
        return
    stop_flag = JARVIS / "tasks" / ".stop_flag"
    stop_flag.write_text(f"stop requested at {time.time()}", encoding="utf-8")
    await update.message.reply_text(
        "Stop flag written to `tasks/.stop_flag`.\n"
        "The autonomous session will halt before the next start.",
        parse_mode="Markdown",
    )
    log.info("/stop: stop flag written to %s", stop_flag)


# ── Main ────────────────────────────────────────────────────────────────────────
def main() -> None:
    global APP
    if not BOT_TOKEN:
        log.error("DQIII8_BOT_TOKEN not configured in .env -- aborting.")
        sys.exit(1)

    log.info("Starting DQIII8 Bot (mobile terminal)...")
    APP = Application.builder().token(BOT_TOKEN).build()

    APP.add_handler(CommandHandler("start", cmd_start))
    APP.add_handler(CommandHandler("status", cmd_status))
    APP.add_handler(CommandHandler("score", cmd_score))
    APP.add_handler(CommandHandler("logs", cmd_logs))
    APP.add_handler(CommandHandler("audit", cmd_audit))
    APP.add_handler(CommandHandler("dq", cmd_dq))
    APP.add_handler(CommandHandler("run", cmd_run))
    APP.add_handler(CommandHandler("task", cmd_task))
    APP.add_handler(CommandHandler("tasks", cmd_tasks))
    APP.add_handler(CommandHandler("output", cmd_output))
    APP.add_handler(CommandHandler("reply", cmd_reply_task))
    APP.add_handler(CommandHandler("kill", cmd_kill))
    APP.add_handler(CommandHandler("loop", cmd_loop))
    APP.add_handler(CommandHandler("images", cmd_images))
    APP.add_handler(CommandHandler("research_status", cmd_research_status))
    APP.add_handler(CommandHandler("sandbox_run", cmd_sandbox_run))
    APP.add_handler(CommandHandler("stop", cmd_stop_autonomous))
    APP.add_handler(MessageHandler(filters.Regex(r"^/integrar"), _handle_integrar))
    APP.add_handler(MessageHandler(filters.Regex(r"^/rechazar"), _handle_rechazar))
    APP.add_handler(MessageHandler(filters.Regex(r"^/aprobar"), _handle_aprobar))
    APP.add_handler(MessageHandler(filters.Regex(r"^/denegar"), _handle_denegar))
    APP.add_handler(CommandHandler("voice", cmd_voice))
    APP.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    APP.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    APP.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    APP.add_handler(CallbackQueryHandler(handle_satisfaction_callback, pattern=r"^sat:"))

    log.info("Bot polling. Ctrl+C to stop.")
    APP.run_polling(drop_pending_updates=True)


# ── Morning Report ───────────────────────────────────────────────────────────────


def send_morning_report() -> None:
    """
    Builds and sends a morning status Telegram message.
    Called via: python3 bin/jarvis_bot.py --morning-report
    """
    import urllib.request
    import urllib.parse
    from datetime import datetime, timedelta

    token = os.getenv("DQIII8_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[morning_report] DQIII8_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping")
        return

    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    score = 0.0
    sessions_yesterday = 0
    spc_alerts: list[str] = []
    research_pending = 0
    active_project = "N/A"
    next_step = "N/A"
    lessons_yesterday = 0

    try:
        conn = sqlite3.connect(str(DB), timeout=5)

        row = conn.execute(
            "SELECT overall_score FROM audit_reports ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            score = row[0]

        sessions_yesterday = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE start_time LIKE ?", (f"{yesterday}%",)
        ).fetchone()[0]

        spc_rows = conn.execute(
            "SELECT trigger_id, reason FROM spc_metrics"
            " WHERE triggered=1 AND checked_at >= datetime('now', '-24 hours')"
            " ORDER BY checked_at DESC"
        ).fetchall()
        spc_alerts = [f"{r[0]}: {r[1][:60]}" for r in spc_rows]

        research_pending = conn.execute(
            "SELECT COUNT(*) FROM research_items WHERE status='PENDIENTE_TEST'"
        ).fetchone()[0]

        lessons_yesterday = (
            conn.execute(
                "SELECT SUM(lessons_added) FROM sessions WHERE start_time LIKE ?",
                (f"{yesterday}%",),
            ).fetchone()[0]
            or 0
        )

        conn.close()
    except Exception as e:
        print(f"[morning_report] DB error: {e}")

    # Find active project + next_step from projects/*.md
    try:
        import re

        for proj_file in sorted(
            (JARVIS / "projects").glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True
        ):
            text = proj_file.read_text(encoding="utf-8")
            if "status: active" in text.lower() or "status:active" in text.lower():
                active_project = proj_file.stem
                m = re.search(r"(?:next[_\s]step|próximo)[:\s]+(.+)", text, re.IGNORECASE)
                if m:
                    next_step = m.group(1).strip()[:80]
                break
    except Exception:
        pass

    spc_line = "\n   • ".join(spc_alerts) if spc_alerts else "none"
    msg = (
        f"☀️ DQIII8 Morning Report — {today_str}\n"
        f"Score: {score:.0f}/100 | Sessions yesterday: {sessions_yesterday}\n"
        f"SPC alerts: {spc_line}\n"
        f"Research queue: {research_pending} pending items\n"
        f"Active project: {active_project}\n"
        f"Next step: {next_step}\n"
        f"New lessons yesterday: {lessons_yesterday}"
    )

    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        urllib.request.urlopen(url, data, timeout=10)
        print(f"[morning_report] Sent OK — {today_str}")
    except Exception as e:
        print(f"[morning_report] Telegram send failed: {e}")


if __name__ == "__main__":
    if "--morning-report" in sys.argv:
        load_dotenv(JARVIS / ".env")
        send_morning_report()
    else:
        main()
