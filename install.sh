#!/bin/bash
# DQIII8 — Installation Script
# Usage: bash install.sh [--with-knowledge]
#   --with-knowledge  Also pull bge-m3 and index the knowledge base (requires Ollama)
# Tested on Ubuntu 22.04/24.04

set -euo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }
step() { echo -e "\n${YELLOW}▶ $*${NC}"; }

# ── Parse flags ───────────────────────────────────────────────────────
WITH_KNOWLEDGE=0
for _arg in "$@"; do
    [[ "$_arg" == "--with-knowledge" ]] && WITH_KNOWLEDGE=1
done

echo "DQIII8 Install — root: $DQIII8_ROOT"
[[ $WITH_KNOWLEDGE -eq 1 ]] && echo "  Mode: full (with knowledge base)"
echo ""

_INSTALLED=()
_SKIPPED=()
_MISSING=()

# ── 1. Python deps ────────────────────────────────────────────────────
step "1/8 Python dependencies"
if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install Python 3.10+."
    exit 1
fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PY_VERSION"
if [[ -f "$DQIII8_ROOT/requirements.lock" ]]; then
    pip install -q --require-hashes --break-system-packages -r "$DQIII8_ROOT/requirements.lock" 2>/dev/null \
        || pip install -q --require-hashes -r "$DQIII8_ROOT/requirements.lock" && ok "Python deps installed (hash-verified)"
else
    warn "requirements.lock not found — falling back to unpinned requirements.txt"
    pip install -q --break-system-packages -r "$DQIII8_ROOT/requirements.txt" 2>/dev/null \
        || pip install -q -r "$DQIII8_ROOT/requirements.txt" && ok "Python deps installed"
fi
_INSTALLED+=("Python deps")

# ── 2. Ollama ─────────────────────────────────────────────────────────
step "2/8 Ollama (local LLM — Tier C, optional)"
_OLLAMA_OK=0
if command -v ollama &>/dev/null; then
    ok "Ollama already installed: $(ollama --version 2>/dev/null | head -1)"
    _SKIPPED+=("Ollama (already present)")
    _OLLAMA_OK=1
else
    warn "Ollama not found."
    echo ""
    echo "  Ollama enables Tier C (free local models: qwen2.5-coder:7b)."
    echo "  Without Ollama, Tier B (Groq) becomes the starting point."
    echo ""
    read -r -p "  Install Ollama now? (y/N): " _REPLY
    if [[ "${_REPLY,,}" == "y" ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
        ok "Ollama installed"
        _INSTALLED+=("Ollama")
        _OLLAMA_OK=1
    else
        warn "Skipped. Tier C inactive — Tier B (Groq) will be the entry point."
        _MISSING+=("Ollama (optional Tier C — run: curl -fsSL https://ollama.com/install.sh | sh)")
    fi
fi

if [[ $_OLLAMA_OK -eq 1 ]]; then
    # Core model: always pull qwen2.5-coder:7b for Tier C
    MODELS=(qwen2.5-coder:7b)
    # Knowledge-base embedding model: only with --with-knowledge
    [[ $WITH_KNOWLEDGE -eq 1 ]] && MODELS+=(bge-m3)
    for MODEL in "${MODELS[@]}"; do
        if ollama list 2>/dev/null | grep -q "^${MODEL}"; then
            ok "Model $MODEL already present"
            _SKIPPED+=("$MODEL")
        else
            echo "  Pulling $MODEL (this may take a few minutes)..."
            ollama pull "$MODEL" && ok "Model $MODEL ready"
            _INSTALLED+=("$MODEL")
        fi
    done
fi

# ── 3. Claude Code ────────────────────────────────────────────────────
step "3/8 Claude Code (optional — needed for /cc Telegram command)"
if command -v claude &>/dev/null; then
    ok "Claude Code already installed: $(claude --version 2>/dev/null | echo 'installed')"
    _SKIPPED+=("Claude Code (already present)")
else
    warn "Claude Code not found."
    echo ""
    echo "  Claude Code requires accepting Anthropic's Terms of Service."
    echo "  To install it manually:"
    echo ""
    echo "    curl -fsSL https://claude.ai/install.sh | bash"
    echo ""
    echo "  After installing, authenticate with:"
    echo "    claude /login"
    echo ""
    read -r -p "  Proceed without Claude Code? (Y/n): " REPLY
    if [[ "${REPLY,,}" == "n" ]]; then
        echo "  Install Claude Code then re-run install.sh."
        exit 0
    else
        warn "Skipped. /cc Telegram command will not work until Claude Code is installed."
        _MISSING+=("Claude Code (optional)")
    fi
fi

# ── 4. Configuration ──────────────────────────────────────────────────
step "4/8 Configuration"
ENV_FILE="$DQIII8_ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    ok ".env already exists"
    _SKIPPED+=(".env")
else
    cp "$DQIII8_ROOT/config/.env.example" "$ENV_FILE"
    warn ".env created from template — add your API keys: $ENV_FILE"
    _INSTALLED+=(".env (from template)")
fi
# Symlink config/.env for scripts that reference either path
if [[ ! -f "$DQIII8_ROOT/config/.env" ]]; then
    ln -sf "$ENV_FILE" "$DQIII8_ROOT/config/.env"
fi

# ── 5. Database schema ────────────────────────────────────────────────
step "5/8 Database schema"

# 5a. Apply schema_v2.sql (idempotent — CREATE TABLE IF NOT EXISTS throughout)
# This is the single source of truth for fresh installs.
mkdir -p "$DQIII8_ROOT/database"
if sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null; then
    ok "dqiii8.db: schema_v2.sql applied (46 tables)"
else
    warn "schema_v2.sql had errors — check database/ directory"
fi
_INSTALLED+=("Database schema (schema_v2.sql)")

# 5b-5d. Knowledge indexing — only with --with-knowledge flag
if [[ $WITH_KNOWLEDGE -eq 1 ]]; then
    if [[ $_OLLAMA_OK -ne 1 ]]; then
        warn "--with-knowledge requires Ollama. Skipping knowledge indexing."
        _MISSING+=("Knowledge index (Ollama required)")
    else
        # 5b. Index knowledge domains
        INDEX_OK=1
        for DOMAIN in formal_sciences natural_sciences social_sciences humanities_arts applied_sciences; do
            if python3 "$DQIII8_ROOT/bin/agents/knowledge_indexer.py" --domain "$DOMAIN" 2>&1; then
                ok "  domain $DOMAIN indexed"
            else
                warn "  domain $DOMAIN indexing failed — check Ollama is running"
                INDEX_OK=0
            fi
        done
        if [[ $INDEX_OK -eq 1 ]]; then
            _INSTALLED+=("Knowledge index (all 5 domains)")
        else
            _MISSING+=("Knowledge index (run per domain: python3 bin/agents/knowledge_indexer.py --domain <name>)")
        fi

        # 5c. Domain classifier centroids
        if python3 "$DQIII8_ROOT/bin/agents/domain_classifier.py" --setup --force 2>&1; then
            ok "Domain classifier centroids seeded"
            _INSTALLED+=("Domain centroids")
        else
            warn "Domain centroids failed — keyword-only fallback active"
            _MISSING+=("Domain centroids (run: python3 bin/agents/domain_classifier.py --setup --force)")
        fi

        # 5d. Migrate JSON index files → sqlite-vec
        if python3 "$DQIII8_ROOT/bin/agents/vector_store.py" --migrate 2>&1; then
            ok "sqlite-vec migration complete"
            _INSTALLED+=("Vector store")
        else
            warn "vector_store migration failed — hybrid search will be limited"
            _MISSING+=("Vector store (run: python3 bin/agents/vector_store.py --migrate)")
        fi
    fi
else
    _SKIPPED+=("Knowledge indexing (run: bash install.sh --with-knowledge)")
fi

# ── 6. Claude Code settings + systemd service ────────────────────────
step "6/8 Claude Code settings + systemd service"

# 6a. Copy Claude Code settings template
CLAUDE_SETTINGS_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_SETTINGS_DIR"
if [[ ! -f "$CLAUDE_SETTINGS_DIR/settings.json" ]]; then
    cp "$DQIII8_ROOT/config/claude_settings_template.json" "$CLAUDE_SETTINGS_DIR/settings.json"
    ok "Claude Code settings.json installed from template"
    _INSTALLED+=("Claude Code settings.json")
else
    ok "Claude Code settings.json already exists"
    _SKIPPED+=("Claude Code settings.json")
fi

# 6a-ii. Optional plugins — skipped in automated installs to avoid unattended LLM calls
# To install oh-my-claudecode manually: claude /plugin marketplace add oh-my-claudecode

# 6b. Create systemd service for Telegram bot
SERVICE_FILE="/etc/systemd/system/dqiii8-bot.service"
if [[ ! -f "$SERVICE_FILE" ]]; then
    cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=DQIII8 Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$DQIII8_ROOT
EnvironmentFile=$DQIII8_ROOT/.env
Environment="PATH=/root/.bun/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/usr/bin/python3 bin/ui/dqiii8_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF
    systemctl daemon-reload
    ok "systemd service created: dqiii8-bot.service"
    warn "Start with: systemctl enable --now dqiii8-bot"
    _INSTALLED+=("systemd service (dqiii8-bot)")
else
    ok "systemd service already exists"
    _SKIPPED+=("systemd service")
fi

# ── 7. Smoke tests ────────────────────────────────────────────────────
step "7/8 Verification"
if python3 -m pytest "$DQIII8_ROOT/tests/test_smoke.py" -q 2>&1; then
    ok "Smoke tests passed"
    _INSTALLED+=("Smoke tests ✓")
else
    warn "Some smoke tests failed — check the output above"
    _MISSING+=("Smoke tests (run: python3 -m pytest tests/test_smoke.py -v)")
fi

# ── 8. CLI setup ──────────────────────────────────────────────────────
step "8/8 CLI commands + aliases"
if ! grep -q "DQIII8_ROOT" ~/.bashrc 2>/dev/null; then
    echo "export DQIII8_ROOT=$DQIII8_ROOT" >> ~/.bashrc
    ok "DQIII8_ROOT added to ~/.bashrc"
    _INSTALLED+=("DQIII8_ROOT in ~/.bashrc")
else
    ok "DQIII8_ROOT already in ~/.bashrc"
    _SKIPPED+=("DQIII8_ROOT in ~/.bashrc")
fi

# ── CLI access — create 'dq' and 'j' commands globally ───────────────
chmod +x "$DQIII8_ROOT/bin/j.sh"
if [ ! -L /usr/local/bin/dq ]; then
    ln -sf "$DQIII8_ROOT/bin/j.sh" /usr/local/bin/dq
    ok "'dq' command linked to /usr/local/bin/dq"
    _INSTALLED+=("dq command → /usr/local/bin/dq")
else
    ok "'dq' already linked"
    _SKIPPED+=("dq command already linked")
fi
if [ ! -L /usr/local/bin/j ]; then
    ln -sf "$DQIII8_ROOT/bin/j.sh" /usr/local/bin/j
    ok "'j' command linked to /usr/local/bin/j"
    _INSTALLED+=("j command → /usr/local/bin/j")
else
    ok "'j' already linked"
    _SKIPPED+=("j command already linked")
fi

# ── dqa/dqo — Claude Code autonomous mode aliases ────────────────────
if command -v claude &>/dev/null; then
    if ! grep -q "alias dqa=" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << 'ALIASEOF'

# DQIII8 autonomous mode
alias dqa='DQIII8_MODE=autonomous claude --model sonnet'
alias dqo='cd /root/dqiii8 && DQIII8_MODE=autonomous claude --model opus'
ALIASEOF
        ok "dqa/dqo aliases added to ~/.bashrc (dqa=Sonnet, dqo=Opus)"
        _INSTALLED+=("dqa/dqo aliases in ~/.bashrc")
    else
        ok "dqa/dqo aliases already in ~/.bashrc"
        _SKIPPED+=("dqa/dqo aliases")
    fi
    # Remove legacy /usr/local/bin/dqa if present
    if [[ -f /usr/local/bin/dqa ]]; then
        rm -f /usr/local/bin/dqa
        ok "Removed legacy /usr/local/bin/dqa (replaced by alias)"
    fi
else
    warn "dqa/dqo not created — Claude Code not installed"
fi

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "Installation complete."
echo ""
if [[ ${#_INSTALLED[@]} -gt 0 ]]; then
    echo "  Installed:"
    for item in "${_INSTALLED[@]}"; do echo "    ✓ $item"; done
fi
if [[ ${#_SKIPPED[@]} -gt 0 ]]; then
    echo "  Already present (skipped):"
    for item in "${_SKIPPED[@]}"; do echo "    — $item"; done
fi
if [[ ${#_MISSING[@]} -gt 0 ]]; then
    echo "  Missing / manual steps:"
    for item in "${_MISSING[@]}"; do echo "    ⚠ $item"; done
fi
echo ""
echo "  Next steps:"
echo "  1. Edit config/.env — add GROQ_API_KEY (free: console.groq.com)"
echo "  2. python3 bin/core/openrouter_wrapper.py --list  — verify routing"
echo "  3. See README.md for full usage guide"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
