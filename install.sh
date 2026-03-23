#!/bin/bash
# DQIII8 — Installation Script
# Usage: bash install.sh
# Tested on Ubuntu 22.04/24.04

set -euo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }
step() { echo -e "\n${YELLOW}▶ $*${NC}"; }

echo "DQIII8 Install — root: $DQIII8_ROOT"
echo ""

# ── 1. Python deps ────────────────────────────────────────────────────
step "1/5 Python dependencies"
if ! command -v python3 &>/dev/null; then err "python3 not found. Install Python 3.10+."; exit 1; fi
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PY_VERSION"
pip install -q -r "$DQIII8_ROOT/requirements.txt" && ok "Python deps installed"

# ── 2. Ollama ─────────────────────────────────────────────────────────
step "2/5 Ollama (local LLM — Tier C)"
if command -v ollama &>/dev/null; then
    ok "Ollama already installed: $(ollama --version 2>/dev/null | head -1)"
else
    warn "Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed"
fi
# Pull required models
for MODEL in qwen2.5-coder:7b nomic-embed-text; do
    if ollama list 2>/dev/null | grep -q "$MODEL"; then
        ok "Model $MODEL already present"
    else
        echo "  Pulling $MODEL (this may take a few minutes)..."
        ollama pull "$MODEL" && ok "Model $MODEL ready"
    fi
done

# ── 3. Claude Code ────────────────────────────────────────────────────
step "3/5 Claude Code (Anthropic CLI)"
if command -v claude &>/dev/null; then
    ok "Claude Code already installed: $(claude --version 2>/dev/null || echo 'version unknown')"
else
    warn "Claude Code not found."
    echo ""
    echo "  Claude Code requires accepting Anthropic's Terms of Service."
    echo "  Install command: npm install -g @anthropic-ai/claude-code"
    echo "  Docs: https://docs.anthropic.com/claude-code"
    echo ""
    read -r -p "  Install Claude Code now? (y/N): " REPLY
    if [[ "${REPLY,,}" == "y" ]]; then
        if ! command -v npm &>/dev/null; then
            err "npm not found. Install Node.js 18+ first: https://nodejs.org"
            exit 1
        fi
        npm install -g @anthropic-ai/claude-code && ok "Claude Code installed"
    else
        warn "Skipped. Install manually before using /cc Telegram commands."
    fi
fi

# ── 4. .env ───────────────────────────────────────────────────────────
step "4/5 Configuration"
ENV_FILE="$DQIII8_ROOT/config/.env"
if [[ -f "$ENV_FILE" ]]; then
    ok ".env already exists"
else
    cp "$DQIII8_ROOT/config/.env.example" "$ENV_FILE"
    warn ".env created from template — fill in your API keys: $ENV_FILE"
fi

# ── 5. Database ───────────────────────────────────────────────────────
step "5/5 Database"
DB="$DQIII8_ROOT/database/dqiii8.db"
if [[ -f "$DB" ]] || [[ -L "$DB" ]]; then
    ok "Database exists: $DB"
else
    sqlite3 "$DB" < "$DQIII8_ROOT/database/schema_v2.sql" && ok "Database created: $DB"
fi

# ── Done ──────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "DQIII8 installation complete."
echo ""
echo "  Next steps:"
echo "  1. Edit config/.env — add your GROQ_API_KEY and DQIII8_BOT_TOKEN"
echo "  2. bash bin/j.sh --status — verify system"
echo "  3. See README.md for full setup guide"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
