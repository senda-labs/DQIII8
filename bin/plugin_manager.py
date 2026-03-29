"""Auto-install/uninstall Tier 3 plugins based on project needs.

Usage:
    from plugin_manager import ensure_plugins, cleanup_plugins, get_project_plugins

    # At project detection time
    ensure_plugins(project)

    # At session end
    cleanup_plugins(project, installed)
"""

import json
import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_STATE_FILE = Path("/tmp/dqiii8_auto_plugins.json")

# Tier 3 plugins that can be auto-installed/uninstalled
TIER3_PLUGINS: dict[str, str] = {
    "playwright": "playwright@claude-plugins-official",
    "greptile": "greptile@claude-plugins-official",
    "pyright-lsp": "pyright-lsp@claude-plugins-official",
    "superpowers-lab": "superpowers-lab@superpowers-marketplace",
    "ralph-loop": "ralph-loop@claude-plugins-official",
    "claude-session-driver": "claude-session-driver@superpowers-marketplace",
}

# Plugins that are always installed (never auto-uninstall)
PERMANENT_PLUGINS: frozenset[str] = frozenset(
    {
        "superpowers",
        "episodic-memory",
        "oh-my-claudecode",
        "frontend-design",
        "firecrawl",
        "hookify",
        "semgrep",
        "context7",
        "code-review",
        "skill-creator",
        "figma",
        "code-simplifier",
        "pr-review-toolkit",
        "claude-md-management",
    }
)


def get_project_plugins(project: dict) -> set[str]:
    """Extract required plugins from PROJECT.md Plugins: field."""
    project_md = project.get("project_md", "")
    if not project_md:
        return set()

    match = re.search(r"plugins?:\s*(.+)", project_md, re.IGNORECASE)
    if not match:
        return set()

    return {p.strip().lower() for p in match.group(1).split(",") if p.strip()}


def ensure_plugins(project: dict) -> list[str]:
    """Install missing Tier 3 plugins required by project.

    Returns list of plugins that were installed.
    """
    needed = get_project_plugins(project)
    installed: list[str] = []

    for plugin_name in needed:
        if plugin_name in PERMANENT_PLUGINS:
            continue  # Already installed permanently

        install_id = TIER3_PLUGINS.get(plugin_name)
        if not install_id:
            log.warning("Unknown Tier 3 plugin: %s", plugin_name)
            continue

        try:
            result = subprocess.run(
                ["claude", "plugin", "install", install_id, "--scope", "local"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                installed.append(plugin_name)
                log.info("Auto-installed plugin: %s", plugin_name)
        except Exception as exc:
            log.warning("Failed to auto-install %s: %s", plugin_name, exc)

    # Persist for cleanup at session end
    if installed:
        existing = _load_state()
        existing.extend(installed)
        _save_state(list(set(existing)))

    return installed


def cleanup_plugins(project: dict, installed: list[str]) -> None:
    """Uninstall Tier 3 plugins that were auto-installed for this project."""
    for plugin_name in installed:
        if plugin_name in PERMANENT_PLUGINS:
            continue

        install_id = TIER3_PLUGINS.get(plugin_name)
        if not install_id:
            continue

        try:
            subprocess.run(
                ["claude", "plugin", "uninstall", install_id],
                capture_output=True,
                text=True,
                timeout=30,
            )
            log.info("Auto-uninstalled plugin: %s", plugin_name)
        except Exception as exc:
            log.warning("Failed to uninstall %s: %s", plugin_name, exc)


def _load_state() -> list[str]:
    """Load auto-installed plugin names from state file."""
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_state(plugins: list[str]) -> None:
    """Save auto-installed plugin names to state file."""
    _STATE_FILE.write_text(json.dumps(plugins), encoding="utf-8")


def cleanup_auto_installed() -> int:
    """Uninstall all auto-installed Tier 3 plugins and clear state.

    Called from stop.py at session end. Returns count of plugins removed.
    """
    installed = _load_state()
    if not installed:
        return 0

    removed = 0
    for plugin_name in installed:
        if plugin_name in PERMANENT_PLUGINS:
            continue
        install_id = TIER3_PLUGINS.get(plugin_name)
        if not install_id:
            continue
        try:
            subprocess.run(
                ["claude", "plugin", "uninstall", install_id],
                capture_output=True,
                text=True,
                timeout=30,
            )
            removed += 1
            log.info("Auto-uninstalled plugin: %s", plugin_name)
        except Exception as exc:
            log.warning("Failed to uninstall %s: %s", plugin_name, exc)

    # Clear state file
    if _STATE_FILE.exists():
        _STATE_FILE.unlink()

    return removed
