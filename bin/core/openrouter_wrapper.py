#!/usr/bin/env python3
"""
DQIII8 — OpenRouter Wrapper
Multi-provider routing with automatic fallback.

Uso:
    python3 openrouter_wrapper.py --agent python-specialist "escribe hello world"
    python3 openrouter_wrapper.py --model qwen/qwen3-coder:free "prompt"
    python3 openrouter_wrapper.py --agent research-analyst        # stdin
    python3 openrouter_wrapper.py --list                          # muestra tabla
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# ── Provider configuration ──────────────────────────────────────────────────

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
            "X-Title": "DQIII8",
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
_ALLOWED_HOSTS = frozenset(
    urlparse(cfg["base_url"]).hostname for cfg in PROVIDERS.values()
)


def _validate_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith(f".{h}") for h in _ALLOWED_HOSTS):
        raise ValueError(f"URL not allowed: {url}")


# ── Tabla de routing por agente ─────────────────────────────────────────────

AGENT_ROUTING = {
    # Tier C — Ollama local (qwen2.5-coder:7b) — code & pipeline tasks only
    # Benchmark: qwen performs well for applied_sciences; timeouts/mediocre elsewhere (4.5/10 vs llama 7.9/10)
    "python-specialist": ("ollama", "qwen2.5-coder:7b"),
    "git-specialist": ("ollama", "qwen2.5-coder:7b"),
    "web-specialist": ("ollama", "qwen2.5-coder:7b"),
    "algo-specialist": ("ollama", "qwen2.5-coder:7b"),
    "content-automator": ("ollama", "qwen2.5-coder:7b"),
    # Tier B — Cloud free (groq/llama-3.3-70b) — domain knowledge specialists
    "ai-ml-specialist": ("groq", "llama-3.3-70b-versatile"),
    "biology-specialist": ("groq", "llama-3.3-70b-versatile"),
    "chemistry-specialist": ("groq", "llama-3.3-70b-versatile"),
    "data-specialist": ("groq", "llama-3.3-70b-versatile"),
    "economics-specialist": ("groq", "llama-3.3-70b-versatile"),
    "history-specialist": ("groq", "llama-3.3-70b-versatile"),
    "language-specialist": ("groq", "llama-3.3-70b-versatile"),
    "legal-specialist": ("groq", "llama-3.3-70b-versatile"),
    "logic-specialist": ("groq", "llama-3.3-70b-versatile"),
    "marketing-specialist": ("groq", "llama-3.3-70b-versatile"),
    "math-specialist": ("groq", "llama-3.3-70b-versatile"),
    "nutrition-specialist": ("groq", "llama-3.3-70b-versatile"),
    "philosophy-specialist": ("groq", "llama-3.3-70b-versatile"),
    "physics-specialist": ("groq", "llama-3.3-70b-versatile"),
    "software-specialist": ("groq", "llama-3.3-70b-versatile"),
    "stats-specialist": ("groq", "llama-3.3-70b-versatile"),
    "writing-specialist": ("groq", "llama-3.3-70b-versatile"),
    # Tier B — Other cloud-free agents
    "research-analyst": ("groq", "llama-3.3-70b-versatile"),
    "code-reviewer": ("openrouter", "openai/gpt-oss-120b:free"),
    # Tier A — Paid / high-stakes agents
    "finance-specialist": ("anthropic", "claude-sonnet-4-6"),
    "auditor": ("anthropic", "claude-sonnet-4-6"),
    "orchestrator": ("anthropic", "claude-sonnet-4-6"),
    "default": ("openrouter", "stepfun/step-3.5-flash:free"),
}

# Agents for which Tier C (Ollama/qwen) is always correct regardless of domain.
# All other agents on Tier C will be auto-escalated to Tier B when domain != applied_sciences.
_TIER_C_AGENTS = frozenset(
    {
        "python-specialist",
        "git-specialist",
        "web-specialist",
        "algo-specialist",
        "content-automator",
    }
)

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

# Tier map — C/B/A/S/S+ for explicit routing and classification
TIER_MAP = {
    "C": {
        "provider": "ollama",
        "model": "qwen2.5-coder:7b",
        "cost_input_1k": 0.0,
        "cost_output_1k": 0.0,
        "desc": "Local — $0",
    },
    "B": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "cost_input_1k": 0.0,
        "cost_output_1k": 0.0,
        "desc": "Cloud free — $0",
    },
    "A": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "cost_input_1k": 0.003,
        "cost_output_1k": 0.015,
        "desc": "Claude Sonnet — ~$0.01-0.05",
    },
    "S": {
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "cost_input_1k": 0.015,
        "cost_output_1k": 0.075,
        "desc": "Opus planner — ~$0.15-0.50",
    },
    "S+": {
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "cost_input_1k": 0.015,
        "cost_output_1k": 0.075,
        "desc": "Opus orchestrator — ~$0.50-2.00",
    },
}

# Priority order for tier comparison (lower index = higher priority = cheaper)
TIER_ORDER = {"C": 0, "B": 1, "A": 2, "S": 3, "S+": 4}

# ── Automatic routing by keywords (classify subcommand) ──────────────────────
# Each entry: (tier, provider, model, route_name, keywords)
# If multiple tiers match → cheapest wins (C > B > A > S > S+)
ROUTING_TABLE = [
    (
        "C",
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
        "B",
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
        "A",
        "anthropic",
        "claude-sonnet-4-6",
        "claude_sonnet",
        [
            "wacc",
            "dcf",
            "finanz",
            "valorac",
            "excel",
            "valuation",
            "novel",
            "fiction",
            "chapter",
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
        ],
    ),
    (
        "S",
        "anthropic",
        "claude-opus-4-6",
        "opus_planner",
        [
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

TIMEOUT = 180
DB_PATH = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / "database" / "dqiii8.db"


# ── Helpers ─────────────────────────────────────────────────────────────────


def sanitize_prompt(prompt: str) -> str:
    """Remove potential prompt-injection patterns before sending to a model."""
    import re

    dangerous_patterns = [
        r"ignore previous instructions",
        r"ignore all previous",
        r"system:\s*you are now",
        r"<\|system\|>",
        r"<\|assistant\|>",
    ]
    sanitized = prompt
    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, "[filtered]", sanitized, flags=re.IGNORECASE)
    return sanitized


def load_agent_system_prompt(agent_name: str, prompt: str = "") -> str:
    """Load agent system prompt.

    For domain specialists (those with `domain:` in YAML frontmatter), calls
    domain_lens.get_domain_lens() to generate a dynamic system prompt with
    automatic knowledge enrichment.

    For core agents (no `domain:` field), returns the MD body as before.
    """
    if not agent_name or agent_name == "default":
        return ""
    jarvis = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    md_path = jarvis / ".claude" / "agents" / f"{agent_name}.md"
    if not md_path.exists():
        return ""
    content = md_path.read_text(encoding="utf-8")

    # Parse YAML frontmatter to detect domain field
    domain = None
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            frontmatter = content[3:end].strip()
            body = content[end + 3 :].lstrip("\n")
            for line in frontmatter.splitlines():
                if line.startswith("domain:"):
                    domain = line.split(":", 1)[1].strip()
                    break

    # Domain specialist: use domain_lens for dynamic system prompt with knowledge
    if domain and prompt:
        try:
            _dl_path = Path(__file__).parent.parent / "agents" / "domain_lens.py"
            if _dl_path.exists():
                import importlib.util as _ilu

                _spec = _ilu.spec_from_file_location("domain_lens", _dl_path)
                _dl = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_dl)
                result = _dl.get_domain_lens(prompt, domain)
                if result.get("system_prompt"):
                    print(
                        f"[DQIII8] domain lens: agent={agent_name} "
                        f"domain={domain} chunks={result['chunks_used']}",
                        file=sys.stderr,
                    )
                    return result["system_prompt"]
        except Exception:
            pass  # fall through to MD body on any error

    return body.strip()


def build_request(provider_name: str, model: str, prompt: str, system_prompt: str = ""):
    """Construye URL, headers y payload para una llamada de chat streaming."""
    cfg = PROVIDERS[provider_name]
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/chat/completions"
    _validate_url(url)

    headers = {"Content-Type": "application/json", "User-Agent": "DQIII8/1.0"}
    api_key_env = cfg["api_key_env"]
    if api_key_env:
        key = os.environ.get(api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    headers.update(cfg["headers_extra"])

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": True,
        }
    ).encode("utf-8")

    return url, headers, payload


def stream_response(
    provider_name: str, model: str, prompt: str, system_prompt: str = ""
) -> tuple[str, int, int, bool]:
    """
    Makes the request and streams to stdout.
    Returns (full_text, tokens_input, tokens_output, success).
    Uses real API tokens if available; estimates by chars otherwise.
    """
    url, headers, payload = build_request(
        provider_name, model, sanitize_prompt(prompt), system_prompt
    )
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
    # Fallback to estimation if the API did not return usage
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
    domain: str = "",
    prompt_hash: str = "",
) -> None:
    """Registra la llamada en agent_actions con tokens reales y coste estimado."""
    if not DB_PATH.exists():
        return
    try:
        cost_in, cost_out = TIER_COSTS.get(provider, (0.0, 0.0))
        cost_usd = (tokens_in / 1000.0) * cost_in + (tokens_out / 1000.0) * cost_out
        tier = (
            "A"
            if provider == "anthropic"
            else ("B" if provider in ("groq", "openrouter") else "C")
        )
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
        # Routing feedback — track per-prompt routing decisions for quality analysis
        if prompt_hash:
            try:
                conn.execute(
                    "INSERT INTO routing_feedback "
                    "(prompt_hash, domain, tier_used, model_used, success, duration_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        prompt_hash,
                        domain or None,
                        tier,
                        f"{provider}/{model}",
                        1 if success else 0,
                        duration_ms,
                    ),
                )
                conn.commit()
            except Exception:
                pass  # fail-open, never block the pipeline
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
    print("\nDQIII8 — Tabla de routing OpenRouter\n")
    print(f"{'Agente':<22} {'Provider':<12} {'Modelo'}")
    print("-" * 72)
    for agent, (provider, model) in AGENT_ROUTING.items():
        print(f"  {agent:<20} {provider:<12} {model}")
    print()
    print("Automatic tiers (classify):")
    print(f"  {'Tier':<6} {'Provider':<12} {'Modelo':<30} {'Route'}")
    print("  " + "-" * 68)
    for tier, provider, model, route, _ in ROUTING_TABLE:
        print(f"  {tier:<6} {provider:<12} {model:<30} {route}")
    print()
    print(
        "Fallback chain (Tier C): Ollama → OpenRouter → Groq → llm7.io → Pollinations"
    )
    print()


def classify_prompt(prompt: str) -> None:
    """
    Determines the optimal tier for a prompt based on keywords.
    Output: tier=X provider=Y model=Z route=W [domain=D]
    If multiple tiers match → cheapest tier wins (C < B < A < S < S+).
    Default (no match): tier C code_local.
    """
    lowered = prompt.lower()
    matched_tier = None

    for tier, provider, model, route, keywords in ROUTING_TABLE:
        for kw in keywords:
            if kw in lowered:
                if matched_tier is None or TIER_ORDER.get(tier, 99) < TIER_ORDER.get(
                    matched_tier[0], 99
                ):
                    matched_tier = (tier, provider, model, route)
                break  # found keyword in this tier, move to next

    if matched_tier is None:
        matched_tier = ("C", "ollama", "qwen2.5-coder:7b", "code_local")

    tier, provider, model, route = matched_tier

    # Domain enrichment (best-effort — no failure if domain_classifier is unavailable)
    domain_suffix = ""
    try:
        _dc_path = Path(__file__).parent.parent / "agents" / "domain_classifier.py"
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
            print("tier=C provider=ollama model=qwen2.5-coder:7b route=code_local")
            sys.exit(0)
        classify_prompt(raw)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="DQIII8 OpenRouter Wrapper — routing multi-provider con fallback."
    )
    parser.add_argument(
        "--agent",
        "-a",
        default="default",
        help="Agente DQIII8 (define modelo y provider)",
    )
    parser.add_argument(
        "--model", "-m", default=None, help="Explicit model (overrides --agent)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="Muestra la tabla de routing y sale"
    )
    parser.add_argument(
        "prompt", nargs="?", default=None, help="Prompt (o stdin si no se pasa)"
    )
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
        print(
            "[openrouter_wrapper] Error: proporciona un prompt o usa stdin.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not prompt:
        print("[openrouter_wrapper] Error: empty prompt.", file=sys.stderr)
        sys.exit(1)

    # Capture original prompt for working memory (before DQ enrichment mutates it)
    _original_prompt = prompt

    # Session ID: use DQIII8_SESSION_ID if set (injected by Telegram bot or loop),
    # otherwise derive from process ID so each CLI invocation is its own session.
    try:
        _wm_path = Path(__file__).parent.parent / "agents" / "working_memory.py"
        if _wm_path.exists():
            import importlib.util as _ilu_wm

            _spec_wm = _ilu_wm.spec_from_file_location("working_memory", _wm_path)
            _wm = _ilu_wm.module_from_spec(_spec_wm)
            _spec_wm.loader.exec_module(_wm)
            _session_id = _wm.get_session_id()
        else:
            _wm = None
            _session_id = None
    except Exception:
        _wm = None
        _session_id = None

    # Linear pipeline: classify → get_chunks (no prompt mutation) → amplify(original)
    # This prevents the double-enrichment bug where enrich_with_knowledge() prepended
    # [DOMAIN CONTEXT] to the prompt before amplify() ran, causing entity="CONTEXT".
    _enriched_domain = None
    _routing_domain = None  # captured for tier escalation below
    _knowledge_chunks = 0
    try:
        _dc_path = Path(__file__).parent.parent / "agents" / "domain_classifier.py"
        _ke_path = Path(__file__).parent.parent / "agents" / "knowledge_enricher.py"
        _ia_path = Path(__file__).parent.parent / "agents" / "intent_amplifier.py"
        if _dc_path.exists() and _ke_path.exists() and _ia_path.exists():
            import importlib.util as _ilu

            _spec = _ilu.spec_from_file_location("domain_classifier", _dc_path)
            _dc = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_dc)
            _domain, _score, _method = _dc.classify_domain(prompt)
            _routing_domain = _domain  # always capture, used for escalation

            if _method != "default":
                # Step 2a: load intent_amplifier first — decompose is fast (no network)
                _spec3 = _ilu.spec_from_file_location("intent_amplifier", _ia_path)
                _ia = _ilu.module_from_spec(_spec3)
                _spec3.loader.exec_module(_ia)
                _decomp = _ia._decompose(prompt)
                # Skip task_relevance re-ranking for code-specialist agents (Tier C):
                # their queries are about code, not domain knowledge, so the extra
                # embedding pass adds latency without benefit.
                _use_task_relevance = (
                    args.agent not in _TIER_C_AGENTS if args.agent else True
                )
                _intent = (
                    _decomp.get("action") or "explain" if _use_task_relevance else None
                )
                _entity = _decomp.get("entity") if _use_task_relevance else None

                # Step 2b: get chunks — re-ranked by task relevance when intent+entity known
                _spec2 = _ilu.spec_from_file_location("knowledge_enricher", _ke_path)
                _ke = _ilu.module_from_spec(_spec2)
                _spec2.loader.exec_module(_ke)
                _chunks = _ke.get_relevant_chunks(
                    prompt, _domain, intent=_intent, entity=_entity
                )

                # Step 2c: confidence gate — skip enrichment when chunks add no value.
                # Derive preliminary tier from agent provider (1=local, 2=cloud-free, 3=paid).
                _gate_tier = (
                    1
                    if args.agent in _TIER_C_AGENTS
                    else (
                        3
                        if AGENT_ROUTING.get(args.agent, (None, None))[0] == "anthropic"
                        else 2
                    )
                )
                try:
                    _cg_path = (
                        Path(__file__).parent.parent / "agents" / "confidence_gate.py"
                    )
                    if _cg_path.exists():
                        _spec_cg = _ilu.spec_from_file_location(
                            "confidence_gate", _cg_path
                        )
                        _cg = _ilu.module_from_spec(_spec_cg)
                        _spec_cg.loader.exec_module(_cg)
                        if not _cg.should_enrich(prompt, _domain, _chunks, _gate_tier):
                            print(
                                f"[DQIII8] confidence gate: skip enrichment "
                                f"domain={_domain} tier={_gate_tier} chunks={len(_chunks)}",
                                file=sys.stderr,
                            )
                            _chunks = []
                except Exception:
                    pass  # gate failure → keep chunks (fail open)

                # Step 3: amplify ORIGINAL prompt with pre-fetched domain + chunks
                _ia_result = _ia.amplify(
                    prompt,
                    domain=_domain,
                    chunks=_chunks,
                    verbose=False,
                )
                if _ia_result.get("chunks_used", 0) > 0 or _ia_result.get("action"):
                    prompt = _ia_result["amplified"]
                    _knowledge_chunks = _ia_result["chunks_used"]
                    _enriched_domain = _domain
                    print(
                        f"[DQIII8] pipeline: domain={_domain} "
                        f"chunks={_knowledge_chunks} "
                        f"intent={_ia_result['intent']} tier={_ia_result['tier']}",
                        file=sys.stderr,
                    )
    except Exception:
        pass

    # Domain agent selector — keyword match selects specialist system prompt when
    # no explicit agent was requested (0ms LLM latency, pure string matching).
    _domain_system: str = ""
    if _routing_domain and (not args.agent or args.agent == "default"):
        try:
            import importlib.util as _ilu_das

            _das_path = (
                Path(__file__).parent.parent / "agents" / "domain_agent_selector.py"
            )
            if _das_path.exists():
                _spec_das = _ilu_das.spec_from_file_location(
                    "domain_agent_selector", _das_path
                )
                _das = _ilu_das.module_from_spec(_spec_das)
                _spec_das.loader.exec_module(_das)
                _sel_agent, _domain_system = _das.select_domain_agent(
                    prompt, _routing_domain
                )
                if _sel_agent != "default":
                    print(
                        f"[DQIII8] domain selector: {_sel_agent} "
                        f"(domain={_routing_domain})",
                        file=sys.stderr,
                    )
        except Exception:
            pass  # selector failure → continue with default system prompt

    # Resolver proveedor y modelo
    if args.model:
        primary_provider = "openrouter"
        primary_model = args.model
    else:
        agent_key = args.agent if args.agent in AGENT_ROUTING else "default"
        primary_provider, primary_model = AGENT_ROUTING[agent_key]

    agent_name = args.agent

    # Escalate from Tier C when domain is not applied_sciences.
    # Code-specialist agents (_TIER_C_AGENTS) always stay on qwen regardless of domain.
    # If Groq later fails, ollama is appended as last-resort fallback.
    _escalated_from_ollama = False
    if (
        primary_provider == "ollama"
        and agent_name not in _TIER_C_AGENTS
        and _routing_domain is not None
        and _routing_domain != "applied_sciences"
    ):
        print(
            f"[DQIII8] Tier C skipped: domain={_routing_domain}, escalated to B",
            file=sys.stderr,
        )
        primary_provider = "groq"
        primary_model = "llama-3.3-70b-versatile"
        _escalated_from_ollama = True

    # Load agent system prompt — domain specialists get dynamic lens + knowledge
    system_prompt = load_agent_system_prompt(agent_name, prompt)
    if not system_prompt and _domain_system:
        system_prompt = _domain_system
    if system_prompt:
        print(
            f"[DQIII8] system prompt loaded: {agent_name} ({len(system_prompt)} chars)",
            file=sys.stderr,
        )

    # Construir cadena: primario + fallbacks
    chain = [(primary_provider, primary_model)]
    for fallback_provider in FALLBACK_CHAIN.get(primary_provider, []):
        fb_provider, fb_model = FALLBACK_MODELS.get(
            fallback_provider, (fallback_provider, "gpt-4o-mini")
        )
        chain.append((fb_provider, fb_model))
    # When escalated from Ollama, add qwen as last-resort (offline fallback)
    if _escalated_from_ollama:
        chain.append(("ollama", "qwen2.5-coder:7b"))

    # Working memory: prepend recent session context for Tier B/A calls.
    # Tier C (Ollama/qwen) skips this — small models choke on extra prefix tokens.
    _wm_tier = (
        3
        if primary_provider == "anthropic"
        else (1 if primary_provider == "ollama" else 2)
    )
    if _wm and _session_id and _wm_tier >= 2:
        try:
            _session_ctx = _wm.get_session_context(_session_id, max_exchanges=3)
            if _session_ctx:
                prompt = _session_ctx[:2000] + "\n\n" + prompt
        except Exception:
            pass  # fail-open

    # Intentar cada proveedor en orden
    for provider, model in chain:
        print(f"[DQIII8] {agent_name} | {provider} | {model}", file=sys.stderr)
        t0 = int(time.time() * 1000)
        text, tokens_in, tokens_out, ok = stream_response(
            provider, model, prompt, system_prompt
        )
        duration_ms = int(time.time() * 1000) - t0

        err_msg = "" if ok else f"{provider}/{model} failed — no response or HTTP error"
        _phash = hashlib.md5(_original_prompt[:200].encode()).hexdigest()[:16]
        log_to_db(
            agent_name,
            model,
            provider,
            tokens_in,
            tokens_out,
            duration_ms,
            ok,
            error_message=err_msg,
            domain=_routing_domain or "",
            prompt_hash=_phash,
        )

        if ok:
            if _wm and _session_id:
                try:
                    _wm.save_exchange(
                        _session_id, _original_prompt, text[:300], _enriched_domain
                    )
                except Exception:
                    pass  # fail-open
            sys.exit(0)

        print(f"[DQIII8] {provider} failed — trying next...", file=sys.stderr)
        _log_escalation("cli", agent_name, provider, model, err_msg)

    print(
        "\n[openrouter_wrapper] Error: todos los providers fallaron.", file=sys.stderr
    )
    sys.exit(1)


# ── Model satisfaction recommender (merged from model_router.py) ───────────

_ROUTER_DEFAULTS: dict[str, tuple[str, str]] = {
    "código": ("tier1", "qwen2.5-coder:7b"),
    "pipeline": ("tier1", "qwen2.5-coder:7b"),
    "análisis": ("tier2", "llama-3.3-70b-versatile"),
    "research": ("tier2", "llama-3.3-70b-versatile"),
    "escritura": ("tier3", "claude-sonnet-4-6"),
    "trading": ("tier3", "claude-sonnet-4-6"),
    "mixto": ("tier3", "claude-sonnet-4-6"),
}
_ROUTER_MIN_SAMPLES = 5
_ROUTER_NEUTRAL = 0.5


def get_recommendation(task_type: str) -> tuple[str, float, int]:
    """Return (model_used, score, n_samples) based on historical satisfaction data."""
    if not DB_PATH.exists():
        _, model = _ROUTER_DEFAULTS.get(task_type, ("tier3", "claude-sonnet-4-6"))
        return model, _ROUTER_NEUTRAL, 0

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        rows = conn.execute(
            """
            SELECT model_used, AVG(user_satisfaction), COUNT(*)
            FROM (
                SELECT model_used, user_satisfaction
                FROM model_satisfaction
                WHERE task_type = ?
                  AND user_satisfaction IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 20
            )
            GROUP BY model_used
            ORDER BY AVG(user_satisfaction) DESC
            """,
            (task_type,),
        ).fetchall()
        conn.close()
    except Exception:
        rows = []

    if rows:
        best_model, best_score, n = rows[0]
        if n >= _ROUTER_MIN_SAMPLES:
            return best_model, round(best_score, 2), n
        blended = round(
            (best_score * n + _ROUTER_NEUTRAL * (_ROUTER_MIN_SAMPLES - n))
            / _ROUTER_MIN_SAMPLES,
            2,
        )
        return best_model, blended, n

    _, model = _ROUTER_DEFAULTS.get(task_type, ("tier3", "claude-sonnet-4-6"))
    return model, _ROUTER_NEUTRAL, 0


if __name__ == "__main__":
    main()
