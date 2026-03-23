"""
JAL Run v3 -- full cycle orchestrator
"""

import os
import subprocess
import sys
from pathlib import Path

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))

sys.path.insert(0, str(JARVIS / "bin"))
from db import get_db
from jal_common import load_env


def get_active_plan() -> tuple:
    with get_db() as conn:
        row = conn.execute("""
            SELECT objective_id, current_attempt FROM jal_objectives
            WHERE status='active' ORDER BY started_at DESC LIMIT 1
        """).fetchone()
        if not row:
            return None, None
        steps = conn.execute(
            """
            SELECT step_number, description, description
            FROM jal_steps
            WHERE objective_id=? AND attempt=? AND status='pending'
            ORDER BY step_number
        """,
            (row[0], row[1]),
        ).fetchall()
    return row[0], steps or []


def mark_step(
    obj_id: str,
    attempt: int,
    step_n: int,
    status: str,
    result: str = "",
    error: str = "",
):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE jal_steps SET status=?, result_summary=?,
                error_raw=?, completed_at=datetime('now')
            WHERE objective_id=? AND attempt=? AND step_number=?
        """,
            (status, result[:500], error[:500], obj_id, attempt, step_n),
        )


def build_executor_prompt(obj_id: str, attempt: int, steps: list) -> str:
    """
    Builds the prompt for Claude Code.
    Structured to minimize non-deterministic behavior:
    - Explicit and verifiable instructions
    - DB registration mandatory per step
    - No ambiguous decisions
    """
    steps_text = "\n".join(
        f"STEP {s[0]}: {s[1]}\n"
        f"  INSTRUCTION: {s[2] or s[1]}\n"
        f"  REGISTER: UPDATE jal_steps SET status='completed',"
        f" result_summary='[result]' WHERE objective_id='{obj_id}'"
        f" AND attempt={attempt} AND step_number={s[0]};"
        for s in steps
    )

    return f"""Execute the following steps in order for objective {obj_id}.

STRICT RULES:
1. Execute each step and register the result in DB BEFORE continuing
2. If a step fails, register status='failed' and error_raw='[message]'
3. DO NOT skip DB registration for any step
4. DO NOT make decisions not in the instructions
5. When all steps are done, run:
   python3 $(dirname "$0")/jal_critic.py

STEPS:
{steps_text}

DB: sqlite3 /root/jarvis/database/dqiii8.db "[SQL]"

Start with Step 1."""


def main():
    # Activar objetivo desde argumento si se pasa
    if len(sys.argv) > 1:
        obj_file = Path(sys.argv[1])
        if obj_file.exists() and obj_file.suffix == ".md":
            target = JARVIS / "objectives" / "active" / obj_file.name
            obj_file.rename(target)
            print(f"[JAL] Activado: {target.name}")

    obj_files = list((JARVIS / "objectives" / "active").glob("*.md"))
    if not obj_files:
        print("[JAL] No objectives in objectives/active/")
        print("[JAL] Usage: python3 bin/jal_run.py objectives/queue/OBJ-001.md")
        sys.exit(0)

    print("[JAL] 1/3 Planning...")
    subprocess.run(
        ["python3", str(JARVIS / "bin" / "jal_planner.py")],
        cwd=str(JARVIS),
        check=True,
    )

    obj_id, steps = get_active_plan()
    if not obj_id or not steps:
        print("[JAL] No pending steps after planning")
        sys.exit(1)

    print(f"[JAL] 2/3 Executing {len(steps)} steps with Claude Code...")
    executor_prompt = build_executor_prompt(obj_id, 1, steps)

    prompt_file = JARVIS / "tasks" / "results" / f"jal_exec_{obj_id}.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(executor_prompt, encoding="utf-8")

    load_env()
    env = dict(os.environ)

    subprocess.run(
        [
            "python3",
            str(JARVIS / "bin" / "openrouter_wrapper.py"),
            "--model",
            "qwen/qwen3-coder:free",
        ],
        input=executor_prompt,
        text=True,
        cwd=str(JARVIS),
        env=env,
    )

    print("[JAL] 3/3 Evaluando con Critic...")
    subprocess.run(
        ["python3", str(JARVIS / "bin" / "jal_critic.py")],
        cwd=str(JARVIS),
    )

    print("[JAL] Ciclo completado.")


if __name__ == "__main__":
    main()
