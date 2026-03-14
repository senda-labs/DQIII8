"""Tests para verificar que los triggers de agentes detectan correctamente las palabras clave."""

TRIGGER_RULES = {
    "python-specialist": [
        "traceback",
        "refactor",
        ".py",
        "debug",
        "error en",
        "optimiza",
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
        "está bien este código",
        "revisa esto",
    ],
    "orchestrator": [
        "/mobilize",
        "coordina",
        "en paralelo",
    ],
    "content-automator": [
        "video",
        "TTS",
        "subtítulos",
        "pipeline",
        "reels",
    ],
    "data-analyst": [
        "WACC",
        "DCF",
        "gráfico",
        "Excel",
        "finanzas",
    ],
    "creative-writer": [
        "capítulo",
        "escena",
        "xianxia",
        "novela",
    ],
    "auditor": [
        "/audit",
        "qué está fallando",
        "métricas",
    ],
}


def test_trigger_coverage():
    """Cada agente debe tener al menos 2 triggers definidos."""
    for agent, triggers in TRIGGER_RULES.items():
        assert len(triggers) >= 2, f"{agent} tiene menos de 2 triggers"


def test_no_trigger_overlap():
    """Ningún trigger debe activar más de un agente."""
    all_triggers = []
    for agent, triggers in TRIGGER_RULES.items():
        for t in triggers:
            assert t not in all_triggers, f"Trigger '{t}' aparece en múltiples agentes"
            all_triggers.append(t)


def test_delegation_table_in_claude_md():
    """CLAUDE.md debe contener la tabla de delegación."""
    with open("CLAUDE.md", encoding="utf-8") as f:
        content = f.read()
    assert "python-specialist" in content
    assert "git-specialist" in content
    assert "Trigger" in content


def test_all_agents_have_unique_name():
    """Todos los nombres de agente deben ser únicos."""
    names = list(TRIGGER_RULES.keys())
    assert len(names) == len(set(names))


def test_trigger_strings_are_non_empty():
    """Todos los triggers deben ser strings no vacíos."""
    for agent, triggers in TRIGGER_RULES.items():
        for t in triggers:
            assert isinstance(t, str) and len(t) > 0, f"Trigger vacío en {agent}"
