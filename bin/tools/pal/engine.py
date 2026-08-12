#!/usr/bin/env python3
"""
PAL Engine — Provider Abstraction Layer business logic.
Wraps openrouter_wrapper.py as SSOT; never reimplements routing/keys/allowlist.
"""

import contextlib
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from typing import Any

from core.openrouter_wrapper import (
    AGENT_ROUTING,
    FALLBACK_CHAIN,
    PROVIDERS,
    stream_response,
    get_recommendation,
    log_to_db,
)

# Canonical model per provider (used when fallback chain fires without explicit model)
_PROVIDER_DEFAULT_MODEL = {
    "ollama": "qwen2.5-coder:7b",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "qwen/qwen3-coder:free",
    "github": "deepseek-v3-0324",
    "pollinations": "openai",
    "anthropic": "claude-sonnet-4-6",
}

# Default cheap model set for benchmark when none specified
_BENCHMARK_DEFAULTS = [
    "ollama/qwen2.5-coder:7b",
    "groq/llama-3.3-70b-versatile",
    "openrouter/qwen/qwen3-coder:free",
]


def parse_model_spec(spec: str) -> tuple[str, str]:
    """Parse 'provider/model' or bare model name → (provider, model).
    First '/' split wins; openrouter model slashes are preserved in model part.
    """
    for pname in PROVIDERS:
        prefix = pname + "/"
        if spec.startswith(prefix):
            return pname, spec[len(prefix):]
    # No provider prefix — try to match against known routing values
    for agent, (prov, mdl) in AGENT_ROUTING.items():
        if mdl == spec:
            return prov, mdl
    return "ollama", spec


def _call_once(
    provider: str,
    model: str,
    prompt: str,
    system_prompt: str,
    max_tokens: int,
) -> tuple[str, int, int, bool]:
    """Call stream_response with stdout captured (prevents JSON-RPC contamination)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        # Pass max_tokens via monkey-patch of the module-level TIMEOUT would be fragile;
        # the wrapper doesn't accept max_tokens arg, so we live with its default (4096).
        # TODO: patch when openrouter_wrapper exposes max_tokens param.
        text, tin, tout, ok = stream_response(provider, model, prompt, system_prompt)
    if max_tokens and len(text) > max_tokens * 4:
        text = text[: max_tokens * 4]
    return text, tin, tout, ok


def _strip_code_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences (```lang ... ```)."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def generate(
    prompt: str,
    model: str | None = None,
    task_type: str | None = None,
    system_prompt: str = "",
    max_tokens: int = 2048,
    allow_fallback: bool = True,
    strip_fences: bool = False,
    project: str | None = None,
) -> dict[str, Any]:
    provider, mdl = _resolve_provider_model(model, task_type)
    t0 = time.time()
    text, tin, tout, ok = _call_once(provider, mdl, prompt, system_prompt, max_tokens)
    fell_back_to = None

    if not ok and allow_fallback:
        chain = FALLBACK_CHAIN.get(provider, [])
        for fb_provider in chain:
            fb_model = _PROVIDER_DEFAULT_MODEL.get(fb_provider, "")
            if not fb_model:
                continue
            text, tin, tout, ok = _call_once(fb_provider, fb_model, prompt, system_prompt, max_tokens)
            if ok:
                fell_back_to = f"{fb_provider}/{fb_model}"
                provider, mdl = fb_provider, fb_model
                break

    latency_ms = int((time.time() - t0) * 1000)
    cost_usd = 0.0  # all current providers are $0; extend if paid tiers used

    if strip_fences:
        text = _strip_code_fences(text)

    log_to_db(
        agent="pal:generate",
        model=mdl,
        provider=provider,
        tokens_in=tin,
        tokens_out=tout,
        duration_ms=latency_ms,
        success=ok,
        session_id="pal-mcp",
        domain=task_type or "",
        project=project,
    )

    return {
        "text": text,
        "provider": provider,
        "model": mdl,
        "tokens_in": tin,
        "tokens_out": tout,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "fell_back_to": fell_back_to,
        "success": ok,
    }


def route(task_type: str | None = None, prompt: str | None = None) -> dict[str, Any]:
    if task_type and task_type in AGENT_ROUTING:
        provider, mdl = AGENT_ROUTING[task_type]
        source = "AGENT_ROUTING"
        score = None
        samples = None
    elif task_type:
        mdl, score, samples = get_recommendation(task_type)
        provider, _ = _resolve_provider_model(mdl, None)
        source = "historical_satisfaction"
    else:
        provider, mdl = AGENT_ROUTING.get("default", ("groq", "llama-3.3-70b-versatile"))
        source = "default"
        score = None
        samples = None

    cost_usd = 0.0
    return {
        "provider": provider,
        "model": mdl,
        "source": source,
        "score": score,
        "samples": samples,
        "cost_usd": cost_usd,
        "spec": f"{provider}/{mdl}",
    }


def models(health_check: bool = False) -> dict[str, Any]:
    result = {}
    for name, cfg in PROVIDERS.items():
        entry: dict[str, Any] = {
            "base_url": cfg["base_url"],
            "requires_key": cfg["api_key_env"] is not None,
            "default_model": _PROVIDER_DEFAULT_MODEL.get(name, ""),
        }
        if health_check:
            entry["available"] = _ping_provider(name, cfg)
        result[name] = entry
    return {
        "providers": result,
        "agent_routing_sample": {k: f"{v[0]}/{v[1]}" for k, v in list(AGENT_ROUTING.items())[:8]},
    }


def benchmark(
    prompt: str,
    model_specs: list[str] | None = None,
    system_prompt: str = "",
    max_tokens: int = 1024,
    judge: bool = False,
    timeout_s: int = 90,
) -> dict[str, Any]:
    specs = model_specs if model_specs else _BENCHMARK_DEFAULTS
    results = []

    def _run_one(spec: str) -> dict[str, Any]:
        provider, mdl = parse_model_spec(spec)
        t0 = time.time()
        try:
            text, tin, tout, ok = _call_once(provider, mdl, prompt, system_prompt, max_tokens)
            latency_ms = int((time.time() - t0) * 1000)
            return {
                "model": spec,
                "ok": ok,
                "latency_ms": latency_ms,
                "tokens_out": tout,
                "cost_usd": 0.0,
                "text": text,
            }
        except Exception as exc:
            latency_ms = int((time.time() - t0) * 1000)
            return {"model": spec, "ok": False, "error": str(exc), "latency_ms": latency_ms}

    max_workers = min(len(specs), 6)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, spec): spec for spec in specs}
        for fut in as_completed(futures, timeout=timeout_s + 5):
            try:
                results.append(fut.result(timeout=1))
            except Exception as exc:
                results.append({"model": futures[fut], "ok": False, "error": str(exc), "latency_ms": timeout_s * 1000})

    if judge and results:
        results = _judge_results(prompt, results)

    # Sort by ok desc, latency asc
    results.sort(key=lambda r: (not r.get("ok"), r.get("latency_ms", 999999)))
    winner = next((r["model"] for r in results if r.get("ok")), None)

    table = _render_table(results, judge)
    return {"prompt_chars": len(prompt), "results": results, "table": table, "winner": winner}


# ── Private helpers ──────────────────────────────────────────────────────────

def _resolve_provider_model(model: str | None, task_type: str | None) -> tuple[str, str]:
    if model:
        return parse_model_spec(model)
    if task_type and task_type in AGENT_ROUTING:
        return AGENT_ROUTING[task_type]
    return AGENT_ROUTING.get("default", ("groq", "llama-3.3-70b-versatile"))


def _ping_provider(name: str, cfg: dict) -> bool:
    import urllib.request, urllib.error, os
    try:
        if name == "ollama":
            url = "http://localhost:11434/api/tags"
        else:
            url = cfg["base_url"].rstrip("/") + "/models"
        req = urllib.request.Request(url, method="GET")
        if cfg.get("api_key_env"):
            key = os.environ.get(cfg["api_key_env"], "")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        # 401/403 = reachable but needs auth → provider is up
        return e.code in (401, 403)
    except Exception:
        return False


def _judge_results(prompt: str, results: list[dict]) -> list[dict]:
    """Score each result 1-10 via groq/llama. Adds 'quality' field."""
    def _score_one(r: dict) -> dict:
        if not r.get("ok") or not r.get("text"):
            return {**r, "quality": None}
        judge_prompt = (
            f"Rate the following response to this prompt on a scale of 1-10 for quality "
            f"(accuracy, completeness, clarity). Output ONLY the integer score.\n\n"
            f"PROMPT: {prompt[:300]}\n\nRESPONSE: {r['text'][:500]}"
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            text, _, _, ok = stream_response("groq", "llama-3.3-70b-versatile", judge_prompt, "")
        try:
            score = int(text.strip().split()[0])
            score = max(1, min(10, score))
        except (ValueError, IndexError):
            score = None
        return {**r, "quality": score}

    with ThreadPoolExecutor(max_workers=min(len(results), 6)) as pool:
        return list(pool.map(_score_one, results))


def _render_table(results: list[dict], judge: bool) -> str:
    header = "| model | ok | latency_ms | tok_out | cost |"
    sep = "|---|---|---|---|---|"
    if judge:
        header += " quality |"
        sep += "---|"
    rows = [header, sep]
    for r in results:
        ok_s = "✅" if r.get("ok") else "❌"
        lat = r.get("latency_ms", "-")
        tok = r.get("tokens_out", "-")
        cost = f"${r.get('cost_usd', 0.0):.4f}"
        row = f"| {r['model']} | {ok_s} | {lat} | {tok} | {cost} |"
        if judge:
            row += f" {r.get('quality', '-')} |"
        rows.append(row)
    return "\n".join(rows)
