"""Domain Lens — generates domain-specific system prompts dynamically.

Used by domain specialist agents to produce rich system prompts
with automatic knowledge enrichment from the domain index.

Usage:
    from domain_lens import get_domain_lens
    result = get_domain_lens("explain glycolysis", "natural_sciences")
    # result["system_prompt"] → inject into API call as system message
"""

from __future__ import annotations

from pathlib import Path
import sys

DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
for _d in [DQIII8_ROOT / "bin" / "core", DQIII8_ROOT / "bin" / "agents"]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from domain_classifier import classify_domain
from knowledge_enricher import enrich_with_knowledge

try:
    from subdomain_classifier import classify_subdomain as _classify_subdomain
except ImportError:

    def _classify_subdomain(prompt: str, domain: str) -> str:
        return domain


# Domain behaviour templates — style guidance injected into every system prompt
DOMAIN_STYLES: dict[str, str] = {
    "formal_sciences": (
        "Respond with mathematical rigor. Show formulas, derivations, "
        "and convergence conditions. Use LaTeX notation when helpful. "
        "State assumptions explicitly."
    ),
    "natural_sciences": (
        "Follow the scientific method. Cite units (SI preferred). "
        "Distinguish between established facts and hypotheses. "
        "Reference experimental evidence when available."
    ),
    "social_sciences": (
        "Use empirical data and specific numbers. Cite sources. "
        "Distinguish between correlation and causation. "
        "Consider economic, legal, and social context."
    ),
    "humanities_arts": (
        "Provide textual analysis with historical context. "
        "Reference specific works, movements, and authors. "
        "Consider multiple interpretive frameworks."
    ),
    "applied_sciences": (
        "Focus on practical implementation. Show code when relevant. "
        "Discuss trade-offs explicitly. Reference best practices "
        "and design patterns."
    ),
}


def get_domain_lens(prompt: str, domain: str | None = None) -> dict:
    """Generate a domain-specific system prompt with knowledge injection.

    Args:
        prompt: The user's original prompt.
        domain: Override domain (if already classified). If None, classifies automatically.

    Returns:
        dict with keys:
            system_prompt  — ready to pass as system message to the model
            domain         — resolved domain string
            chunks_used    — number of knowledge chunks injected
            style          — style guidance string used
    """
    if domain is None:
        domain, _score, _method = classify_domain(prompt)

    # Get knowledge chunks for this domain
    enriched_prompt, chunks_used = enrich_with_knowledge(prompt, domain)

    # Extract the prepended knowledge context (everything before the original prompt)
    knowledge_context = ""
    if chunks_used > 0 and enriched_prompt != prompt:
        try:
            knowledge_context = enriched_prompt[: enriched_prompt.index(prompt)].strip()
        except ValueError:
            knowledge_context = ""

    style = DOMAIN_STYLES.get(domain, DOMAIN_STYLES["applied_sciences"])

    subdomain = _classify_subdomain(prompt, domain)
    role_label = (
        subdomain.replace("_", " ") if subdomain != domain else domain.replace("_", " ")
    )
    system_prompt = f"You are an expert in {role_label}.\n\n"
    system_prompt += f"{style}\n\n"
    if knowledge_context:
        system_prompt += (
            f"Use this reference material when relevant:\n"
            f"<knowledge>\n{knowledge_context}\n</knowledge>\n\n"
        )
    system_prompt += "If uncertain about a specific value, say so explicitly."

    return {
        "system_prompt": system_prompt,
        "domain": domain,
        "subdomain": subdomain,
        "chunks_used": chunks_used,
        "style": style,
    }


if __name__ == "__main__":
    import json

    test_prompts = {
        "formal_sciences": "What is the time complexity of merge sort?",
        "natural_sciences": "Explain the Krebs cycle and ATP production.",
        "social_sciences": "How does the Taylor rule guide monetary policy?",
        "humanities_arts": "Analyze the role of the unreliable narrator in fiction.",
        "applied_sciences": "Compare microservices vs monolith architecture.",
    }
    for domain, prompt in test_prompts.items():
        r = get_domain_lens(prompt, domain)
        print(f"{domain}: chunks={r['chunks_used']} len={len(r['system_prompt'])}")
