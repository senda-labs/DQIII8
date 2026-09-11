"""agent_name -> effective model, shared by pre_tool_use.py (write path) and
dashboard.py (read path) so the two never diverge.

See .claude/rules/03_tiering_and_routing.md (REGLA NIM, Anthropic-only) and
.claude/rules_db/common/agents.md: the Agent tool runtime ignores a dormant
ollama/groq `model:` frontmatter value and falls back to the default Tier A
model, so an agent's *declared* model and its *effective* model can differ.
"""

import os
from pathlib import Path

ROOT_DIR = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))

NATIVE_MODEL_SLUGS = {
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-haiku-4-5-20251001",
    "claude-fable-5-1",
}
DEFAULT_MODEL = "claude-sonnet-5"

# Claude Code's own built-in subagent types (not files under .claude/agents/).
_BUILTIN_AGENTS = ("Plan", "Explore", "general-purpose", "fork", "workflow-subagent", "default")


def build_model_map() -> dict:
    """agent_name -> effective model. Reads `.claude/agents/*.md` frontmatter once."""
    mapping: dict = {}
    agents_dir = ROOT_DIR / ".claude" / "agents"
    if agents_dir.is_dir():
        for f in agents_dir.glob("*.md"):
            model = None
            try:
                for line in f.read_text(encoding="utf-8").splitlines()[:15]:
                    if line.startswith("model:"):
                        model = line.split(":", 1)[1].strip()
                        break
            except OSError:
                continue
            mapping[f.stem] = model if model in NATIVE_MODEL_SLUGS else DEFAULT_MODEL
    for builtin in _BUILTIN_AGENTS:
        mapping[builtin] = DEFAULT_MODEL
    return mapping


MODEL_MAP = build_model_map()


def resolve_model(agent_name: str) -> str:
    """Effective model for an agent_name, falling back to the session default."""
    return MODEL_MAP.get(agent_name, DEFAULT_MODEL)
