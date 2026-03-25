---
name: blue-team
description: Defensive security — reads red-team findings and systematically patches every vulnerability. Hardens code, adds input validation, fixes permissions, and verifies each fix. Works from the latest red-team report.
command: /blue-team
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob]
user-invocable: true
disable-model-invocation: true
---

# /blue-team — Defensive Security Hardening

Read the latest red-team report and systematically fix every finding.

## Usage

```
/blue-team                          # Fix all findings from latest report
/blue-team $ARGUMENTS               # Fix specific finding (e.g. RT-001)
```

## Pipeline

### Step 1: Load latest red-team report

```bash
ls -t tasks/audit/red-team-*.md | head -1
```

Read and parse all findings.

### Step 2: Prioritize fixes

Order: CRITICAL → HIGH → MEDIUM → LOW

Within same severity: kill chain findings first (they have multiplied impact).

### Step 3: For each finding, apply fix pattern

| Finding type | Fix pattern |
|-------------|-------------|
| SQL injection | Replace f-strings with parameterized queries (`?`) |
| Command injection | Use `shlex.quote()` on user input, whitelist commands |
| Path traversal | Use `pathlib.resolve()` + check prefix matches allowed dir |
| XSS | Escape HTML output with `html.escape()` or template engine |
| Auth bypass | Add auth decorator/middleware to unprotected routes |
| Hardcoded secrets | Move to `.env`, use `os.environ.get()` |
| Debug exposure | Remove `print(error)`, use `logging` with appropriate level |
| File permissions | `chmod 600` on `.env`, `.db`, `.pem`, `.key` files |
| Missing validation | Add type checks, range checks, sanitization |
| Dependency vuln | `pip install --upgrade {package}` |
| Vibe-coding pattern | Rewrite the specific pattern with secure alternative |

### Step 4: Verify each fix

After applying a fix:

1. Run the original proof-of-concept from the red-team report
2. It should now FAIL (vulnerability patched)
3. Run tests to ensure the fix didn't break functionality
4. Document: "Finding RT-XXX: PATCHED, verified, tests pass"

```bash
python3 -m pytest tests/ -q
```

### Step 5: Generate blue-team report

Generate: `tasks/audit/blue-team-{date}.md`

```markdown
# Blue Team Report — {date}
Source: {red-team report filename}

## Fixes Applied
| ID | Finding | Severity | Fix | Verified | Tests |
|----|---------|----------|-----|----------|-------|
| RT-001 | SQL injection in db.py | CRITICAL | Parameterized queries | ✅ | ✅ |
| RT-002 | .env readable | HIGH | chmod 600 | ✅ | N/A |

## Kill Chains Broken
### Kill Chain 1: {name}
- Step broken at: {step N}
- Fix applied: {description}
- Chain now terminates at: {safe state}

## Remaining Risks
{Any findings that could not be fully fixed, with justification}

## Security Score
Before: {red-team score}/100
After: {blue-team score}/100
Improvement: +{delta} points
```

## Rules

- ALWAYS run tests after each fix: `python3 -m pytest tests/ -q`
- NEVER introduce new vulnerabilities while fixing old ones
- If a fix requires breaking API compatibility, flag it for user review
- Document the reasoning for each fix, not just the change
