#!/bin/bash
# DQIII8 Nightly Maintenance Script
# Run with: bash /root/jarvis/bin/nightly.sh > /root/jarvis/tasks/nightly-report.md 2>&1 &
# Review tomorrow: cat /root/jarvis/tasks/nightly-report.md

set -e
JARVIS_ROOT="${JARVIS_ROOT:-/root/jarvis}"
cd "$JARVIS_ROOT"

echo "# DQ Nightly Report — $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# ── 1. Auto-learner consolidation ──
echo "## 1. Auto-learner consolidation"
if python3 bin/auto_learner.py --consolidate 2>&1; then
    echo "✓ Auto-learner completed"
else
    echo "✗ Auto-learner failed"
fi
echo ""

# ── 2. Knowledge indexing ──
echo "## 2. Knowledge indexing"
for domain in formal_sciences natural_sciences social_sciences humanities_arts applied_sciences; do
    if [ -d "knowledge/$domain" ]; then
        echo -n "  Indexing $domain... "
        if python3 bin/knowledge_indexer.py --domain "$domain" 2>&1; then
            echo "✓"
        else
            echo "✗ (failed or no files)"
        fi
    else
        echo "  ⚠ knowledge/$domain not found — skipping"
    fi
done
echo ""

# ── 3. Domain classifier tests ──
echo "## 3. Domain classifier tests"
echo '  Test 1: "calculate portfolio VaR at 95%"'
python3 bin/domain_classifier.py "calculate portfolio VaR at 95%" 2>&1 || echo "  ✗ failed"
echo ""
echo '  Test 2: "write chapter 5 where Lin Feng finds the artifact"'
python3 bin/domain_classifier.py "write chapter 5 where Lin Feng finds the artifact" 2>&1 || echo "  ✗ failed"
echo ""
echo '  Test 3: "refactor the DatabaseManager class"'
python3 bin/domain_classifier.py "refactor the DatabaseManager class" 2>&1 || echo "  ✗ failed"
echo ""

# ── 4. Unresolved errors review ──
echo "## 4. Unresolved errors"
sqlite3 "$JARVIS_ROOT/database/jarvis_metrics.db" \
    "SELECT id, error_type, error_message FROM error_log WHERE resolved=0 ORDER BY id;" 2>&1 || echo "  ✗ query failed"
echo ""

# ── 5. System health ──
echo "## 5. System health"
echo "  Disk: $(df -h / | tail -1 | awk '{print $4 " free (" $5 " used)"}')"
echo "  RAM: $(free -m | awk '/Mem:/{print $7 "MB available"}')"
echo "  DB size: $(du -h $JARVIS_ROOT/database/jarvis_metrics.db | cut -f1)"
echo "  Uptime: $(uptime -p)"
echo ""

# ── 6. Telemetry (opt-in) ──
echo "## 6. Telemetry"
python3 "$JARVIS_ROOT/bin/telemetry.py" --send 2>&1 || echo "  Telemetry: disabled or failed"
echo ""

# ── 7. Git commit (no push) ──
echo "## 7. Git status"
git add -A
if git diff --cached --quiet; then
    echo "  No changes to commit"
else
    git commit -m "chore: nightly maintenance — $(date -u '+%Y-%m-%d')" 2>&1
    echo "  ✓ Changes committed (push pending)"
fi
echo ""

echo "## Summary"
echo "  Completed at: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "  Next action: review this report, then git push origin main"
