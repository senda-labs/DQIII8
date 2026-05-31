"""Provider abstract base class — contract for every LLM tier provider.

Status: interface only. Not enforced yet — `openrouter_wrapper.py` and
`github_models_wrapper.py` still use the legacy `PROVIDERS` dict pattern.

Future refactor: each provider (Ollama, Groq, GitHub Models, OpenRouter,
Anthropic) becomes a subclass registered via `@register_provider("name")`,
and the wrappers route through `PROVIDER_REGISTRY[name]()` instead of
hand-coded if/elif chains.

Design goals:
  - Single contract for all tiers (C/B/B+/A/S)
  - Streaming-first (tokens arrive as available)
  - Cost-aware (paid tiers override `cost_estimate`)
  - Health-check separable from a real call (cheap probe for routing decisions)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class ProviderResponse:
    """Result of a single tier provider call.

    `text`: full response body (empty if streamed and not collected)
    `tokens_in/out`: best-effort counts (some providers don't report; 0 = unknown)
    `success`: True if the call completed without HTTP error or upstream failure
    `error`: short failure description (provider/model-specific)
    `elapsed_ms`: total wall time including network
    `model`: actual model id used (may differ from requested if provider remapped)
    """

    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    success: bool = True
    error: str | None = None
    elapsed_ms: int = 0
    model: str = ""


class Provider(ABC):
    """Contract for any LLM provider feeding the DQIII8 tier router.

    Subclasses must set the four class attributes (name, base_url, api_key_env,
    tier) and implement `is_available`, `call`, and `stream_call`.
    """

    name: str  # canonical id — "ollama", "groq", "github_models", ...
    base_url: str
    api_key_env: str | None  # env var holding the key, or None for unauthenticated
    tier: str  # "C" | "B" | "B+" | "A" | "S"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True iff the provider is reachable AND credentials are set.

        Implementations should be cheap — used by the router to skip dead
        providers without paying a full call. A bare TCP/HTTPS probe to
        `base_url` is usually enough.
        """
        ...

    @abstractmethod
    def call(
        self,
        prompt: str,
        model: str,
        system_prompt: str = "",
        timeout_s: int = 60,
    ) -> ProviderResponse:
        """Synchronous call. Returns the full response in `ProviderResponse.text`."""
        ...

    @abstractmethod
    def stream_call(
        self,
        prompt: str,
        model: str,
        system_prompt: str = "",
        timeout_s: int = 60,
    ) -> Iterator[str]:
        """Yield response tokens as they arrive (SSE / streaming).

        Implementations must handle reconnection on transient errors and
        raise on terminal failures (auth, model-not-found, rate-limit-exceeded).
        """
        ...

    def cost_estimate(self, tokens_in: int, tokens_out: int) -> float:
        """USD cost for a call. Default: free tier (C/B/B+).

        Paid providers (Anthropic, OpenRouter paid models) must override
        with their per-1k token pricing.
        """
        return 0.0

    def __repr__(self) -> str:
        return f"<Provider name={self.name!r} tier={self.tier!r}>"


# ── Registry ──────────────────────────────────────────────────────────────────

PROVIDER_REGISTRY: dict[str, type[Provider]] = {}


def register_provider(name: str):
    """Decorator: register a Provider subclass under `name` in `PROVIDER_REGISTRY`.

    Usage:
        @register_provider("groq")
        class GroqProvider(Provider):
            name = "groq"
            base_url = "https://api.groq.com/openai/v1"
            api_key_env = "GROQ_API_KEY"
            tier = "B"
            ...
    """

    def _decorator(cls: type[Provider]) -> type[Provider]:
        if not issubclass(cls, Provider):
            raise TypeError(f"{cls.__name__} must subclass Provider")
        if name in PROVIDER_REGISTRY:
            raise ValueError(f"Provider {name!r} already registered")
        PROVIDER_REGISTRY[name] = cls
        return cls

    return _decorator
