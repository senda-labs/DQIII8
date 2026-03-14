#!/usr/bin/env python3
"""
OrchestratorLoop — JARVIS autonomous project management.

Ciclo: analyze → plan → build_prompt → execute → capture → store → repeat
Ejecutar: python3 bin/orchestrator_loop.py --project content-automation
En modo autónomo: JARVIS_MODE=autonomous python3 bin/orchestrator_loop.py ...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
MAX_RETRIES = 3  # Por objetivo — si falla 3 veces → BLOCKED
MAX_CYCLES = 10  # Por sesión del loop
GROQ_MODEL = "llama-3.3-70b-versatile"


class OrchestratorLoop:

    def check_rejections(self) -> list[dict]:
        """
        FIX D: Lee el buzón permission_rejection.json y lo vacía tras leer.
        Permite al loop detectar y reaccionar ante DENYs/ESCALATEs recientes
        sin esperar al siguiente ciclo completo.
        """
        reject_path = JARVIS_ROOT / "tasks" / "permission_rejection.json"
        if not reject_path.exists():
            return []
        try:
            data = json.loads(reject_path.read_text(encoding="utf-8"))
            # Vaciar el buzón tras leer (consume el mensaje)
            reject_path.write_text("[]", encoding="utf-8")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def analyze(self, project: str) -> dict:
        """Lee BD + MD + buzón de rechazos para construir contexto completo."""
        project_md = JARVIS_ROOT / f"projects/{project}.md"
        lessons_md = JARVIS_ROOT / "tasks/lessons.md"

        context: dict = {
            "project": project,
            "timestamp": datetime.now().isoformat(),
        }

        if project_md.exists():
            context["project_state"] = project_md.read_text(encoding="utf-8")

        # Lecciones relevantes — solo las del proyecto actual
        if lessons_md.exists():
            all_lessons = lessons_md.read_text(encoding="utf-8")
            relevant: list[str] = []
            in_section = False
            for line in all_lessons.splitlines():
                if line.startswith(f"## {project}"):
                    in_section = True
                elif line.startswith("## ") and in_section:
                    break
                elif in_section and line.startswith("- ["):
                    relevant.append(line)
            context["lessons"] = relevant[-10:]

        # Objetivos pendientes/fallidos de la BD
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            rows = conn.execute(
                "SELECT id, objective_text, status, retry_count "
                "FROM objectives WHERE project=? AND status IN "
                "('pending','failed') ORDER BY created_at LIMIT 5",
                (project,),
            ).fetchall()
            conn.close()
            context["pending_objectives"] = [
                {"id": r[0], "text": r[1], "status": r[2], "retries": r[3]} for r in rows
            ]
        except Exception:
            context["pending_objectives"] = []

        # Buzón de rechazos del PermissionAnalyzer
        context["recent_rejections"] = self.check_rejections()

        return context

    def _get_recent_cycles(self, project: str, limit: int = 3) -> list[dict]:
        """Obtiene los últimos N ciclos completados para evitar repetir objetivos."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            rows = conn.execute(
                """
                SELECT objective_text, status, result_summary
                FROM objectives
                WHERE project = ?
                  AND status IN ('completed', 'failed', 'blocked')
                ORDER BY completed_at DESC
                LIMIT ?
                """,
                (project, limit),
            ).fetchall()
            conn.close()
            return [
                {
                    "objective": r[0],
                    "status": r[1],
                    "result": r[2][:100] if r[2] else "",
                }
                for r in rows
            ]
        except Exception:
            return []

    def plan(self, context: dict) -> dict:
        """Usa Groq para determinar el siguiente objetivo."""
        import requests

        recent = self._get_recent_cycles(context["project"])
        context["recent_cycles"] = recent  # disponible para build_prompt

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if not groq_key:
            # Fallback: extraer próximo paso del project.md
            state = context.get("project_state", "")
            for line in state.splitlines():
                if "próximo paso" in line.lower() or "next step" in line.lower():
                    return {
                        "objective": line.strip("# -"),
                        "success_criteria": "Verificado con tests y sin errores",
                        "priority": "high",
                    }
            return {
                "objective": "Revisar estado del proyecto y continuar",
                "success_criteria": "Sin errores en CI",
                "priority": "medium",
            }

        prompt = f"""Eres el director técnico del proyecto JARVIS.
Analiza este estado del proyecto y determina el siguiente objetivo más impactante.

ESTADO ACTUAL:
{context.get('project_state', 'No disponible')[:2000]}

LECCIONES APRENDIDAS (errores a evitar):
{chr(10).join(context.get('lessons', []))}

OBJETIVOS PENDIENTES EN BD:
{json.dumps(context.get('pending_objectives', []), ensure_ascii=False, indent=2)}

Responde SOLO en JSON sin explicaciones ni markdown:
{{"objective": "descripción en 1-2 frases", "success_criteria": "cómo verificar que está hecho", "priority": "high|medium|low"}}"""

        if recent:
            prompt += "\n\nCICLOS RECIENTES (NO repetir estos objetivos):\n"
            for c in recent:
                prompt += f"- [{c['status']}] {c['objective'][:80]}\n"

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=30,
        )
        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = re.sub(r"```json?|```", "", text).strip()
        return json.loads(text)

    def build_prompt(self, objective: dict, context: dict) -> str:
        """Construye el prompt para Claude Code con formato estructurado."""
        lessons_text = "\n".join(context.get("lessons", []))
        return f"""=== JARVIS ORCHESTRATOR — OBJETIVO ACTUAL ===

PROYECTO: {context['project']}
OBJETIVO: {objective['objective']}
CRITERIO DE ÉXITO: {objective['success_criteria']}
PRIORIDAD: {objective.get('priority', 'high')}

ESTADO DEL PROYECTO:
{context.get('project_state', '')[:1500]}

LECCIONES A TENER EN CUENTA (errores pasados):
{lessons_text}

INSTRUCCIONES:
1. Ejecuta el objetivo descrito arriba
2. Verifica que se cumple el criterio de éxito
3. Si encuentras un bloqueante que requiere decisión humana, detente y explícalo
4. Al terminar, escribe exactamente este bloque (con los datos reales):

---FINAL_REPORT---
{{
  "success": true|false,
  "files_modified": ["lista de archivos"],
  "errors_found": ["errores encontrados"],
  "fixes_applied": ["correcciones aplicadas"],
  "lessons": ["nuevas lecciones en formato [KEYWORD] causa → solución"],
  "blocker": null | "descripción del bloqueante si lo hay",
  "next_step": "siguiente paso recomendado"
}}
---END_REPORT---"""

    def execute(self, prompt: str, project: str) -> str:
        """Lanza Claude Code en modo headless."""
        project_path = Path(f"/root/{project}")
        if not project_path.exists():
            project_path = Path("/root/jarvis")

        result = subprocess.run(
            ["claude", "--headless", "-p", prompt],
            capture_output=True,
            text=True,
            cwd=str(project_path),
            timeout=1800,
            env={**os.environ, "JARVIS_MODE": "autonomous"},
        )
        return result.stdout + result.stderr

    def capture(self, output: str) -> dict:
        """Extrae el FINAL_REPORT del output de Claude Code."""
        match = re.search(
            r"---FINAL_REPORT---\s*(\{.*?\})\s*---END_REPORT---",
            output,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Fallback: inferir éxito por ausencia de palabras de error
        has_error = any(w in output.lower() for w in ["error", "traceback", "failed", "exception"])
        return {
            "success": not has_error,
            "files_modified": [],
            "errors_found": [],
            "fixes_applied": [],
            "lessons": [],
            "blocker": None,
            "next_step": "Revisar output manualmente",
        }

    def store(self, obj_id: str, project: str, objective: dict, result: dict) -> None:
        """Guarda resultado en BD y actualiza lessons.md."""
        conn = sqlite3.connect(str(DB_PATH), timeout=10)

        status = "completed" if result.get("success") else "failed"
        if result.get("blocker"):
            status = "blocked"

        conn.execute(
            """
            UPDATE objectives SET
                status=?, completed_at=datetime('now'),
                result_summary=?, lessons_added=?,
                error_message=?
            WHERE id=?
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False),
                json.dumps(result.get("lessons", []), ensure_ascii=False),
                result.get("blocker")
                or (str(result.get("errors_found", [])) if not result["success"] else None),
                obj_id,
            ),
        )
        conn.commit()
        conn.close()

        # Añadir lecciones nuevas a lessons.md
        new_lessons = result.get("lessons", [])
        if new_lessons:
            lessons_path = JARVIS_ROOT / "tasks/lessons.md"
            today = datetime.now().strftime("%Y-%m-%d")
            with open(lessons_path, "a", encoding="utf-8") as f:
                for lesson in new_lessons:
                    f.write(f"- [{today}] {lesson}\n")

    def create_objective(self, project: str, text: str, criteria: str) -> str:
        """Inserta un nuevo objetivo en la BD."""
        obj_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO objectives
                (id, project, status, objective_text, success_criteria, created_at)
            VALUES (?, ?, 'pending', ?, ?, datetime('now'))
            """,
            (obj_id, project, text, criteria),
        )
        conn.commit()
        conn.close()
        return obj_id

    def _notify_telegram(self, message: str) -> None:
        """
        Envía notificación al bot de Telegram cuando el loop se pausa
        por ESCALATE o bloqueante humano, o cuando completa con éxito.
        Requiere TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env
        """
        import requests

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"🤖 *JARVIS OrchestratorLoop*\n\n{message}",
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        except Exception:
            pass

    def _sync_todo_md(self, project: str) -> None:
        """
        Regenera tasks/todo.md desde la tabla objectives de la BD.
        El OrchestratorLoop es el ÚNICO escritor de tasks/todo.md.
        Otros agentes escriben resultados SOLO en tasks/results/[agent]-[ts].md.
        """
        STATUS_ICON = {
            "running":   "🔄",
            "pending":   "⏳",
            "failed":    "❌",
            "blocked":   "🚨",
            "completed": "✅",
        }
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            rows = conn.execute(
                """
                SELECT id, objective_text, status, retry_count,
                       success_criteria, created_at
                FROM objectives
                WHERE project = ?
                ORDER BY
                    CASE status
                        WHEN 'running'   THEN 1
                        WHEN 'pending'   THEN 2
                        WHEN 'failed'    THEN 3
                        WHEN 'blocked'   THEN 4
                        WHEN 'completed' THEN 5
                    END, created_at DESC
                LIMIT 20
                """,
                (project,),
            ).fetchall()
            conn.close()

            lines = [
                f"# tasks/todo.md — {project}",
                f"_Generado por OrchestratorLoop — "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}_",
                "_Solo el OrchestratorLoop escribe aquí. "
                "Otros agentes → tasks/results/_",
                "",
            ]
            for status_group in ("running", "pending", "failed", "blocked", "completed"):
                group_rows = [r for r in rows if r[2] == status_group]
                if not group_rows:
                    continue
                lines.append(
                    f"## {STATUS_ICON.get(status_group, '')} {status_group.upper()}"
                )
                for r in group_rows:
                    obj_id, text, status, retries, criteria, _ = r
                    retry_str = (
                        f" (intento {retries}/{MAX_RETRIES})" if retries > 0 else ""
                    )
                    lines.append(f"- [{obj_id}]{retry_str} {text}")
                    if criteria:
                        lines.append(f"  → Criterio: {criteria}")
                lines.append("")

            todo_path = JARVIS_ROOT / "tasks" / "todo.md"
            todo_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"  [todo.md] sync error: {e}")

    def _print_effectiveness(self, project: str) -> None:
        """Imprime métricas históricas del proyecto desde loop_effectiveness."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                "SELECT total_cycles, successful, failed, escalated, "
                "success_rate_pct FROM loop_effectiveness WHERE project=?",
                (project,),
            ).fetchone()
            conn.close()
            if row and row[0]:
                print(
                    f"  📊 Historial: {row[0]} ciclos | "
                    f"✅ {row[1]} | ❌ {row[2]} | 🚨 {row[3]} | "
                    f"Tasa éxito: {row[4]}%"
                )
        except Exception:
            pass

    def run(self, project: str, max_cycles: int = MAX_CYCLES) -> None:
        """Loop principal del orquestador."""
        print(f"\n[ORCHESTRATOR] Iniciando loop — proyecto: {project}")
        self._print_effectiveness(project)

        for cycle in range(1, max_cycles + 1):
            print(f"\n── Ciclo {cycle}/{max_cycles} ──────────────────")

            # Sincronizar todo.md desde BD (único escritor)
            self._sync_todo_md(project)

            # ANALYZE
            context = self.analyze(project)

            # PLAN
            objective = self.plan(context)
            print(f"  Objetivo: {objective['objective'][:80]}...")

            # Crear registro en BD
            obj_id = self.create_objective(
                project,
                objective["objective"],
                objective.get("success_criteria", ""),
            )

            # Verificar max_retries
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            retries = conn.execute(
                "SELECT retry_count FROM objectives WHERE id=?", (obj_id,)
            ).fetchone()
            conn.close()
            if retries and retries[0] >= MAX_RETRIES:
                print(f"  ⛔ Objetivo bloqueado tras {MAX_RETRIES} intentos")
                conn = sqlite3.connect(str(DB_PATH), timeout=10)
                conn.execute("UPDATE objectives SET status='blocked' WHERE id=?", (obj_id,))
                conn.commit()
                conn.close()
                continue

            # BUILD PROMPT
            prompt = self.build_prompt(objective, context)

            # Pre-tests (snapshot de estado)
            pre_test = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "--tb=no", "-q"],
                capture_output=True,
                text=True,
                cwd=f"/root/{project}",
                timeout=120,
            )
            pre_ok = pre_test.returncode == 0
            print(f"  Pre-tests: {'✅' if pre_ok else '⚠️'}")

            # EXECUTE Claude Code
            print("  Ejecutando Claude Code (headless)...")
            output = self.execute(prompt, project)

            # CAPTURE
            result = self.capture(output)

            # Post-tests para verificar que no se rompió nada
            post_test = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "--tb=no", "-q"],
                capture_output=True,
                text=True,
                cwd=f"/root/{project}",
                timeout=120,
            )
            post_ok = post_test.returncode == 0
            if not post_ok and pre_ok:
                result["success"] = False
                result["errors_found"].append("Tests rompieron tras la ejecución")

            # STORE
            self.store(obj_id, project, objective, result)

            status_icon = "✅" if result["success"] else ("⛔" if result.get("blocker") else "🔄")
            print(f"  {status_icon} {result.get('next_step', '')[:60]}")

            # Parar si hay bloqueante humano (MEJORA 5: notificar)
            if result.get("blocker"):
                print(f"\n⚠️  BLOQUEANTE HUMANO: {result['blocker']}")
                print("  El loop se detiene. Resuelve el bloqueante y relanza.")
                self._notify_telegram(
                    f"🛑 *Bloqueante humano* en `{project}`\n"
                    f"*Ciclo {cycle}:* {result.get('blocker', '')[:200]}\n"
                    f"*Próximo paso:* {result.get('next_step', '')[:100]}"
                )
                break

            # Parar si hay ESCALATEs en el buzón de rechazos (MEJORA 5)
            escalates = [
                r for r in context.get("recent_rejections", [])
                if r.get("decision") == "ESCALATE"
            ]
            if escalates:
                e = escalates[0]
                print(f"\n🚨 ESCALATE detectado — loop pausado.")
                self._notify_telegram(
                    f"⚠️ *ESCALATE* en proyecto `{project}`\n"
                    f"Ciclo {cycle}/{max_cycles}\n\n"
                    f"*Razón:* {e.get('reason', '')[:150]}\n"
                    f"*Fix sugerido:* {e.get('suggested_fix', 'N/A')[:100]}\n\n"
                    f"Resuelve y relanza:\n`j --loop {project}`"
                )
                break

            # Parar si éxito y sin más pendientes (MEJORA 5: notificar)
            pending = context.get("pending_objectives", [])
            if result["success"] and not pending:
                print(f"\n✅ Proyecto {project} al día. Loop completado.")
                self._notify_telegram(
                    f"✅ *Loop completado* — `{project}`\n"
                    f"{cycle} ciclo(s) | objetivo cumplido"
                )
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS OrchestratorLoop")
    parser.add_argument("--project", required=True, help="Nombre del proyecto")
    parser.add_argument(
        "--cycles", type=int, default=MAX_CYCLES, help=f"Máximo de ciclos (default: {MAX_CYCLES})"
    )
    args = parser.parse_args()

    loop = OrchestratorLoop()
    loop.run(args.project, args.cycles)
