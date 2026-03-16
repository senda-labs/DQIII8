---
name: security-review
description: Use this skill when adding authentication, handling user input, working with secrets, creating API endpoints, or implementing any feature that touches credentials or external services. Provides JARVIS-adapted security checklist.
origin: ECC/affaan-m (adaptado para JARVIS — Python/SQLite/FastAPI)
status: APROBADA
---

# Security Review Skill

## When to Activate

- Adding or modifying authentication / authorization logic
- Handling user input (API endpoints, Telegram bot commands, CLI args)
- Working with secrets, API keys, or `.env` files
- Creating or modifying database queries (jarvis_metrics.db)
- Implementing new hooks that execute shell commands
- Any feature that touches `permission_analyzer.py`

## Checklist

### 1. Secrets Management

**NEVER do this:**
```python
API_KEY = "sk-real-key-here"           # hardcoded secret
os.system(f"curl -H 'Auth: {key}'")    # secret in shell log
```

**ALWAYS do this:**
```python
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path("/root/jarvis/.env"))
key = os.getenv("OPENROUTER_API_KEY", "")
if not key:
    raise KeyError("OPENROUTER_API_KEY missing from .env")
```

**Verify:**
- [ ] No secrets in source files (`grep -r "sk-" . --include="*.py"`)
- [ ] All keys load from `/root/jarvis/.env` via dotenv
- [ ] `.env` in `.gitignore`

### 2. SQL Injection Prevention

**NEVER concatenate SQL:**
```python
# BAD
conn.execute(f"SELECT * FROM sessions WHERE project = '{project}'")
```

**ALWAYS use parameterized queries:**
```python
# GOOD
conn.execute("SELECT * FROM sessions WHERE project = ?", (project,))
```

**Verify:**
- [ ] All queries use `?` placeholders
- [ ] No f-strings or `%` formatting inside SQL strings

### 3. Input Validation (API / Telegram / CLI)

Validate at system boundaries — never trust external input:

```python
def _validate_topic(topic: str) -> str:
    if not topic or not topic.strip():
        raise ValueError("topic cannot be empty")
    if len(topic) > 500:
        raise ValueError("topic too long (max 500 chars)")
    # Strip control characters
    return topic.strip()
```

**For Telegram bot commands:**
```python
# Sanitize before passing to subprocess or SQL
safe_cmd = re.sub(r"[^\w\s\-_./]", "", raw_cmd)[:200]
```

**Verify:**
- [ ] All API/bot inputs validated before use
- [ ] Length limits enforced
- [ ] No shell injection via user-controlled strings

### 4. Shell Command Safety

**NEVER construct shell commands from user input:**
```python
# BAD
subprocess.run(f"ffmpeg -i {user_path} output.mp4", shell=True)
```

**ALWAYS use list form + validate path:**
```python
# GOOD
from pathlib import Path
safe_path = Path(user_path).resolve()
assert safe_path.suffix in {".mp4", ".mov", ".avi"}
subprocess.run(["ffmpeg", "-i", str(safe_path), "output.mp4"], check=True)
```

**Verify:**
- [ ] `shell=True` not used with any user-supplied value
- [ ] File paths resolved and validated before use

### 5. Hook Safety (permission_analyzer.py)

- [ ] New hooks exit 0 on all code paths (never block Claude Code startup)
- [ ] DB connections use `timeout=10` and are always closed in `finally`
- [ ] No secrets logged to `database/audit_reports/jarvis_bot.log`
- [ ] `evaluate()` decisions logged to `agent_actions` table

### 6. Sensitive Data in Logs

```python
# BAD
logger.info(f"Using key: {api_key}")

# GOOD
logger.info(f"Using key: {api_key[:8]}***")
```

**Verify:**
- [ ] No full API keys or tokens in log statements
- [ ] Error messages don't leak internal paths beyond `/root/jarvis`

## Pre-Commit Security Checklist

- [ ] `grep -rn "sk-\|api_key\s*=\s*['\"]" . --include="*.py"` returns nothing suspicious
- [ ] All SQL uses parameterized queries
- [ ] No `shell=True` with user input
- [ ] Hook exits 0 on all paths
- [ ] No new secrets added to committed files

## Resources

- JARVIS prohibitions: `.claude/rules/jarvis-prohibitions.md`
- Python security rules: `.claude/rules/python/security.md`
- OWASP Top 10: https://owasp.org/www-project-top-ten/
