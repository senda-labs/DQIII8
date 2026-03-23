#!/bin/bash
# DQIII8 Nightly Maintenance Script
# Run with: bash $(dirname "$0")/nightly.sh > $DQIII8_ROOT/tasks/nightly-report.md 2>&1 &
# Review tomorrow: cat $DQIII8_ROOT/tasks/nightly-report.md

set -e
DQIII8_ROOT="${DQIII8_ROOT:-/root/jarvis}"
cd "$DQIII8_ROOT"

echo "# DQ Nightly Report — $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

# ── 1. Auto-learner consolidation ──
echo "## 1. Auto-learner consolidation"
if python3 bin/tools/auto_learner.py --consolidate 2>&1; then
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
        if python3 bin/agents/knowledge_indexer.py --domain "$domain" 2>&1; then
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
python3 bin/agents/domain_classifier.py "calculate portfolio VaR at 95%" 2>&1 || echo "  ✗ failed"
echo ""
echo '  Test 2: "write chapter 5 where Lin Feng finds the artifact"'
python3 bin/agents/domain_classifier.py "write chapter 5 where Lin Feng finds the artifact" 2>&1 || echo "  ✗ failed"
echo ""
echo '  Test 3: "refactor the DatabaseManager class"'
python3 bin/agents/domain_classifier.py "refactor the DatabaseManager class" 2>&1 || echo "  ✗ failed"
echo ""

# ── 4. Unresolved errors review ──
echo "## 4. Unresolved errors"
sqlite3 "$DQIII8_ROOT/database/dqiii8.db" \
    "SELECT id, error_type, error_message FROM error_log WHERE resolved=0 ORDER BY id;" 2>&1 || echo "  ✗ query failed"
echo ""

# ── 5. System health ──
echo "## 5. System health"
echo "  Disk: $(df -h / | tail -1 | awk '{print $4 " free (" $5 " used)"}')"
echo "  RAM: $(free -m | awk '/Mem:/{print $7 "MB available"}')"
echo "  DB size: $(du -h $DQIII8_ROOT/database/dqiii8.db | cut -f1)"
echo "  Uptime: $(uptime -p)"
echo ""

# ── 6. Local health audit ──
echo "## 6. Health Audit"
if python3 "$DQIII8_ROOT/bin/monitoring/auditor_local.py" 2>&1; then
    echo "✓ Audit completed"
else
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -eq 1 ]; then
        echo "⚠ Audit: WARNING — review score above"
    else
        echo "✗ Audit: CRITICAL — immediate attention required"
    fi
fi
echo ""

# ── 7. Telemetry (opt-in) ──
echo "## 6. Telemetry"
python3 "$DQIII8_ROOT/bin/monitoring/telemetry.py" --send 2>&1 || echo "  Telemetry: disabled or failed"
echo ""

# ── 8. Git commit (no push) ──
echo "## 8. Git status"
git add -A
if git diff --cached --quiet; then
    echo "  No changes to commit"
else
    git commit -m "chore: nightly maintenance — $(date -u '+%Y-%m-%d')" 2>&1
    echo "  ✓ Changes committed (push pending)"
fi
echo ""

REPORT="${DQIII8_ROOT}/tasks/nightly-report.md"

# ── 9. Paper harvester ──
echo "## 9. Paper Harvest"
python3 "$DQIII8_ROOT/bin/tools/paper_harvester.py" --all 2>&1 || echo "  Paper harvest failed"
echo ""

# ── 10. Prune outdated papers ──
echo "## 10. Prune Outdated Papers"
python3 "$DQIII8_ROOT/bin/tools/paper_harvester.py" --prune --prune-days 180 2>&1 || echo "  Prune failed"
echo ""

# ── 11. Smoke tests ──
echo "## 11. Smoke Tests"
if python3 -m pytest "$DQIII8_ROOT/tests/test_smoke.py" --tb=short -q 2>&1; then
    echo "  ✓ All smoke tests passed"
else
    echo "  ✗ Smoke tests FAILED — audit max score capped at 80"
fi
echo ""

echo "## Summary"
echo "  Completed at: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "  Next action: review this report, then git push origin main"
