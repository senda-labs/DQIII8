"""End-to-end pipeline tests for DQ.

Tests the full pipeline: input → amplification → routing → knowledge retrieval.
Does NOT call a model (no cost). Verifies everything up to the amplified prompt.

Note on schema: amplify() returns flat keys — result["action"], result["amplified"],
result["intent"], result["chunks_used"], result["tier"] (int 1/2/3), result["routing"].
"""
import sys
import pytest

sys.path.insert(0, "bin")

# ── Pipeline tests ────────────────────────────────────────────────────────────


def test_full_pipeline_business():
    from intent_amplifier import amplify

    result = amplify("Create a digital marketing agency for cleaning products")

    # action: "create" is a keyword of the "generate" intent pattern
    assert result["action"] == "generate"
    # at least one domain scored
    assert result["domains"], "Expected at least one domain"
    top_domain = result["domains"][0]["domain"]
    assert top_domain in ("social_sciences", "applied_sciences"), (
        f"Expected social or applied, got {top_domain}"
    )
    # amplified prompt must contain the structural sections
    assert "[CONTEXT]" in result["amplified"]
    assert "[REQUEST]" in result["amplified"]
    assert len(result["amplified"]) > 100
    # tier must be a valid value
    assert result["tier"] in (1, 2, 3)


def test_full_pipeline_finance():
    from intent_amplifier import amplify

    result = amplify("Calculate VaR at 95% confidence for my portfolio")

    # Domain routing is embedding-based — just verify it resolved to something
    assert result["domains"], "Expected at least one domain"
    # Amplified prompt must have the canonical sections
    assert "[REQUEST]" in result["amplified"]
    assert result["tier"] in (1, 2, 3)


def test_full_pipeline_code():
    from intent_amplifier import amplify

    result = amplify("Fix the TypeError in my database manager class")

    # "fix" is a keyword of the "debug" intent pattern
    assert result["action"] == "debug"
    assert result["domains"], "Expected at least one domain"
    # niche should be detected as code
    assert result["niche"] == "code"
    assert "[REQUEST]" in result["amplified"]


def test_full_pipeline_creative_writing():
    from intent_amplifier import amplify

    result = amplify("Write chapter 5 where Lin Feng discovers the ancestral artifact")

    # "write" is a keyword of the "generate" pattern
    assert result["action"] == "generate"
    assert result["niche"] == "writing"
    assert len(result["amplified"]) > 50


def test_amplify_always_returns_required_keys():
    from intent_amplifier import amplify

    result = amplify("hello world")

    required_keys = {
        "original", "amplified", "action", "entity", "niche",
        "intent", "domains", "tier", "tier_label", "chunks_used", "routing",
    }
    missing = required_keys - set(result.keys())
    assert not missing, f"Missing keys: {missing}"


def test_amplified_prompt_contains_original():
    from intent_amplifier import amplify

    prompt = "Explain gradient descent in neural networks"
    result = amplify(prompt)

    assert prompt in result["amplified"], "Original prompt must appear in amplified version"


# ── Hierarchical router tests ─────────────────────────────────────────────────


def test_hierarchical_router_multi_centroid():
    from hierarchical_router import classify_hierarchical

    result = classify_hierarchical("Create a marketing agency for cleaning products")

    assert len(result["active_centroids"]) <= 2
    assert len(result["active_centroids"]) >= 1
    assert result["classification_ms"] < 1000  # Under 1 second total
    domains = [c["domain"] for c in result["active_centroids"]]
    assert "social_sciences" in domains, (
        f"Expected social_sciences as active centroid, got {domains}"
    )


def test_hierarchical_router_has_agents():
    from hierarchical_router import classify_hierarchical

    result = classify_hierarchical("Build a REST API with authentication")

    assert result["active_centroids"], "Expected at least one active centroid"
    first = result["active_centroids"][0]
    assert len(first.get("agents", [])) >= 1, "Expected at least one agent within first centroid"


def test_hierarchical_router_all_5_domains_scored():
    from hierarchical_router import classify_hierarchical

    result = classify_hierarchical("Design a machine learning pipeline for fraud detection")

    assert len(result["level1"]) == 5, (
        f"Expected all 5 domains scored, got {len(result['level1'])}"
    )
    expected_domains = {
        "formal_sciences", "natural_sciences", "social_sciences",
        "humanities_arts", "applied_sciences",
    }
    assert set(result["level1"].keys()) == expected_domains


def test_hierarchical_router_weights_sum_to_one():
    from hierarchical_router import classify_hierarchical

    result = classify_hierarchical("Analyze market trends for a SaaS product")

    total = sum(result["level1"].values())
    assert abs(total - 1.0) < 0.01, f"Level-1 weights must sum to ~1.0, got {total:.4f}"


def test_hierarchical_router_max_2_active():
    from hierarchical_router import classify_hierarchical

    # Prompt intentionally spans many domains
    result = classify_hierarchical(
        "Create a health tech startup using AI to analyze patient genomics "
        "and predict cancer outcomes with statistical confidence intervals"
    )

    assert len(result["active_centroids"]) <= 2
    assert len(result["level1"]) == 5


def test_queued_centroids_are_not_active():
    from hierarchical_router import classify_hierarchical

    result = classify_hierarchical(
        "Create a health tech startup using AI and statistics for patient care"
    )

    active_domains = {c["domain"] for c in result["active_centroids"]}
    queued_domains = {c["domain"] for c in result["queued_centroids"]}
    # Active and queued must be disjoint
    overlap = active_domains & queued_domains
    assert not overlap, f"Domains appear in both active and queued: {overlap}"


def test_knowledge_retrieval_returns_content():
    from hierarchical_router import classify_hierarchical, retrieve_knowledge_by_routing
    from embeddings import get_embedding

    query = "Explain microeconomics supply and demand"
    result = classify_hierarchical(query)
    emb = get_embedding(query)
    knowledge = retrieve_knowledge_by_routing(result, emb)

    assert isinstance(knowledge, str)
    assert len(knowledge) > 0, "Expected knowledge content for economics query"


def test_fallback_result_on_empty_centroids(monkeypatch):
    """Router must return a safe fallback when no centroids are in DB."""
    from hierarchical_router import classify_hierarchical
    import hierarchical_router as hr

    monkeypatch.setattr(hr, "load_centroids", lambda: {})
    result = classify_hierarchical("anything")

    assert result["active_centroids"] == []
    assert result["level1"] == {}
    assert result["classification_ms"] == 0
