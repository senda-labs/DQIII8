#!/usr/bin/env bash
# DQIII8 — Installer for Ubuntu 22.04 / 24.04
# Usage: chmod +x install.sh && ./install.sh [--no-model]
#
# Flags:
#   --no-model    Skip pulling qwen2.5-coder:7b (useful in CI/Docker)
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${CYAN}[DQIII8]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
fail()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Parse flags ───────────────────────────────────────────────────────
SKIP_MODEL=0
for arg in "$@"; do
    [[ "$arg" == "--no-model" ]] && SKIP_MODEL=1
done

# ── Root detection (Docker/CI runs as root without sudo) ──────────────
if [ "$(id -u)" = "0" ]; then
    SUDO=""
else
    SUDO="sudo"
fi

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
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq python3 python3-venv python3-pip git curl sqlite3 zstd > /dev/null
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

if [ "$SKIP_MODEL" = "1" ]; then
    info "Skipping model pull (--no-model flag set)"
    ok "To pull the model later: ollama pull qwen2.5-coder:7b"
else
    info "Pulling qwen2.5-coder:7b (Tier 1 model, ~4.4GB)..."
    # Start ollama serve in background if no service is running
    if ! ollama list &>/dev/null 2>&1; then
        ollama serve &>/tmp/ollama.log &
        sleep 3
    fi
    ollama pull qwen2.5-coder:7b
    ok "Model qwen2.5-coder:7b ready"
fi

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
        curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO -E bash -
        $SUDO apt-get install -y -qq nodejs > /dev/null
        npm install -g @anthropic-ai/claude-code
        ok "Node.js + Claude Code installed"
    fi
fi

# ── 6. Environment file ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f "config/.env.example" ]; then
        cp config/.env.example .env
        info "Created .env from template — edit it with your API keys"
    else
        info ".env.example not found — create .env manually with your API keys"
    fi
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
