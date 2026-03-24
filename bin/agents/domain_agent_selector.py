"""
domain_agent_selector.py — Select domain specialist system prompt via keyword matching.

0ms LLM latency: pure keyword matching against domain_agent_map.json triggers.
Called by openrouter_wrapper.py after domain_classifier, before LLM call.

Returns the specialist's .md system prompt when keywords match, or the
domain's generic default_system string when no specific match is found.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_MAP_PATH = Path(__file__).parent.parent.parent / "config" / "domain_agent_map.json"
_AGENTS_DIR = Path(__file__).parent.parent.parent / ".claude" / "agents"
_cache: dict | None = None


def _load_map() -> dict:
    global _cache
    if _cache is None:
        with open(_MAP_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def _extract_system_from_md(md_content: str) -> str:
    """Strip YAML frontmatter from .md and return body content only."""
    lines = md_content.splitlines()
    if not lines or lines[0].strip() != "---":
        return md_content
    # Find closing ---
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1 :]).strip()
    return md_content


def select_domain_agent(prompt: str, domain: str) -> tuple[str, str]:
    """Return (agent_name, system_prompt) for the best specialist match.

    Args:
        prompt: user prompt text
        domain: classified domain (e.g. "social_sciences")

    Returns:
        (agent_name, system_prompt)
          - agent_name: matched agent slug, or "default" if no trigger matched
          - system_prompt: full .md body (frontmatter stripped), or domain's
            default_system string, or "" if domain not in map
    """
    dmap = _load_map()
    domain_config = dmap.get(domain)
    if not domain_config:
        return "default", ""

    prompt_lower = prompt.lower()
    best_agent: str | None = None
    best_hits = 0

    for agent_name, agent_config in domain_config.get("agents", {}).items():
        hits = sum(
            1
            for t in agent_config.get("triggers", [])
            if re.search(r"\b" + re.escape(t.lower()) + r"\b", prompt_lower)
        )
        if hits > best_hits:
            best_hits = hits
            best_agent = agent_name

    if best_agent and best_hits > 0:
        md_path = _AGENTS_DIR / f"{best_agent}.md"
        if md_path.exists():
            raw = md_path.read_text(encoding="utf-8")
            return best_agent, _extract_system_from_md(raw)
        # Agent in map but no .md yet — fall back to domain default
        return best_agent, domain_config.get("default_system", "")

    return "default", domain_config.get("default_system", "")


def invalidate_cache() -> None:
    """Force reload of domain_agent_map.json on next call."""
    global _cache
    _cache = None
