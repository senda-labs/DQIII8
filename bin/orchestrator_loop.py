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
                "SELECT id, objective_text, status, retry_count, success_criteria "
                "FROM objectives WHERE project=? AND status IN "
                "('pending','failed') ORDER BY created_at LIMIT 5",
                (project,),
            ).fetchall()
            conn.close()
            context["pending_objectives"] = [
                {
                    "id": r[0],
                    "text": r[1],
                    "status": r[2],
                    "retries": r[3],
                    "criteria": r[4] or "",
                }
                for r in rows
            ]
        except Exception:
            context["pending_objectives"] = []

        # Si hay pending en BD → señal para plan() de usar el primero directamente
        if context["pending_objectives"]:
            context["use_seeded_objective"] = True
            context["next_seeded_objective"] = context["pending_objectives"][0]

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
        """
        Determina el siguiente objetivo.
        Prioridad: (1) objetivos pre-sembrados en BD → (2) Groq → (3) fallback.
        """
        # Cargar ciclos recientes para build_prompt (siempre, independiente del path)
        context["recent_cycles"] = self._get_recent_cycles(context["project"])

        # Fast-path: usar objetivo pending de la BD directamente
        if context.get("use_seeded_objective"):
            obj = context["next_seeded_objective"]
            print(f"  [plan] Usando objetivo pre-sembrado [{obj['id']}]")
            return {
                "objective": obj["text"],
                "success_criteria": obj.get("criteria", ""),
                "priority": "high",
                "objective_id": obj["id"],  # ID existente → no crear nuevo en BD
            }

        return self._plan_with_groq(context)

    def _plan_with_groq(self, context: dict) -> dict:
        """
        Llama a Groq para generar un nuevo objetivo cuando no hay pending en BD.
        Enriquece el prompt con archivos existentes y métricas reales del proyecto.
        """
        import requests

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if not groq_key:
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

        # Leer estado real del proyecto (archivos existentes)
        project_path = Path(f"/root/{context['project']}")
        existing_files: list[str] = []
        if project_path.exists():
            existing_files = [
                str(p.relative_to(project_path))
                for p in project_path.rglob("*.py")
                if "__pycache__" not in str(p)
            ]
            cpp_files = list(project_path.rglob("*.cpp")) + list(project_path.rglob("*.so"))
            existing_files += [str(p.relative_to(project_path)) for p in cpp_files]

        # Leer métricas del último ciclo completado
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            last_metrics = conn.execute(
                """
                SELECT renderer, lines_of_code, cpu_seconds,
                       memory_peak_mb, ssim_score, passes_tests,
                       speedup_vs_python
                FROM code_metrics
                WHERE project = ?
                ORDER BY timestamp DESC LIMIT 3
                """,
                (context["project"],),
            ).fetchall()
            conn.close()
        except Exception:
            last_metrics = []

        metrics_text = (
            "\n".join(
                [
                    f"  - {r[0]}: {r[1]} líneas, {r[2]:.1f}s, "
                    f"{r[3]:.0f}MB RAM, SSIM={r[4]}, tests={'✅' if r[5] else '❌'}"
                    for r in last_metrics
                ]
            )
            if last_metrics
            else "Sin métricas previas"
        )

        ref_analysis = self._analyze_reference_image()
        recent = context.get("recent_cycles", [])

        prompt = f"""Eres el director técnico del proyecto {context['project']}.

ARCHIVOS EXISTENTES EN EL PROYECTO:
{chr(10).join(existing_files) if existing_files else 'Directorio vacío'}

MÉTRICAS DE LOS ÚLTIMOS RENDERERS COMPLETADOS:
{metrics_text}

OBJETIVOS COMPLETADOS RECIENTEMENTE:
{json.dumps(self._get_recent_cycles(context['project']), ensure_ascii=False, indent=2)}

ESTADO DEL PROYECTO:
{context.get('project_state', '')[:1500]}

ANÁLISIS DE IMAGEN DE REFERENCIA:
{ref_analysis}
REGLAS DEL PROYECTO math-image-generator:
- Stack: Python + C++ (ctypes). Sin IA, sin APIs de imagen.
- RAM máxima: 500MB en cualquier momento
- Targets: render <30s, C++ speedup >=5x, SSIM >0.5 (objetivo ambicioso)
- Código: <80 líneas por renderer Python, <120 líneas C++

Basándote en los archivos existentes y las métricas, determina
el SIGUIENTE objetivo más impactante para mejorar el sistema.

Prioridades (en orden):
1. Si falta algún renderer (julia, perlin, compositor) → crearlo
2. Si algún SSIM < 0.3 → mejorar el colormap de ese renderer
3. Si algún render > 30s → optimizar con C++
4. Si todos los tests pasan y SSIM > 0.3 → intentar mejorar SSIM
5. Si SSIM > 0.5 en todos → crear nuevo renderer más complejo

Responde SOLO en JSON:
{{"objective": "descripción específica en 2-3 frases con métricas target",
  "success_criteria": "cómo verificar que está hecho",
  "priority": "high|medium|low",
  "renderer": "mandelbrot|julia|perlin|cpp|compositor|nuevo"}}"""

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
                "max_tokens": 400,
                "temperature": 0.2,
            },
            timeout=30,
        )
        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = re.sub(r"```json?|```", "", text).strip()
        return json.loads(text)

    def _post_cycle_evaluation(
        self,
        project: str,
        result: dict,
        obj_id: str,
        cycle_num: int = 0,
        model_tier: str = "tier3",
    ) -> None:
        """
        Evalúa el resultado del ciclo: calcula SSIM del PNG generado y crea
        un objetivo de mejora automáticamente si el score es insuficiente.
        También envía las imágenes generadas por Telegram.
        """
        if not result.get("success"):
            return

        png_files = [f for f in result.get("files_modified", []) if f.endswith(".png")]
        if not png_files:
            return

        ssim_result = None
        for png in png_files:
            png_path = f"/root/{project}/{png}"
            try:
                r = subprocess.run(
                    [
                        "python3",
                        "-c",
                        f"import sys; sys.path.insert(0, '/root/{project}/src/python');"
                        f"from ssim_scorer import score_against_reference;"
                        f"import json; print(json.dumps(score_against_reference('{png_path}')))",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=f"/root/{project}",
                )
                if r.returncode == 0:
                    ssim_result = json.loads(r.stdout)
                    break
            except Exception:
                continue

        # Enviar imágenes generadas por Telegram (con o sin SSIM)
        project_output = Path(f"/root/{project}/output")
        if project_output.exists():
            png_files = sorted(
                project_output.glob("*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:3]
            for png in png_files:
                ssim_info = ""
                if ssim_result:
                    score_val = ssim_result.get("score") or 0
                    quality = ssim_result.get("quality", "")
                    ssim_bar = "🟢" if score_val > 0.6 else ("🟡" if score_val > 0.3 else "🔴")
                    ssim_info = f"\n{ssim_bar} SSIM: {score_val:.4f} ({quality})"
                safe_stem = png.stem.replace("_", "\\_")
                caption = (
                    f"*{safe_stem}* — `{project}`\n"
                    f"Ciclo {cycle_num} | Tier: {model_tier}"
                    f"{ssim_info}\n"
                    f"1080x1920 | Matematica pura"
                )
                self._send_image_telegram(str(png), caption)

        if not ssim_result:
            return

        score = ssim_result.get("score") or 0

        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            conn.execute(
                "UPDATE objectives SET result_summary=json_set("
                "COALESCE(result_summary,'{}'), '$.ssim_score', ?) WHERE id=?",
                (score, obj_id),
            )
            if score < 0.4:
                renderer = (result.get("code_metrics") or {}).get("renderer", "unknown")
                improvement_text = (
                    f"Mejorar SSIM del renderer '{renderer}' de {score:.3f} a >0.4. "
                    f"El PNG actual no se parece suficientemente a la imagen de referencia. "
                    f"Ajustar el colormap para usar más azules fríos "
                    f"(#4060a0, #6080c0) y aumentar el contraste a ~255/255."
                )
                new_id = str(uuid.uuid4())[:8]
                conn.execute(
                    "INSERT INTO objectives "
                    "(id, project, status, objective_text, success_criteria, "
                    "created_at, model_tier) VALUES (?,?,?,?,?,datetime('now'),?)",
                    (
                        new_id,
                        project,
                        "pending",
                        improvement_text,
                        "SSIM > 0.4 vs imagen de referencia",
                        "tier3",
                    ),
                )
                print(f"  🎯 Auto-objetivo creado: mejorar SSIM {renderer} ({score:.3f} → >0.4)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  [post-eval] Error: {e}")

    def _analyze_reference_image(self) -> str:
        """
        Analiza la imagen de referencia y devuelve descripción técnica
        para incluir en el prompt del generador matemático.
        """
        ref_path = JARVIS_ROOT / "tasks/reference_image.jpg"
        if not ref_path.exists():
            return ""
        try:
            result = subprocess.run(
                ["python3", str(JARVIS_ROOT / "bin/analyze_reference.py"), str(ref_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                palette_str = ", ".join(
                    f"{c['hex']} ({c['weight']*100:.0f}%)" for c in data["palette"]
                )
                return f"""
IMAGEN DE REFERENCIA — Análisis técnico:
  Paleta dominante: {palette_str}
  Temperatura de color: {data['color_temperature']}
  Distribución vertical (brillo):
    - Tercio superior: {data['distribution']['top_third_brightness']:.0f}/255
    - Tercio medio:    {data['distribution']['middle_third_brightness']:.0f}/255
    - Tercio inferior: {data['distribution']['bottom_third_brightness']:.0f}/255
  Complejidad textural:
    - Superior: {data['texture']['top_complexity']:.1f} (mayor = más detalle)
    - Medio:    {data['texture']['middle_complexity']:.1f}
    - Inferior: {data['texture']['bottom_complexity']:.1f}
  Contraste tonal: {data['tonal']['contrast']:.0f}/255

USA ESTOS DATOS para parametrizar el generador matemático:
- Ajusta los colormaps para usar la paleta dominante
- Distribuye la complejidad vertical según los valores de textura
- El contraste del output debe aproximarse a {data['tonal']['contrast']:.0f}
"""
        except Exception:
            return ""

    def build_prompt(self, objective: dict, context: dict) -> str:
        """Construye el prompt para Claude Code con formato estructurado."""
        lessons_text = "\n".join(context.get("lessons", []))
        ref_analysis = self._analyze_reference_image()
        return f"""=== JARVIS ORCHESTRATOR — OBJETIVO ACTUAL ===

PROYECTO: {context['project']}
OBJETIVO: {objective['objective']}
CRITERIO DE ÉXITO: {objective['success_criteria']}
PRIORIDAD: {objective.get('priority', 'high')}

ESTADO DEL PROYECTO:
{context.get('project_state', '')[:1500]}

LECCIONES A TENER EN CUENTA (errores pasados):
{lessons_text}
{ref_analysis}
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
  "next_step": "siguiente paso recomendado",
  "code_metrics": {{
    "renderer": "mandelbrot|julia|perlin|cpp|compositor",
    "lines_of_code": <número entero>,
    "lines_functional": <líneas sin blancos ni comentarios>,
    "cpu_seconds": <tiempo medido con time.perf_counter>,
    "memory_peak_mb": <peak medido con tracemalloc>,
    "uses_vectorization": true|false,
    "uses_numpy_only": true|false,
    "passes_tests": true|false,
    "ssim_score": <score de ssim_scorer o null>,
    "output_variance": <np.var() del array de píxeles>,
    "speedup_vs_python": <ratio C++/Python o null>,
    "compiled_ok": true|false|null
  }}
}}
---END_REPORT---"""

    def execute(self, prompt: str, project: str, model_tier: str = "tier3") -> str:
        """
        Lanza el modelo correspondiente al tier.
        tier1  → Ollama qwen2.5-coder:7b (local, gratis)
        tier2  → OpenRouter free (via openrouter_wrapper.py)
        tier3  → Claude Code headless (default, Sonnet 4.6)
        haiku  → Claude Haiku 4.5 via Anthropic API directo
        """
        dispatch = {
            "tier1": self._execute_ollama,
            "tier2": self._execute_openrouter,
            "tier3": self._execute_claude,
            "haiku": self._execute_haiku,
        }
        executor = dispatch.get(model_tier, self._execute_claude)
        return executor(prompt, project)

    def _execute_claude(self, prompt: str, project: str) -> str:
        """
        Ejecuta Claude Code como usuario jarvis (non-root).
        Los permisos los gestiona el PermissionAnalyzer via hooks.
        Sin --dangerously-skip-permissions — el analyzer decide.
        """
        import tempfile

        project_path = Path(f"/root/{project}")
        if not project_path.exists():
            project_path = JARVIS_ROOT

        # Escribir prompt a archivo temporal legible por jarvis
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, dir="/tmp", encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name
        os.chmod(prompt_file, 0o644)

        try:
            # su - crea un login shell nuevo que resetea el entorno.
            # JARVIS_MODE y JARVIS_ROOT deben exportarse explícitamente
            # dentro del comando -c para que pre_tool_use.py los vea.
            result = subprocess.run(
                [
                    "su",
                    "-",
                    "jarvis",
                    "-c",
                    f"export JARVIS_MODE=autonomous; "
                    f"export JARVIS_ROOT={JARVIS_ROOT}; "
                    f"cd {project_path} && "
                    f'claude -p "$(cat {prompt_file})" '
                    f"--output-format text "
                    f"--add-dir {JARVIS_ROOT} 2>&1",
                ],
                capture_output=True,
                text=True,
                timeout=900,
            )
            return result.stdout + result.stderr
        finally:
            try:
                os.unlink(prompt_file)
            except Exception:
                pass

    def _execute_ollama(self, prompt: str, project: str) -> str:
        """Tier 1: 2-step — Qwen genera el plan, Claude Code lo ejecuta."""
        import requests

        model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

        # Paso 1: Qwen genera plan/código (sin herramientas)
        plan = ""
        plan_quality = "unavailable"
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model,
                    "prompt": (
                        "Eres un experto en Python y C++. Genera un plan detallado "
                        "y el código completo para la siguiente tarea. "
                        "No uses herramientas. Solo genera texto.\n\n"
                        f"{prompt}\n\n"
                        "Responde con:\n1. Plan paso a paso\n2. Código completo listo para ejecutar"
                    ),
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 3000},
                },
                timeout=600,
            )
            plan = resp.json().get("response", "")
            if len(plan) > 500:
                plan_quality = "good"
            elif len(plan) > 100:
                plan_quality = "partial"
            else:
                plan_quality = "poor"
        except Exception as e:
            print(f"  [tier1] Ollama no disponible: {e} → fallback tier3")
            return self._execute_claude(prompt, project)

        # Paso 2: Claude Code ejecuta el plan con herramientas reales
        combined_prompt = (
            f"{prompt}\n\n"
            f"--- PLAN GENERADO POR QWEN2.5-CODER ---\n"
            f"{plan}\n"
            f"--- FIN DEL PLAN ---\n\n"
            "Ejecuta el plan anterior usando las herramientas disponibles. "
            "Cuando termines, incluye en tu respuesta:\n"
            "---FINAL_REPORT---\n"
            '{"success": true, "files_modified": [], '
            '"errors_found": [], "fixes_applied": [], '
            '"lessons": [], "blocker": null, "next_step": "", '
            f'"qwen_plan_quality": "{plan_quality}"}}\n'
            "---END_REPORT---"
        )
        return self._execute_claude(combined_prompt, project)

    def _execute_openrouter(self, prompt: str, project: str) -> str:
        """Tier 2: OpenRouter free tier via openrouter_wrapper.py."""
        wrapper = JARVIS_ROOT / "bin" / "openrouter_wrapper.py"
        if not wrapper.exists():
            return "[OpenRouter] wrapper no encontrado en bin/openrouter_wrapper.py"
        result = subprocess.run(
            ["python3", str(wrapper), "generate", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ},
        )
        return result.stdout + result.stderr

    def _execute_haiku(self, prompt: str, project: str) -> str:
        """Haiku 4.5: 2-step — Haiku genera el plan, Claude Code lo ejecuta."""
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            print("  [haiku] ANTHROPIC_API_KEY no configurada → fallback tier3")
            return self._execute_claude(prompt, project)

        # Paso 1: Haiku genera plan/código (sin herramientas)
        plan = ""
        plan_quality = "error"
        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Genera un plan detallado y el código completo para la siguiente tarea. "
                            "Sé específico y concreto. No uses herramientas, solo genera texto.\n\n"
                            f"{prompt}\n\n"
                            "Responde con:\n1. Plan paso a paso\n2. Código completo listo para ejecutar"
                        ),
                    }
                ],
            )
            plan = msg.content[0].text
            if len(plan) > 500:
                plan_quality = "good"
            elif len(plan) > 100:
                plan_quality = "partial"
            else:
                plan_quality = "poor"
        except Exception as e:
            print(f"  [haiku] API error: {e} → fallback tier3")
            return self._execute_claude(prompt, project)

        # Paso 2: Claude Code ejecuta el plan con herramientas reales
        combined_prompt = (
            f"{prompt}\n\n"
            f"--- PLAN GENERADO POR CLAUDE HAIKU ---\n"
            f"{plan}\n"
            f"--- FIN DEL PLAN ---\n\n"
            "Ejecuta el plan anterior usando las herramientas disponibles. "
            "Cuando termines, incluye en tu respuesta:\n"
            "---FINAL_REPORT---\n"
            '{"success": true, "files_modified": [], '
            '"errors_found": [], "fixes_applied": [], '
            '"lessons": [], "blocker": null, "next_step": "", '
            f'"haiku_plan_quality": "{plan_quality}"}}\n'
            "---END_REPORT---"
        )
        return self._execute_claude(combined_prompt, project)

    def capture(self, output: str) -> dict:
        """Extrae el FINAL_REPORT del output de Claude Code."""

        def _normalize(report: dict) -> dict:
            """Normaliza campos de tier-planner y SSIM."""
            if "planner_quality" not in report:
                report["planner_quality"] = report.get("qwen_plan_quality") or report.get(
                    "haiku_plan_quality"
                )
            report.setdefault("ssim_score", None)
            report.setdefault("ssim_quality", None)
            return report

        # Intento 1: formato estricto con marcadores
        match = re.search(
            r"---FINAL_REPORT---\s*(\{.*?\})\s*---END_REPORT---",
            output,
            re.DOTALL,
        )
        if match:
            try:
                return _normalize(json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass

        # Intento 2: buscar cualquier JSON con "success" en el output
        for m in re.findall(r"\{[^{}]*\"success\"[^{}]*\}", output, re.DOTALL):
            try:
                data = json.loads(m)
                if "success" in data:
                    return _normalize(data)
            except json.JSONDecodeError:
                continue

        # Intento 3: inferir éxito por señales en el contenido del output
        output_lower = output.lower()
        success_signals = ["successfully", "created", "completed", "pytest", "passed", "✅", "done"]
        error_signals = ["error", "traceback", "failed", "exception", "timeout"]
        success_count = sum(1 for s in success_signals if s in output_lower)
        error_count = sum(1 for e in error_signals if e in output_lower)

        return {
            "success": success_count > error_count,
            "files_modified": [],
            "errors_found": [],
            "fixes_applied": [],
            "lessons": [],
            "blocker": None,
            "next_step": "Inferred from output signals",
            "planner_quality": None,
            "ssim_score": None,
            "ssim_quality": None,
            "inferred": True,
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
                error_message=?, planner_quality=?,
                ssim_score=?, ssim_quality=?
            WHERE id=?
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False),
                json.dumps(result.get("lessons", []), ensure_ascii=False),
                result.get("blocker")
                or (str(result.get("errors_found", [])) if not result["success"] else None),
                result.get("planner_quality"),
                result.get("ssim_score"),
                result.get("ssim_quality"),
                obj_id,
            ),
        )

        # Guardar métricas de benchmark si el agente las reportó
        metrics = result.get("code_metrics")
        if metrics and isinstance(metrics, dict) and metrics.get("renderer"):
            megapixels = 1080 * 1920 / 1_000_000  # 2.0736 mpx (resolución estándar)
            cpu_s = metrics.get("cpu_seconds")

            # Contar decisiones de permisos de la última hora (proxy del ciclo actual)
            perm_rows = conn.execute("""
                SELECT
                    SUM(CASE WHEN decision='APPROVE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN decision='DENY'    THEN 1 ELSE 0 END),
                    SUM(CASE WHEN decision='ESCALATE' THEN 1 ELSE 0 END)
                FROM permission_decisions
                WHERE timestamp > datetime('now', '-1 hour')
                """).fetchone()
            perm_approvals = perm_rows[0] or 0
            perm_denials = perm_rows[1] or 0
            escalations = perm_rows[2] or 0

            conn.execute(
                """
                INSERT INTO code_metrics
                    (project, model_tier, renderer, objective_id,
                     lines_of_code, lines_functional, cpu_seconds,
                     memory_peak_mb, megapixels, cpu_per_megapixel,
                     uses_vectorization, uses_numpy_only, passes_tests,
                     ssim_score, ssim_quality, output_variance,
                     speedup_vs_python, compiled_ok,
                     permission_approvals, permission_denials, escalations_needed,
                     success)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    project,
                    objective.get("model_tier", "tier3"),
                    metrics.get("renderer"),
                    obj_id,
                    metrics.get("lines_of_code"),
                    metrics.get("lines_functional"),
                    cpu_s,
                    metrics.get("memory_peak_mb"),
                    megapixels,
                    cpu_s / megapixels if cpu_s is not None else None,
                    1 if metrics.get("uses_vectorization") else 0,
                    1 if metrics.get("uses_numpy_only") else 0,
                    1 if metrics.get("passes_tests") else 0,
                    metrics.get("ssim_score"),
                    metrics.get("ssim_quality"),
                    metrics.get("output_variance"),
                    metrics.get("speedup_vs_python"),
                    1 if metrics.get("compiled_ok") else 0,
                    perm_approvals,
                    perm_denials,
                    escalations,
                    1 if result.get("success") else 0,
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

    def create_objective(
        self, project: str, text: str, criteria: str, model_tier: str = "tier3"
    ) -> str:
        """Inserta un nuevo objetivo en la BD, incluyendo model_tier."""
        obj_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO objectives
                (id, project, status, objective_text, success_criteria,
                 created_at, model_tier)
            VALUES (?, ?, 'pending', ?, ?, datetime('now'), ?)
            """,
            (obj_id, project, text, criteria, model_tier),
        )
        conn.commit()
        conn.close()
        return obj_id

    def _send_image_telegram(self, image_path: str, caption: str) -> None:
        """Envía una imagen al chat de Telegram via Bot API (sendPhoto multipart)."""
        import requests

        token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN", "")).strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not token or not chat_id:
            return

        img = Path(image_path)
        if not img.exists():
            print(f"  [img] No existe: {image_path}")
            return

        try:
            with open(img, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={
                        "chat_id": chat_id,
                        "caption": caption[:1024],
                        "parse_mode": "Markdown",
                    },
                    files={"photo": (img.name, f, "image/png")},
                    timeout=30,
                )
            if resp.status_code == 200:
                print(f"  [img] Enviada: {img.name}")
            else:
                print(f"  [img] Error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  [img] Error: {e}")

    def _notify_telegram(self, message: str) -> None:
        """
        Envía notificación al bot de Telegram cuando el loop se pausa
        por ESCALATE o bloqueante humano, o cuando completa con éxito.
        Requiere TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env
        """
        import requests

        token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN", "")).strip()
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
            "running": "🔄",
            "pending": "⏳",
            "failed": "❌",
            "blocked": "🚨",
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
                "_Solo el OrchestratorLoop escribe aquí. " "Otros agentes → tasks/results/_",
                "",
            ]
            for status_group in ("running", "pending", "failed", "blocked", "completed"):
                group_rows = [r for r in rows if r[2] == status_group]
                if not group_rows:
                    continue
                lines.append(f"## {STATUS_ICON.get(status_group, '')} {status_group.upper()}")
                for r in group_rows:
                    obj_id, text, status, retries, criteria, _ = r
                    retry_str = f" (intento {retries}/{MAX_RETRIES})" if retries > 0 else ""
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

    def _warmup_ollama(self) -> bool:
        """
        Envía un prompt mínimo a Ollama para cargar el modelo
        antes de que el loop empiece. Evita timeout en primer ciclo.
        """
        import requests

        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                    "prompt": "hi",
                    "stream": False,
                    "options": {"num_predict": 1},
                },
                timeout=600,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def run(self, project: str, max_cycles: int = MAX_CYCLES, model_tier: str = "tier3") -> None:
        """Loop principal del orquestador."""
        print(f"\n[ORCHESTRATOR] Iniciando loop — proyecto: {project} | tier: {model_tier}")
        self._print_effectiveness(project)

        if model_tier == "tier1":
            print("  [Tier1] Calentando Ollama (carga modelo ~60-120s)...")
            if self._warmup_ollama():
                print("  [Tier1] Ollama listo")
            else:
                print("  [Tier1] Ollama no responde — continuando con fallback")

        for cycle in range(1, max_cycles + 1):
            print(f"\n── Ciclo {cycle}/{max_cycles} ──────────────────")

            # Sincronizar todo.md desde BD (único escritor)
            self._sync_todo_md(project)

            # ANALYZE
            context = self.analyze(project)

            # PLAN
            objective = self.plan(context)
            print(f"  Objetivo: {objective['objective'][:80]}...")

            # Crear o reusar registro en BD
            seeded_id = objective.get("objective_id")
            if seeded_id:
                # Objetivo pre-sembrado: actualizar a 'running', no crear nuevo
                obj_id = seeded_id
                conn = sqlite3.connect(str(DB_PATH), timeout=10)
                conn.execute("UPDATE objectives SET status='running' WHERE id=?", (obj_id,))
                conn.commit()
                conn.close()
                print(f"  [run] Retomando objetivo [{obj_id}] (pre-sembrado)")
            else:
                obj_id = self.create_objective(
                    project,
                    objective["objective"],
                    objective.get("success_criteria", ""),
                    model_tier,
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
            output = self.execute(prompt, project, model_tier)

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
            self._post_cycle_evaluation(
                project, result, obj_id, cycle_num=cycle, model_tier=model_tier
            )

            status_icon = "✅" if result["success"] else ("⛔" if result.get("blocker") else "🔄")
            print(f"  {status_icon} {result.get('next_step', '')[:60]}")

            # Notificación de progreso por ciclo
            if result.get("success"):
                metrics = result.get("code_metrics") or {}
                ssim = metrics.get("ssim_score") or 0
                ssim_bar = "🟢" if ssim > 0.5 else ("🟡" if ssim > 0.3 else "🔴")
                self._notify_telegram(
                    f"✅ Ciclo {cycle}/{max_cycles} completado\n"
                    f"*{objective['objective'][:60]}*\n\n"
                    f"📊 Métricas:\n"
                    f"  {ssim_bar} SSIM: {ssim:.4f}\n"
                    f"  ⏱ Render: {metrics.get('cpu_seconds', 0):.1f}s\n"
                    f"  💾 RAM: {metrics.get('memory_peak_mb', 0):.0f}MB\n"
                    f"  📝 LOC: {metrics.get('lines_of_code', 0)}\n"
                    f"  🚀 C++ speedup: {metrics.get('speedup_vs_python') or 'N/A'}"
                )
                composite = Path(f"/root/{project}/output/composite_final.png")
                if composite.exists():
                    ssim_bar2 = "🟢" if ssim > 0.6 else ("🟡" if ssim > 0.3 else "🔴")
                    self._send_image_telegram(
                        str(composite),
                        f"*Compositor\\_final* — Ciclo {cycle}/{max_cycles}\n"
                        f"{ssim_bar2} SSIM: {ssim:.4f}\n"
                        f"⏱ {metrics.get('cpu_seconds', 0):.1f}s | "
                        f"💾 {metrics.get('memory_peak_mb', 0):.0f}MB | "
                        f"📝 {metrics.get('lines_of_code', 0)} LOC\n"
                        f"_Generado con matematica pura_",
                    )
            else:
                self._notify_telegram(
                    f"⚠️ Ciclo {cycle}/{max_cycles} falló\n"
                    f"*{objective['objective'][:60]}*\n"
                    f"Error: {str(result.get('errors_found', ''))[:100]}"
                )

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
                r for r in context.get("recent_rejections", []) if r.get("decision") == "ESCALATE"
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
                    f"✅ *Loop completado* — `{project}`\n" f"{cycle} ciclo(s) | objetivo cumplido"
                )
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS OrchestratorLoop")
    parser.add_argument("--project", required=True, help="Nombre del proyecto")
    parser.add_argument(
        "--cycles",
        type=int,
        default=MAX_CYCLES,
        help=f"Máximo de ciclos (default: {MAX_CYCLES})",
    )
    parser.add_argument(
        "--tier",
        choices=["tier1", "tier2", "tier3", "haiku"],
        default="tier3",
        help=(
            "Modelo a usar: tier1=Ollama local, tier2=OpenRouter free, "
            "tier3=Claude Sonnet (default), haiku=Claude Haiku 4.5"
        ),
    )
    args = parser.parse_args()

    loop = OrchestratorLoop()
    loop.run(args.project, args.cycles, args.tier)
