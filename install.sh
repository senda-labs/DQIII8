#!/usr/bin/env bash
# DQIII8 — Universal Installer
# Supports: Ubuntu 22.04+, Debian 12+, macOS 13+ (Ventura)
#
# Usage:
#   From cloned repo:  bash install.sh [--no-model]
#   Via curl:          curl -fsSL https://raw.githubusercontent.com/senda-labs/DQIII8/main/install.sh | bash
#
# Flags:
#   --no-model    Skip pulling qwen2.5-coder:7b (recommended for CI/Docker)
#
# Environment vars:
#   DQIII8_DIR    Override install location (default: /opt/dqiii8 for root, ~/dqiii8 for users)

set -euo pipefail

cat << 'BANNER'

    ██████╗  ██████╗ ██╗██╗██╗ █████╗
    ██╔══██╗██╔═══██╗██║██║██║██╔══██╗
    ██║  ██║██║   ██║██║██║██║╚█████╔╝
    ██║  ██║██║▄▄ ██║██║██║██║██╔══██╗
    ██████╔╝╚██████╔╝██║██║██║╚█████╔╝
    ╚═════╝  ╚══▀▀═╝ ╚═╝╚═╝╚═╝ ╚════╝

    Works for you. Go outside and live.

    Self-auditing AI orchestrator
    70% free model routing | Auto-learning | Zero prompting skill needed

    github.com/senda-labs/DQIII8

BANNER

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[DQIII8]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  {
    local num="$1" total="$2" msg="$3"
    echo ""
    echo -e "  ${BOLD}[$num/$total]${NC} $msg"
    echo "  ─────────────────────────────────────"
}

# ── Parse flags ─────────────────────────────────────────────────────────────
SKIP_MODEL=0
for arg in "$@"; do
    [[ "$arg" == "--no-model" ]] && SKIP_MODEL=1
done

# ── Root / sudo detection ────────────────────────────────────────────────────
NO_SYSTEM_PKGS=0
if [ "$(id -u)" = "0" ]; then
    SUDO=""
    info "Running as root"
elif command -v sudo &>/dev/null; then
    SUDO="sudo"
    info "Running as user with sudo"
else
    warn "Not root and no sudo available."
    warn "System packages must be pre-installed: python3.11+, python3-venv, git, curl, zstd, sqlite3"
    SUDO=""
    NO_SYSTEM_PKGS=1
fi

# ── OS / platform detection ──────────────────────────────────────────────────
step 1 7 "Detecting platform..."

OS="$(uname -s)"
ARCH="$(uname -m)"
DISTRO=""
OS_VERSION=""

case "$OS" in
    MINGW*|MSYS*|CYGWIN*)
        echo ""
        echo "══════════════════════════════════════════════════════"
        echo "  Windows detected — DQIII8 requires WSL2"
        echo ""
        echo "  Install WSL2 (5 minutes, free):"
        echo "  1. Open PowerShell as Administrator"
        echo "  2. Run: wsl --install -d Ubuntu-24.04"
        echo "  3. Restart your computer"
        echo "  4. Open 'Ubuntu' from Start menu"
        echo "  5. Run this installer again inside Ubuntu"
        echo "══════════════════════════════════════════════════════"
        exit 1
        ;;
    Linux)
        if [ -f /etc/os-release ]; then
            # shellcheck disable=SC1091
            . /etc/os-release
            DISTRO="${ID:-linux}"
            OS_VERSION="${VERSION_ID:-}"
        else
            DISTRO="linux"
        fi
        ;;
    Darwin)
        DISTRO="macos"
        OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
        ;;
    *)
        fail "Unsupported OS: $OS. DQIII8 supports Ubuntu 22.04+, Debian 12+, macOS 13+"
        ;;
esac

# WSL2 detection (runs as Linux — just log it)
if grep -qi microsoft /proc/version 2>/dev/null; then
    info "WSL2 detected — installing normally"
fi

ok "Platform: $DISTRO $OS_VERSION ($ARCH)"

# ── Install directory ────────────────────────────────────────────────────────
if [ "$(id -u)" = "0" ]; then
    DEFAULT_DIR="/opt/dqiii8"
else
    DEFAULT_DIR="$HOME/dqiii8"
fi

# If requirements.txt exists here, we're already inside the repo
if [ -f "requirements.txt" ] && [ -f "database/schema.sql" ]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
    cd "$PROJECT_DIR"
    info "Running from existing repo: $PROJECT_DIR"
else
    # Curl-pipe mode: clone the repo first
    INSTALL_DIR="${DQIII8_DIR:-$DEFAULT_DIR}"
    info "Target install location: $INSTALL_DIR"
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Repo already exists — pulling latest..."
        git -C "$INSTALL_DIR" pull --quiet
    else
        info "Cloning DQIII8..."
        git clone --depth=1 https://github.com/senda-labs/DQIII8.git "$INSTALL_DIR"
    fi
    PROJECT_DIR="$INSTALL_DIR"
    cd "$PROJECT_DIR"
fi

# ── Phase 1: System packages (needs root/sudo) ───────────────────────────────
step 2 7 "Installing system dependencies..."

if [ "$NO_SYSTEM_PKGS" = "0" ]; then
    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            $SUDO apt-get update -qq
            $SUDO apt-get install -y -qq \
                python3 python3-venv python3-pip git curl sqlite3 zstd > /dev/null
            ok "System packages installed (apt)"
            ;;
        macos)
            if ! command -v brew &>/dev/null; then
                info "Homebrew not found. Installing..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            brew install python@3.12 git curl sqlite zstd --quiet
            ok "System packages installed (brew)"
            ;;
        *)
            warn "Unknown distro '$DISTRO'. Skipping system package install."
            warn "Please ensure python3.11+, python3-venv, git, curl, sqlite3, zstd are installed."
            ;;
    esac
else
    info "Skipping system package install (no sudo/root)"
fi

# ── Phase 2: Python virtual environment ─────────────────────────────────────
PYTHON_BIN="python3"
if [ "$DISTRO" = "macos" ] && command -v python3.12 &>/dev/null; then
    PYTHON_BIN="python3.12"
fi

if [ ! -d "$PROJECT_DIR/.venv" ]; then
    "$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$PROJECT_DIR/.venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q
ok "Python venv ready (.venv) — $($PYTHON_BIN --version)"

# ── Phase 3: Ollama ──────────────────────────────────────────────────────────
step 3 7 "Installing Ollama (Tier C — free local AI)..."

if command -v ollama &>/dev/null; then
    ok "Ollama already installed"
else
    case "$DISTRO" in
        macos)
            if command -v brew &>/dev/null; then
                brew install ollama --quiet
                ok "Ollama installed (brew)"
            else
                warn "Homebrew not available. Download Ollama from https://ollama.com/download"
                warn "Then re-run: bash $PROJECT_DIR/install.sh --no-model"
                SKIP_MODEL=1
            fi
            ;;
        *)
            curl -fsSL https://ollama.com/install.sh | sh
            ok "Ollama installed"
            ;;
    esac
fi

if [ "$SKIP_MODEL" = "1" ]; then
    info "Skipping model pull (--no-model)"
    ok "Pull later with: ollama pull qwen2.5-coder:7b"
else
    info "Pulling qwen2.5-coder:7b (~4.4GB, Tier 1 local model)..."
    if ! ollama list &>/dev/null 2>&1; then
        ollama serve &>/tmp/ollama-dqiii8.log &
        sleep 3
    fi
    ollama pull qwen2.5-coder:7b
    ok "Model qwen2.5-coder:7b ready"
fi

# ── Phase 4: SQLite database ─────────────────────────────────────────────────
step 4 7 "Setting up DQIII8..."

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
        ok "Empty database created (schema.sql not found)"
    fi
else
    ok "Database already exists"
fi

# ── Phase 5: Claude Code (optional) ──────────────────────────────────────────
step 5 7 "Installing Node.js + Claude Code..."

_install_claude_code() {
    if [ -n "$SUDO" ] && [ "$(id -u)" != "0" ]; then
        npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null \
            || npm install --prefix "$HOME/.local" @anthropic-ai/claude-code --quiet 2>/dev/null \
            || { warn "Claude Code install failed. Install manually: npm install -g @anthropic-ai/claude-code"; return 0; }
    else
        npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null \
            || { warn "Claude Code install failed. Install manually: npm install -g @anthropic-ai/claude-code"; return 0; }
    fi
    ok "Claude Code installed"
}

if command -v claude &>/dev/null; then
    ok "Claude Code already installed"
elif command -v npm &>/dev/null; then
    _install_claude_code
else
    info "Node.js not found. Installing..."
    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            if [ -z "$SUDO" ]; then
                curl -fsSL https://deb.nodesource.com/setup_22.x | bash - 2>/dev/null
            else
                curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - 2>/dev/null
            fi
            $SUDO apt-get install -y -qq nodejs > /dev/null
            _install_claude_code
            ;;
        macos)
            brew install node --quiet
            _install_claude_code
            ;;
        *)
            warn "Cannot auto-install Node.js on $DISTRO. Install manually then run: npm install -g @anthropic-ai/claude-code"
            ;;
    esac
fi

# ── Phase 6: Environment + alias ────────────────────────────────────────────
step 6 7 "Configuring environment..."

if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/config/.env.example" ]; then
        cp "$PROJECT_DIR/config/.env.example" "$PROJECT_DIR/.env"
        info "Created .env from template — edit it with your API keys"
    else
        info ".env.example not found — create .env manually with your API keys"
    fi
else
    ok ".env already exists"
fi

SHELL_RC="$HOME/.bashrc"
[ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"

ALIAS_LINE="alias dq='bash $PROJECT_DIR/bin/j.sh'"
if ! grep -q "alias dq=" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# DQIII8" >> "$SHELL_RC"
    echo "$ALIAS_LINE" >> "$SHELL_RC"
    ok "Added 'dq' alias to $SHELL_RC"
else
    ok "'dq' alias already in $SHELL_RC"
fi

# ── Phase 7: Security verification ──────────────────────────────────────────
step 7 7 "Running security checks..."

if [ -f "$PROJECT_DIR/bin/verify_install.py" ]; then
    python3 "$PROJECT_DIR/bin/verify_install.py" || warn "Some security checks failed — see above"
else
    warn "bin/verify_install.py not found — skipping security check"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
# Read API key status from .env for the tier summary
GROQ_KEY=""
ANTHROPIC_KEY=""
if [ -f "$PROJECT_DIR/.env" ]; then
    GROQ_KEY="$(grep -E '^GROQ_API_KEY=' "$PROJECT_DIR/.env" | cut -d= -f2 | tr -d '[:space:]')"
    ANTHROPIC_KEY="$(grep -E '^ANTHROPIC_API_KEY=' "$PROJECT_DIR/.env" | cut -d= -f2 | tr -d '[:space:]')"
fi

TIER_B_STATUS="✗ Add GROQ_API_KEY to .env"
TIER_A_STATUS="✗ Add ANTHROPIC_API_KEY to .env"
[ -n "$GROQ_KEY" ] && TIER_B_STATUS="✓ Ready"
[ -n "$ANTHROPIC_KEY" ] && TIER_A_STATUS="✓ Ready"

echo ""
echo -e "${GREEN}  ══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   DQIII8 installed successfully!${NC}"
echo -e "${GREEN}  ══════════════════════════════════════════════════${NC}"
echo ""
echo "   Location:  $PROJECT_DIR"
echo "   Config:    $PROJECT_DIR/.env"
echo ""
echo "   Quick start:"
echo "     source $SHELL_RC"
echo "     dq \"hello, who are you?\""
echo ""
echo "   Tiers available:"
echo "     Tier C (local, free)  ✓ Ready"
echo "     Tier B (Groq, free)   $TIER_B_STATUS"
echo "     Tier A (Claude, paid) $TIER_A_STATUS"
echo ""
echo "   Learn more:  github.com/senda-labs/DQIII8"
echo "   Privacy:     $PROJECT_DIR/PRIVACY.md"
echo -e "${GREEN}  ══════════════════════════════════════════════════${NC}"
echo ""
