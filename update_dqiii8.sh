#!/bin/bash
# DQIII8 Update Script v3 — Complete system update
# Usage: bash update_dqiii8.sh
set -uo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }

echo "=== DQIII8 Update v3 — $DQIII8_ROOT ==="
cd "$DQIII8_ROOT"

# 1. Pull latest
echo ""
echo "▶ 1/10 Git pull"
git pull origin main && ok "Code updated" || warn "Git pull failed (may need auth)"

# 2. Python deps
echo ""
echo "▶ 2/10 Python dependencies"
pip install -q --break-system-packages --ignore-installed \
    crawl4ai pdfplumber docxtpl scrapling 2>/dev/null \
    || pip install -q --break-system-packages --ignore-installed \
    crawl4ai pdfplumber docxtpl scrapling 2>/dev/null \
    || warn "Some Python deps failed — check manually"
ok "Python deps"

# 3. DB schemas (both databases, idempotent)
echo ""
echo "▶ 3/10 Database schemas"
sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null || true
sqlite3 "$DQIII8_ROOT/database/dqiii8_metrics.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null || true
sqlite3 "$DQIII8_ROOT/database/dqiii8_metrics.db" \
    "CREATE TABLE IF NOT EXISTS session_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, domain TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);" 2>/dev/null || true
ok "Schemas applied"

# 4. Database integrity (fix broken symlinks)
echo ""
echo "▶ 4/10 Database integrity"
if [ -L "$DQIII8_ROOT/database/dqiii8.db" ]; then
    TARGET=$(readlink "$DQIII8_ROOT/database/dqiii8.db")
    if [ ! -f "$TARGET" ]; then
        warn "Broken symlink: $TARGET — recreating as real file"
        rm "$DQIII8_ROOT/database/dqiii8.db"
        sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null || true
        ok "Database recreated"
    else
        ok "Database symlink OK"
    fi
else
    ok "Database is real file"
fi

# 5. Knowledge re-index (before centroids) — per-domain chunk count check
echo ""
echo "▶ 5/10 Knowledge indexes"
REINDEXED=false
python3 -c "
import json, os, sys, glob

domains = ['applied_sciences','formal_sciences','natural_sciences','social_sciences','humanities_arts']
reindexed = []
for domain in domains:
    idx_path = f'knowledge/{domain}/index.json'
    md_dir = f'knowledge/{domain}'
    md_count = len(glob.glob(os.path.join(md_dir, '*.md')))

    needs_reindex = False
    if not os.path.exists(idx_path):
        needs_reindex = True
    else:
        idx = json.load(open(idx_path))
        chunks = idx.get('chunks', [])
        if not chunks:
            needs_reindex = True
        else:
            dim = chunks[0].get('embedding_dim', len(chunks[0].get('embedding', [])))
            if dim != 1024:
                needs_reindex = True
            elif len(chunks) != md_count:
                needs_reindex = True

    if needs_reindex:
        reindexed.append(domain)
        print(f'  REINDEX {domain} (md={md_count})')
    else:
        print(f'  OK {domain} ({len(chunks)} chunks, {md_count} files)')

if reindexed:
    print('NEEDS_REINDEX:' + ','.join(reindexed))
    sys.exit(1)
else:
    sys.exit(0)
" 2>/dev/null
KNOWLEDGE_STATUS=$?

if [ $KNOWLEDGE_STATUS -eq 0 ]; then
    ok "Knowledge indexes up to date"
else
    REINDEXED=true
    DOMAINS_TO_INDEX=$(python3 -c "
import json, os, glob
domains = ['applied_sciences','formal_sciences','natural_sciences','social_sciences','humanities_arts']
for domain in domains:
    idx_path = f'knowledge/{domain}/index.json'
    md_dir = f'knowledge/{domain}'
    md_count = len(glob.glob(os.path.join(md_dir, '*.md')))
    needs = False
    if not os.path.exists(idx_path):
        needs = True
    else:
        idx = json.load(open(idx_path))
        chunks = idx.get('chunks', [])
        if not chunks: needs = True
        else:
            dim = chunks[0].get('embedding_dim', len(chunks[0].get('embedding', [])))
            if dim != 1024 or len(chunks) != md_count: needs = True
    if needs: print(domain)
" 2>/dev/null)
    for d in $DOMAINS_TO_INDEX; do
        warn "Re-indexing $d..."
        python3 bin/agents/knowledge_indexer.py --domain "$d" 2>/dev/null && ok "  $d indexed" || warn "  $d failed"
    done
fi

# 6. Seed centroids (AFTER indexing)
echo ""
echo "▶ 6/10 Domain centroids"
CENTROID_COUNT=$(sqlite3 "$DQIII8_ROOT/database/dqiii8.db" \
    "SELECT COUNT(*) FROM domain_enrichment;" 2>/dev/null || echo "0")
if [ "$CENTROID_COUNT" -lt 5 ] || [ "$REINDEXED" = true ]; then
    python3 -c "
import sqlite3, json, os
conn = sqlite3.connect('$DQIII8_ROOT/database/dqiii8.db')
conn.execute('''CREATE TABLE IF NOT EXISTS domain_enrichment
    (domain TEXT PRIMARY KEY, centroid_json TEXT, chunk_count INTEGER)''')
seeded = 0
for domain in ['applied_sciences','formal_sciences','natural_sciences','social_sciences','humanities_arts']:
    idx_path = f'$DQIII8_ROOT/knowledge/{domain}/index.json'
    if not os.path.exists(idx_path): continue
    idx = json.load(open(idx_path))
    chunks = idx.get('chunks', [])
    embs = [c['embedding'] for c in chunks if 'embedding' in c]
    if not embs: continue
    dim = len(embs[0])
    centroid = [sum(e[i] for e in embs)/len(embs) for i in range(dim)]
    conn.execute('INSERT OR REPLACE INTO domain_enrichment VALUES (?,?,?)',
        (domain, json.dumps(centroid), len(chunks)))
    seeded += 1
    print(f'  {domain}: {len(chunks)} chunks, {dim}d centroid')
conn.commit()
print(f'Seeded {seeded} centroids')
" 2>/dev/null && ok "Centroids seeded" || warn "Centroid seeding failed"
else
    ok "Centroids present ($CENTROID_COUNT)"
fi

# 7. Claude Code settings (permissions + plugins)
echo ""
echo "▶ 7/10 Claude Code settings"
if [ -f "$DQIII8_ROOT/config/claude_settings_template.json" ]; then
    if [ ! -f "$HOME/.claude/settings.json" ]; then
        mkdir -p "$HOME/.claude"
        cp "$DQIII8_ROOT/config/claude_settings_template.json" "$HOME/.claude/settings.json"
        ok "Global Claude settings configured (permissions + plugins)"
    else
        ok "Global Claude settings exist"
    fi
    if [ ! -f "$DQIII8_ROOT/.claude/settings.json" ]; then
        cp "$DQIII8_ROOT/config/claude_settings_template.json" "$DQIII8_ROOT/.claude/settings.json"
        ok "Project Claude settings configured"
    else
        ok "Project Claude settings exist"
    fi
else
    warn "No settings template found"
fi

# 8. Bun runtime (required for OMC + Channels plugins)
echo ""
echo "▶ 8/10 Bun runtime"
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
if command -v bun &>/dev/null; then
    ok "Bun $(bun --version)"
else
    warn "Installing Bun..."
    curl -fsSL https://bun.sh/install | bash 2>/dev/null
    export BUN_INSTALL="$HOME/.bun"
    export PATH="$BUN_INSTALL/bin:$PATH"
    bun --version &>/dev/null && ok "Bun installed" || warn "Bun install failed"
fi

# 9. Services
echo ""
echo "▶ 9/10 Services"
# Bot service
if systemctl is-active dqiii8-bot >/dev/null 2>&1; then
    systemctl restart dqiii8-bot && ok "dqiii8-bot restarted"
elif [ -f "/etc/systemd/system/dqiii8-bot.service" ]; then
    systemctl daemon-reload
    systemctl enable --now dqiii8-bot && ok "dqiii8-bot started"
else
    # Create service automatically
    cat > /etc/systemd/system/dqiii8-bot.service << 'SVCEOF'
[Unit]
Description=DQIII8 Telegram Bot
After=network.target ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/dqiii8
ExecStart=/usr/bin/python3 bin/ui/dqiii8_bot.py
Restart=always
RestartSec=5
Environment=DQIII8_ROOT=/root/dqiii8

[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable --now dqiii8-bot && ok "dqiii8-bot service created and started" || warn "Bot service creation failed"
fi
# Ollama
systemctl restart ollama 2>/dev/null && ok "Ollama restarted" || warn "Ollama not managed by systemd"

# 10. Verify
echo ""
echo "▶ 10/10 Verification"
echo "  Tests:"
python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -3
echo "  Claude Code:"
claude --version 2>/dev/null && ok "Claude Code $(claude --version 2>/dev/null)" || warn "Claude Code not installed"
echo "  Ollama models:"
ollama list 2>/dev/null | head -5 || warn "Ollama not available"
echo "  Bot:"
systemctl is-active dqiii8-bot 2>/dev/null && ok "Bot active" || warn "Bot not running"

echo ""
echo "=== Update complete ==="
echo ""
echo "Next steps:"
echo "  1. Configure API keys if not done: nano .env"
echo "  2. Install Claude Code plugins: dqa then /plugin install oh-my-claudecode"
echo "  3. Full test suite: python3 -m pytest tests/ -q"
echo "  4. Test Telegram: send /cc echo test to your bot"
