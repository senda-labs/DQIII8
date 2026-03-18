#!/usr/bin/env bash
# DQIII8 — Installer for Ubuntu 22.04 / 24.04
# Usage: chmod +x install.sh && ./install.sh
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${CYAN}[DQIII8]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
fail()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Check OS ─────────────────────────────────────────────────────────
if ! grep -qE 'Ubuntu (22|24)\.' /etc/os-release 2>/dev/null; then
    echo "Warning: This script is designed for Ubuntu 22.04/24.04."
    echo "It may work on other Debian-based systems."
    read -rp "Continue anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── 1. System packages ──────────────────────────────────────────────
info "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git curl sqlite3 > /dev/null
ok "System packages installed"

# ── 2. Python venv ──────────────────────────────────────────────────
info "Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
ok "Python venv ready (.venv)"

# ── 3. Ollama (local AI models) ─────────────────────────────────────
info "Installing Ollama..."
if command -v ollama &>/dev/null; then
    ok "Ollama already installed"
else
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed"
fi

info "Pulling qwen2.5-coder:7b (Tier 1 model, ~4.4GB)..."
ollama pull qwen2.5-coder:7b
ok "Model qwen2.5-coder:7b ready"

# ── 4. Initialize database ─────────────────────────────────────────
info "Initializing SQLite database..."
DB_PATH="$PROJECT_DIR/database/jarvis_metrics.db"
SCHEMA_PATH="$PROJECT_DIR/database/schema.sql"
mkdir -p "$PROJECT_DIR/database"
if [ ! -f "$DB_PATH" ]; then
    if [ -f "$SCHEMA_PATH" ]; then
        sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
        ok "Database created from schema.sql"
    else
        sqlite3 "$DB_PATH" "SELECT 1;" > /dev/null
        ok "Empty database created (no schema.sql found)"
    fi
else
    ok "Database already exists"
fi

# ── 5. Claude Code (optional) ──────────────────────────────────────
info "Checking Claude Code..."
if command -v claude &>/dev/null; then
    ok "Claude Code already installed"
else
    if command -v npm &>/dev/null; then
        npm install -g @anthropic-ai/claude-code
        ok "Claude Code installed"
    else
        info "Node.js not found. Installing via NodeSource..."
        curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
        sudo apt-get install -y -qq nodejs > /dev/null
        npm install -g @anthropic-ai/claude-code
        ok "Node.js + Claude Code installed"
    fi
fi

# ── 6. Environment file ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp config/.env.example .env
    info "Created .env from template — edit it with your API keys"
else
    ok ".env already exists"
fi

# ── Done ────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  DQIII8 installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys (optional for local-only usage)"
echo "  2. source .venv/bin/activate"
echo "  3. claude   # Launch DQIII8"
echo ""
