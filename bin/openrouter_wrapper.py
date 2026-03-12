#!/usr/bin/env python3
"""
JARVIS — OpenRouter Wrapper
Routing multi-provider con fallback automático.

Uso:
    python3 openrouter_wrapper.py --agent python-specialist "escribe hello world"
    python3 openrouter_wrapper.py --model qwen/qwen3-coder:free "prompt"
    python3 openrouter_wrapper.py --agent research-analyst        # stdin
    python3 openrouter_wrapper.py --list                          # muestra tabla
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Configuración de providers ──────────────────────────────────────────────

PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "headers_extra": {
            "HTTP-Referer": "https://jarvis.local",
            "X-Title": "JARVIS",
        },
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "headers_extra": {},
    },
    "llm7": {
        "base_url": "https://llm7.io/v1",
        "api_key_env": None,
        "headers_extra": {},
    },
    "pollinations": {
        "base_url": "https://text.pollinations.ai/openai",
        "api_key_env": None,
        "headers_extra": {},
    },
}

# ── Tabla de routing por agente ─────────────────────────────────────────────

AGENT_ROUTING = {
    "python-specialist": ("openrouter", "qwen/qwen3-coder:free"),
    "backend-builder":   ("openrouter", "qwen/qwen3-coder:free"),
    "git-specialist":    ("groq",       "llama-3.3-70b-versatile"),
    "research-analyst":  ("openrouter", "stepfun/step-3.5-flash:free"),
    "auditor":           ("openrouter", "stepfun/step-3.5-flash:free"),
    "data-analyst":      ("openrouter", "openai/gpt-oss-120b:free"),
    "code-reviewer":     ("openrouter", "openai/gpt-oss-120b:free"),
    "creative-writer":   ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    "content-automator": ("openrouter", "nvidia/nemotron-nano-12b-v2-vl:free"),
    "default":           ("openrouter", "stepfun/step-3.5-flash:free"),
}

# Fallback universal por proveedor (cuando el modelo primario falla)
FALLBACK_MODELS = {
    "groq":       ("groq",        "llama-3.3-70b-versatile"),
    "llm7":       ("llm7",        "gpt-4o-mini"),
    "pollinations":("pollinations","openai"),
}

# Cadena de fallback por proveedor primario
FALLBACK_CHAIN = {
    "openrouter": ["groq", "llm7", "pollinations"],
    "groq":       ["llm7", "pollinations"],
    "llm7":       ["pollinations"],
    "pollinations": [],
}

# ── Routing automático por keywords (classify subcommand) ────────────────────
# Cada entrada: (tier, provider, model, route_name, keywords)
# Si múltiples tiers coinciden → gana el más bajo (tier 1 > tier 2 > tier 3)
ROUTING_TABLE = [
    (
        1, "ollama", "qwen2.5-coder:7b", "code_local",
        [
            "python", "refactor", "debug", "test", "tests", "git", "commit",
            "código", "codigo", "función", "funcion", "fix", "bug", "patch",
            "script", "error traceback", "optimize", "optimiza", "clase",
            "variable", "loop", "import", "módulo", "modulo",
        ],
    ),
    (
        2, "groq", "llama-3.3-70b-versatile", "review_groq",
        [
            "review", "revisar", "analiz", "análisis", "analisis",
            "research", "investigar", "evaluar", "compar", "documenta",
            "explica", "resumen", "summary", "audit",
        ],
    ),
    (
        3, "claude", "claude-sonnet-4-6", "claude_api",
        [
            "wacc", "dcf", "finanz", "valorac", "excel", "valuation",
            "novel", "xianxia", "capítulo", "capitulo", "scene", "narrativ",
            "creative", "escritura", "dialogue", "diálogo",
            "arquitectura", "architecture", "seguridad", "security", "auth",
            "mobilize", "coordinar", "orchestrat", "multi-agent", "multiagent",
            "diseño de sistema", "system design",
        ],
    ),
]

TIMEOUT = 120
DB_PATH = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis")) / "database" / "jarvis_metrics.db"


# ── Helpers ─────────────────────────────────────────────────────────────────

def build_request(provider_name: str, model: str, prompt: str):
    """Construye URL, headers y payload para una llamada de chat streaming."""
    cfg = PROVIDERS[provider_name]
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/chat/completions"

    headers = {"Content-Type": "application/json"}
    api_key_env = cfg["api_key_env"]
    if api_key_env:
        key = os.environ.get(api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    headers.update(cfg["headers_extra"])

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }).encode("utf-8")

    return url, headers, payload


def stream_response(provider_name: str, model: str, prompt: str) -> tuple[str, int, bool]:
    """
    Realiza la petición y hace streaming a stdout.
    Devuelve (texto_completo, tokens_estimados, exito).
    """
    url, headers, payload = build_request(provider_name, model, prompt)
    req = urllib.request.Request(url, data=payload, headers=headers)
    full_text = ""

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line or line == "data: [DONE]":
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    chunk = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                # Detectar error embebido en el stream
                if "error" in chunk:
                    return full_text, 0, False
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    print(token, end="", flush=True)
                    full_text += token
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503):
            return full_text, 0, False
        return full_text, 0, False
    except (urllib.error.URLError, TimeoutError):
        return full_text, 0, False

    if full_text:
        print()  # newline final
    return full_text, len(full_text) // 4, bool(full_text)  # tokens estimados ~4 chars/token


def log_to_db(agent: str, model: str, provider: str, tokens: int,
              duration_ms: int, success: bool, session_id: str = "cli") -> None:
    """Registra la llamada en agent_actions."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        conn.execute(
            "INSERT INTO agent_actions "
            "(session_id, agent_name, tool_used, action_type, model_used, "
            "tokens_used, duration_ms, success, start_time_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                agent,
                "openrouter_wrapper",
                "api_call",
                f"{provider}/{model}",
                tokens,
                duration_ms,
                1 if success else 0,
                int(time.time() * 1000) - duration_ms,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def print_routing_table() -> None:
    print("\nJARVIS — Tabla de routing OpenRouter\n")
    print(f"{'Agente':<22} {'Provider':<12} {'Modelo'}")
    print("-" * 72)
    for agent, (provider, model) in AGENT_ROUTING.items():
        print(f"  {agent:<20} {provider:<12} {model}")
    print()
    print("Tiers automáticos (classify):")
    print(f"  {'Tier':<6} {'Provider':<12} {'Modelo':<30} {'Route'}")
    print("  " + "-" * 68)
    for tier, provider, model, route, _ in ROUTING_TABLE:
        print(f"  {tier:<6} {provider:<12} {model:<30} {route}")
    print()
    print("Fallback chain: OpenRouter → Groq → llm7.io → Pollinations")
    print()


def classify_prompt(prompt: str) -> None:
    """
    Determina el tier óptimo para un prompt según keywords.
    Salida: tier=N provider=X model=Y route=Z
    Si múltiples tiers coinciden → tier más bajo gana.
    Default (sin match): tier 1 code_local.
    """
    lowered = prompt.lower()
    matched_tier = None

    for tier, provider, model, route, keywords in ROUTING_TABLE:
        for kw in keywords:
            if kw in lowered:
                if matched_tier is None or tier < matched_tier[0]:
                    matched_tier = (tier, provider, model, route)
                break  # ya encontró keyword en este tier, pasa al siguiente

    if matched_tier is None:
        matched_tier = (1, "ollama", "qwen2.5-coder:7b", "code_local")

    tier, provider, model, route = matched_tier
    print(f"tier={tier} provider={provider} model={model} route={route}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Subcommand: classify <prompt>
    if len(sys.argv) >= 2 and sys.argv[1] == "classify":
        raw = " ".join(sys.argv[2:]).strip()
        if not raw and not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
        if not raw:
            print("tier=1 provider=ollama model=qwen2.5-coder:7b route=code_local")
            sys.exit(0)
        classify_prompt(raw)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="JARVIS OpenRouter Wrapper — routing multi-provider con fallback."
    )
    parser.add_argument("--agent", "-a", default="default",
                        help="Agente JARVIS (define modelo y provider)")
    parser.add_argument("--model", "-m", default=None,
                        help="Modelo explícito (sobreescribe --agent)")
    parser.add_argument("--list", "-l", action="store_true",
                        help="Muestra la tabla de routing y sale")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="Prompt (o stdin si no se pasa)")
    args = parser.parse_args()

    if args.list:
        print_routing_table()
        sys.exit(0)

    # Resolver prompt
    if args.prompt:
        prompt = args.prompt
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        print("[openrouter_wrapper] Error: proporciona un prompt o usa stdin.", file=sys.stderr)
        sys.exit(1)

    if not prompt:
        print("[openrouter_wrapper] Error: prompt vacío.", file=sys.stderr)
        sys.exit(1)

    # Resolver proveedor y modelo
    if args.model:
        primary_provider = "openrouter"
        primary_model = args.model
    else:
        agent_key = args.agent if args.agent in AGENT_ROUTING else "default"
        primary_provider, primary_model = AGENT_ROUTING[agent_key]

    agent_name = args.agent

    # Construir cadena: primario + fallbacks
    chain = [(primary_provider, primary_model)]
    for fallback_provider in FALLBACK_CHAIN.get(primary_provider, []):
        fb_provider, fb_model = FALLBACK_MODELS.get(fallback_provider, (fallback_provider, "gpt-4o-mini"))
        chain.append((fb_provider, fb_model))

    # Intentar cada proveedor en orden
    for provider, model in chain:
        print(f"[JARVIS] {agent_name} | {provider} | {model}", file=sys.stderr)
        t0 = int(time.time() * 1000)
        text, tokens, ok = stream_response(provider, model, prompt)
        duration_ms = int(time.time() * 1000) - t0

        log_to_db(agent_name, model, provider, tokens, duration_ms, ok)

        if ok:
            sys.exit(0)

        print(f"[JARVIS] {provider} falló — intentando siguiente...", file=sys.stderr)

    print("\n[openrouter_wrapper] Error: todos los providers fallaron.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
