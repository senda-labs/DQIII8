# DQIII8 — Plugin Ecosystem Phase 2

> Claude Code reads this and executes ALL blocks in sequence.
> Each block has verification. Fix before proceeding.
> ASK user for manual actions when needed.

---

## Pre-flight

```bash
python3 -m pytest tests/ -q          # Expected: 142+ passed
systemctl is-active dqiii8-bot        # Expected: active
claude --version                      # Expected: 2.1.87+
```

Read CLAUDE.md and RULE before starting.

---

## BLOCK 1: Install Tier 2 Plugins (requires user interaction)

### 1.1 Telegram Channel Plugin

ASK THE USER to run these inside Claude Code:

```
/plugin install telegram@claude-plugins-official
/telegram:configure
```

Then configure the bot token (same as DQIII8_BOT_TOKEN from .env).

IMPORTANT: Telegram channel requires a SEPARATE bot from dqiii8_bot.
The channel plugin polls Telegram for messages — it would conflict
with dqiii8_bot.py which also polls. Two options:

Option A: Create a NEW bot via @BotFather for Channels only
  - dqiii8_bot.py keeps @YourBotName for /cc, /auto, /intl
  - Channels bot handles direct Claude Code sessions
  
Option B: Skip Telegram channel for now, keep our custom /cc
  - Our /cc already has DQ enrichment which Channels doesn't
  - Channels adds value only when we want raw Claude Code access

ASK THE USER which option they prefer. Wait for response.

### 1.2 Figma Plugin

ASK THE USER to run:

```
/plugin install figma@claude-plugins-official
```

No additional config needed — it uses Figma URLs directly.
Test: ask Claude Code "What plugins do you have for Figma?"

### 1.3 Playwright Plugin

ASK THE USER to run:

```
/plugin install playwright@claude-plugins-official
```

After install, verify Playwright is available:
```bash
npx playwright --version 2>/dev/null || echo "Need: npx playwright install chromium"
```

If Playwright browsers not installed:
```bash
npx playwright install chromium --with-deps
```

NOTE: Playwright on a headless VPS (no display) works with --headless flag.
Claude Code handles this automatically.

### 1.4 Code Simplifier Plugin

ASK THE USER to run:

```
/plugin install code-simplifier@claude-plugins-official
```

No config needed. Activates automatically when Claude simplifies code.

### 1.5 PR Review Toolkit

ASK THE USER to run:

```
/plugin install pr-review-toolkit@claude-plugins-official
```

Adds /pr-review-toolkit:review-pr command with 6 specialized agents.

### 1.6 Claude-MD-Management (from Tier 3)

ASK THE USER to run:

```
/plugin install claude-md-management@claude-plugins-official
```

This plugin helps maintain CLAUDE.md automatically.

IMPORTANT: After install, add a rule to .claude/rules/:

```bash
cat > .claude/rules/claude-md-limit.md << 'EOF'
# CLAUDE.md Size Limit

CLAUDE.md must NEVER exceed 100 lines.
If claude-md-management suggests additions that would exceed 100 lines,
condense existing content first.
The file is a quick reference map, not documentation.
Detailed docs belong in docs/CHECKPOINT_*.md or PROJECT.md files.
EOF
```

### 1.7 Claude Notifications (smart-notifications)

This is a Go binary, not a standard plugin. Install separately:

```bash
curl -fsSL https://raw.githubusercontent.com/777genius/claude-notifications-go/main/bin/bootstrap.sh | bash
```

After install, configure for Telegram webhook in Claude Code:
```
/claude-notifications-go:settings
```

### 1.8 Verify Block 1

```bash
# Reload plugins
# ASK USER to run: /reload-plugins

# Count plugins - should be 28+ (was 22)
# ASK USER to run: /plugins and count installed
```

Commit: `feat: install Tier 2 plugins — figma, playwright, code-simplifier, pr-review, claude-md-mgmt`
Push to premium and origin.

---

## BLOCK 2: Auto-Install/Uninstall System for Tier 3 Plugins (45 min)

### 2.1 Concept

Tier 3 plugins are heavy or niche. They should NOT be loaded permanently.
Instead, DQIII8 auto-installs them when a project needs them,
and auto-uninstalls when the project session ends.

This is managed via PROJECT.md — each project declares what plugins it needs:

```markdown
# my-project — Name
Keywords: ...
Status: active
Plugins: playwright, greptile
```

When detect_project() identifies a project, it checks the `Plugins:` field
and installs any missing plugins. When the session ends, it uninstalls them.

### 2.2 Implementation

Create bin/plugin_manager.py:

```python
"""Auto-install/uninstall Tier 3 plugins based on project needs.

Usage:
    from plugin_manager import ensure_plugins, cleanup_plugins
    
    # At project detection time
    ensure_plugins(project)
    
    # At session end
    cleanup_plugins(project)
"""

import subprocess
import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Tier 3 plugins that can be auto-installed/uninstalled
TIER3_PLUGINS = {
    "playwright": "playwright@claude-plugins-official",
    "greptile": "greptile@claude-plugins-official",
    "pyright-lsp": "pyright-lsp@claude-plugins-official",
    "superpowers-lab": "superpowers-lab@superpowers-marketplace",
    "ralph-loop": "ralph-loop@claude-plugins-official",
    "claude-session-driver": "claude-session-driver@superpowers-marketplace",
}

# Plugins that are always installed (never auto-uninstall)
PERMANENT_PLUGINS = {
    "superpowers", "episodic-memory", "oh-my-claudecode",
    "frontend-design", "firecrawl", "hookify", "semgrep",
    "context7", "code-review", "skill-creator",
    "figma", "code-simplifier", "pr-review-toolkit",
    "claude-md-management", "telegram",
}


def get_project_plugins(project: dict) -> set:
    """Extract required plugins from PROJECT.md Plugins: field."""
    if not project.get("project_md"):
        return set()
    
    match = re.search(r"plugins?:\s*(.+)", project["project_md"], re.IGNORECASE)
    if not match:
        return set()
    
    return {p.strip().lower() for p in match.group(1).split(",") if p.strip()}


def ensure_plugins(project: dict) -> list:
    """Install missing Tier 3 plugins required by project.
    
    Returns list of plugins that were installed.
    """
    needed = get_project_plugins(project)
    installed = []
    
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
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                installed.append(plugin_name)
                log.info("Auto-installed plugin: %s", plugin_name)
        except Exception as e:
            log.warning("Failed to auto-install %s: %s", plugin_name, e)
    
    return installed


def cleanup_plugins(project: dict, installed: list) -> None:
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
                capture_output=True, text=True, timeout=30
            )
            log.info("Auto-uninstalled plugin: %s", plugin_name)
        except Exception as e:
            log.warning("Failed to uninstall %s: %s", plugin_name, e)
```

### 2.3 Wire into orchestrator

In bin/orchestrator.py, after detect_project():

```python
# In build_context or as a separate step
from plugin_manager import ensure_plugins, get_project_plugins

def prepare_project(project: dict) -> dict:
    """Detect project + ensure plugins + build context."""
    plugins_needed = get_project_plugins(project)
    if plugins_needed:
        installed = ensure_plugins(project)
        project["auto_installed_plugins"] = installed
    return project
```

### 2.4 Add Plugins field to PROJECT.md files that need it

For example, if content-automation needs playwright for video testing:

```markdown
# content-automation — Faceless Video Pipeline
Keywords: video, faceless, ...
Plugins: playwright
```

### 2.5 Verify Block 2

```python
# Test get_project_plugins
from plugin_manager import get_project_plugins
project = {"project_md": "# test\nPlugins: playwright, greptile\nStatus: active"}
assert get_project_plugins(project) == {"playwright", "greptile"}

project_no_plugins = {"project_md": "# test\nStatus: active"}
assert get_project_plugins(project_no_plugins) == set()
```

Add tests to tests/test_plugin_manager.py.

Commit: `feat: auto-install/uninstall Tier 3 plugins via PROJECT.md Plugins field`
Push to premium and origin.

---

## BLOCK 3: Update CLAUDE.md with Plugin Ecosystem (15 min)

### 3.1 Add plugin section to CLAUDE.md

IMPORTANT: CLAUDE.md must stay under 100 lines. Add this section
by condensing other sections if needed:

```markdown
## Plugins (Claude Code)
Permanent: superpowers, episodic-memory, omc, frontend-design, firecrawl,
  hookify, semgrep, context7, code-review, skill-creator, figma,
  code-simplifier, pr-review-toolkit, claude-md-management
On-demand: Tier 3 plugins auto-install via PROJECT.md "Plugins:" field
  Available: playwright, greptile, pyright-lsp, superpowers-lab
Config: .mcp.json (MCP servers), ~/.claude/settings.json (permissions + plugins)
```

### 3.2 Verify line count

```bash
wc -l CLAUDE.md  # Must be <= 100
```

If over 100, condense. Architecture and Key Files sections can be shortened.

Commit: `docs: add plugin ecosystem to CLAUDE.md (under 100 lines)`

---

## BLOCK 4: DQIII8 as Official Claude Code Plugin (design + scaffold)

### 4.1 Read existing design doc

```bash
cat docs/DQIII8_PLUGIN_DESIGN.md 2>/dev/null
```

### 4.2 Create plugin scaffold

The goal: anyone with Claude Code can run:
```
/plugin marketplace add https://github.com/senda-labs/DQIII8
/plugin install dqiii8
```

And get: DQ enrichment, domain classification, knowledge search,
17 skills, 9 agents, 12 hooks.

Create the plugin structure:

```
.claude-plugin/
  marketplace.json      # Marketplace catalog
  plugin.json           # Plugin metadata

# The plugin exposes:
skills/                 # Already exist in .claude/skills/
agents/                 # Already exist in .claude/agents/
hooks/                  # Already exist in .claude/hooks/
```

### 4.3 Create marketplace.json

```json
{
  "name": "dqiii8",
  "displayName": "DQIII8 — Domain-Quality AI Orchestration",
  "owner": {
    "name": "Senda Labs",
    "url": "https://github.com/senda-labs"
  },
  "plugins": [
    {
      "name": "dqiii8",
      "description": "Multi-tier AI orchestration with domain knowledge enrichment. Routes prompts through cheapest capable model (Ollama > Groq > Anthropic). 17 skills, 9 specialized agents, 12 lifecycle hooks. Knowledge base with bge-m3 embeddings.",
      "source": {
        "type": "git",
        "url": "https://github.com/senda-labs/DQIII8.git"
      },
      "homepage": "https://github.com/senda-labs/DQIII8",
      "license": "MIT"
    }
  ]
}
```

### 4.4 Create plugin.json

```json
{
  "name": "dqiii8",
  "version": "1.0.0",
  "description": "Domain-Quality AI orchestration — multi-tier routing with knowledge enrichment",
  "author": "Senda Labs",
  "homepage": "https://github.com/senda-labs/DQIII8",
  "supportedPlatforms": ["linux"],
  "minClaudeCodeVersion": "2.1.80"
}
```

### 4.5 Verify the plugin structure works locally

```bash
# Test marketplace locally
claude plugin marketplace add /root/dqiii8
# Should recognize dqiii8 as a plugin
```

### 4.6 Self-evaluate

Before pushing the plugin structure:
1. Does the public repo have everything needed?
   - Skills, agents, hooks: YES (already in repo)
   - Knowledge base: partially (indexes are gitignored)
   - Database: NO (created by install.sh)
   - .env: NO (user creates)

2. What's missing for a clean plugin install?
   - Post-install script that runs install.sh
   - Knowledge indexing after install
   - Database schema application

3. The plugin.json needs a "postInstall" script.
   Check if Claude Code supports this — read the docs.

Document findings. Do NOT push a broken plugin structure.

Commit: `feat: DQIII8 plugin scaffold for Claude Code marketplace`
Push to premium and origin.

---

## BLOCK 5: Verify Everything (15 min)

### 5.1 Full test suite

```bash
python3 -m pytest tests/ -q
# Expected: 142+ passed, 0 failed, 0 skipped, 0 xfailed
```

### 5.2 Plugin count

ASK USER to run in Claude Code:
```
/reload-plugins
```
Report the count of plugins, skills, agents, hooks.

### 5.3 CLAUDE.md line count

```bash
wc -l CLAUDE.md  # Must be <= 100
```

### 5.4 Bot functional

```bash
systemctl is-active dqiii8-bot
```

Test from Telegram:
```
/cc que plugins tenemos instalados
```

### 5.5 Generate new checkpoint

Create docs/CHECKPOINT_2026-03-29.md with current state.
Delete old checkpoints.

### 5.6 Final commit

```
git add -A
git commit -m "ecosystem: Tier 2 plugins + auto-install system + DQIII8 plugin scaffold"
git push premium main
git push origin main
```

---

## RULES

- NEVER skip verification steps
- CLAUDE.md must NEVER exceed 100 lines
- Tier 3 plugins are TEMPORARY — auto-uninstall after use
- Permanent plugins (Tier 1+2) are NEVER auto-uninstalled
- ASK user for every /plugin install command (requires interactive Claude Code)
- If a plugin install fails, document why and continue
- The DQIII8 plugin scaffold is a DESIGN — test locally before pushing
- Maximum 1 Opus escalation per block
