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
from urllib.parse import urlparse

# ── Configuración de providers ──────────────────────────────────────────────

PROVIDERS = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "headers_extra": {},
    },
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

# Allowlist derived from PROVIDERS — only these hosts are ever called
_ALLOWED_HOSTS = frozenset(urlparse(cfg["base_url"]).hostname for cfg in PROVIDERS.values())


def _validate_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith(f".{h}") for h in _ALLOWED_HOSTS):
        raise ValueError(f"URL no permitida: {url}")


# ── Tabla de routing por agente ─────────────────────────────────────────────

AGENT_ROUTING = {
    # Tier 1 — Ollama local (qwen2.5-coder:7b)
    "python-specialist": ("ollama", "qwen2.5-coder:7b"),
    "git-specialist": ("ollama", "qwen2.5-coder:7b"),
    "content-automator": ("ollama", "qwen2.5-coder:7b"),
    # Tier 2 — Cloud free
    "backend-builder": ("openrouter", "qwen/qwen3-coder:free"),
    "research-analyst": ("openrouter", "stepfun/step-3.5-flash:free"),
    "auditor": ("openrouter", "stepfun/step-3.5-flash:free"),
    "data-analyst": ("openrouter", "openai/gpt-oss-120b:free"),
    "code-reviewer": ("openrouter", "openai/gpt-oss-120b:free"),
    "creative-writer": ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    "default": ("openrouter", "stepfun/step-3.5-flash:free"),
}

# Fallback universal por proveedor (cuando el modelo primario falla)
FALLBACK_MODELS = {
    "openrouter": ("openrouter", "stepfun/step-3.5-flash:free"),
    "groq": ("groq", "llama-3.3-70b-versatile"),
    "llm7": ("llm7", "gpt-4o-mini"),
    "pollinations": ("pollinations", "openai"),
}

# Cadena de fallback por proveedor primario
FALLBACK_CHAIN = {
    "ollama": ["openrouter", "groq", "llm7", "pollinations"],
    "openrouter": ["groq", "llm7", "pollinations"],
    "groq": ["llm7", "pollinations"],
    "llm7": ["pollinations"],
    "pollinations": [],
}

# Coste por 1K tokens (input, output) en USD — 0.0 = gratuito/local
TIER_COSTS: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "groq": (0.0, 0.0),
    "llm7": (0.0, 0.0),
    "pollinations": (0.0, 0.0),
    "openrouter": (0.003, 0.015),  # Claude Sonnet pricing aprox.
}

# ── Routing automático por keywords (classify subcommand) ────────────────────
# Cada entrada: (tier, provider, model, route_name, keywords)
# Si múltiples tiers coinciden → gana el más bajo (tier 1 > tier 2 > tier 3)
ROUTING_TABLE = [
    (
        1,
        "ollama",
        "qwen2.5-coder:7b",
        "code_local",
        [
            "python",
            "refactor",
            "debug",
            "test",
            "tests",
            "git",
            "commit",
            "código",
            "codigo",
            "función",
            "funcion",
            "fix",
            "bug",
            "patch",
            "script",
            "error traceback",
            "optimize",
            "optimiza",
            "clase",
            "variable",
            "loop",
            "import",
            "módulo",
            "modulo",
        ],
    ),
    (
        2,
        "groq",
        "llama-3.3-70b-versatile",
        "review_groq",
        [
            "review",
            "revisar",
            "analiz",
            "análisis",
            "analisis",
            "research",
            "investigar",
            "evaluar",
            "compar",
            "documenta",
            "explica",
            "resumen",
            "summary",
            "audit",
        ],
    ),
    (
        3,
        "claude",
        "claude-sonnet-4-6",
        "claude_api",
        [
            "wacc",
            "dcf",
            "finanz",
            "valorac",
            "excel",
            "valuation",
            "novel",
            "xianxia",
            "capítulo",
            "capitulo",
            "scene",
            "narrativ",
            "creative",
            "escritura",
            "dialogue",
            "diálogo",
            "arquitectura",
            "architecture",
            "seguridad",
            "security",
            "auth",
            "mobilize",
            "coordinar",
            "orchestrat",
            "multi-agent",
            "multiagent",
            "diseño de sistema",
            "system design",
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
    _validate_url(url)

    headers = {"Content-Type": "application/json"}
    api_key_env = cfg["api_key_env"]
    if api_key_env:
        key = os.environ.get(api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    headers.update(cfg["headers_extra"])

    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
    ).encode("utf-8")

    return url, headers, payload


def stream_response(provider_name: str, model: str, prompt: str) -> tuple[str, int, int, bool]:
    """
    Realiza la petición y hace streaming a stdout.
    Devuelve (texto_completo, tokens_input, tokens_output, exito).
    Usa tokens reales de la API si están disponibles; estima por chars si no.
    """
    url, headers, payload = build_request(provider_name, model, prompt)
    req = urllib.request.Request(url, data=payload, headers=headers)
    full_text = ""
    tokens_in = 0
    tokens_out = 0

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosemgrep
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
                    return full_text, tokens_in, tokens_out, False
                # Capturar tokens reales si la API los devuelve (OpenRouter/Groq)
                if "usage" in chunk:
                    usage = chunk["usage"]
                    tokens_in = usage.get("prompt_tokens", tokens_in)
                    tokens_out = usage.get("completion_tokens", tokens_out)
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
            return full_text, tokens_in, tokens_out, False
        return full_text, tokens_in, tokens_out, False
    except (urllib.error.URLError, TimeoutError):
        return full_text, tokens_in, tokens_out, False

    if full_text:
        print()  # newline final
    # Fallback a estimación si la API no devolvió usage
    if not tokens_in and not tokens_out:
        tokens_in = len(prompt) // 4
        tokens_out = len(full_text) // 4
    return full_text, tokens_in, tokens_out, bool(full_text)


def log_to_db(
    agent: str,
    model: str,
    provider: str,
    tokens_in: int,
    tokens_out: int,
    duration_ms: int,
    success: bool,
    session_id: str = "cli",
    error_message: str = "",
) -> None:
    """Registra la llamada en agent_actions con tokens reales y coste estimado."""
    if not DB_PATH.exists():
        return
    try:
        cost_in, cost_out = TIER_COSTS.get(provider, (0.0, 0.0))
        cost_usd = (tokens_in / 1000.0) * cost_in + (tokens_out / 1000.0) * cost_out
        tier = "A" if cost_in > 0 else ("B" if provider in ("groq", "openrouter") else "C")
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        conn.execute(
            "INSERT INTO agent_actions "
            "(session_id, agent_name, tool_used, action_type, model_used, "
            "tokens_used, tokens_input, tokens_output, estimated_cost_usd, tier, "
            "duration_ms, success, error_message, start_time_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                agent,
                "openrouter_wrapper",
                "api_call",
                f"{provider}/{model}",
                tokens_in + tokens_out,
                tokens_in,
                tokens_out,
                round(cost_usd, 6),
                tier,
                duration_ms,
                1 if success else 0,
                error_message[:500] if error_message else None,
                int(time.time() * 1000) - duration_ms,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _log_escalation(
    session_id: str, agent: str, from_provider: str, from_model: str, reason: str
) -> None:
    """Registra un escalado de fallback en error_log con keyword ESCALATION."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        conn.execute(
            "INSERT INTO error_log "
            "(timestamp, session_id, agent_name, error_type, error_message, keywords, resolved) "
            "VALUES (datetime('now'), ?, ?, 'ESCALATION', ?, ?, 0)",
            (
                session_id,
                agent,
                f"Escalated from {from_provider}/{from_model}: {reason[:300]}",
                json.dumps([agent, "ESCALATION", from_provider]),
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
    print("Fallback chain (Tier 1): Ollama → OpenRouter → Groq → llm7.io → Pollinations")
    print()


def classify_prompt(prompt: str) -> None:
    """
    Determina el tier óptimo para un prompt según keywords.
    Salida: tier=N provider=X model=Y route=Z [domain=D]
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

    # Domain enrichment (best-effort — no falla si domain_classifier no está disponible)
    domain_suffix = ""
    try:
        _dc_path = Path(__file__).parent / "domain_classifier.py"
        if _dc_path.exists():
            import importlib.util as _ilu

            _spec = _ilu.spec_from_file_location("domain_classifier", _dc_path)
            _dc = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_dc)
            _domain, _score, _method = _dc.classify_domain(prompt)
            if _method != "default":
                domain_suffix = f" domain={_domain}"
    except Exception:
        pass

    print(f"tier={tier} provider={provider} model={model} route={route}{domain_suffix}")


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
    parser.add_argument(
        "--agent", "-a", default="default", help="Agente JARVIS (define modelo y provider)"
    )
    parser.add_argument(
        "--model", "-m", default=None, help="Modelo explícito (sobreescribe --agent)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="Muestra la tabla de routing y sale"
    )
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt (o stdin si no se pasa)")
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
        fb_provider, fb_model = FALLBACK_MODELS.get(
            fallback_provider, (fallback_provider, "gpt-4o-mini")
        )
        chain.append((fb_provider, fb_model))

    # Intentar cada proveedor en orden
    for provider, model in chain:
        print(f"[JARVIS] {agent_name} | {provider} | {model}", file=sys.stderr)
        t0 = int(time.time() * 1000)
        text, tokens_in, tokens_out, ok = stream_response(provider, model, prompt)
        duration_ms = int(time.time() * 1000) - t0

        err_msg = "" if ok else f"{provider}/{model} falló — sin respuesta o HTTP error"
        log_to_db(
            agent_name,
            model,
            provider,
            tokens_in,
            tokens_out,
            duration_ms,
            ok,
            error_message=err_msg,
        )

        if ok:
            sys.exit(0)

        print(f"[JARVIS] {provider} falló — intentando siguiente...", file=sys.stderr)
        _log_escalation("cli", agent_name, provider, model, err_msg)

    print("\n[openrouter_wrapper] Error: todos los providers fallaron.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
