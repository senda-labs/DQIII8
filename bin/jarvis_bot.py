"""
JARVIS Telegram Bot — terminal móvil completo.
Requiere: python-telegram-bot>=20, JARVIS_BOT_TOKEN en .env
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
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ── Rutas ──────────────────────────────────────────────────────────────────────
JARVIS = Path("/root/jarvis")
DB = JARVIS / "database" / "jarvis_metrics.db"
LOG_FILE = JARVIS / "database" / "audit_reports" / "jarvis_bot.log"
QUEUE_DIR = JARVIS / "objectives" / "queue"

# ── Configuración ──────────────────────────────────────────────────────────────
load_dotenv(JARVIS / ".env")
BOT_TOKEN = os.getenv("JARVIS_BOT_TOKEN", "")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # vacío = sin restricción

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

# ── Referencia global a la app (se asigna en main()) ───────────────────────────
APP: Application = None  # type: ignore[assignment]

# ── Estado de tareas activas ────────────────────────────────────────────────────
# {task_id: {start_time, description, chat_id, proc, monitor: asyncio.Task}}
ACTIVE_TASKS: dict[str, dict] = {}

ACTION_VERBS_RE = re.compile(
    r"\b(arregla|crea|refactoriza|implementa|añade|ejecuta|"
    r"fix|create|implement|update|deploy)\b",
    re.IGNORECASE,
)


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
    """Divide mensajes largos en chunks de 4000 chars."""
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        await update.message.reply_text(text[i : i + chunk_size])


def run_cmd(cmd: list[str], timeout: int = 120) -> str:
    """Ejecuta un subproceso y devuelve stdout+stderr combinados."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=JARVIS,
            encoding="utf-8",
        )
        return (result.stdout + result.stderr).strip() or "(sin salida)"
    except subprocess.TimeoutExpired:
        return "Timeout: el proceso tardo demasiado."
    except Exception as exc:
        return f"Error al ejecutar: {exc}"


def _load_env_dict() -> dict:
    """os.environ + .env como dict para subprocesos."""
    env = dict(os.environ)
    env_file = JARVIS / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


# ── Ejecución de tarea (subprocess asyncio) ─────────────────────────────────────
async def _run_task(task_id: str, description: str, chat_id: str) -> None:
    """
    Ejecuta claude -p en un subprocess asyncio.
    Manda update cada 30s si sigue corriendo.
    Manda resultado completo al terminar.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--add-dir", str(JARVIS), "-p", description,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(JARVIS),
        )
        if task_id in ACTIVE_TASKS:
            ACTIVE_TASKS[task_id]["proc"] = proc

        # communicate() recoge todo el output; shield() evita que wait_for
        # lo cancele en cada iteración del bucle de 30s
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
                output = (stderr or b"").decode("utf-8").strip() or "(sin respuesta)"
        else:
            output = "Timeout (300s) — tarea terminada forzosamente."

    except Exception as exc:
        output = f"Error lanzando claude: {exc}"
    finally:
        ACTIVE_TASKS.pop(task_id, None)

    # Enviar resultado en chunks si es largo
    chunks = [output[i : i + 3800] for i in range(0, max(len(output), 1), 3800)]
    for i, chunk in enumerate(chunks):
        prefix = f"✅ `{task_id}`:\n" if i == 0 else f"`{task_id}` (cont.):\n"
        await APP.bot.send_message(
            chat_id=chat_id,
            text=f"{prefix}```\n{chunk}\n```",
            parse_mode="Markdown",
        )
    log.info("Tarea completada: %s (%d chars)", task_id, len(output))


async def _spawn_task(update: Update, description: str) -> str:
    """Registra la tarea y lanza _run_task en background. Retorna task_id."""
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

    log.info("Tarea spawned: %s | %s", task_id, description[:60])
    return task_id


# ── Handlers de tareas ──────────────────────────────────────────────────────────
async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "Uso: `/task [descripción de la tarea]`", parse_mode="Markdown"
        )
        return
    task_id = await _spawn_task(update, description)
    await update.message.reply_text(
        f"🚀 `{task_id}` lanzado\n_{description[:80]}_\n\n"
        f"Notificaré con el resultado. Update cada 30s si tarda.",
        parse_mode="Markdown",
    )
    log.info("/task: %s | %s", task_id, description[:60])


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    if not ACTIVE_TASKS:
        await update.message.reply_text("No hay tareas activas.")
        return
    now = time.time()
    lines = ["*Tareas activas:*\n"]
    for tid, info in ACTIVE_TASKS.items():
        elapsed = int(now - info["start_time"])
        m, s = divmod(elapsed, 60)
        proc = info.get("proc")
        alive = "🟢" if (proc and proc.returncode is None) else "🟡"
        lines.append(
            f"{alive} `{tid}` — {m}m{s}s\n"
            f"   _{info['description'][:60]}_"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_output(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    if not context.args:
        await update.message.reply_text("Uso: `/output [task_id]`", parse_mode="Markdown")
        return
    task_id = context.args[0]
    if task_id not in ACTIVE_TASKS:
        await update.message.reply_text(
            f"Tarea `{task_id}` no encontrada.", parse_mode="Markdown"
        )
        return
    info = ACTIVE_TASKS[task_id]
    elapsed = int(time.time() - info["start_time"])
    proc = info.get("proc")
    status = "en progreso" if (proc and proc.returncode is None) else "finalizando"
    await update.message.reply_text(
        f"`{task_id}` — {status} ({elapsed}s)\n"
        f"_{info['description'][:80]}_\n\n"
        f"El resultado completo se enviará al terminar.",
        parse_mode="Markdown",
    )


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    if not context.args:
        await update.message.reply_text("Uso: `/kill [task_id]`", parse_mode="Markdown")
        return
    task_id = context.args[0]
    if task_id not in ACTIVE_TASKS:
        await update.message.reply_text(
            f"Tarea `{task_id}` no encontrada.", parse_mode="Markdown"
        )
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
        await update.message.reply_text("No autorizado.")
        return
    await update.message.reply_text(
        "Las tareas corren con `claude -p` (no interactivo).\n"
        "Para interacción usa `/task` con instrucciones completas.",
        parse_mode="Markdown",
    )


# ── Handlers existentes ─────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    chat_id = update.effective_chat.id
    text = (
        f"*JARVIS Bot — terminal móvil*\n\n"
        f"Chat ID: `{chat_id}`\n\n"
        "*Tareas Claude Code:*\n"
        "/task [desc] — lanza claude -p en background\n"
        "/tasks — lista tareas activas\n"
        "/output [id] — estado de la tarea\n"
        "/kill [id] — cancelar tarea\n\n"
        "*Sistema JAL:*\n"
        "/status — objetivos activos en BD\n"
        "/score — ultimo scoring snapshot\n"
        "/logs — ultimas 20 lineas del log\n"
        "/audit — ejecuta gemini\\_review.py\n"
        "/run [nombre.md] — ejecuta jal\\_run.py\n\n"
        "Mensaje libre: verbo de acción o \\>15 palabras → /task automático.\n"
        "Resto → respuesta rápida."
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    log.info("/start desde chat_id=%s", chat_id)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    rows = db_query(
        """
        SELECT objective_id, title, status, priority, score_final, current_attempt
        FROM jal_objectives
        ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'queue' THEN 1 ELSE 2 END,
                 started_at DESC
        LIMIT 5
        """
    )
    if not rows:
        await update.message.reply_text("No hay objetivos en la BD.")
        return
    lines = ["*Ultimos objetivos (jal\\_objectives):*\n"]
    for obj_id, title, status, priority, score, attempt in rows:
        emoji = {"active": "[ON]", "queue": "[Q]", "done": "[OK]", "failed": "[X]"}.get(
            status, "[ ]"
        )
        lines.append(
            f"{emoji} `{obj_id}` - {title}\n"
            f"   Estado: {status} | P{priority} | Score: {score:.2f} | Intento {attempt}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    log.info("/status consultado")


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    rows = db_query(
        """
        SELECT s.objective_id, s.attempt, s.evaluated_at, s.score_raw,
               s.score_final, s.converges, s.steps_completed, s.steps_total
        FROM jal_scoring_snapshots s
        ORDER BY s.evaluated_at DESC
        LIMIT 1
        """
    )
    if not rows:
        await update.message.reply_text("No hay snapshots de scoring.")
        return
    (obj_id, attempt, evaluated_at, score_raw, score_final, converges,
     steps_done, steps_total) = rows[0]
    converge_str = "[OK] Converge" if converges else "[~] Sin convergencia"
    text = (
        f"*Ultimo scoring snapshot:*\n\n"
        f"Objetivo: `{obj_id}`\n"
        f"Intento: {attempt}\n"
        f"Evaluado: {evaluated_at}\n"
        f"Score raw: {score_raw:.3f}\n"
        f"Score final: {score_final:.3f}\n"
        f"Pasos: {steps_done}/{steps_total}\n"
        f"Convergencia: {converge_str}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    log.info("/score consultado")


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        tail = "\n".join(lines[-20:]) if lines else "(log vacio)"
    except FileNotFoundError:
        tail = "(log aun no creado)"
    await send_chunks(update, f"*Log del bot (ultimas 20 lineas):*\n```\n{tail}\n```")
    log.info("/logs consultado")


async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    await update.message.reply_text("Ejecutando gemini_review.py... (puede tardar)")
    log.info("/audit iniciado")
    output = run_cmd(["python3", "bin/gemini_review.py"], timeout=180)
    await send_chunks(update, f"*Resultado audit:*\n```\n{output[:3800]}\n```")
    log.info("/audit completado")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if not args:
        queue_files = sorted(QUEUE_DIR.glob("*.md")) if QUEUE_DIR.exists() else []
        if not queue_files:
            await update.message.reply_text("Cola vacia. Usa `/run nombre.md` para ejecutar.")
            return
        names = "\n".join(f"- `{f.name}`" for f in queue_files)
        await update.message.reply_text(
            f"*Objetivos en queue:*\n{names}\n\nUsa `/run nombre.md` para ejecutar.",
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        await update.message.reply_text("No autorizado.")
        return
    user_msg = (update.message.text or "").strip()
    if not user_msg:
        return

    word_count = len(user_msg.split())
    is_action = bool(ACTION_VERBS_RE.search(user_msg)) or word_count > 15

    if is_action:
        task_id = await _spawn_task(update, user_msg)
        await update.message.reply_text(
            f"🚀 `{task_id}` lanzado\n_{user_msg[:80]}_",
            parse_mode="Markdown",
        )
        log.info("Mensaje → task: %s | %s", task_id, user_msg[:60])
        return

    # Respuesta rápida vía OpenRouter (sin claude CLI)
    await update.message.reply_text("Procesando...")
    log.info("Mensaje rápido: %s", user_msg[:80])
    prompt = (
        "Eres JARVIS, el sistema de orquestacion de Iker. "
        f"Responde de forma concisa y tecnica:\n\n{user_msg}"
    )
    result = subprocess.run(
        [
            "python3", str(JARVIS / "bin" / "openrouter_wrapper.py"),
            "--model", "stepfun/step-3.5-flash:free",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        cwd=str(JARVIS),
        timeout=60,
        env=_load_env_dict(),
    )
    output = result.stdout.strip() or "(sin respuesta)"
    await send_chunks(update, output)
    log.info("Respuesta rápida enviada (%d chars)", len(output))


# ── Main ────────────────────────────────────────────────────────────────────────
def main() -> None:
    global APP
    if not BOT_TOKEN:
        log.error("JARVIS_BOT_TOKEN no configurado en .env -- abortando.")
        sys.exit(1)

    log.info("Iniciando JARVIS Bot (terminal móvil)...")
    APP = Application.builder().token(BOT_TOKEN).build()

    APP.add_handler(CommandHandler("start", cmd_start))
    APP.add_handler(CommandHandler("status", cmd_status))
    APP.add_handler(CommandHandler("score", cmd_score))
    APP.add_handler(CommandHandler("logs", cmd_logs))
    APP.add_handler(CommandHandler("audit", cmd_audit))
    APP.add_handler(CommandHandler("run", cmd_run))
    APP.add_handler(CommandHandler("task", cmd_task))
    APP.add_handler(CommandHandler("tasks", cmd_tasks))
    APP.add_handler(CommandHandler("output", cmd_output))
    APP.add_handler(CommandHandler("reply", cmd_reply_task))
    APP.add_handler(CommandHandler("kill", cmd_kill))
    APP.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Bot en polling. Ctrl+C para detener.")
    APP.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
