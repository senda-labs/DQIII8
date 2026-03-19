"""
gemini_export.py — Exporta contexto del pipeline para auditoría Gemini Pro.
Uso: python3 gemini_export.py [módulo] [--metric X] [--question "..."]
Genera un .md estructurado listo para pegar en Gemini Pro.
Módulos: full | script | audio | video | subtitles
"""

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
PROJ = Path(os.environ.get("CONTENT_PROJECT_ROOT", str(JARVIS)))
OUT_DIR = JARVIS / "tasks" / "gemini_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def export_last_errors(n: int = 5) -> str:
    conn = sqlite3.connect(DB)
    errors = conn.execute(
        """
        SELECT created_at, objective_id, error_type,
               error_message, file, line, resolved
        FROM loop_errors
        ORDER BY id DESC LIMIT ?
        """,
        (n,),
    ).fetchall()
    conn.close()
    if not errors:
        return "Sin errores recientes en loop_errors.\n"
    lines = ["## Últimos errores del pipeline\n"]
    for e in errors:
        lines.append(
            f"**[{e[0]}]** `{e[2]}` en objetivo `{e[1]}`\n"
            f"```\n{e[3]}\n```\n"
            f"Archivo: `{e[4]}:{e[5]}` | Resuelto: {'✅' if e[6] else '❌'}\n"
        )
    return "\n".join(lines)


def export_code_snippet(file_path: str, func_name: str = None) -> str:
    # FIX 2: archivos completos hasta 8000 chars, funciones sin límite
    p = Path(file_path)
    if not p.exists():
        return f"Archivo no encontrado: {file_path}\n"
    content = p.read_text(encoding="utf-8")
    if func_name:
        lines = content.split("\n")
        start = next(
            (
                i
                for i, l in enumerate(lines)
                if f"def {func_name}" in l or f"class {func_name}" in l
            ),
            None,
        )
        if start is not None:
            snippet = []
            indent = len(lines[start]) - len(lines[start].lstrip())
            for l in lines[start:]:
                stripped = l.lstrip()
                if (
                    stripped
                    and len(l) - len(stripped) <= indent
                    and snippet
                    and (stripped.startswith("def ") or stripped.startswith("class "))
                ):
                    break
                snippet.append(l)
            return f"```python\n# {p.name} — def {func_name}\n" f"{''.join(snippet)}\n```\n"
    return f"```python\n# {p.name}\n{content[:8000]}\n```\n"


def export_pipeline_metrics() -> str:
    conn = sqlite3.connect(DB)
    videos = conn.execute("""
        SELECT topic, mode, language, duration_s,
               file_size_mb, renderer_used, pipeline_ms,
               telegram_sent, approved
        FROM video_outputs ORDER BY id DESC LIMIT 5
        """).fetchall()
    objectives = conn.execute("""
        SELECT objective_id, description, status, result
        FROM loop_objectives ORDER BY id DESC LIMIT 10
        """).fetchall()
    conn.close()

    lines = ["## Métricas del pipeline\n", "### Últimos vídeos\n"]
    for v in videos:
        approved = "✅" if v[8] == 1 else ("❌" if v[8] == 0 else "⏳ pendiente")
        lines.append(
            f"- **{v[0][:60]}**\n"
            f"  Modo: `{v[1]}` | Lang: `{v[2]}` | {v[3]}s | "
            f"{v[5]} | {v[6] // 1000 if v[6] else '?'}s render | "
            f"Aprobado: {approved}\n"
        )
    lines.append("\n### Objetivos del loop\n")
    for o in objectives:
        icon = "✅" if o[2] == "done" else ("❌" if o[2] == "failed" else "⏳")
        lines.append(f"{icon} **[{o[0]}]** {o[1][:80]}\n")
        if o[3]:
            lines.append(f"   → {o[3][:100]}\n")
    return "\n".join(lines)


def generate_gemini_report(
    module: str = "full",
    include_errors: bool = True,
    code_files: list = None,
    question: str = None,  # FIX 1: parámetro añadido
    metric: str = "viralidad",  # FIX 1: parámetro añadido
) -> str:
    """
    Genera reporte estructurado para Gemini Pro.
    module:  'full' | 'audio' | 'video' | 'script' | 'subtitles'
    metric:  'viralidad' | 'rendimiento' | 'arquitectura'
    question: pregunta específica para el auditor (opcional)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    sections = []

    # Header — FIX 1: usa metric y question
    sections.append(
        f"# DQIII8 — Reporte para Auditoría Gemini Pro\n"
        f"**Timestamp:** {timestamp}\n"
        f"**Módulo:** {module}\n"
        f"**Métrica de éxito:** {metric}\n"
        f"**Pregunta específica:** {question or 'Auditoría general'}\n\n---\n"
    )

    # Stack técnico
    sections.append(
        "## Stack técnico\n"
        "- **VPS:** Ubuntu 24.04 | 8GB RAM | 4 CPUs | 100GB NVMe\n"
        "- **Pipeline:** Python + MoviePy + ElevenLabs + FFmpeg\n"
        "- **Modelos:** Groq (LLaMA 3.3 70b) + ElevenLabs TTS + Claude API\n"
        "- **BD:** SQLite jarvis_metrics.db\n"
        f"- **Repo:** {PROJ}/\n\n---\n"
    )

    sections.append(export_pipeline_metrics())
    sections.append("\n---\n")

    if include_errors:
        sections.append(export_last_errors())
        sections.append("\n---\n")

    MODULE_FILES = {
        "script": ["backend/services/script_service.py"],
        "audio": [
            "backend/services/sound_design.py",
            "scripts/pipeline/audio.py",
        ],
        "video": ["scripts/pipeline/renderer.py"],
        "subtitles": ["backend/services/netflix_subtitle_generator.py"],
        "full": [
            "backend/services/script_service.py",
            "scripts/pipeline/renderer.py",
            "backend/services/netflix_subtitle_generator.py",
        ],
    }
    files_to_export = code_files or MODULE_FILES.get(module, [])

    sections.append("## Código relevante\n")
    for f in files_to_export:
        sections.append(f"### `{f}`\n")
        sections.append(export_code_snippet(str(PROJ / f)))

    # Footer — FIX 1: usa question y metric
    sections.append(
        f"---\n## Pregunta para el auditor\n\n"
        f"Estamos optimizando para: **{metric}**\n\n"
        + (
            question
            or (
                "Revisa el pipeline completo e identifica:\n"
                "1. Fallos potenciales de FFmpeg/OpenCV/NumPy antes de ejecutar\n"
                "2. Cuellos de botella de rendimiento\n"
                "3. Gaps de calidad para alcanzar estándar viral (1M views)\n"
                "Sé específico con números de línea y funciones concretas."
            )
        )
        + "\n"
    )

    report = "\n".join(sections)
    out_path = OUT_DIR / f"gemini_{module}_{timestamp}.md"
    out_path.write_text(report, encoding="utf-8")

    # Formato exacto que el handler de Telegram busca (FIX 3 dependency):
    print(f"✅ Reporte generado: {out_path}")
    print(f"   Tamaño: {len(report)} chars")
    print(f"\nPrimeras 300 chars:")
    print(report[:300])
    return str(out_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera reporte de auditoría para Gemini Pro")
    parser.add_argument(
        "module",
        nargs="?",
        default="full",
        choices=["full", "audio", "video", "script", "subtitles"],
    )
    parser.add_argument(
        "--metric",
        default="viralidad",
        choices=["viralidad", "rendimiento", "arquitectura"],
    )
    parser.add_argument("--question", default=None)
    parser.add_argument("--no-errors", action="store_true", default=False)
    args = parser.parse_args()

    generate_gemini_report(
        module=args.module,
        include_errors=not args.no_errors,
        question=args.question,
        metric=args.metric,
    )
