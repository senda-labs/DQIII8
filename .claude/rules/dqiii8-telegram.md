# DQIII8 — Telegram

## Notificaciones

```python
from bin.core.notify import send_telegram
send_telegram("mensaje")
```

CLI: `python3 bin/core/notify.py "mensaje"`

## /cc desde Telegram

```
/cc <prompt>      — Ejecuta en Claude Code (sonnet-4-6, timeout 300s)
/cc_status        — Auth, versión, uptime, rate limit
/auth_status      — Detalles ~/.claude/.credentials.json
/auth_test        — Prueba mínima de auth
```

**Seguridad:** solo `TELEGRAM_CHAT_ID`, rate limit 10/hora, blacklist de comandos peligrosos.
**Auth:** OAuth via `~/.claude/.credentials.json` — `CLAUDE_CODE_OAUTH_TOKEN` se elimina del entorno antes de cada llamada.
**Implementado en:** `bin/ui/dqiii8_bot.py`
