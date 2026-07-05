#!/usr/bin/env bash
# Symbol-anchor verification for the 4 real jarvis-control3 v2 patches applied
# this session. Anchors by symbol name, not line number (lines rot). This repo
# is not git-tracked, so there is nothing to `git apply` here — the patches
# were applied in place; this script only verifies they're present and intact.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

check() {
  local desc="$1" file="$2" pattern="$3"
  if grep -qE "$pattern" "$file" 2>/dev/null; then
    echo "OK   $desc"
  else
    echo "FAIL $desc  ($file :: $pattern)"
    FAIL=1
  fi
}

echo "== Schema =="
check "human_pending_tasks table exists" \
  <(sqlite3 "$ROOT/database/dqiii8.db" ".tables") "human_pending_tasks"
check "resumable_actions has seed rows" \
  <(sqlite3 "$ROOT/database/dqiii8.db" "SELECT count(*) FROM resumable_actions;") "^[1-9]"
check "trg_hpt_valid_transition trigger present" \
  <(sqlite3 "$ROOT/database/dqiii8.db" "SELECT name FROM sqlite_master WHERE type='trigger';") "trg_hpt_valid_transition"
check "trg_hpt_immutable_exec_fields trigger present" \
  <(sqlite3 "$ROOT/database/dqiii8.db" "SELECT name FROM sqlite_master WHERE type='trigger';") "trg_hpt_immutable_exec_fields"

echo "== bin/core/db.py =="
check "get_db accepts busy_timeout_ms" "$ROOT/bin/core/db.py" \
  "def get_db\(timeout=10, busy_timeout_ms=None\)"

echo "== bin/core/notify.py =="
check "send_telegram signature has reply_markup+chat_id+retries" "$ROOT/bin/core/notify.py" \
  "def send_telegram\(message: str, \*, parse_mode: str = None, reply_markup: dict = None,"
check "SendResult dataclass defined" "$ROOT/bin/core/notify.py" "class SendResult"

echo "== bin/core/human_pending/ =="
check "register_and_notify defined" "$ROOT/bin/core/human_pending/__init__.py" \
  "^def register_and_notify\("
check "claim (atomic, CAS on version) defined" "$ROOT/bin/core/human_pending/__init__.py" \
  "^def claim\(task_id: str, claimed_by: str, version: int"
check "secrets.py stub defined" "$ROOT/bin/core/human_pending/secrets.py" \
  "^def resolve\(secret_ref"

echo "== bin/ui/dqiii8_bot.py =="
check "handle_satisfaction_callback untouched (sat: pattern still registered)" "$ROOT/bin/ui/dqiii8_bot.py" \
  'CallbackQueryHandler\(handle_satisfaction_callback, pattern=r"\^sat:"\)'
check "handle_resume_callback defined" "$ROOT/bin/ui/dqiii8_bot.py" \
  "^async def handle_resume_callback\("
check "hpt: handler registered in main()" "$ROOT/bin/ui/dqiii8_bot.py" \
  'CallbackQueryHandler\(handle_resume_callback, pattern=r"\^hpt"\)'
check "row-level allowed_chat_id check (not global ALLOWED_CHAT_ID) in resume handler" \
  "$ROOT/bin/ui/dqiii8_bot.py" 'row\["allowed_chat_id"\]'

echo "== cobrowsing_batch.py (patch real #1) =="
check "register_and_notify wired on session error" \
  "$ROOT/my-projects/intl-reports/scripts/cobrowsing_batch.py" "human_pending.register_and_notify"
check "exits after registering (releases Chrome 9222)" \
  "$ROOT/my-projects/intl-reports/scripts/cobrowsing_batch.py" "sys.exit\(0\)"

echo "== intel_navigator/resolver.py (patch real #2) =="
check "_notify_hard_block defined" \
  "$ROOT/my-projects/intl-reports/tools/intel/navigator/resolver.py" \
  "async def _notify_hard_block\("
check "called once in resolve(), not per-source _safe_fetch" \
  "$ROOT/my-projects/intl-reports/tools/intel/navigator/resolver.py" \
  "await self._notify_hard_block\(results, identity, task_id\)"
NOTIFY_IN_SAFE_FETCH=$(awk '/async def _safe_fetch/,/^    async def _fetch_once/' \
  "$ROOT/my-projects/intl-reports/tools/intel/navigator/resolver.py" | grep -c "_notify_hard_block" || true)
if [ "$NOTIFY_IN_SAFE_FETCH" -eq 0 ]; then
  echo "OK   _notify_hard_block NOT called inside _safe_fetch (no per-attempt flood)"
else
  echo "FAIL _notify_hard_block called inside _safe_fetch -- would flood-ban on retries"
  FAIL=1
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "SOME CHECKS FAILED"
fi
exit "$FAIL"
