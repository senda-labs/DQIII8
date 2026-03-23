"""Tests to verify that agent triggers correctly detect keywords."""
import os
import pytest

TRIGGER_RULES = {
    "python-specialist": [
        "traceback",
        "refactor",
        ".py",
        "debug",
        "error in",
        "optimize",
    ],
    "git-specialist": [
        "commit",
        "branch",
        "PR",
        "merge",
        "push",
        "pull request",
    ],
    "code-reviewer": [
        "review",
        "is this code ok",
        "review this",
    ],
    "orchestrator": [
        "/mobilize",
        "coordinate",
        "in parallel",
    ],
    "content-automator": [
        "video",
        "TTS",
        "subtitles",
        "pipeline",
        "reels",
    ],
    "data-analyst": [
        "WACC",
        "DCF",
        "chart",
        "Excel",
        "finance",
    ],
    "creative-writer": [
        "chapter",
        "scene",
        "novel",
        "story",
    ],
    "auditor": [
        "/audit",
        "what's failing",
        "metrics",
    ],
}


def test_trigger_coverage():
    """Each agent must have at least 2 triggers defined."""
    for agent, triggers in TRIGGER_RULES.items():
        assert len(triggers) >= 2, f"{agent} has fewer than 2 triggers"


def test_no_trigger_overlap():
    """No trigger should activate more than one agent."""
    all_triggers = []
    for agent, triggers in TRIGGER_RULES.items():
        for t in triggers:
            assert t not in all_triggers, f"Trigger '{t}' appears in multiple agents"
            all_triggers.append(t)


@pytest.mark.skip(
    reason="CLAUDE.md is gitignored — test would always fail in CI. "
    "Manually verify delegation table if CLAUDE.md is modified."
)
def test_delegation_table_in_claude_md():
    """CLAUDE.md must contain the delegation table."""
    claude_md = os.path.join(os.path.dirname(__file__), "..", "CLAUDE.md")
    if not os.path.isfile(claude_md):
        pytest.skip("CLAUDE.md not present in this repo (cleaned for public release)")
    with open(claude_md, encoding="utf-8") as f:
        content = f.read()
    assert "python-specialist" in content
    assert "git-specialist" in content
    assert "Trigger" in content


def test_all_agents_have_unique_name():
    """All agent names must be unique."""
    names = list(TRIGGER_RULES.keys())
    assert len(names) == len(set(names))


def test_trigger_strings_are_non_empty():
    """All triggers must be non-empty strings."""
    for agent, triggers in TRIGGER_RULES.items():
        for t in triggers:
            assert isinstance(t, str) and len(t) > 0, f"Empty trigger in {agent}"
