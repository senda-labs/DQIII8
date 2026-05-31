"""DQIII8 provider abstractions.

Defines the Provider contract that any LLM tier provider must implement.
Legacy wrappers (openrouter_wrapper.py, github_models_wrapper.py) still use
the PROVIDERS dict pattern — this package is the new target for future
consolidation.
"""

from .base import PROVIDER_REGISTRY, Provider, ProviderResponse, register_provider

__all__ = ["Provider", "ProviderResponse", "PROVIDER_REGISTRY", "register_provider"]
