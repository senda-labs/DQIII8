#!/bin/bash
# DQIII8 Update Script — Run on target VPS after git pull
# Usage: bash update_dqiii8.sh
set -euo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}✓${NC} $*"; }
err() { echo -e "${RED}✗${NC} $*"; }

echo "=== DQIII8 Update — $DQIII8_ROOT ==="
cd "$DQIII8_ROOT"

# 1. Pull latest
echo ""
echo "▶ 1/6 Git pull"
git pull origin main && ok "Code updated" || err "Git pull failed"

# 2. Python deps
echo ""
echo "▶ 2/6 Python dependencies"
pip install -q --break-system-packages -U crawl4ai pdfplumber docxtpl scrapling pydantic-ai \
    2>/dev/null || pip install -q -U crawl4ai pdfplumber docxtpl scrapling pydantic-ai
ok "Python deps updated"

# 3. DB schemas
echo ""
echo "▶ 3/6 Database schemas"
sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null
ok "Schema applied (idempotent)"

# 4. Knowledge re-index (only if indexes look stale)
echo ""
echo "▶ 4/6 Knowledge index check"
if python3 -c "
import json
idx = json.load(open('knowledge/applied_sciences/index.json'))
dim = idx.get('chunks', [{}])[0].get('embedding_dim', 0) if idx.get('chunks') else 0
exit(0 if dim == 1024 else 1)
" 2>/dev/null; then
    ok "Knowledge indexes already bge-m3 (1024d)"
else
    echo "  Re-indexing knowledge (bge-m3)..."
    python3 bin/agents/knowledge_indexer.py --all 2>/dev/null && ok "Re-indexed" || err "Re-index failed"
fi

# 5. Services
echo ""
echo "▶ 5/6 Services"
if systemctl is-active dqiii8-bot >/dev/null 2>&1; then
    systemctl restart dqiii8-bot && ok "dqiii8-bot restarted"
elif systemctl is-active jarvis-bot >/dev/null 2>&1; then
    systemctl restart jarvis-bot && ok "jarvis-bot restarted (legacy name)"
else
    echo "  No bot service found — start manually: python3 bin/ui/dqiii8_bot.py"
fi
systemctl restart ollama 2>/dev/null && ok "Ollama restarted" || echo "  Ollama not managed by systemd"

# 6. Verify
echo ""
echo "▶ 6/6 Verification"
python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -3
claude --version 2>/dev/null && ok "Claude Code: $(claude --version 2>/dev/null)" || echo "  Claude Code not installed"

echo ""
echo "=== Update complete ==="
