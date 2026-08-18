#!/usr/bin/env python3
"""
DQIII8 — OpenRouter Wrapper
Multi-provider routing with automatic fallback.

Uso:
    python3 openrouter_wrapper.py --agent python-specialist "escribe hello world"
    python3 openrouter_wrapper.py --model qwen/qwen3-coder "prompt"
    python3 openrouter_wrapper.py --agent research-analyst        # stdin
    python3 openrouter_wrapper.py --list                          # muestra tabla
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import logging
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin.core.logging_config import get_logger as _get_logger
log = _get_logger(__name__)

# ── Auto-load .env so API keys are available regardless of shell environment ─
def _load_dotenv() -> None:
    """Load /root/dqiii8/.env into os.environ (setdefault — never overwrites existing vars)."""
    root = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()

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
            "HTTP-Referer": "https://dqiii8.local",
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
    # GitHub Models — manual tier (pending benchmark vs groq/llama)
    # 5 confirmed models: gpt-4o-mini, deepseek-r1, deepseek-v3-0324, llama-3.3-70b-instruct, codestral-2501
    # Rate limits: 20k req / 2M tokens. Short model IDs (no publisher prefix).
    # Direct wrapper: bin/core/github_models_wrapper.py --model <id> "<prompt>"
    # CONFIRMADO CAÍDO 2026-08-11 (stress-routing.md #13): este endpoint (deprecado)
    # da 404; el endpoint sucesor "https://models.github.ai/inference" da 410
    # {"code":"github_models_retirement_brownout"} — GitHub está retirando el
    # servicio a nivel de plataforma. No es un bug de token/endpoint local;
    # no reparable en código. github ya es el último eslabón de FALLBACK_CHAIN
    # salvo pollinations, así que su caída no bloquea nada aguas arriba.
    "github": {
        "base_url": "https://models.inference.ai.azure.com/v1",
        "api_key_env": "GITHUB_TOKEN",
        "headers_extra": {},
    },
    # NVIDIA NIM — Tier B+ (free, OpenAI-compatible, 50/121 models activos, 40 RPM global)
    # Sondeo completo 2026-06-26: 50 OK, 58 404, 9 timeout, 4 error
    # RÁPIDOS (<1s): llama-3.1-70b(0.3s), llama-4-maverick(0.3s),
    #               ministral-14b(0.1s), nemotron-mini-4b(0.1s), phi-4-multimodal(0.2s)
    # RAZONAMIENTO: nvidia/llama-3.3-nemotron-super-49b-v1.5 (mistral-large-3-675b: EOL/410 2026-07-23)
    # CÓDIGO: deepseek-v4-flash-0731 (1M ctx) — granite/codestral/starcoder son 404
    # SAFETY: nemoguard-8b-content-safety(0.1s), llama-guard-4-12b(0.1s), gliner-pii(0.1s)
    # VISIÓN: phi-4-multimodal(0.2s), llama-3.2-90b-vision(0.3s), llama-3.2-11b-vision(4.9s)
    # TRADUCCIÓN: riva-translate-4b-v1.1(0.2s)
    # EMBEDDINGS: todos 404 en esta cuenta — usar alternativa externa
    # Rate limit: 40 RPM global (no x-ratelimit headers — exponential backoff en 429)
    "nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "headers_extra": {},
    },
    # Anthropic — uses ANTHROPIC_API_KEY if set, otherwise falls back to
    # Claude Code CLI (`claude -p`) which uses OAuth credentials.
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
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
    # ── Tier C — Ollama local ────────────────────────────────────────────────
    "git-specialist":    ("ollama", "qwen2.5-coder:7b"),
    "content-automator": ("ollama", "qwen2.5-coder:7b"),

    # ── Tier B+ NIM — Código (DeepSeek V4 Flash: 1.4s, 1M ctx, confirmado) ──
    # Patrón: pseudocódigo → [nim] → code-validator [Opus] revisión estricta
    "python-specialist": ("nim", "deepseek-ai/deepseek-v4-flash-0731"),
    "web-specialist":    ("nim", "deepseek-ai/deepseek-v4-flash-0731"),
    "algo-specialist":   ("nim", "deepseek-ai/deepseek-v4-flash-0731"),
    "code-engineer":     ("nim", "deepseek-ai/deepseek-v4-flash-0731"),   # MetaGPT Engineer role
    "opt-analyst":       ("nim", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),  # optimization analysis
    "context-probe":     ("anthropic", "claude-haiku-4-5-20251001"),  # Haiku context bombardment

    # ── Tier B+ NIM — Alta calidad (Nemotron Super 49B v1.5) ────────────────
    # Reemplaza mistral-large-3-675b-instruct-2512, EOL/410 desde 2026-07-23.
    "research-analyst":  ("nim", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),
    "software-specialist":("nim", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),
    "data-specialist":   ("nim", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),
    "ai-ml-specialist":  ("nim", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),

    # ── Tier B+ NIM — Safety / Moderation (0.1s, confirmados) ───────────────
    "safety-checker":    ("nim", "nvidia/llama-3.1-nemoguard-8b-content-safety"),
    "content-safety":    ("nim", "meta/llama-guard-4-12b"),
    "pii-detector":      ("nim", "nvidia/gliner-pii"),

    # ── Tier B+ NIM — Vision (phi-4-multimodal: 0.2s, confirmado) ───────────
    "vision-specialist": ("nim", "microsoft/phi-4-multimodal-instruct"),

    # ── Tier B+ NIM — Traducción (riva: 0.2s, confirmado) ───────────────────
    "translate-specialist": ("nim", "nvidia/riva-translate-4b-instruct-v1.1"),

    # ── Tier B — Groq (dominio general, baja latencia) ───────────────────────
    "biology-specialist":   ("groq", "llama-3.3-70b-versatile"),
    "chemistry-specialist": ("groq", "llama-3.3-70b-versatile"),
    "economics-specialist": ("groq", "llama-3.3-70b-versatile"),
    "history-specialist":   ("groq", "llama-3.3-70b-versatile"),
    "language-specialist":  ("groq", "llama-3.3-70b-versatile"),
    "legal-specialist":     ("groq", "llama-3.3-70b-versatile"),
    "logic-specialist":     ("groq", "llama-3.3-70b-versatile"),
    "marketing-specialist": ("groq", "llama-3.3-70b-versatile"),
    "math-specialist":      ("groq", "llama-3.3-70b-versatile"),
    "nutrition-specialist": ("groq", "llama-3.3-70b-versatile"),  # palmyra-med 404
    "philosophy-specialist":("groq", "llama-3.3-70b-versatile"),
    "physics-specialist":   ("groq", "llama-3.3-70b-versatile"),
    "stats-specialist":     ("groq", "llama-3.3-70b-versatile"),
    "writing-specialist":   ("groq", "llama-3.3-70b-versatile"),

    # ── Tier S — Opus: revisión estricta post-generación ────────────────────
    # Recibe código generado + spec original + contexto proyecto. Ataca el código.
    "code-reviewer":  ("anthropic", "claude-opus-4-8"),
    "code-validator": ("anthropic", "claude-opus-4-8"),
    # hermes — NousResearch Hermes-3 405B (OpenRouter free, $0) — estrategia, analytics, datos
    "hermes":         ("openrouter", "nousresearch/hermes-3-llama-3.1-405b:free"),

    # ── Tier A — Sonnet: agentes de alto valor ───────────────────────────────
    "finance-specialist": ("anthropic", "claude-sonnet-4-6"),
    "auditor":            ("anthropic", "claude-sonnet-4-6"),
    "orchestrator":       ("anthropic", "claude-sonnet-4-6"),

    # ── Accounting-ERP ───────────────────────────────────────────────────────
    "customer-accountant": ("groq", "llama-3.3-70b-versatile"),
    "supplier-accountant": ("groq", "llama-3.3-70b-versatile"),
    "invoice-extractor":   ("groq", "llama-3.3-70b-versatile"),
    "tax-auditor":         ("anthropic", "claude-sonnet-4-6"),
    "closing-specialist":  ("anthropic", "claude-sonnet-4-6"),

    "default": ("groq", "llama-3.3-70b-versatile"),
}

# Agents locked to Tier C (Ollama) regardless of domain — never auto-escalated.
# python/web/algo-specialist ahora en NIM B+ (DeepSeek V4 Flash).
_TIER_C_AGENTS = frozenset({"git-specialist", "content-automator"})

# Fallback universal por proveedor (cuando el modelo primario falla)
# Fallback models — llm7 removed (0% success rate over 40 calls in 7d audit)
# Verificado en vivo 2026-08-11 (stress-routing.md #13):
#   - "openrouter" con sufijo ":free" -> 404 (retirado); slug correcto es "qwen/qwen3-coder"
#     PERO la cuenta no tiene créditos (402 "Insufficient credits") -> fallback
#     openrouter sigue caído hasta que se recarguen créditos (acción del usuario, no de código).
#   - "github" (models.inference.ai.azure.com) -> 404 (endpoint deprecado);
#     el endpoint nuevo (models.github.ai/inference) responde 410
#     "github_models_retirement_brownout" -> GitHub está retirando el servicio,
#     no es un fallo de token ni de endpoint mal escrito. No reparable en código.
_PROVIDER_DEFAULT_MODEL = {
    "ollama": "qwen2.5-coder:7b",
    "groq": "llama-3.3-70b-versatile",
    "github": "deepseek-v3-0324",
    "openrouter": "qwen/qwen3-coder",
    "pollinations": "openai",
    "anthropic": "claude-sonnet-4-6",
    "nim": "nvidia/llama-3.3-nemotron-super-49b-v1.5",  # sustituye al mistral-large-3-675b EOL (410)
}

# Cadena de fallback por proveedor primario
# Fallback chain — llm7 removed (0% success), anthropic added, nim added as B+
# 2026-08-16: `openrouter` y `github` eliminados como DESTINOS de fallback (openrouter
# sin créditos → 402; github retirado a nivel de plataforma → 404/410). Sus entradas en
# PROVIDERS/_PROVIDER_DEFAULT_MODEL se conservan intactas para reactivación de una línea.
FALLBACK_CHAIN = {
    "ollama": ["groq", "nim", "pollinations"],
    "openrouter": ["groq", "nim", "pollinations"],
    "groq": ["nim", "pollinations"],
    "nim": ["groq", "pollinations"],
    "github": ["groq", "nim", "pollinations"],
    "anthropic": ["groq", "nim", "pollinations"],
    "pollinations": [],
}

# ── No-downgrade guard (audit 2026-07-05, HIGH #5) ──────────────────────────
# Agents whose PRIMARY provider is Anthropic (Tier A/S). If the claude CLI/OAuth
# fails, these must FAIL LOUDLY (exit 2) instead of silently falling back to a
# free-tier model: an "adversarial Opus review" produced by Llama-70B is worse
# than no review. Derived from AGENT_ROUTING so it can never drift out of sync.
# Explicit opt-in escape hatch: DQIII8_ALLOW_DOWNGRADE=1.
_NO_DOWNGRADE = frozenset(
    agent for agent, (prov, _m) in AGENT_ROUTING.items() if prov == "anthropic"
)


def build_chain(
    primary_provider: str,
    primary_model: str,
    escalated_from_ollama: bool = False,
    allow_downgrade: bool | None = None,
) -> tuple[list[tuple[str, str]], bool]:
    """Build the ordered (provider, model) attempt chain for one call.

    Anthropic-tier primaries get NO free-tier fallback (see _NO_DOWNGRADE):
    returns ([(anthropic, model)], no_downgrade=True) so the caller can exit
    loudly on failure. All other providers keep their FALLBACK_CHAIN.
    """
    if allow_downgrade is None:
        allow_downgrade = os.environ.get("DQIII8_ALLOW_DOWNGRADE", "") == "1"
    no_downgrade = primary_provider == "anthropic" and not allow_downgrade
    chain: list[tuple[str, str]] = [(primary_provider, primary_model)]
    if not no_downgrade:
        for fb_provider in FALLBACK_CHAIN.get(primary_provider, []):
            chain.append(
                (fb_provider, _PROVIDER_DEFAULT_MODEL.get(fb_provider, "llama-3.3-70b-versatile"))
            )
        # When escalated from Ollama, add qwen as last-resort (offline fallback)
        if escalated_from_ollama:
            chain.append(("ollama", "qwen2.5-coder:7b"))
    return chain, no_downgrade


# ── Retry / backoff / circuit breaker (audit 2026-07-05, HIGH #4) ────────────
# Per-provider: up to _RETRY_ATTEMPTS on TRANSIENT errors (429/5xx/network),
# exponential backoff 1s→2s (+jitter). Fatal errors (401/403/404 auth/config)
# skip retries and move to the next provider immediately — satisfies the NIM
# invariant ("exponential backoff en 429") in 00_core_behavior.md.
# Circuit breaker state persists across wrapper invocations in a JSON file:
# _BREAKER_THRESHOLD consecutive failures open the circuit for
# _BREAKER_COOLDOWN_S seconds (then one half-open probe is allowed).
# Best-effort state (atomic replace, fail-open on any I/O error).
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 1.0
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_S = 120
_BREAKER_PATH = (
    Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / "var" / "circuit_breaker.json"
)

# Coste por 1K tokens (input, output) en USD — 0.0 = gratuito/local
TIER_COSTS: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "groq": (0.0, 0.0),
    "nim": (0.0, 0.0),
    "github": (0.0, 0.0),
    "llm7": (0.0, 0.0),
    "pollinations": (0.0, 0.0),
    "openrouter": (0.003, 0.015),  # Claude Sonnet pricing aprox.
    "anthropic": (0.003, 0.015),
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
    "B+": {
        "provider": "nim",
        "model": "meta/llama-3.3-70b-instruct",
        "cost_input_1k": 0.0,
        "cost_output_1k": 0.0,
        "desc": "NVIDIA NIM — $0, 40 RPM global, 1M ctx models",
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
        "model": "claude-opus-4-8",
        "cost_input_1k": 0.015,
        "cost_output_1k": 0.075,
        "desc": "Opus 4.8 planner — ~$0.15-0.50",
    },
    "S+": {
        "provider": "anthropic",
        "model": "claude-opus-4-8",
        "cost_input_1k": 0.015,
        "cost_output_1k": 0.075,
        "desc": "Opus 4.8 orchestrator — ~$0.50-2.00",
    },
}

# Priority order for tier comparison (lower index = higher priority = cheaper)
TIER_ORDER = {"C": 0, "B": 1, "B+": 1, "B++": 1, "A": 2, "S": 3, "S+": 4}

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
        "claude-opus-4-8",
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


def _resolve_project_for_log(project: str | None, session_id: str) -> str | None:
    """Stage 2: prefer an explicit project= arg, else consult the project_context
    SSOT via resolve_project(); fail open to None if the module can't be loaded."""
    if project:
        return project
    from core.action_log import resolve_project_safe

    return resolve_project_safe(session_id)


# ── Helpers ─────────────────────────────────────────────────────────────────


def sanitize_prompt(prompt: str) -> str:
    """Remove potential prompt-injection patterns before sending to a model."""
    import re

    dangerous_patterns = [
        r"ignore previous instructions",
        r"ignore all previous",
        r"ignore all instructions",
        r"disregard (?:(?:all |your |previous ){1,3})?instructions",
        r"system:\s*you are now",
        r"new (role|persona|instructions?|context)",
        r"you are now (a |an )?",
        r"act as (a |an )?(?!helpful)",  # allow "act as a helpful assistant"
        r"forget (everything|all|your instructions)",
        r"<\|system\|>",
        r"<\|assistant\|>",
        r"\[INST\]",
        r"###\s*(instruction|system|prompt)",
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
    dqiii8_root = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    md_path = dqiii8_root / ".claude" / "agents" / f"{agent_name}.md"
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
                    log.debug(
                        "domain lens: agent=%s domain=%s chunks=%s",
                        agent_name, domain, result["chunks_used"],
                    )
                    return result["system_prompt"]
        except Exception as _exc:
            log.warning("system_prompt extraction failed: %s", _exc)
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


def _stream_via_claude_cli(
    model: str, prompt: str, system_prompt: str = "", echo: bool = True
) -> tuple[str, int, int, bool, bool]:
    """Tier A fallback: call Claude Code CLI when ANTHROPIC_API_KEY is not set.

    Uses OAuth via ~/.claude/.credentials.json (same as dqiii8_bot /cc).
    Returns (text, tokens_in, tokens_out, success, retryable).
    """
    # prompt goes via stdin, not argv: a single subprocess argument is capped
    # at MAX_ARG_STRLEN (128KB on Linux) regardless of ARG_MAX, and a prompt
    # embedding a long plan/spec (e.g. panel-review over a multi-thousand-line
    # plan) blows past that — confirmed live 2026-08-13 ("Argument list too
    # long" on `claude`, same root cause already fixed in dispatch.py's
    # subprocess.run of the wrapper itself). `claude -p` with no value reads
    # the prompt from stdin.
    cmd = ["claude", "-p", "--output-format", "json", "--model", model]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    env = {**os.environ}
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            env=env,
        )
        raw = result.stdout.strip()
        text = raw
        cli_reported_error = result.returncode != 0
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                if data.get("is_error") or data.get("subtype") not in (None, "success"):
                    cli_reported_error = True
                text = data.get("result") or data.get("content") or raw
            except json.JSONDecodeError:
                pass
        if cli_reported_error:
            # The CLI ran and produced text, but flagged the call itself as
            # failed (bad/retired model, auth issue, etc.) — treating that
            # text as a real answer would silently defeat _NO_DOWNGRADE for
            # Tier A/S agents (found by stress test, 2026-08-11).
            log.warning("claude CLI reported failure (returncode=%s): %s", result.returncode, text[:200])
            return "", 0, 0, False, False
        if text:
            if echo:
                print(text, flush=True)
            tokens_in = len(prompt) // 4
            tokens_out = len(text) // 4
            return str(text).strip(), tokens_in, tokens_out, True, False
        # Ran but produced nothing → likely auth/model config; retry won't help
        return "", 0, 0, False, False
    except subprocess.TimeoutExpired as exc:
        log.warning("claude CLI timeout: %s", exc)
        return "", 0, 0, False, True  # transient — retryable
    except FileNotFoundError as exc:
        log.warning("claude CLI not found: %s", exc)
        return "", 0, 0, False, False  # fatal — CLI absent
    except Exception as exc:
        log.warning("claude CLI failed: %s", exc)
        return "", 0, 0, False, False


def _request_once(
    provider_name: str,
    model: str,
    prompt: str,
    system_prompt: str = "",
    echo: bool = True,
) -> tuple[str, int, int, bool, bool]:
    """One attempt against one provider.

    Returns (full_text, tokens_in, tokens_out, success, retryable):
      retryable=True  → transient (429/408/5xx/network/timeout) — worth retrying.
      retryable=False → fatal for this provider (auth/config 4xx) — skip retries.
    With echo=False output is fully buffered (nothing hits stdout), so a failed
    attempt can never contaminate the final response (audit 2026-07-05 P0-3).
    """
    # Anthropic without API key → delegate to Claude Code CLI (OAuth)
    if provider_name == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        return _stream_via_claude_cli(model, prompt, system_prompt, echo=echo)

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
                    return full_text, tokens_in, tokens_out, False, True
                # Capturar tokens reales si la API los devuelve (OpenRouter/Groq)
                # Guard against "usage": null in NIM streaming responses
                usage = chunk.get("usage") or {}
                if usage:
                    tokens_in = usage.get("prompt_tokens", tokens_in)
                    tokens_out = usage.get("completion_tokens", tokens_out)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    if echo:
                        print(token, end="", flush=True)
                    full_text += token
    except urllib.error.HTTPError as e:
        # 429/408/5xx = transient → retryable; other 4xx (401/403/404) = auth/config → fatal
        retryable = e.code in (408, 429, 500, 502, 503, 504)
        return full_text, tokens_in, tokens_out, False, retryable
    except (urllib.error.URLError, TimeoutError):
        return full_text, tokens_in, tokens_out, False, True

    if full_text and echo:
        print()  # newline final
    # Fallback to estimation if the API did not return usage
    if not tokens_in and not tokens_out:
        tokens_in = len(prompt) // 4
        tokens_out = len(full_text) // 4
    return full_text, tokens_in, tokens_out, bool(full_text), True


def stream_response(
    provider_name: str, model: str, prompt: str, system_prompt: str = ""
) -> tuple[str, int, int, bool]:
    """
    Makes the request and streams to stdout (compat shim over _request_once —
    kept 4-tuple for external callers: pal/engine.py, dqiii8_bot.py).
    Returns (full_text, tokens_input, tokens_output, success).
    Uses real API tokens if available; estimates by chars otherwise.
    """
    text, tokens_in, tokens_out, ok, _retryable = _request_once(
        provider_name, model, prompt, system_prompt, echo=True
    )
    return text, tokens_in, tokens_out, ok


# ── Circuit breaker helpers (file-backed, best-effort, fail-open) ────────────


def _breaker_load() -> dict:
    try:
        return json.loads(_BREAKER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _breaker_save(state: dict) -> None:
    try:
        _BREAKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _BREAKER_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, _BREAKER_PATH)
    except Exception as _exc:
        log.warning("circuit breaker save failed: %s", _exc)


def _breaker_allows(provider: str) -> bool:
    """True unless the provider's circuit is open and still cooling down."""
    entry = _breaker_load().get(provider)
    if not entry:
        return True
    if entry.get("failures", 0) < _BREAKER_THRESHOLD:
        return True
    if time.time() >= entry.get("opened_until", 0):
        return True  # cooldown elapsed → allow one half-open probe
    return False


def _breaker_record(provider: str, success: bool) -> None:
    state = _breaker_load()
    if success:
        if provider in state:
            state.pop(provider, None)
            _breaker_save(state)
        return
    entry = state.get(provider) or {"failures": 0, "opened_until": 0}
    entry["failures"] = int(entry.get("failures", 0)) + 1
    if entry["failures"] >= _BREAKER_THRESHOLD:
        entry["opened_until"] = time.time() + _BREAKER_COOLDOWN_S
        log.warning(
            "circuit OPEN for %s (%d consecutive failures, cooldown %ds)",
            provider, entry["failures"], _BREAKER_COOLDOWN_S,
        )
    state[provider] = entry
    _breaker_save(state)


def _call_with_retry(
    provider: str, model: str, prompt: str, system_prompt: str = ""
) -> tuple[str, int, int, bool]:
    """One provider attempt with retry/backoff + circuit breaker.

    Transient failures (429/5xx/network) retry up to _RETRY_ATTEMPTS with
    exponential backoff (1s, 2s + jitter). Fatal errors (auth/config 4xx) break
    immediately so the fallback chain moves on. Output is buffered per attempt —
    nothing reaches stdout until the caller decides (no partial+full concat).
    """
    import random

    if not _breaker_allows(provider):
        log.warning(
            "circuit open for %s — skipping provider (cooldown %ds)",
            provider, _BREAKER_COOLDOWN_S,
        )
        return "", 0, 0, False
    text, tokens_in, tokens_out = "", 0, 0
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        text, tokens_in, tokens_out, ok, retryable = _request_once(
            provider, model, prompt, system_prompt, echo=False
        )
        if ok:
            _breaker_record(provider, True)
            return text, tokens_in, tokens_out, True
        if not retryable:
            log.warning(
                "%s/%s fatal error (auth/config) — not retrying", provider, model
            )
            break
        if attempt < _RETRY_ATTEMPTS:
            delay = _RETRY_BASE_DELAY_S * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
            log.warning(
                "%s/%s attempt %d/%d failed — retrying in %.1fs",
                provider, model, attempt, _RETRY_ATTEMPTS, delay,
            )
            time.sleep(delay)
    _breaker_record(provider, False)
    return text, tokens_in, tokens_out, False


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
    project: str | None = None,
    request_id: str | None = None,
    task_complexity: str | None = None,
) -> None:
    """Registra la llamada en agent_actions con tokens reales y coste estimado."""
    if not DB_PATH.exists():
        return
    try:
        cost_in, cost_out = TIER_COSTS.get(provider, (0.0, 0.0))
        cost_usd = (tokens_in / 1000.0) * cost_in + (tokens_out / 1000.0) * cost_out
        # Correct tier labeling (audit 2026-07-05 MED #8: nim/github/pollinations
        # were all mislabeled "C", corrupting tier/cost analytics)
        _provider_tier = {
            "ollama": "C", "groq": "B", "openrouter": "B", "pollinations": "B",
            "nim": "B+", "github": "B++",
        }
        if provider == "anthropic":
            tier = "S" if "opus" in model.lower() else "A"
        else:
            tier = _provider_tier.get(provider, "C")
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        # Stage 1: this is a single-shot log written after the call already
        # completed — end_time_ms is derivable directly, not left NULL like the
        # hook-driven rows that close asynchronously.
        _end_time_ms = int(time.time() * 1000)
        _start_time_ms = _end_time_ms - duration_ms
        cur = conn.execute(
            "INSERT INTO agent_actions "
            "(session_id, agent_name, tool_used, action_type, model_used, "
            "tokens_used, tokens_input, tokens_output, estimated_cost_usd, tier, "
            "duration_ms, success, error_message, start_time_ms, end_time_ms, project, domain, request_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                _start_time_ms,
                _end_time_ms,
                _resolve_project_for_log(project, session_id),
                domain or None,
                request_id,
            ),
        )
        conn.commit()
        action_id = cur.lastrowid
        # Link failure to error_log so audit Component_2 (pipeline integrity) stays intact
        if not success and error_message:
            try:
                conn.execute(
                    "INSERT INTO error_log "
                    "(timestamp, session_id, agent_name, error_type, error_message, "
                    "keywords, severity, resolved, action_id) "
                    "VALUES (datetime('now'), ?, ?, ?, ?, ?, 'transient', 0, ?)",
                    (
                        session_id,
                        agent,
                        f"{provider}Error",
                        error_message[:500],
                        json.dumps([agent, provider, model]),
                        action_id,
                    ),
                )
                conn.commit()
            except Exception as _elog_exc:
                log.warning("error_log insert failed: %s", _elog_exc)
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
            except Exception as _exc:
                log.warning("DB log write failed (action_id=%s): %s", action_id, _exc)
                pass  # fail-open, never block the pipeline
        # model_satisfaction — per-call technical outcome for routing feedback
        try:
            conn.execute(
                "INSERT INTO model_satisfaction "
                "(session_id, model_used, task_type, duration_ms, technical_success, tier_used) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    f"{provider}/{model}",
                    domain or None,
                    duration_ms,
                    1 if success else 0,
                    tier,
                ),
            )
            conn.commit()
        except Exception as _exc:
            log.warning("model_satisfaction insert failed: %s", _exc)
        conn.close()
        # Token usage granular tracking
        log_token_usage(
            session_id,
            f"{provider}/{model}",
            tier,
            agent,
            tokens_in,
            tokens_out,
            cost_usd,
            task_complexity=task_complexity,
        )
    except Exception as _exc:
        log.warning("DB logging block failed: %s", _exc)
        pass  # Fail-open: failure must not break pipeline


def log_token_usage(
    session_id: str,
    model: str,
    tier: str,
    operation: str,
    tokens_in: int,
    tokens_out: int,
    cost_estimate: float,
    source: str = "openrouter_wrapper",
    task_complexity: str | None = None,
) -> None:
    """Insert one row into token_usage. Fail-open — never blocks the pipeline."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.execute(
            "INSERT INTO token_usage "
            "(session_id, model, tier, operation, input_tokens, output_tokens, "
            "total_tokens, cost_estimate, source, task_complexity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                model,
                tier,
                operation,
                tokens_in,
                tokens_out,
                tokens_in + tokens_out,
                round(cost_estimate, 6),
                source,
                task_complexity,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as _exc:
        log.warning("token_usage insert failed: %s", _exc)


def _log_escalation(
    session_id: str, agent: str, from_provider: str, from_model: str, reason: str
) -> None:
    """Registra un escalado de fallback en error_log con keyword ESCALATION."""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
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
    except Exception as _exc:
        log.warning("%s: %s", __name__, _exc)


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
        "Fallback chain (Tier C): Ollama → OpenRouter → Groq → Pollinations"
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
    except Exception as _exc:
        log.warning("%s: %s", __name__, _exc)

    print(f"tier={tier} provider={provider} model={model} route={route}{domain_suffix}")


# ── Main ─────────────────────────────────────────────────────────────────────


def _enforce_sensitive_permissions() -> None:
    """Ensure sensitive files and dirs have owner-only permissions at startup."""
    import stat

    root = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    # Active files → 600 (owner read-write only).
    # session_memory moved to dqiii8.db (working_memory.py) in the 2026-08-14
    # db-consolidation; dqiii8_history.db is now a frozen pre-migration archive,
    # still chmod'd defensively since it retains a copy of the same data.
    for rel in (".env", "database/dqiii8.db", "database/dqiii8_history.db",
                "database/dqiii8_knowledge.db"):
        path = root / rel
        if path.exists() and not path.is_symlink():
            current = path.stat().st_mode & 0o777
            if current not in (0o600, 0o640):
                try:
                    os.chmod(str(path), stat.S_IRUSR | stat.S_IWUSR)
                except OSError as _exc:
                    log.warning("chmod %s failed: %s", path, _exc)
    # Database directory → 700 (owner only)
    db_dir = root / "database"
    if db_dir.exists():
        current_dir = db_dir.stat().st_mode & 0o777
        if current_dir != 0o700:
            try:
                os.chmod(str(db_dir), 0o700)
            except OSError as _exc:
                log.warning("chmod database/ failed: %s", _exc)


def main() -> None:
    _enforce_sensitive_permissions()

    # Subcommand: classify <prompt>
    if len(sys.argv) >= 2 and sys.argv[1] == "classify":
        raw = " ".join(sys.argv[2:]).strip()
        # Sanitize shell metacharacters from CLI input (Fix RT-010)
        raw = raw.replace("`", "").replace("$(", "(").replace("${", "{")
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
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip DQ enrichment pipeline (benchmark DQ OFF mode)",
    )
    parser.add_argument(
        "--project",
        default="",
        help="Active project name for knowledge-scoped retrieval (B10)",
    )
    args = parser.parse_args()

    # Also honour env-var form (used by benchmark subprocess calls)
    _skip_enrich = args.no_enrich or os.environ.get("DQ_SKIP_ENRICHER", "") == "1"

    if args.list:
        print_routing_table()
        sys.exit(0)

    # Resolver prompt
    if args.prompt:
        prompt = args.prompt
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        log.error("no prompt provided — use stdin or pass a prompt argument")
        sys.exit(1)

    if not prompt:
        log.error("empty prompt")
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
    except Exception as _exc:
        log.warning("working_memory load failed: %s", _exc)
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
        if (
            (not _skip_enrich)
            and _dc_path.exists()
            and _ke_path.exists()
            and _ia_path.exists()
        ):
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
                # B10: active project comes from the --project arg only —
                # there is no --cwd arg, so CWD-based detection never ran
                # (removed 2026-08-11, was dead code with UnboundLocalError risk).
                _project = args.project or ""
                _chunks = _ke.get_relevant_chunks(
                    prompt,
                    _domain,
                    intent=_intent,
                    entity=_entity,
                    project=_project,
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
                            log.debug(
                                "confidence gate: skip enrichment domain=%s tier=%d chunks=%d",
                                _domain, _gate_tier, len(_chunks),
                            )
                            _chunks = []
                except Exception as _exc:
                    log.warning("confidence gate failed: %s", _exc)
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
                    log.debug(
                        "pipeline: domain=%s chunks=%d intent=%s tier=%s",
                        _domain, _knowledge_chunks,
                        _ia_result["intent"], _ia_result["tier"],
                    )
    except Exception as _exc:
        log.warning("%s: %s", __name__, _exc)

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
                    log.debug(
                        "domain selector: %s domain=%s", _sel_agent, _routing_domain
                    )
        except Exception as _exc:
            log.warning("selector/enricher failed: %s", _exc)
            pass  # selector failure → continue with default system prompt

    # Resolver proveedor y modelo
    if args.model:
        # Detect provider from model prefix (e.g. "groq/llama-..." → groq)
        _model_parts = args.model.split("/", 1)
        if len(_model_parts) == 2 and _model_parts[0] in PROVIDERS:
            primary_provider = _model_parts[0]
            primary_model = _model_parts[1]
        else:
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
        log.info("Tier C skipped: domain=%s, escalated to B", _routing_domain)
        primary_provider = "groq"
        primary_model = "llama-3.3-70b-versatile"
        _escalated_from_ollama = True

    # Load agent system prompt — domain specialists get dynamic lens + knowledge
    system_prompt = load_agent_system_prompt(agent_name, prompt)
    if not system_prompt and _domain_system:
        system_prompt = _domain_system
    if system_prompt:
        log.debug("system prompt loaded: %s (%d chars)", agent_name, len(system_prompt))

    # Construir cadena: primario + fallbacks.
    # Anthropic-tier primaries get NO free-tier fallback (_NO_DOWNGRADE) — they
    # fail loudly (exit 2) instead of silently downgrading to Llama-70B.
    chain, _no_downgrade = build_chain(
        primary_provider, primary_model, escalated_from_ollama=_escalated_from_ollama
    )
    if _no_downgrade:
        log.info(
            "no-downgrade guard active: %s is Anthropic-tier — free-tier fallback "
            "disabled (DQIII8_ALLOW_DOWNGRADE=1 to opt in)",
            agent_name,
        )

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
        except Exception as _exc:
            log.warning("working_memory session context failed: %s", _exc)
            pass  # fail-open

    # Intentar cada proveedor en orden (con retry/backoff + circuit breaker).
    # La salida se bufferiza por intento y solo se emite tras éxito — un intento
    # fallido nunca contamina stdout con respuesta parcial.
    # Stage 3: one request_id shared by every attempt in this cascade, so
    # agent_actions rows from a failed primary + successful fallback can be
    # grouped as one logical request afterward.
    from core.action_log import generate_request_id
    from bin.orchestrator import classify_task_complexity

    _request_id = generate_request_id()
    _task_complexity = classify_task_complexity(_original_prompt)

    for provider, model in chain:
        log.info("%s | %s | %s", agent_name, provider, model)
        t0 = int(time.time() * 1000)
        text, tokens_in, tokens_out, ok = _call_with_retry(
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
            session_id=_session_id or "cli",
            error_message=err_msg,
            domain=_routing_domain or "",
            prompt_hash=_phash,
            project=args.project or None,
            request_id=_request_id,
            task_complexity=_task_complexity,
        )

        if ok:
            # Machine-readable line on stderr with the provider/model that
            # actually answered — dispatch.py's static AGENT_ROUTING lookup
            # reported the *intended* provider even when a fallback served
            # the request (found by stress test, 2026-08-11).
            print(
                f"__DQ_META__ {json.dumps({'provider': provider, 'model': model})}",
                file=sys.stderr, flush=True,
            )
            print(text, flush=True)
            if _wm and _session_id:
                try:
                    _wm.save_exchange(
                        _session_id, _original_prompt, text[:300], _enriched_domain
                    )
                except Exception as _exc:
                    log.warning("working_memory save_exchange failed: %s", _exc)
                    pass  # fail-open
            sys.exit(0)

        log.warning("%s failed — trying next...", provider)
        _log_escalation("cli", agent_name, provider, model, err_msg)

    if _no_downgrade:
        log.error(
            "Anthropic-tier call FAILED for agent '%s' and downgrade is disabled "
            "(_NO_DOWNGRADE). NOT falling back to a free-tier model. Fix the "
            "claude CLI / OAuth credentials, or set DQIII8_ALLOW_DOWNGRADE=1 to "
            "permit an explicit downgrade.",
            agent_name,
        )
        print(
            f"ERROR: anthropic-tier call failed for agent '{agent_name}'; "
            "free-tier downgrade disabled (_NO_DOWNGRADE). See error_log.",
            file=sys.stderr,
        )
        sys.exit(2)

    log.error("all providers failed")
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
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
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
    except Exception as _exc:
        log.warning("routing_feedback query failed: %s", _exc)
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
