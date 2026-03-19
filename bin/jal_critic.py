"""
JAL Critic v3
=============
Evalua el cumplimiento del objetivo con Gemini.
Alimenta el motor de scoring MCDA.
Aprende patrones de fallo de Claude Code.
Gestiona conversacion Telegram con NLU via Claude.
"""

import json
import os
import sys
import subprocess
import requests
import time
from pathlib import Path
from datetime import datetime

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))

# Import scoring engine (same directory)
sys.path.insert(0, str(JARVIS / "bin"))
from db import get_db
from jal_common import load_env
from jal_scoring import (
    ScoringResult,
    StepMeasurement,
    load_from_db,
    PASS_THRESHOLD,
)
from notify import send_telegram as _send_raw


# ─────────────────────────────────────────────
# GEMINI: evaluacion por paso
# ─────────────────────────────────────────────


def evaluate_with_gemini(obj_content: str, steps_summary: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"steps": [], "error": "GEMINI_API_KEY no configurada"}

    prompt = f"""Eres un evaluador tecnico senior.
Evalua el cumplimiento de cada paso con precision decimal.

OBJETIVO:
{obj_content}

EJECUCION:
{steps_summary}

Para cada paso evalua:
- completion_pct: proporcion real completada [0.0-1.0]
  (0.73 != 0.70, se preciso)
- weight_suggested: importancia para el objetivo [0.0-1.0]
- criticality: 1=normal, 2=importante, 3=bloquea el objetivo
- error_category: dependency|logic|config|env|timeout|permission|unknown
- error_message: descripcion exacta del fallo ('' si OK)
- fix_action: accion concreta para resolver ('' si OK)

Responde SOLO con JSON valido:
{{
    "steps": [
        {{
            "step_number": 1,
            "completion_pct": 0.0,
            "weight_suggested": 0.0,
            "criticality": 1,
            "error_category": "unknown",
            "error_message": "",
            "fix_action": ""
        }}
    ],
    "root_cause": "causa raiz principal en 1 linea ('' si todo OK)",
    "strengths": ["que salio bien"],
    "lessons": ["que aprender para proximas ejecuciones"]
}}"""

    resp = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash-exp:generateContent",
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=45,
    )
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    for d in ["```json", "```"]:
        if d in raw:
            raw = raw.split(d)[1].split("```")[0]
    return json.loads(raw.strip())


# ─────────────────────────────────────────────
# APRENDIZAJE: actualizar patrones de Claude Code
# ─────────────────────────────────────────────


def learn_from_errors(obj_id: str, attempt: int, result: ScoringResult, gemini_eval: dict):
    """
    Actualiza jal_error_patterns con los fallos observados.
    Este es el mecanismo por el que el sistema aprende que
    falla en Claude Code y puede prevenirlo en futuros planes.
    """
    with get_db() as conn:
        for err in result.errors:
            sig = err["message"][:80].lower().strip()
            if not sig:
                continue

            existing = conn.execute(
                """
                SELECT id, frequency, total_executions
                FROM jal_error_patterns
                WHERE error_signature=? AND category=?
            """,
                (sig, err["category"]),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE jal_error_patterns SET
                        frequency = frequency + 1,
                        total_executions = total_executions + 1,
                        failure_rate = CAST(frequency+1 AS REAL) /
                                       CAST(total_executions+1 AS REAL),
                        avg_severity = (avg_severity + ?) / 2,
                        avg_propagation = (avg_propagation + ?) / 2,
                        last_seen = datetime('now')
                    WHERE id=?
                """,
                    (err["severity"], err["propagation"], existing[0]),
                )
            else:
                pattern_id = f"PAT-{err['category'].upper()[:3]}-"
                pattern_id += datetime.now().strftime("%Y%m%d%H%M%S")
                conn.execute(
                    """
                    INSERT INTO jal_error_patterns
                    (pattern_id, category, error_signature,
                     frequency, total_executions, failure_rate,
                     avg_severity, avg_propagation, last_seen)
                    VALUES (?,?,?,1,1,1.0,?,?,datetime('now'))
                """,
                    (
                        pattern_id,
                        err["category"],
                        sig,
                        err["severity"],
                        err["propagation"],
                    ),
                )

            conn.execute(
                """
                INSERT INTO jal_error_taxonomy
                (objective_id, attempt, step_number, error_code,
                 category, severity, propagation, fix_complexity,
                 critical_score, priority_label, error_message,
                 fix_suggested)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    obj_id,
                    attempt,
                    err["step"],
                    err["error_code"],
                    err["category"],
                    err["severity"],
                    err["propagation"],
                    err["fix_complexity"],
                    err["critical_score"],
                    err["label"],
                    err["message"],
                    gemini_eval.get("root_cause", ""),
                ),
            )

        conn.execute(
            """
            UPDATE jal_error_patterns SET
                total_executions = total_executions + 1,
                failure_rate = CAST(frequency AS REAL) /
                               CAST(total_executions + 1 AS REAL)
            WHERE category NOT IN (
                SELECT DISTINCT category FROM jal_error_taxonomy
                WHERE objective_id=? AND attempt=?
            )
        """,
            (obj_id, attempt),
        )


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────


def send_telegram(text: str, obj_id: str = "", score: float = 0.0):
    _send_raw(text, parse_mode="Markdown")
    if obj_id:
        _save_conv(obj_id, "out", text, score=score)


def _save_conv(
    obj_id: str,
    direction: str,
    text: str,
    intent: str = "",
    score: float = 0.0,
    update_id: int = 0,
):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jal_conversations
            (objective_id, direction, message_text,
             intent, score_at_time, update_id)
            VALUES (?,?,?,?,?,?)
        """,
            (obj_id, direction, text, intent, score, update_id),
        )


def get_telegram_reply(obj_id: str, timeout_s: int = 600) -> tuple[str, int]:
    """
    Escucha respuesta de Telegram.
    Retorna (texto, update_id) o ('', 0) si timeout.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return "", 0

    with get_db() as conn:
        last = conn.execute("""
            SELECT update_id FROM jal_conversations
            WHERE direction='in' AND update_id > 0
            ORDER BY id DESC LIMIT 1
        """).fetchone()
    offset = (last[0] + 1) if last else 0

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            ).json()
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) == str(chat_id):
                    return msg.get("text", ""), upd["update_id"]
        except Exception:
            time.sleep(5)
    return "", 0


def classify_intent_with_claude(user_text: str, score: float) -> str:
    """
    Clasifica la intencion del usuario via OpenRouter.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "clarify"

    prompt = f"""Clasifica la intencion de este mensaje en una de estas categorias:

approve       -> el usuario acepta el resultado actual
retry_full    -> quiere reintentar el objetivo completo hasta mejor score
retry_critical -> quiere corregir solo los errores criticos
audit         -> quiere una auditoria del codigo/sistema
next_objective -> quiere pasar al siguiente objetivo
abandon       -> quiere cancelar este objetivo
clarify       -> no se entiende la intencion

Mensaje: "{user_text}"
Score actual: {score:.0%}

Responde SOLO con una de estas palabras exactas:
approve | retry_full | retry_critical | audit | next_objective | abandon | clarify"""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://jarvis.local",
                "X-Title": "DQIII8",
            },
            json={
                "model": "stepfun/step-3.5-flash:free",
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        intent = resp.json()["choices"][0]["message"]["content"].strip().lower()
    except Exception:
        return "clarify"

    valid = {
        "approve",
        "retry_full",
        "retry_critical",
        "audit",
        "next_objective",
        "abandon",
        "clarify",
    }
    return intent if intent in valid else "clarify"


# ─────────────────────────────────────────────
# FORMATEO DEL REPORTE
# ─────────────────────────────────────────────


def format_report(result: ScoringResult, gemini_eval: dict, title: str) -> str:
    s = result.score_final
    pct = round(s * 100, 1)
    conv = result.convergence_est

    status = (
        "COMPLETADO"
        if s >= 0.95
        else (
            "APROBADO"
            if s >= PASS_THRESHOLD
            else "PARCIAL" if s >= 0.60 else "CRITICO" if s >= 0.30 else "FALLIDO"
        )
    )

    r = f"{status} -- *{title[:50]}*\n\n"
    r += f"*Score: {pct}%* (intento {result.attempt})\n"
    r += "```\n"
    r += f"score_raw:   {result.score_raw*100:.1f}%\n"
    r += f"entropy_H:   {result.entropy_H:.3f}"
    if result.entropy_H > 0.7:
        r += " alta dispersion"
    r += f"\nmomentum:    {result.delta_score*100:+.1f}%\n"
    r += f"bloqueante:  {'SI' if any(s.is_blocker for s in result.steps) else 'NO'}\n"
    if conv is not None:
        r += f"convergencia: ~{conv} intentos mas\n"
    elif s < PASS_THRESHOLD:
        r += "convergencia: no converge\n"
    r += "```\n"

    if result.errors:
        r += "\n*Errores:*\n"
        for e in result.errors[:3]:
            label_map = {
                "BLOQUEANTE": "[BLOQ]",
                "CRITICO": "[CRIT]",
                "MODERADO": "[MOD]",
                "MENOR": "[MEN]",
            }
            icon = label_map.get(e["label"], "[?]")
            r += (
                f"{icon} `{e['error_code']}` cs={e['critical_score']:.3f}"
                f" -- {e['message'][:60]}\n"
            )

    root = gemini_eval.get("root_cause", "")
    if root:
        r += f"\n*Causa raiz:* {root[:120]}\n"

    strengths = gemini_eval.get("strengths", [])
    if strengths:
        r += "\n*Bien:* " + " - ".join(strengths[:2]) + "\n"

    r += "\n" + "=" * 20 + "\n"
    if s >= PASS_THRESHOLD:
        r += "*Que hacemos?*\n" "- auditoria rapida\n" "- siguiente objetivo\n" "- aprobado\n"
    else:
        r += (
            f"*Como continuamos?*\n"
            f"- repite hasta el 100%\n"
            f"- corrige solo los criticos\n"
            f"- es suficiente, continua ({pct}%)\n"
        )
    return r.strip()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────


def main():
    load_env()

    with get_db() as conn:
        row = conn.execute("""
            SELECT objective_id, title, current_attempt, max_attempts
            FROM jal_objectives WHERE status='active'
            ORDER BY started_at DESC LIMIT 1
        """).fetchone()

    if not row:
        print("[CRITIC] No hay objetivo activo")
        sys.exit(0)

    obj_id, title, current_attempt, max_attempts = row
    attempt = current_attempt

    print(f"[CRITIC] {obj_id} -- intento {attempt}/{max_attempts}")

    obj_files = sorted((JARVIS / "objectives" / "active").glob("*.md"))
    obj_content = obj_files[0].read_text("utf-8") if obj_files else title

    with get_db() as conn:
        steps_rows = conn.execute(
            """
            SELECT step_number, description, status, result_summary, error_raw
            FROM jal_steps WHERE objective_id=? AND attempt=?
            ORDER BY step_number
        """,
            (obj_id, attempt),
        ).fetchall()

    steps_summary = "\n".join(
        f"{'OK' if r[2]=='completed' else 'FAIL'} "
        f"Paso {r[0]}: {r[1]}\n"
        f"  -> {(r[3] or r[4] or 'sin info')[:200]}"
        for r in steps_rows
    )

    print("[CRITIC] Evaluando con Gemini...")
    gemini_eval = evaluate_with_gemini(obj_content, steps_summary)

    with get_db() as conn:
        for step_data in gemini_eval.get("steps", []):
            conn.execute(
                """
                UPDATE jal_steps SET
                    completion_pct = ?,
                    weight         = ?,
                    criticality    = ?,
                    error_category = ?,
                    result_summary = ?
                WHERE objective_id=? AND attempt=? AND step_number=?
            """,
                (
                    step_data.get("completion_pct", 0.0),
                    step_data.get("weight_suggested", 0.33),
                    step_data.get("criticality", 1),
                    step_data.get("error_category", "unknown"),
                    step_data.get("error_message", "") or step_data.get("fix_action", ""),
                    obj_id,
                    attempt,
                    step_data["step_number"],
                ),
            )

    result = load_from_db(obj_id, attempt)
    result.save()

    pct = round(result.score_final * 100, 1)
    print(
        f"[CRITIC] Score: {pct}% | H={result.entropy_H:.3f} | "
        f"delta={result.delta_score*100:+.1f}%"
    )

    learn_from_errors(obj_id, attempt, result, gemini_eval)

    with get_db() as conn:
        conn.execute(
            """
            UPDATE jal_objectives SET
                score_final = ?, score_raw = ?, entropy_H = ?,
                passed = ?,
                status = CASE
                    WHEN ? >= 0.85 THEN 'completed'
                    WHEN ? >= ?    THEN 'failed'
                    ELSE 'active'
                END
            WHERE objective_id=?
        """,
            (
                result.score_final,
                result.score_raw,
                result.entropy_H,
                1 if result.score_final >= PASS_THRESHOLD else 0,
                result.score_final,
                attempt,
                max_attempts,
                obj_id,
            ),
        )

    lessons = gemini_eval.get("lessons", [])
    if lessons:
        date = datetime.now().strftime("%Y-%m-%d")
        with open(JARVIS / "tasks" / "lessons.md", "a", encoding="utf-8") as f:
            for lesson in lessons:
                f.write(f"\n[{date}] [JAL-{obj_id}] {lesson}")

    report = format_report(result, gemini_eval, title)
    send_telegram(report, obj_id=obj_id, score=result.score_final)

    if result.score_final >= PASS_THRESHOLD:
        _handle_pass(obj_id, title, result, attempt, max_attempts)
    elif attempt >= max_attempts:
        _handle_max_attempts(obj_id, title, result, attempt)
    else:
        _handle_retry(obj_id, result, gemini_eval)


def _handle_pass(obj_id, title, result, attempt, max_attempts):
    print("[CRITIC] Aprobado. Esperando decision Telegram...")
    for _ in range(5):
        user_msg, upd_id = get_telegram_reply(obj_id, timeout_s=1800)
        if not user_msg:
            send_telegram(
                "Sin respuesta. El objetivo queda pendiente de tu aprobacion.",
                obj_id=obj_id,
            )
            break

        intent = classify_intent_with_claude(user_msg, result.score_final)
        _save_conv(
            obj_id,
            "in",
            user_msg,
            intent=intent,
            score=result.score_final,
            update_id=upd_id,
        )
        print(f"[CRITIC] Intent: {intent}")

        if intent == "audit":
            send_telegram("Ejecutando auditoria...", obj_id=obj_id)
            subprocess.run(
                ["python3", str(JARVIS / "bin" / "gemini_review.py")],
                cwd=str(JARVIS),
            )
            send_telegram(
                "Auditoria completada.\nContinuo con el siguiente objetivo?",
                obj_id=obj_id,
            )

        elif intent == "next_objective":
            _activate_next(obj_id)
            break

        elif intent == "approve":
            with get_db() as conn:
                conn.execute(
                    """UPDATE jal_objectives SET
                    status='completed', completed_at=datetime('now'),
                    user_approved=1 WHERE objective_id=?""",
                    (obj_id,),
                )
            send_telegram("Aprobado. En espera de proximo objetivo.", obj_id=obj_id)
            break

        elif intent == "retry_full":
            _extend_and_retry(obj_id, "completo")
            break

        else:
            send_telegram(
                "No entendi. Puedes decir:\n"
                "- auditoria rapida\n"
                "- siguiente objetivo\n"
                "- aprobado\n"
                "- repite hasta el 100%",
                obj_id=obj_id,
            )


def _handle_max_attempts(obj_id, title, result, attempt):
    pct = round(result.score_final * 100, 1)
    send_telegram(
        f"Maximo intentos ({attempt}) alcanzado.\n"
        f"Mejor score: *{pct}%*\n\n"
        f"- amplia intentos\n"
        f"- acepto {pct}%\n"
        f"- abandona",
        obj_id=obj_id,
        score=result.score_final,
    )
    user_msg, upd_id = get_telegram_reply(obj_id, timeout_s=3600)
    if user_msg:
        intent = classify_intent_with_claude(user_msg, result.score_final)
        _save_conv(
            obj_id,
            "in",
            user_msg,
            intent=intent,
            score=result.score_final,
            update_id=upd_id,
        )
        if intent == "retry_full":
            _extend_and_retry(obj_id, "ampliado")
        elif intent in ("approve", "next_objective"):
            with get_db() as conn:
                conn.execute(
                    """UPDATE jal_objectives SET
                    status='completed', completed_at=datetime('now'),
                    user_approved=1 WHERE objective_id=?""",
                    (obj_id,),
                )
            _activate_next(obj_id)
        elif intent == "abandon":
            with get_db() as conn:
                conn.execute(
                    """UPDATE jal_objectives SET
                    status='abandoned' WHERE objective_id=?""",
                    (obj_id,),
                )
            obj_files = list((JARVIS / "objectives" / "active").glob(f"{obj_id}*.md"))
            if obj_files:
                obj_files[0].rename(JARVIS / "objectives" / "failed" / obj_files[0].name)
            send_telegram("Objetivo abandonado.", obj_id=obj_id)


def _handle_retry(obj_id, result, gemini_eval):
    errors_str = " - ".join(e["message"][:50] for e in result.errors[:2]) or "ver BD para detalles"
    send_telegram(
        f"Replanificando (H={result.entropy_H:.2f})...\n" f"Errores: {errors_str}",
        obj_id=obj_id,
    )
    subprocess.run(
        ["python3", str(JARVIS / "bin" / "jal_planner.py")],
        cwd=str(JARVIS),
    )


def _extend_and_retry(obj_id: str, mode: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE jal_objectives SET
            max_attempts = max_attempts + 3,
            status = 'active'
            WHERE objective_id=?""",
            (obj_id,),
        )
    send_telegram(f"Ampliados intentos (+3). Reiniciando ({mode})...")
    subprocess.run(
        ["python3", str(JARVIS / "bin" / "jal_run.py")],
        cwd=str(JARVIS),
    )


def _activate_next(obj_id: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE jal_objectives SET
            status='completed', completed_at=datetime('now'),
            user_approved=1 WHERE objective_id=?""",
            (obj_id,),
        )
    obj_files = list((JARVIS / "objectives" / "active").glob(f"{obj_id}*.md"))
    if obj_files:
        obj_files[0].rename(JARVIS / "objectives" / "completed" / obj_files[0].name)
    queue = sorted((JARVIS / "objectives" / "queue").glob("*.md"))
    if queue:
        next_obj = queue[0]
        next_obj.rename(JARVIS / "objectives" / "active" / next_obj.name)
        send_telegram(
            f"Siguiente objetivo activado:\n*{next_obj.stem}*\n\n"
            f"Ejecuta: python3 bin/jal_run.py"
        )
    else:
        send_telegram("Queue vacio. Define el proximo objetivo.")


if __name__ == "__main__":
    main()
