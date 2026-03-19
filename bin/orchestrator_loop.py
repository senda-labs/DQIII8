#!/usr/bin/env python3
"""
OrchestratorLoop — DQIII8 autonomous project management.

Cycle: analyze → plan → build_prompt → execute → capture → store → repeat
Run: python3 bin/orchestrator_loop.py --project my-project
Autonomous mode: JARVIS_MODE=autonomous python3 bin/orchestrator_loop.py ...
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
MAX_RETRIES = 3  # Per objective — fails 3 times → BLOCKED
MAX_CYCLES = 10  # Per loop session
GROQ_MODEL = "llama-3.3-70b-versatile"


class OrchestratorLoop:

    def check_rejections(self) -> list[dict]:
        """
        FIX D: Reads permission_rejection.json inbox and empties it after reading.
        Allows the loop to detect and react to recent DENYs/ESCALATEs
        without waiting for the next full cycle.
        """
        reject_path = JARVIS_ROOT / "tasks" / "permission_rejection.json"
        if not reject_path.exists():
            return []
        try:
            data = json.loads(reject_path.read_text(encoding="utf-8"))
            # Empty the inbox after reading (consume the message)
            reject_path.write_text("[]", encoding="utf-8")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def analyze(self, project: str) -> dict:
        """Reads DB + MD + rejection inbox to build complete context."""
        project_md = JARVIS_ROOT / f"projects/{project}.md"
        lessons_md = JARVIS_ROOT / "tasks/lessons.md"

        context: dict = {
            "project": project,
            "timestamp": datetime.now().isoformat(),
        }

        if project_md.exists():
            context["project_state"] = project_md.read_text(encoding="utf-8")

        # Relevant lessons — only for the current project
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

        # Pending/failed objectives from the DB
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

        # If pending in DB → signal for plan() to use the first one directly
        if context["pending_objectives"]:
            context["use_seeded_objective"] = True
            context["next_seeded_objective"] = context["pending_objectives"][0]

        # PermissionAnalyzer rejection inbox
        context["recent_rejections"] = self.check_rejections()

        return context

    def _get_recent_cycles(self, project: str, limit: int = 3) -> list[dict]:
        """Gets the last N completed cycles to avoid repeating objectives."""
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
        Determines the next objective.
        Priority: (1) pre-seeded objectives in DB → (2) Groq → (3) fallback.
        """
        # Load recent cycles for build_prompt (always, independent of path)
        context["recent_cycles"] = self._get_recent_cycles(context["project"])

        # Fast-path: use pending objective from DB directly
        if context.get("use_seeded_objective"):
            obj = context["next_seeded_objective"]
            print(f"  [plan] Using pre-seeded objective [{obj['id']}]")
            return {
                "objective": obj["text"],
                "success_criteria": obj.get("criteria", ""),
                "priority": "high",
                "objective_id": obj["id"],  # ID existente → no crear nuevo en BD
            }

        return self._plan_with_groq(context)

    def _plan_with_groq(self, context: dict) -> dict:
        """
        Calls Groq to generate a new objective when there are no pending items in DB.
        Enriches the prompt with existing files and real project metrics.
        """
        import requests

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if not groq_key:
            state = context.get("project_state", "")
            for line in state.splitlines():
                if "próximo paso" in line.lower() or "next step" in line.lower():
                    return {
                        "objective": line.strip("# -"),
                        "success_criteria": "Verified with tests and no errors",
                        "priority": "high",
                    }
            return {
                "objective": "Review project status and continue",
                "success_criteria": "No CI errors",
                "priority": "medium",
            }

        # Read real project state (existing files)
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

        # Read metrics from the last completed cycle
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
                    f"  - {r[0]}: {r[1]} lines, {r[2]:.1f}s, "
                    f"{r[3]:.0f}MB RAM, SSIM={r[4]}, tests={'✅' if r[5] else '❌'}"
                    for r in last_metrics
                ]
            )
            if last_metrics
            else "No previous metrics"
        )

        ref_analysis = self._analyze_reference_image()
        recent = context.get("recent_cycles", [])

        prompt = f"""You are the technical lead for project {context['project']}.

EXISTING FILES IN THE PROJECT:
{chr(10).join(existing_files) if existing_files else 'Empty directory'}

METRICS FROM THE LAST COMPLETED RENDERERS:
{metrics_text}

RECENTLY COMPLETED OBJECTIVES:
{json.dumps(self._get_recent_cycles(context['project']), ensure_ascii=False, indent=2)}

PROJECT STATE:
{context.get('project_state', '')[:1500]}

REFERENCE IMAGE ANALYSIS:
{ref_analysis}
RULES FOR PROJECT math-image-generator:
- Stack: Python + C++ (ctypes). No AI, no image APIs.
- Max RAM: 500MB at any point
- Targets: render <30s, C++ speedup >=5x, SSIM >0.5 (ambitious goal)
- Code: <80 lines per Python renderer, <120 lines C++

Based on the existing files and metrics, determine
the NEXT most impactful objective to improve the system.

Priorities (in order):
1. If any renderer is missing (julia, perlin, compositor) → create it
2. If any SSIM < 0.3 → improve the colormap for that renderer
3. If any render > 30s → optimize with C++
4. If all tests pass and SSIM > 0.3 → try to improve SSIM
5. If SSIM > 0.5 on all → create a more complex new renderer

Respond ONLY in JSON:
{{"objective": "specific description in 2-3 sentences with target metrics",
  "success_criteria": "how to verify it is done",
  "priority": "high|medium|low",
  "renderer": "mandelbrot|julia|perlin|cpp|compositor|new"}}"""

        if recent:
            prompt += "\n\nRECENT CYCLES (DO NOT repeat these objectives):\n"
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
        Evaluates the cycle result: calculates SSIM of the generated PNG and creates
        an improvement objective automatically if the score is insufficient.
        Also sends generated images via Telegram.
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

        # Send generated images via Telegram (with or without SSIM)
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
                    f"Cycle {cycle_num} | Tier: {model_tier}"
                    f"{ssim_info}\n"
                    f"1080x1920 | Pure mathematics"
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
                    f"Improve SSIM of renderer '{renderer}' from {score:.3f} to >0.4. "
                    f"The current PNG does not resemble the reference image closely enough. "
                    f"Adjust the colormap to use more cool blues "
                    f"(#4060a0, #6080c0) and increase contrast to ~255/255."
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
                        "SSIM > 0.4 vs reference image",
                        "tier3",
                    ),
                )
                print(f"  🎯 Auto-objective created: improve SSIM {renderer} ({score:.3f} → >0.4)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  [post-eval] Error: {e}")

    def _analyze_reference_image(self) -> str:
        """
        Analyzes the reference image and returns a technical description
        to include in the mathematical generator prompt.
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
REFERENCE IMAGE — Technical analysis:
  Dominant palette: {palette_str}
  Color temperature: {data['color_temperature']}
  Vertical distribution (brightness):
    - Top third:    {data['distribution']['top_third_brightness']:.0f}/255
    - Middle third: {data['distribution']['middle_third_brightness']:.0f}/255
    - Bottom third: {data['distribution']['bottom_third_brightness']:.0f}/255
  Textural complexity:
    - Top:    {data['texture']['top_complexity']:.1f} (higher = more detail)
    - Middle: {data['texture']['middle_complexity']:.1f}
    - Bottom: {data['texture']['bottom_complexity']:.1f}
  Tonal contrast: {data['tonal']['contrast']:.0f}/255

USE THIS DATA to parameterize the mathematical generator:
- Adjust colormaps to use the dominant palette
- Distribute vertical complexity according to texture values
- Output contrast should approximate {data['tonal']['contrast']:.0f}
"""
        except Exception:
            return ""

    def build_prompt(self, objective: dict, context: dict) -> str:
        """Builds the prompt for Claude Code with structured format."""
        lessons_text = "\n".join(context.get("lessons", []))
        ref_analysis = self._analyze_reference_image()
        return f"""=== DQIII8 ORCHESTRATOR — CURRENT OBJECTIVE ===

PROJECT: {context['project']}
OBJECTIVE: {objective['objective']}
SUCCESS CRITERIA: {objective['success_criteria']}
PRIORITY: {objective.get('priority', 'high')}

PROJECT STATE:
{context.get('project_state', '')[:1500]}

LESSONS TO KEEP IN MIND (past errors):
{lessons_text}
{ref_analysis}
INSTRUCTIONS:
1. Execute the objective described above
2. Verify that the success criteria is met
3. If you encounter a blocker requiring a human decision, stop and explain it
4. When done, write exactly this block (with real data):

---FINAL_REPORT---
{{
  "success": true|false,
  "files_modified": ["list of files"],
  "errors_found": ["errors found"],
  "fixes_applied": ["fixes applied"],
  "lessons": ["new lessons in format [KEYWORD] cause → solution"],
  "blocker": null | "description of blocker if any",
  "next_step": "recommended next step",
  "code_metrics": {{
    "renderer": "mandelbrot|julia|perlin|cpp|compositor",
    "lines_of_code": <integer>,
    "lines_functional": <lines without blanks or comments>,
    "cpu_seconds": <time measured with time.perf_counter>,
    "memory_peak_mb": <peak measured with tracemalloc>,
    "uses_vectorization": true|false,
    "uses_numpy_only": true|false,
    "passes_tests": true|false,
    "ssim_score": <score from ssim_scorer or null>,
    "output_variance": <np.var() of the pixel array>,
    "speedup_vs_python": <C++/Python ratio or null>,
    "compiled_ok": true|false|null
  }}
}}
---END_REPORT---"""

    def execute(self, prompt: str, project: str, model_tier: str = "tier3") -> str:
        """
        Launches the model corresponding to the tier.
        tier1  → Ollama qwen2.5-coder:7b (local, free)
        tier2  → OpenRouter free (via openrouter_wrapper.py)
        tier3  → Claude Code headless (default, Sonnet 4.6)
        haiku  → Claude Haiku 4.5 via CLI OAuth (--model claude-haiku-4-5-20251001)
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
        Runs Claude Code as the jarvis user (non-root).
        Permissions are managed by PermissionAnalyzer via hooks.
        No --dangerously-skip-permissions — the analyzer decides.
        """
        import tempfile

        project_path = Path(f"/root/{project}")
        if not project_path.exists():
            project_path = JARVIS_ROOT

        # Write prompt to temporary file readable by jarvis
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, dir="/tmp", encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name
        os.chmod(prompt_file, 0o644)

        try:
            # su - creates a new login shell that resets the environment.
            # JARVIS_MODE and JARVIS_ROOT must be exported explicitly
            # inside the -c command so that pre_tool_use.py can see them.
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
        """Tier 1: 2-step — Qwen generates the plan, Claude Code executes it."""
        import requests

        model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

        # Step 1: Qwen generates plan/code (no tools)
        plan = ""
        plan_quality = "unavailable"
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model,
                    "prompt": (
                        "You are an expert in Python and C++. Generate a detailed plan "
                        "and complete code for the following task. "
                        "Do not use tools. Only generate text.\n\n"
                        f"{prompt}\n\n"
                        "Respond with:\n1. Step-by-step plan\n2. Complete code ready to execute"
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
            print(f"  [tier1] Ollama unavailable: {e} → fallback tier2")
            return self._execute_openrouter(prompt, project)

        # Step 2: Claude Code executes the plan with real tools
        combined_prompt = (
            f"{prompt}\n\n"
            f"--- PLAN GENERATED BY QWEN2.5-CODER ---\n"
            f"{plan}\n"
            f"--- END OF PLAN ---\n\n"
            "Execute the above plan using the available tools. "
            "When done, include in your response:\n"
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
            return "[OpenRouter] wrapper not found at bin/openrouter_wrapper.py"
        result = subprocess.run(
            ["python3", str(wrapper), "--agent", "default", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ},
        )
        return result.stdout + result.stderr

    def _execute_haiku(self, prompt: str, project: str) -> str:
        """Haiku 4.5: 2-step — Haiku generates the plan via CLI OAuth, Claude Code executes it."""
        import tempfile

        # Step 1: Haiku generates plan via `claude --model` (OAuth, no tools)
        plan = ""
        plan_quality = "error"
        planning_prompt = (
            "Generate a detailed plan and complete code for the following task. "
            "Be specific and concrete. Do not use tools, only generate text.\n\n"
            f"{prompt}\n\n"
            "Respond with:\n1. Step-by-step plan\n2. Complete code ready to execute"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, dir="/tmp", encoding="utf-8"
        ) as f:
            f.write(planning_prompt)
            plan_file = f.name
        os.chmod(plan_file, 0o644)

        try:
            result = subprocess.run(
                [
                    "su",
                    "-",
                    "jarvis",
                    "-c",
                    f"export JARVIS_MODE=autonomous; "
                    f"export JARVIS_ROOT={JARVIS_ROOT}; "
                    f'claude -p "$(cat {plan_file})" '
                    f"--model claude-haiku-4-5-20251001 "
                    f"--output-format text 2>&1",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            plan = result.stdout.strip()
            if len(plan) > 500:
                plan_quality = "good"
            elif len(plan) > 100:
                plan_quality = "partial"
            else:
                plan_quality = "poor"
        except Exception as e:
            print(f"  [haiku] CLI error: {e} → fallback tier3")
            return self._execute_claude(prompt, project)
        finally:
            try:
                os.unlink(plan_file)
            except Exception:
                pass

        if not plan or plan_quality == "error":
            print("  [haiku] No plan generated → fallback tier3")
            return self._execute_claude(prompt, project)

        # Step 2: Claude Code executes the plan with real tools
        combined_prompt = (
            f"{prompt}\n\n"
            f"--- PLAN GENERATED BY CLAUDE HAIKU ---\n"
            f"{plan}\n"
            f"--- END OF PLAN ---\n\n"
            "Execute the above plan using the available tools. "
            "When done, include in your response:\n"
            "---FINAL_REPORT---\n"
            '{"success": true, "files_modified": [], '
            '"errors_found": [], "fixes_applied": [], '
            '"lessons": [], "blocker": null, "next_step": "", '
            f'"haiku_plan_quality": "{plan_quality}"}}\n'
            "---END_REPORT---"
        )
        return self._execute_claude(combined_prompt, project)

    def capture(self, output: str) -> dict:
        """Extracts the FINAL_REPORT from Claude Code output."""

        def _normalize(report: dict) -> dict:
            """Normalizes tier-planner and SSIM fields."""
            if "planner_quality" not in report:
                report["planner_quality"] = report.get("qwen_plan_quality") or report.get(
                    "haiku_plan_quality"
                )
            report.setdefault("ssim_score", None)
            report.setdefault("ssim_quality", None)
            return report

        # Attempt 1: strict format with markers
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

        # Attempt 2: find any JSON with "success" in the output
        for m in re.findall(r"\{[^{}]*\"success\"[^{}]*\}", output, re.DOTALL):
            try:
                data = json.loads(m)
                if "success" in data:
                    return _normalize(data)
            except json.JSONDecodeError:
                continue

        # Attempt 3: infer success from signals in the output content
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
        """Saves result to DB and updates lessons.md."""
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

        # Save benchmark metrics if the agent reported them
        metrics = result.get("code_metrics")
        if metrics and isinstance(metrics, dict) and metrics.get("renderer"):
            megapixels = 1080 * 1920 / 1_000_000  # 2.0736 mpx (standard resolution)
            cpu_s = metrics.get("cpu_seconds")

            # Count permission decisions in the last hour (proxy for current cycle)
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

        # Add new lessons to lessons.md
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
        """Inserts a new objective in the DB, including model_tier."""
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
        """Sends an image to the Telegram chat via Bot API (sendPhoto multipart)."""
        import requests

        token = (os.getenv("DQIII8_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN", "")).strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not token or not chat_id:
            return

        img = Path(image_path)
        if not img.exists():
            print(f"  [img] Not found: {image_path}")
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
                print(f"  [img] Sent: {img.name}")
            else:
                print(f"  [img] Error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  [img] Error: {e}")

    def _notify_telegram(self, message: str) -> None:
        """
        Sends a Telegram bot notification when the loop pauses
        due to ESCALATE or human blocker, or when it completes successfully.
        Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
        """
        import requests

        token = (os.getenv("DQIII8_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("JARVIS_BOT_TOKEN", "")).strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"🤖 *DQIII8 OrchestratorLoop*\n\n{message}",
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        except Exception:
            pass

    def _sync_todo_md(self, project: str) -> None:
        """
        Regenerates tasks/todo.md from the objectives table in the DB.
        The OrchestratorLoop is the ONLY writer of tasks/todo.md.
        Other agents write results ONLY to tasks/results/[agent]-[ts].md.
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
                f"_Generated by OrchestratorLoop — "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}_",
                "_Only OrchestratorLoop writes here. " "Other agents → tasks/results/_",
                "",
            ]
            for status_group in ("running", "pending", "failed", "blocked", "completed"):
                group_rows = [r for r in rows if r[2] == status_group]
                if not group_rows:
                    continue
                lines.append(f"## {STATUS_ICON.get(status_group, '')} {status_group.upper()}")
                for r in group_rows:
                    obj_id, text, status, retries, criteria, _ = r
                    retry_str = f" (attempt {retries}/{MAX_RETRIES})" if retries > 0 else ""
                    lines.append(f"- [{obj_id}]{retry_str} {text}")
                    if criteria:
                        lines.append(f"  → Criterion: {criteria}")
                lines.append("")

            todo_path = JARVIS_ROOT / "tasks" / "todo.md"
            todo_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"  [todo.md] sync error: {e}")

    def _print_effectiveness(self, project: str) -> None:
        """Prints historical project metrics from loop_effectiveness."""
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
                    f"Success rate: {row[4]}%"
                )
        except Exception:
            pass

    def _warmup_ollama(self) -> bool:
        """
        Sends a minimal prompt to Ollama to load the model
        before the loop starts. Avoids timeout on the first cycle.
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
        """Main orchestrator loop."""
        print(f"\n[ORCHESTRATOR] Starting loop — project: {project} | tier: {model_tier}")
        self._print_effectiveness(project)

        if model_tier == "tier1":
            print("  [Tier1] Warming up Ollama (loading model ~60-120s)...")
            if self._warmup_ollama():
                print("  [Tier1] Ollama ready")
            else:
                print("  [Tier1] Ollama not responding — continuing with fallback")

        for cycle in range(1, max_cycles + 1):
            print(f"\n── Cycle {cycle}/{max_cycles} ──────────────────")

            # Sync todo.md from DB (sole writer)
            self._sync_todo_md(project)

            # ANALYZE
            context = self.analyze(project)

            # PLAN
            objective = self.plan(context)
            print(f"  Objective: {objective['objective'][:80]}...")

            # Crear o reusar registro en BD
            seeded_id = objective.get("objective_id")
            if seeded_id:
                # Pre-seeded objective: update to 'running', do not create new
                obj_id = seeded_id
                conn = sqlite3.connect(str(DB_PATH), timeout=10)
                conn.execute("UPDATE objectives SET status='running' WHERE id=?", (obj_id,))
                conn.commit()
                conn.close()
                print(f"  [run] Resuming objective [{obj_id}] (pre-seeded)")
            else:
                obj_id = self.create_objective(
                    project,
                    objective["objective"],
                    objective.get("success_criteria", ""),
                    model_tier,
                )

            # Verify max_retries
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            retries = conn.execute(
                "SELECT retry_count FROM objectives WHERE id=?", (obj_id,)
            ).fetchone()
            conn.close()
            if retries and retries[0] >= MAX_RETRIES:
                print(f"  ⛔ Objective blocked after {MAX_RETRIES} attempts")
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
            print("  Running Claude Code (headless)...")
            output = self.execute(prompt, project, model_tier)

            # CAPTURE
            result = self.capture(output)

            # Post-tests to verify nothing was broken
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
                result["errors_found"].append("Tests broke after execution")

            # STORE
            self.store(obj_id, project, objective, result)
            self._post_cycle_evaluation(
                project, result, obj_id, cycle_num=cycle, model_tier=model_tier
            )

            status_icon = "✅" if result["success"] else ("⛔" if result.get("blocker") else "🔄")
            print(f"  {status_icon} {result.get('next_step', '')[:60]}")

            # Progress notification per cycle
            if result.get("success"):
                metrics = result.get("code_metrics") or {}
                ssim = metrics.get("ssim_score") or 0
                ssim_bar = "🟢" if ssim > 0.5 else ("🟡" if ssim > 0.3 else "🔴")
                self._notify_telegram(
                    f"✅ Cycle {cycle}/{max_cycles} completed\n"
                    f"*{objective['objective'][:60]}*\n\n"
                    f"📊 Metrics:\n"
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
                        f"*Compositor\\_final* — Cycle {cycle}/{max_cycles}\n"
                        f"{ssim_bar2} SSIM: {ssim:.4f}\n"
                        f"⏱ {metrics.get('cpu_seconds', 0):.1f}s | "
                        f"💾 {metrics.get('memory_peak_mb', 0):.0f}MB | "
                        f"📝 {metrics.get('lines_of_code', 0)} LOC\n"
                        f"_Generated with pure mathematics_",
                    )
            else:
                self._notify_telegram(
                    f"⚠️ Cycle {cycle}/{max_cycles} failed\n"
                    f"*{objective['objective'][:60]}*\n"
                    f"Error: {str(result.get('errors_found', ''))[:100]}"
                )

            # Stop if there is a human blocker (notify)
            if result.get("blocker"):
                print(f"\n⚠️  HUMAN BLOCKER: {result['blocker']}")
                print("  Loop stopping. Resolve the blocker and relaunch.")
                self._notify_telegram(
                    f"🛑 *Human blocker* in `{project}`\n"
                    f"*Cycle {cycle}:* {result.get('blocker', '')[:200]}\n"
                    f"*Next step:* {result.get('next_step', '')[:100]}"
                )
                break

            # Stop if there are ESCALATEs in the rejection inbox
            escalates = [
                r for r in context.get("recent_rejections", []) if r.get("decision") == "ESCALATE"
            ]
            if escalates:
                e = escalates[0]
                print(f"\n🚨 ESCALATE detected — loop paused.")
                self._notify_telegram(
                    f"⚠️ *ESCALATE* en proyecto `{project}`\n"
                    f"Ciclo {cycle}/{max_cycles}\n\n"
                    f"*Reason:* {e.get('reason', '')[:150]}\n"
                    f"*Fix sugerido:* {e.get('suggested_fix', 'N/A')[:100]}\n\n"
                    f"Resuelve y relanza:\n`j --loop {project}`"
                )
                break

            # Stop if success and no more pending (notify)
            pending = context.get("pending_objectives", [])
            if result["success"] and not pending:
                print(f"\n✅ Project {project} up to date. Loop completed.")
                self._notify_telegram(
                    f"✅ *Loop completed* — `{project}`\n" f"{cycle} cycle(s) | objective met"
                )
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DQIII8 OrchestratorLoop")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument(
        "--cycles",
        type=int,
        default=MAX_CYCLES,
        help=f"Maximum cycles (default: {MAX_CYCLES})",
    )
    parser.add_argument(
        "--tier",
        choices=["tier1", "tier2", "tier3", "haiku"],
        default="tier3",
        help=(
            "Model to use: tier1=Ollama local, tier2=OpenRouter free, "
            "tier3=Claude Sonnet (default), haiku=Claude Haiku 4.5"
        ),
    )
    args = parser.parse_args()

    loop = OrchestratorLoop()
    loop.run(args.project, args.cycles, args.tier)
