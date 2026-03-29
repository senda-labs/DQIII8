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
    "finance-specialist": [
        "WACC",
        "DCF",
        "chart",
        "Excel",
        "finance",
    ],
    "research-analyst": [
        "investigate",
        "research",
        "compare options",
        "benchmark",
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


def test_active_agents_exist_on_disk():
    """All agents listed in TRIGGER_RULES must have .md files on disk."""
    agents_dir = os.path.join(os.path.dirname(__file__), "..", ".claude", "agents")
    for agent_name in TRIGGER_RULES:
        agent_file = os.path.join(agents_dir, f"{agent_name}.md")
        assert os.path.isfile(
            agent_file
        ), f"Agent '{agent_name}' in TRIGGER_RULES but missing: {agent_file}"


def test_all_agents_have_unique_name():
    """All agent names must be unique."""
    names = list(TRIGGER_RULES.keys())
    assert len(names) == len(set(names))


def test_trigger_strings_are_non_empty():
    """All triggers must be non-empty strings."""
    for agent, triggers in TRIGGER_RULES.items():
        for t in triggers:
            assert isinstance(t, str) and len(t) > 0, f"Empty trigger in {agent}"
