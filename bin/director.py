#!/usr/bin/env python3
"""
DQIII8 — Director Central v3

Intent parsing real: LLM (tier2) + instincts DB + model_router.
Evoluciona el routing estático de keywords de CLAUDE.md a análisis semántico.

Uso:
    python3 bin/director.py "analiza el WACC de Apple y genera un informe ejecutivo"
    python3 bin/director.py --json "backtesting estrategia momentum BTC 3 años"
    python3 bin/director.py --quiet "escribe capítulo 3 de la novela"
    echo "solicitud" | python3 bin/director.py

Importable:
    from director import analyze_intent
    plan = analyze_intent("backtesting momentum BTC")
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
WRAPPER = JARVIS_ROOT / "bin" / "openrouter_wrapper.py"

# ── Tablas de mapping estático ────────────────────────────────────────────────

TASK_AGENT_MAP: dict[str, str] = {
    "código": "python-specialist",
    "análisis": "data-analyst",
    "finanzas": "finance-analyst",
    "escritura": "creative-writer",
    "research": "research-analyst",
    "pipeline": "content-automator",
    "trading": "quant-analyst",
    "mixto": "orchestrator",
}

TASK_TIER_MAP: dict[str, int] = {
    "código": 1,
    "pipeline": 1,
    "research": 2,
    "análisis": 3,
    "finanzas": 3,
    "trading": 3,
    "escritura": 3,
    "mixto": 3,
}

# Keywords → task_type para fast-path (instincts + fallback de keywords)
KEYWORD_TASK_TYPE: dict[str, str] = {
    "backtesting": "trading",
    "backtest": "trading",
    "momentum": "trading",
    "trading": "trading",
    "estrategia": "trading",
    "binance": "trading",
    "sharpe": "trading",
    "garch": "trading",
    "arbitrage": "trading",
    "arbitraje": "trading",
    "wacc": "finanzas",
    "dcf": "finanzas",
    "valoraci": "finanzas",
    "financi": "finanzas",
    "coste de capital": "finanzas",
    "balance": "análisis",
    "novel": "escritura",
    "capítulo": "escritura",
    "narrativ": "escritura",
    "xianxia": "escritura",
    "diálogo": "escritura",
    "scene": "escritura",
    "research": "research",
    "investiga": "research",
    "video": "pipeline",
    "subtítulos": "pipeline",
    "tts": "pipeline",
    "elevenlabs": "pipeline",
    "reels": "pipeline",
    "python": "código",
    "refactor": "código",
    "debug": "código",
    "script": "código",
    "pytest": "código",
    "función": "código",
}

OUTPUT_FORMAT_KEYWORDS: dict[str, str] = {
    "informe": "report",
    "report": "report",
    "email": "email",
    "correo": "email",
    "pdf": "pdf",
    "script": "script",
    "código": "code",
    "code": "code",
    "markdown": "markdown",
}

# ── Prompt LLM ────────────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
Eres un clasificador de tareas para DQIII8, un sistema de agentes de IA.

Analiza la solicitud del usuario y produce ÚNICAMENTE un objeto JSON válido
(sin texto adicional, sin bloques markdown, sin explicaciones).

Esquema JSON requerido:
{{
  "task_type": "<código|análisis|finanzas|escritura|research|pipeline|trading|mixto>",
  "subtasks": [
    {{
      "description": "<descripción concisa de la subtarea>",
      "agent": "<python-specialist|data-analyst|finance-analyst|quant-analyst|creative-writer|research-analyst|content-automator|orchestrator|code-reviewer|git-specialist>",
      "parallel": <true|false>,
      "depends_on": []
    }}
  ],
  "output_format": "<markdown|pdf|email|script|code|report>",
  "complexity": "<simple|medium|complex>",
  "recommended_tier": <1|2|3>
}}

Reglas de asignación de agente y tier:
- task_type=código      → agent=python-specialist,  tier=1
- task_type=pipeline    → agent=content-automator,   tier=1
- task_type=research    → agent=research-analyst,    tier=2
- task_type=análisis    → agent=data-analyst,         tier=3  (pandas, matplotlib, estadística)
- task_type=finanzas    → agent=finance-analyst,      tier=3  (WACC, DCF, valoración, ratios)
- task_type=trading     → agent=quant-analyst,        tier=3  (backtesting, VaR, GARCH)
- task_type=escritura   → agent=creative-writer,      tier=3  (novela, narrativa, diálogo)
- task_type=mixto       → múltiples subtareas con depends_on, tier=3

Para tareas mixtas, divide en subtareas ordenadas. La primera subtarea
con parallel=false y depends_on=[] es el punto de entrada. Las siguientes
pueden ser paralelas si no dependen entre sí.

Solicitud del usuario: "{request}"

Responde ÚNICAMENTE con el JSON. Sin markdown, sin texto adicional."""


# ── Instincts DB ──────────────────────────────────────────────────────────────


def _query_instincts_fast_path(user_request: str) -> tuple[str | None, float]:
    """
    Busca instincts con confidence > 0.7 cuyo keyword aparezca en el request.
    Si hay match → devuelve (task_type, confidence) para saltarse la llamada LLM.
    Devuelve (None, 0.0) si no hay match suficiente.
    """
    if not DB_PATH.exists():
        return None, 0.0

    lowered = user_request.lower()
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        rows = conn.execute(
            "SELECT keyword, confidence FROM instincts "
            "WHERE confidence > 0.7 ORDER BY confidence DESC LIMIT 100"
        ).fetchall()
        conn.close()
    except Exception:
        return None, 0.0

    for keyword, confidence in rows:
        kw_lower = keyword.lower()
        if kw_lower in lowered:
            for prefix, task_type in KEYWORD_TASK_TYPE.items():
                if prefix in kw_lower:
                    return task_type, float(confidence)

    return None, 0.0


# ── model_router integration ──────────────────────────────────────────────────


def _get_model_for_task(task_type: str) -> tuple[str, float]:
    """
    Consulta model_router.get_recommendation() para el task_type dado.
    Devuelve (model_name, score). Fallback a defaults si import falla.
    """
    bin_dir = str(JARVIS_ROOT / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    try:
        from model_router import get_recommendation  # type: ignore

        model, score, _ = get_recommendation(task_type)
        return model, score
    except Exception:
        _defaults: dict[str, str] = {
            "código": "qwen2.5-coder:7b",
            "pipeline": "qwen2.5-coder:7b",
            "research": "llama-3.3-70b-versatile",
            "análisis": "claude-sonnet-4-6",
            "trading": "claude-sonnet-4-6",
            "escritura": "claude-sonnet-4-6",
            "mixto": "claude-sonnet-4-6",
        }
        return _defaults.get(task_type, "claude-sonnet-4-6"), 0.5


# ── LLM call via openrouter_wrapper ──────────────────────────────────────────


def _call_llm_for_intent(user_request: str) -> dict | None:
    """
    Llama al modelo tier2 (research-analyst) via openrouter_wrapper para
    análisis de intent. Captura stdout (respuesta JSON), ignora stderr.
    Devuelve el dict parseado, o None si la llamada o el parse fallan.
    """
    prompt = _ANALYSIS_PROMPT.format(request=user_request.replace('"', '\\"'))
    try:
        result = subprocess.run(
            [sys.executable, str(WRAPPER), "--agent", "research-analyst", prompt],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ},
        )
        raw = result.stdout.strip()
        if not raw:
            return None
        # Extraer primer bloque JSON del output (el LLM puede añadir texto)
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return None
        return json.loads(json_match.group())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


# ── Fallback: keyword-only analysis (sin LLM) ────────────────────────────────


def _keyword_fallback(user_request: str) -> dict:
    """
    Análisis sin LLM: keywords estáticas + tablas de mapping.
    Usado cuando el LLM no está disponible o hay timeout.
    """
    lowered = user_request.lower()

    task_type = "mixto"
    for kw, tt in KEYWORD_TASK_TYPE.items():
        if kw in lowered:
            task_type = tt
            break

    output_format = "markdown"
    for kw, fmt in OUTPUT_FORMAT_KEYWORDS.items():
        if kw in lowered:
            output_format = fmt
            break

    word_count = len(user_request.split())
    if word_count < 8:
        complexity = "simple"
    elif word_count < 20:
        complexity = "medium"
    else:
        complexity = "complex"

    agent = TASK_AGENT_MAP.get(task_type, "orchestrator")
    tier = TASK_TIER_MAP.get(task_type, 3)

    return {
        "task_type": task_type,
        "subtasks": [
            {
                "description": user_request,
                "agent": agent,
                "parallel": False,
                "depends_on": [],
            }
        ],
        "output_format": output_format,
        "complexity": complexity,
        "recommended_tier": tier,
    }


# ── Main function ─────────────────────────────────────────────────────────────


def analyze_intent(user_request: str, verbose: bool = True) -> dict:
    """
    Analiza el intent de una solicitud y devuelve un plan de ejecución.

    Prioridad:
      1. Instincts DB (confidence > 0.7) → fast path sin LLM
      2. LLM via openrouter_wrapper (tier2, gratis)
      3. Keyword fallback estático

    Enriquece cada subtarea con 'recommended_model' y 'model_score'
    via model_router.get_recommendation().

    Args:
        user_request: Solicitud del usuario en lenguaje natural.
        verbose: Si True, imprime estado a stderr.

    Returns:
        dict con keys: task_type, subtasks, output_format, complexity,
        recommended_tier, _source.
    """

    def _log(msg: str) -> None:
        if verbose:
            print(f"[director] {msg}", file=sys.stderr)

    plan: dict | None = None
    source = "llm"

    # Paso 1: Consultar instincts con alta confianza
    instinct_task_type, instinct_confidence = _query_instincts_fast_path(user_request)

    if instinct_task_type:
        _log(
            f"instinct match: {instinct_task_type} "
            f"(conf={instinct_confidence:.2f}) — saltando LLM"
        )
        source = f"instinct:{instinct_confidence:.2f}"
        agent = TASK_AGENT_MAP.get(instinct_task_type, "orchestrator")
        tier = TASK_TIER_MAP.get(instinct_task_type, 3)
        plan = {
            "task_type": instinct_task_type,
            "subtasks": [
                {
                    "description": user_request,
                    "agent": agent,
                    "parallel": False,
                    "depends_on": [],
                }
            ],
            "output_format": "report",
            "complexity": "medium",
            "recommended_tier": tier,
        }
    else:
        # Paso 2: LLM via openrouter_wrapper (tier2, gratis)
        _log("consultando LLM para análisis de intent...")
        plan = _call_llm_for_intent(user_request)

        if plan is None:
            # Retry único tras 2 segundos
            _log("retry LLM tras fallo...")
            import time as _time

            _time.sleep(2)
            plan = _call_llm_for_intent(user_request)

        if plan is None:
            # Paso 3: Fallback de keywords
            _log("LLM no disponible — usando keyword fallback")
            source = "keyword_fallback"
            plan = _keyword_fallback(user_request)

    # Validar campos obligatorios del plan LLM (puede venir incompleto)
    plan.setdefault("task_type", "mixto")
    plan.setdefault("subtasks", [])
    plan.setdefault("output_format", "markdown")
    plan.setdefault("complexity", "medium")
    plan.setdefault("recommended_tier", 3)

    if not plan["subtasks"]:
        # LLM devolvió plan vacío — reconstruir desde task_type
        agent = TASK_AGENT_MAP.get(plan["task_type"], "orchestrator")
        plan["subtasks"] = [
            {"description": user_request, "agent": agent, "parallel": False, "depends_on": []}
        ]

    # Paso 4: Enriquecer subtareas con model_router
    task_type = plan["task_type"]
    for subtask in plan["subtasks"]:
        subtask.setdefault("parallel", False)
        subtask.setdefault("depends_on", [])

        # Resolver task_type del agente para la consulta a model_router
        agent = subtask.get("agent", "")
        agent_task_type_map = {
            "quant-analyst": "trading",
            "data-analyst": "análisis",
            "creative-writer": "escritura",
            "python-specialist": "código",
            "git-specialist": "código",
            "research-analyst": "research",
            "content-automator": "pipeline",
        }
        st_type = agent_task_type_map.get(agent, task_type)

        model, score = _get_model_for_task(st_type)
        subtask["recommended_model"] = model
        subtask["model_score"] = score

    plan["_source"] = source
    return plan


# ── CLI ───────────────────────────────────────────────────────────────────────


def _print_human(plan: dict) -> None:
    """Formato human-readable del plan."""
    tt = plan.get("task_type", "?")
    tier = plan.get("recommended_tier", "?")
    complexity = plan.get("complexity", "?")
    fmt = plan.get("output_format", "?")
    source = plan.get("_source", "?")
    subtasks = plan.get("subtasks", [])

    print()
    print("[DIRECTOR v3] Intent Analysis")
    print(f"  task_type       : {tt}")
    print(f"  complexity      : {complexity}")
    print(f"  output_format   : {fmt}")
    print(f"  recommended_tier: {tier}")
    print(f"  source          : {source}")
    print(f"  subtasks        : {len(subtasks)}")

    for i, st in enumerate(subtasks):
        parallel = "parallel" if st.get("parallel") else "sequential"
        deps = st.get("depends_on", [])
        dep_str = f"  depends_on={deps}" if deps else ""
        model = st.get("recommended_model", "?")
        score = st.get("model_score", 0.0)
        desc = st.get("description", "")[:72]
        print(f"\n  [{i}] agent={st.get('agent', '?')}  {parallel}{dep_str}")
        print(f"       desc  : {desc}")
        print(f"       model : {model}  (score={score:.2f})")
    print()


def main() -> None:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    quiet = "--quiet" in argv
    argv = [a for a in argv if not a.startswith("--")]

    if argv:
        request = " ".join(argv)
    elif not sys.stdin.isatty():
        request = sys.stdin.read().strip()
    else:
        print(
            'Uso: python3 bin/director.py [--json|--quiet] "<solicitud>"',
            file=sys.stderr,
        )
        sys.exit(1)

    if not request:
        print("[director] Error: solicitud vacía.", file=sys.stderr)
        sys.exit(1)

    plan = analyze_intent(request, verbose=not quiet)

    if quiet:
        # Línea compacta para integración con otros scripts
        agent = plan["subtasks"][0]["agent"] if plan.get("subtasks") else "?"
        print(
            f"task_type={plan.get('task_type')} "
            f"agent={agent} "
            f"tier={plan.get('recommended_tier')}"
        )
    else:
        if not as_json:
            _print_human(plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
