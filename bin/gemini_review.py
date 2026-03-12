#!/usr/bin/env python3
"""
JARVIS — Gemini Pro Code Reviewer via Aider
Detecta archivos .py no revisados y ejecuta auditoría de eficiencia.
Guarda reporte en database/audit_reports/ y lo registra en BD.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
REPORTS_DIR = JARVIS / "database" / "audit_reports"
AIDER_PROMPT = """\
Eres un revisor de código Python de nivel senior. Analiza el archivo de forma eficiente:

1. **Bugs potenciales**: errores lógicos, condiciones de carrera, excepciones no manejadas.
2. **Eficiencia**: operaciones costosas, consultas N+1, uso innecesario de memoria.
3. **Legibilidad**: nombres confusos, funciones demasiado largas, comentarios obsoletos.
4. **Seguridad**: inyección de comandos, rutas sin sanitizar, credenciales expuestas.

Responde SOLO con JSON válido (sin markdown):
{
  "file": "<nombre>",
  "score": <0.0-1.0>,
  "issues": [{"severity": "high|medium|low", "line": <n|null>, "description": "<texto>"}],
  "recommendations": ["<acción concreta>"]
}
"""


def load_env() -> None:
    env_path = JARVIS / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() and key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()


def get_unreviewed_files() -> list[Path]:
    """Retorna archivos .py modificados desde el último review registrado en BD."""
    reviewed: set[str] = set()

    if DB.exists():
        try:
            conn = sqlite3.connect(str(DB), timeout=5)
            rows = conn.execute(
                "SELECT top_error_keywords FROM audit_reports "
                "WHERE top_error_keywords IS NOT NULL ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
            conn.close()
            for (raw,) in rows:
                if raw and raw.startswith("["):
                    reviewed.update(json.loads(raw))
        except Exception:
            pass

    # Archivos .py modificados en git (staged + unstaged + untracked)
    result = subprocess.run(
        ["git", "-C", str(JARVIS), "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    candidates: list[Path] = []
    for name in result.stdout.splitlines():
        if name.endswith(".py"):
            p = JARVIS / name
            if p.exists() and p.name not in reviewed:
                candidates.append(p)

    # También incluir archivos tracked con cambios unstaged
    result2 = subprocess.run(
        ["git", "-C", str(JARVIS), "diff", "--name-only"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    for name in result2.stdout.splitlines():
        if name.endswith(".py"):
            p = JARVIS / name
            if p.exists() and p not in candidates and p.name not in reviewed:
                candidates.append(p)

    return candidates


def run_review(files: list[Path]) -> list[dict]:
    """Ejecuta aider sobre cada archivo y parsea el JSON de respuesta."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[gemini-review] ERROR: GEMINI_API_KEY no configurada en .env", file=sys.stderr)
        sys.exit(1)

    results = []
    for f in files:
        print(f"[gemini-review] Revisando {f.name} ...", flush=True)
        try:
            proc = subprocess.run(
                [
                    "aider",
                    "--model", "gemini/gemini-2.0-flash",
                    "--no-git",
                    "--yes",
                    "--no-auto-commits",
                    "--message", AIDER_PROMPT,
                    str(f),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "GEMINI_API_KEY": api_key},
            )
            output = proc.stdout + proc.stderr
            # Extraer primer bloque JSON de la salida
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                parsed = json.loads(output[json_start:json_end])
                parsed["file"] = f.name
                results.append(parsed)
            else:
                results.append({
                    "file": f.name,
                    "score": 0.5,
                    "issues": [],
                    "recommendations": ["No se pudo parsear la respuesta de Gemini"],
                    "raw": output[:500],
                })
        except subprocess.TimeoutExpired:
            results.append({
                "file": f.name,
                "score": 0.5,
                "issues": [],
                "recommendations": ["Timeout al revisar el archivo"],
            })
        except Exception as e:
            results.append({
                "file": f.name,
                "score": 0.5,
                "issues": [],
                "recommendations": [f"Error: {e}"],
            })
    return results


def save_report(files: list[Path], results: list[dict]) -> Path:
    """Guarda reporte .md en audit_reports/ y registra en BD."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"gemini_review_{ts}.md"

    avg_score = sum(r.get("score", 0.5) for r in results) / len(results) if results else 0.0

    lines = [
        f"# Gemini Code Review — {now.strftime('%Y-%m-%d %H:%M')}",
        f"\n**Score global:** {avg_score:.2f}  |  **Archivos revisados:** {len(results)}\n",
    ]
    for r in results:
        lines.append(f"\n## {r['file']}  (score: {r.get('score', '?')})")
        issues = r.get("issues", [])
        if issues:
            lines.append("\n### Issues")
            for issue in issues:
                sev = issue.get("severity", "?").upper()
                ln = issue.get("line")
                desc = issue.get("description", "")
                loc = f" (l.{ln})" if ln else ""
                lines.append(f"- [{sev}]{loc} {desc}")
        recs = r.get("recommendations", [])
        if recs:
            lines.append("\n### Recomendaciones")
            for rec in recs:
                lines.append(f"- {rec}")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[gemini-review] Reporte guardado: {report_path}")

    # Registrar en BD
    if DB.exists():
        try:
            conn = sqlite3.connect(str(DB), timeout=5)
            conn.execute(
                """INSERT INTO audit_reports
                   (timestamp, global_success_rate, top_error_keywords,
                    worst_agent, recommendations, overall_score)
                   VALUES (?,?,?,?,?,?)""",
                (
                    now.isoformat(),
                    1.0,
                    json.dumps([f.name for f in files]),
                    None,
                    json.dumps([r.get("recommendations", []) for r in results]),
                    avg_score,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[gemini-review] BD skip: {e}", file=sys.stderr)

    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Pro code reviewer via Aider")
    parser.add_argument("--check-only", action="store_true",
                        help="Solo reportar cuántos archivos hay pendientes (sin revisar)")
    parser.add_argument("files", nargs="*", help="Archivos específicos a revisar")
    args = parser.parse_args()

    if args.check_only:
        files = get_unreviewed_files()
        print(f"{len(files)} archivos pendientes")
        sys.exit(0)

    load_env()

    if args.files:
        files = [Path(f) for f in args.files if Path(f).exists()]
    else:
        files = get_unreviewed_files()

    if not files:
        print("[gemini-review] No hay archivos .py pendientes de revisión.")
        sys.exit(0)

    print(f"[gemini-review] Revisando {len(files)} archivo(s) con Gemini 2.0 Flash...")
    results = run_review(files)
    report = save_report(files, results)

    # Git add + push para que llegue a Obsidian
    try:
        subprocess.run(
            ["git", "-C", str(JARVIS), "add", str(report)],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", str(JARVIS), "commit", "-m",
             f"chore(review): gemini review {datetime.now().strftime('%Y-%m-%d')}"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", str(JARVIS), "push", "origin", "master"],
            capture_output=True, timeout=30
        )
        print("[gemini-review] Reporte pusheado a Obsidian.")
    except Exception as e:
        print(f"[gemini-review] Git push skip: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
