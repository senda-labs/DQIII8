---
name: vibesec
description: Security review skill for DQIII8 code-reviewer agent. Covers OWASP top vulnerabilities with detection checklists and bypass technique tables. Use when reviewing Python/FastAPI/SQLite code for SQL injection, XSS, CSRF, path traversal, secret exposure, SSRF, file upload, XXE, JWT, and API security issues.
source: BehiSecc/VibeSec-Skill
reviewed: 2026-03-18
approved_by: Iker + Claude
status: APROBADA
---

# VibeSec — DQIII8 Adaptation Notes

## Scope Adjustment for DQIII8 Stack
- **Primary stack**: Python + FastAPI + SQLite + Telegram Bot
- **Out of scope**: Java, .NET, PHP, GraphQL (not used in DQIII8)
- **High priority**: SQL injection (SQLite), path traversal (pathlib), secret exposure (.env), file upload (ElevenLabs/content pipeline)
- **Medium priority**: SSRF (webhook URLs from Telegram), JWT (jarvis_bot auth), XSS (FastAPI responses)
- **Low priority**: CSRF (API-only, no browser sessions), XXE (no XML parsing)

## DQIII8-specific SQL Injection Patterns to Flag as CRITICAL

```python
# VULNERABLE — always CRITICAL in DQIII8 reviews
conn.execute("SELECT * FROM sessions WHERE id = " + session_id)
cursor.execute(f"UPDATE tasks SET status = '{status}' WHERE id = {task_id}")
conn.execute("SELECT * FROM audit_reports WHERE model = '%s'" % model_name)

# SECURE — parameterized queries
conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
```

## DQIII8 Path Safety Pattern

```python
# SECURE — use pathlib.Path.resolve() and validate base
from pathlib import Path
BASE = Path("/root/dqiii8")

def safe_path(user_input: str) -> Path:
    target = (BASE / user_input).resolve()
    if not str(target).startswith(str(BASE)):
        raise ValueError("Path traversal detected")
    return target
```

---

# Secure Coding Guide for Web Applications

## Overview

This guide provides comprehensive secure coding practices for web applications. As an AI assistant, your role is to approach code from a **bug hunter's perspective** and make applications **as secure as possible** without breaking functionality.

**Key Principles:**
- Defense in depth: Never rely on a single security control
- Fail securely: When something fails, fail closed (deny access)
- Least privilege: Grant minimum permissions necessary
- Input validation: Never trust user input, validate everything server-side
- Output encoding: Encode data appropriately for the context it's rendered in

---

## Access Control Issues

Access control vulnerabilities occur when users can access resources or perform actions beyond their intended permissions.

### Core Requirements

For **every data point and action** that requires authentication:

1. **User-Level Authorization**
   - Each user must only access/modify their own data
   - No user should access data from other users or organizations
   - Always verify ownership at the data layer, not just the route level

2. **Use UUIDs Instead of Sequential IDs**
   - Use UUIDv4 or similar non-guessable identifiers
   - Exception: Only use sequential IDs if explicitly requested by user

3. **Account Lifecycle Handling**
   - When a user is removed from an organization: immediately revoke all access tokens and sessions
   - When an account is deleted/deactivated: invalidate all active sessions and API keys
   - Implement token revocation lists or short-lived tokens with refresh mechanisms

### Authorization Checks Checklist

- [ ] Verify user owns the resource on every request (don't trust client-side data)
- [ ] Check organization membership for multi-tenant apps
- [ ] Validate role permissions for role-based actions
- [ ] Re-validate permissions after any privilege change
- [ ] Check parent resource ownership (e.g., if accessing a comment, verify user owns the parent post)

### Common Pitfalls to Avoid

- **IDOR (Insecure Direct Object Reference)**: Always verify the requesting user has permission to access the requested resource ID
- **Privilege Escalation**: Validate role changes server-side; never trust role info from client
- **Horizontal Access**: User A accessing User B's resources with the same privilege level
- **Vertical Access**: Regular user accessing admin functionality
- **Mass Assignment**: Filter which fields users can update; don't blindly accept all request body fields

---

## Client-Side Bugs

### Cross-Site Scripting (XSS)

Every input controllable by the user must be sanitized against XSS.

#### Protection Strategies

1. **Output Encoding** (Context-Specific)
   - HTML context: HTML entity encode (`<` → `&lt;`)
   - Use framework's built-in escaping (FastAPI's JSONResponse auto-escapes)

2. **Content Security Policy (CSP)**
   ```
   Content-Security-Policy: default-src 'self'; script-src 'self'; frame-ancestors 'none';
   ```

3. **Additional Headers**
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`

---

### Cross-Site Request Forgery (CSRF)

> **DQIII8 note**: Low priority for pure API backends (no browser sessions). Apply if adding web UI.

#### Verification Checklist

- [ ] Token is cryptographically random
- [ ] Token is tied to user session
- [ ] Token validated on all state-changing requests
- [ ] SameSite cookie attribute set to Strict or Lax

---

### Secret Keys and Sensitive Data Exposure

No secrets or sensitive information should be accessible to client-side code or committed to git.

#### Never Expose

- API keys (ANTHROPIC_API_KEY, TELEGRAM_TOKEN, ELEVENLABS_API_KEY, etc.)
- Database connection strings
- JWT signing secrets / OAuth client secrets

#### Where Secrets Hide (Check These!)

- Hardcoded strings in `.py` files
- `os.environ.get("KEY", "fallback-secret-hardcoded")` — the default IS a secret exposure
- Log output that prints env vars or request headers
- `.env` files accidentally committed

#### DQIII8 Rule
Always use `os.environ["KEY"]` (raises `KeyError` if missing) instead of `.get("KEY", "default")` for secrets.

---

## Open Redirect

### Bypass Techniques to Block

| Technique | Example | Why It Works |
|-----------|---------|--------------|
| @ symbol | `https://legit.com@evil.com` | Browser navigates to evil.com |
| Double URL encoding | `%252f%252fevil.com` | Decodes to `//evil.com` |
| Protocol-relative | `//evil.com` | Uses current page's protocol |
| Protocol tricks | `javascript:alert(1)` | XSS via redirect |

---

## Server-Side Bugs

### Server-Side Request Forgery (SSRF)

> **DQIII8 note**: High priority for Telegram webhook handlers and any URL-fetching features.

Any endpoint where server makes requests to user-provided URLs must be validated.

#### Protection Strategies

1. **Allowlist Approach** — Only allow requests to pre-approved domains
2. **Block internal IPs** — Reject `127.x`, `10.x`, `192.168.x`, `169.254.169.254` (cloud metadata)

#### IP Bypass Techniques to Block

| Technique | Example |
|-----------|---------|
| Decimal IP | `http://2130706433` (= 127.0.0.1) |
| IPv6 localhost | `http://[::1]` |
| AWS metadata | `http://169.254.169.254/latest/meta-data/` |

#### Implementation Checklist

- [ ] Validate URL scheme is HTTP/HTTPS only
- [ ] Resolve DNS and validate IP is not private/internal
- [ ] Block cloud metadata IPs explicitly
- [ ] Set timeout on requests, limit response size

---

### Insecure File Upload

> **DQIII8 note**: High priority for content-automation pipeline (video/audio/image uploads).

#### Validation Requirements

- Check file extension against allowlist
- Validate magic bytes match expected type
- Set maximum file size server-side

#### Common Bypasses

| Attack | Description | Prevention |
|--------|-------------|------------|
| Extension bypass | `shell.php.jpg` | Check full extension, use allowlist |
| MIME type spoofing | Set Content-Type to image/jpeg | Validate magic bytes |
| SVG with JavaScript | `<svg onload="alert(1)">` | Sanitize SVG or disallow |
| ZIP slip | `../../../etc/passwd` in archive | Validate extracted paths |

#### Magic Bytes Reference

| Type | Magic Bytes (hex) |
|------|-------------------|
| JPEG | `FF D8 FF` |
| PNG | `89 50 4E 47 0D 0A 1A 0A` |
| PDF | `25 50 44 46` |
| ZIP | `50 4B 03 04` |

---

### SQL Injection

> **DQIII8 note**: CRITICAL priority — SQLite used throughout jarvis_metrics.db. Flag all f-string or %-format SQL as CRITICAL.

#### Prevention — PRIMARY DEFENSE: Parameterized Queries

```python
# VULNERABLE — CRITICAL
query = "SELECT * FROM users WHERE id = " + userId
conn.execute(f"SELECT * FROM audit_reports WHERE model = '{model}'")

# SECURE
conn.execute("SELECT * FROM users WHERE id = ?", (userId,))
conn.execute("SELECT * FROM audit_reports WHERE model = ?", (model,))
```

#### Injection Points to Watch

- WHERE clauses (most common)
- ORDER BY clauses — **cannot use parameters, must whitelist column names**
- Table and column names — **must whitelist**
- LIKE patterns — also escape wildcards (`%`, `_`)
- IN clauses with dynamic lists

#### Additional Defenses

- Least privilege: DB user should have minimum permissions
- Never expose SQL errors to users (log server-side only)

---

### XML External Entity (XXE)

> **DQIII8 note**: Low priority — DQIII8 uses JSON/SQLite. Apply only if parsing DOCX, XLSX, SVG uploads.

#### Prevention (Python)

```python
from lxml import etree
parser = etree.XMLParser(resolve_entities=False, no_network=True)
# Or: import defusedxml.ElementTree as ET
```

---

### Path Traversal

> **DQIII8 note**: Medium priority — DQIII8 accesses many files via pathlib. Flag `BASE_DIR + user_input` patterns.

#### Prevention

```python
import os
from pathlib import Path

def safe_join(base_directory: str, user_path: str) -> Path:
    base = Path(os.path.abspath(os.path.realpath(base_directory)))
    target = Path(os.path.abspath(os.path.realpath(os.path.join(base, user_path))))
    if os.path.commonpath([base, target]) != str(base):
        raise ValueError("Path traversal detected")
    return target
```

#### Path Traversal Checklist

- [ ] Never use user input directly in file paths
- [ ] Canonicalize paths and validate against base directory
- [ ] Restrict file extensions if applicable

---

## Security Headers Checklist

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Cache-Control: no-store  # for sensitive API responses
```

---

## JWT Security

### Vulnerabilities

| Vulnerability | Prevention |
|---------------|------------|
| `alg: none` attack | Always verify algorithm server-side, reject `none` |
| Algorithm confusion | Explicitly specify expected algorithm |
| Weak HMAC secrets | Use 256+ bit cryptographically random secrets |
| Missing expiration | Always set `exp` claim |
| Token in localStorage | Store in httpOnly, Secure, SameSite=Strict cookies |

### JWT Checklist

- [ ] Algorithm explicitly specified on verification
- [ ] `alg: none` rejected
- [ ] Secret is 256+ bits of random data
- [ ] `exp` claim always set and validated
- [ ] Tokens in httpOnly cookies, not localStorage

---

## API Security

### Mass Assignment

```python
# VULNERABLE — user can set { role: "admin" } in request body
User.update(**request.json())

# SECURE — whitelist allowed fields
ALLOWED = {"name", "email", "avatar"}
updates = {k: v for k, v in request.json().items() if k in ALLOWED}
User.update(**updates)
```

---

## General Security Principles

When reviewing code:

1. **Validate all input server-side** — Never trust client-side validation alone
2. **Use parameterized queries** — Never concatenate user input into SQL
3. **Encode output contextually** — HTML, JS, URL contexts need different encoding
4. **Apply authentication checks** — On every endpoint
5. **Apply authorization checks** — Verify the user can access the specific resource
6. **Use secure defaults**
7. **Handle errors securely** — Don't leak stack traces or internal details
8. **Keep dependencies updated** — Track vulnerable dependencies
