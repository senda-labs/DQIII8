#!/bin/bash
# DQIII8 Update Script v2 — Complete system update
# Usage: bash update_dqiii8.sh
set -euo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }

echo "=== DQIII8 Update v2 — $DQIII8_ROOT ==="
cd "$DQIII8_ROOT"

# 1. Pull latest
echo ""
echo "▶ 1/10 Git pull"
git pull origin main && ok "Code updated" || err "Git pull failed"

# 2. Python deps
echo ""
echo "▶ 2/10 Python dependencies"
pip install -q --break-system-packages -U crawl4ai pdfplumber docxtpl scrapling \
    2>/dev/null || pip install -q -U crawl4ai pdfplumber docxtpl scrapling
ok "Python deps"

# 3. DB schemas (both databases)
echo ""
echo "▶ 3/10 Database schemas"
sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null
sqlite3 "$DQIII8_ROOT/database/dqiii8_metrics.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null
# Ensure session_memory has domain column
sqlite3 "$DQIII8_ROOT/database/dqiii8_metrics.db" "ALTER TABLE session_memory ADD COLUMN domain TEXT;" 2>/dev/null || true
ok "Schemas applied (both DBs)"

# 4. Seed centroids (if missing)
echo ""
echo "▶ 4/10 Domain centroids"
CENTROID_COUNT=$(sqlite3 "$DQIII8_ROOT/database/dqiii8.db" "SELECT COUNT(*) FROM domain_enrichment;" 2>/dev/null || echo "0")
if [ "$CENTROID_COUNT" -lt 5 ]; then
    warn "Centroids missing ($CENTROID_COUNT found). Seeding..."
    python3 -c "
import sqlite3, json, os
conn = sqlite3.connect('$DQIII8_ROOT/database/dqiii8.db')
conn.execute('CREATE TABLE IF NOT EXISTS domain_enrichment (domain TEXT PRIMARY KEY, centroid_json TEXT, chunk_count INTEGER)')
for domain in ['applied_sciences','formal_sciences','natural_sciences','social_sciences','humanities_arts']:
    idx_path = f'$DQIII8_ROOT/knowledge/{domain}/index.json'
    if not os.path.exists(idx_path): continue
    idx = json.load(open(idx_path))
    chunks = idx.get('chunks', [])
    if not chunks: continue
    embs = [c['embedding'] for c in chunks if 'embedding' in c]
    if not embs: continue
    dim = len(embs[0])
    centroid = [sum(e[i] for e in embs)/len(embs) for i in range(dim)]
    conn.execute('INSERT OR REPLACE INTO domain_enrichment VALUES (?,?,?)',
        (domain, json.dumps(centroid), len(chunks)))
conn.commit()
print(f'Seeded {conn.execute(\"SELECT COUNT(*) FROM domain_enrichment\").fetchone()[0]} centroids')
" 2>/dev/null && ok "Centroids seeded" || warn "Centroid seeding failed (may need Ollama)"
else
    ok "Centroids present ($CENTROID_COUNT)"
fi

# 5. Knowledge re-index (only if stale)
echo ""
echo "▶ 5/10 Knowledge indexes"
if python3 -c "
import json
idx = json.load(open('knowledge/applied_sciences/index.json'))
dim = idx.get('chunks', [{}])[0].get('embedding_dim', 0) if idx.get('chunks') else 0
exit(0 if dim == 1024 else 1)
" 2>/dev/null; then
    ok "Knowledge indexes bge-m3 (1024d)"
else
    warn "Re-indexing knowledge..."
    for d in applied_sciences formal_sciences natural_sciences social_sciences humanities_arts; do
        python3 bin/agents/knowledge_indexer.py --domain "$d" 2>/dev/null
    done && ok "Re-indexed" || err "Re-index failed"
fi

# 6. Claude Code settings (permissions + plugins)
echo ""
echo "▶ 6/10 Claude Code settings"
if [ -f "$DQIII8_ROOT/config/claude_settings_template.json" ]; then
    if [ ! -f "$HOME/.claude/settings.json" ]; then
        mkdir -p "$HOME/.claude"
        cp "$DQIII8_ROOT/config/claude_settings_template.json" "$HOME/.claude/settings.json"
        ok "Global Claude settings configured"
    else
        ok "Global Claude settings already exist"
    fi
    if [ ! -f "$DQIII8_ROOT/.claude/settings.json" ]; then
        cp "$DQIII8_ROOT/config/claude_settings_template.json" "$DQIII8_ROOT/.claude/settings.json"
        ok "Project Claude settings configured"
    else
        ok "Project Claude settings already exist"
    fi
fi

# 7. Bun (required for OMC + Channels)
echo ""
echo "▶ 7/10 Bun runtime"
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
if command -v bun &>/dev/null; then
    ok "Bun $(bun --version)"
else
    warn "Installing Bun..."
    curl -fsSL https://bun.sh/install | bash 2>/dev/null
    export BUN_INSTALL="$HOME/.bun"
    export PATH="$BUN_INSTALL/bin:$PATH"
    ok "Bun installed"
fi

# 8. Symlink dqiii8.db (fix if broken)
echo ""
echo "▶ 8/10 Database integrity"
if [ -L "$DQIII8_ROOT/database/dqiii8.db" ]; then
    TARGET=$(readlink "$DQIII8_ROOT/database/dqiii8.db")
    if [ ! -f "$TARGET" ]; then
        warn "Broken symlink: $TARGET — recreating as real file"
        rm "$DQIII8_ROOT/database/dqiii8.db"
        sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql"
        ok "Database recreated"
    else
        ok "Database symlink OK"
    fi
else
    ok "Database is real file"
fi

# 9. Services
echo ""
echo "▶ 9/10 Services"
if systemctl is-active dqiii8-bot >/dev/null 2>&1; then
    systemctl restart dqiii8-bot && ok "dqiii8-bot restarted"
elif [ -f "/etc/systemd/system/dqiii8-bot.service" ]; then
    systemctl daemon-reload
    systemctl enable --now dqiii8-bot && ok "dqiii8-bot started"
else
    warn "No bot service found. Create with:"
    echo "  See docs/dqiii8_guide.html for systemd setup"
fi
systemctl restart ollama 2>/dev/null && ok "Ollama restarted" || warn "Ollama not managed by systemd"

# 10. Verify
echo ""
echo "▶ 10/10 Verification"
python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -3
claude --version 2>/dev/null && ok "Claude Code: $(claude --version 2>/dev/null)" || warn "Claude Code not installed"
echo ""
echo "=== Update complete ==="
echo ""
echo "Next steps:"
echo "  1. Configure API keys: nano .env"
echo "  2. Install Claude Code plugins: dqa then /plugin install oh-my-claudecode"
echo "  3. Full test suite: python3 -m pytest tests/ -q"
