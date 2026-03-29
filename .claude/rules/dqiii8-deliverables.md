# DQIII8 — Deliverables via Telegram

After generating any of these artifacts, ALWAYS send them as Telegram documents:

| Artifact | When |
|----------|------|
| Audit report (`database/audit_reports/audit-*.md`) | After every `/audit` run |
| Checkpoint (`docs/CHECKPOINT_*.md`) | After generating a new checkpoint |

## How to send

```python
from bin.core.notify import send_document

send_document("database/audit_reports/audit-YYYY-MM-DD-HH.md",
              caption="📊 Audit Report YYYY-MM-DD — Score: X/100")

send_document("docs/CHECKPOINT_YYYY-MM-DD.md",
              caption="📋 CHECKPOINT_YYYY-MM-DD — Full system state")
```

Or via CLI:
```bash
python3 -c "
from bin.core.notify import send_document
send_document('path/to/file.md', caption='caption')
"
```

## Notes
- `send_document()` is in `bin/core/notify.py`
- Uses `sendDocument` Telegram Bot API endpoint
- Falls back silently if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set
- Caption max 1024 chars; file size limit 50 MB
