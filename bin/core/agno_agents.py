#!/usr/bin/env python3
"""
DQIII8 — Agno AgentOS Registry

Wraps the dqiii8 ``AGENT_ROUTING`` table (SSOT in ``openrouter_wrapper.py``)
into Agno ``Agent`` objects with SQLite-backed session memory.

Provider routing:
  - nim       → agno.models.nvidia.Nvidia   (NVIDIA_API_KEY, no OPENAI_API_KEY needed)
  - groq      → agno.models.groq.Groq       (GROQ_API_KEY, no OPENAI_API_KEY needed)
  - github    → agno.models.openai.OpenAIChat (GITHUB_TOKEN as api_key)
  - openrouter→ agno.models.openai.OpenAIChat (OPENROUTER_API_KEY as api_key)
  - ollama    → dispatch() subprocess (no Agno model)
  - anthropic → dispatch() subprocess (OAuth via Claude CLI)

Usage:
    from bin.core.agno_agents import AgentRegistry
    registry = AgentRegistry()
    out = registry.run("research-analyst", "What is a semaphore?", session_id="s1")
    # {"response": str, "agent": str, "provider": str, "model": str, "latency_ms": int}
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from bin.core.logging_config import get_logger as _get_logger

log = _get_logger(__name__)

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
_DEFAULT_DB = str(DQIII8_ROOT / "database" / "dqiii8.db")

# Providers with no Agno model — always use dispatch() subprocess.
_FALLBACK_PROVIDERS = frozenset({"ollama", "anthropic"})

# Substrings that indicate a silent auth/config failure in Agno response text.
_AGNO_ERROR_MARKERS = (
    "OPENAI_API_KEY",
    "api key",
    "authentication",
    "Unauthorized",
    "401",
    "invalid_api_key",
)

_ENV_LOADED = False


def _load_env_once() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_file = DQIII8_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            pass
    _ENV_LOADED = True


def _is_agno_error_response(text: str) -> bool:
    """Return True if the response string signals an Agno auth/config failure."""
    lo = text.lower()
    return any(m.lower() in lo for m in _AGNO_ERROR_MARKERS)


class DqAgentModel:
    """Builds a native Agno model for any dqiii8 AGENT_ROUTING agent.

    Uses provider-native Agno classes (Nvidia, Groq) to avoid the silent
    OPENAI_API_KEY failure bug when using OpenAIChat with a custom base_url.
    Falls back to OpenAIChat only for providers without a native Agno class
    (github, openrouter) where an explicit api_key is always available.
    """

    _BASE_URLS = {
        "github": "https://models.inference.ai.azure.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    @classmethod
    def for_agent(cls, agent_name: str, timeout: int = 120):
        """Return a native Agno model, or None if dispatch() should be used."""
        _load_env_once()

        from bin.core.openrouter_wrapper import AGENT_ROUTING, PROVIDERS

        provider, model_id = AGENT_ROUTING.get(
            agent_name, AGENT_ROUTING.get("default", ("groq", "llama-3.3-70b-versatile"))
        )
        if provider in _FALLBACK_PROVIDERS:
            return None

        cfg = PROVIDERS.get(provider, {})
        api_key_env = cfg.get("api_key_env")
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""

        try:
            if provider == "nim":
                from agno.models.nvidia import Nvidia
                return Nvidia(id=model_id)

            if provider == "groq":
                from agno.models.groq import Groq
                return Groq(id=model_id)

            # github / openrouter: OpenAI-compatible, need explicit api_key.
            base_url = cfg.get("base_url") or cls._BASE_URLS.get(provider)
            if not base_url or not api_key:
                log.warning(
                    "DqAgentModel: missing base_url or api_key for provider=%s, falling back",
                    provider,
                )
                return None
            from agno.models.openai import OpenAIChat
            return OpenAIChat(id=model_id, base_url=base_url, api_key=api_key, timeout=timeout)

        except Exception as _exc:
            log.warning("DqAgentModel.for_agent(%s) failed: %s", agent_name, _exc)
            return None


class AgentRegistry:
    """
    Registry that wraps AGENT_ROUTING into Agno Agents with SQLite sessions.

    Falls back to ``dispatch()`` for ollama/anthropic providers, model build
    failures, and Agno responses that signal silent auth errors.
    """

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path
        self._db = None  # lazy Agno SqliteDb

    def _get_db(self):
        if self._db is None:
            try:
                from agno.db.sqlite import SqliteDb

                self._db = SqliteDb(
                    db_file=self._db_path,
                    session_table="agno_sessions",
                )
            except Exception as _exc:
                log.warning("Agno SqliteDb init failed: %s", _exc)
                self._db = False  # sentinel: tried and failed
        return self._db or None

    def _resolve_meta(self, agent_name: str) -> tuple[str, str]:
        from bin.core.openrouter_wrapper import AGENT_ROUTING

        return AGENT_ROUTING.get(
            agent_name, AGENT_ROUTING.get("default", ("groq", "llama-3.3-70b-versatile"))
        )

    def run(
        self,
        agent_name: str,
        prompt: str,
        session_id: Optional[str] = None,
        timeout: int = 120,
    ) -> dict:
        """
        Run an agent. Returns:
            {"response", "agent", "provider", "model", "latency_ms",
             "status", "backend"}
        """
        provider, model_id = self._resolve_meta(agent_name)
        model = DqAgentModel.for_agent(agent_name, timeout=timeout)

        # Fallback path: ollama / anthropic / model build failure → dispatch()
        if model is None:
            return self._dispatch_fallback(agent_name, prompt, provider, model_id, timeout)

        # Agno path
        t0 = time.time()
        try:
            from agno.agent import Agent

            kwargs = {"name": agent_name, "model": model}
            db = self._get_db()
            if db is not None and session_id:
                kwargs["db"] = db
                kwargs["session_id"] = session_id
                kwargs["add_history_to_context"] = True
                kwargs["num_history_runs"] = 3

            agent = Agent(**kwargs)
            output = agent.run(prompt)
            response = getattr(output, "content", None) or str(output)

            # Health-check: detect silent auth errors returned as response text.
            if not response or _is_agno_error_response(response):
                log.warning(
                    "Agno(%s) returned error response, falling back to dispatch: %.120s",
                    agent_name,
                    response,
                )
                return self._dispatch_fallback(agent_name, prompt, provider, model_id, timeout)

            return {
                "response": response,
                "agent": agent_name,
                "provider": provider,
                "model": model_id,
                "latency_ms": int((time.time() - t0) * 1000),
                "status": "ok",
                "backend": "agno",
            }

        except Exception as _exc:
            log.warning("Agno run(%s) failed, falling back to dispatch: %s", agent_name, _exc)
            return self._dispatch_fallback(agent_name, prompt, provider, model_id, timeout)

    def _dispatch_fallback(
        self,
        agent_name: str,
        prompt: str,
        provider: str,
        model_id: str,
        timeout: int,
    ) -> dict:
        from bin.core.dispatch import dispatch

        res = dispatch(agent_name, prompt, timeout=timeout)
        return {
            "response": res.get("response", ""),
            "agent": agent_name,
            "provider": res.get("provider", provider),
            "model": res.get("model", model_id),
            "latency_ms": res.get("latency_ms", 0),
            "status": res.get("status", "ok"),
            "backend": "dispatch",
        }

    def run_parallel(self, tasks: list[dict], max_workers: int = 6) -> list[dict]:
        """
        Run multiple agent tasks in parallel.

        Each task: {agent, prompt, session_id?, timeout?}
        Returns results in the same order as input (mirrors dispatch_parallel).
        """
        results: list[Optional[dict]] = [None] * len(tasks)

        def _run(idx: int, task: dict):
            return idx, self.run(
                agent_name=task["agent"],
                prompt=task["prompt"],
                session_id=task.get("session_id"),
                timeout=task.get("timeout", 120),
            )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run, i, t): i for i, t in enumerate(tasks)}
            for fut in as_completed(futures):
                idx, result = fut.result()
                results[idx] = result

        return results


if __name__ == "__main__":
    import json
    import sys

    _agent = sys.argv[1] if len(sys.argv) > 1 else "research-analyst"
    _prompt = " ".join(sys.argv[2:]) or "Say hello in one sentence."
    print(json.dumps(AgentRegistry().run(_agent, _prompt, session_id="cli-test"), indent=2))
