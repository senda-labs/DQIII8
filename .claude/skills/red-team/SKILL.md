---
name: red-team
description: Adversarial security testing — attempts to break the codebase using real hacker techniques. Tests OWASP Top 10, prompt injection, MCP poisoning, dependency attacks, auth bypass, and vibe-coding-specific patterns. Generates exploit report. NEVER auto-invoked — user must explicitly request.
command: /red-team
allowed-tools: [Bash, Read, Grep, Glob]
user-invocable: true
disable-model-invocation: true
context: fork
agent: Explore
---

# /red-team — Adversarial Security Testing

Attack the codebase like a real hacker. Find vulnerabilities that static
scanners miss. Think like an attacker, not a checker.

## Usage

```
/red-team                          # Full attack on current project
/red-team $ARGUMENTS               # Attack specific path or component
```

## Philosophy

- You are NOT a scanner. You are an attacker.
- Think: "How would I break this?" not "Does this follow best practices?"
- Chain vulnerabilities: a LOW finding + another LOW = potential CRITICAL
- Test the DEPLOYMENT, not just the code (env vars, permissions, exposed ports)
- Vibe-coded patterns are predictable — exploit that predictability

## Attack Phases

### Phase 1: Reconnaissance

Map the attack surface:

```bash
# Find all entry points (web routes, API endpoints, CLI args)
grep -rn "@app\.\|@router\.\|argparse\|sys.argv" --include="*.py" .
# Find all external connections (DB, API, network)
grep -rn "connect\|requests\.\|urllib\|subprocess\|exec\|eval" --include="*.py" .
# Find authentication mechanisms
grep -rn "auth\|token\|session\|cookie\|password\|jwt\|oauth" --include="*.py" .
# Find file operations (path traversal candidates)
grep -rn "open(\|Path(\|os.path\|shutil" --include="*.py" .
# Map MCP servers and their permissions
cat ~/.claude.json 2>/dev/null | python3 -c "import json,sys; [print(f'MCP: {k} → {v.get(\"command\",\"?\")}') for k,v in json.load(sys.stdin).get('mcpServers',{}).items()]"
```

### Phase 2: Vibe Coding Pattern Attacks

AI-generated code has specific weaknesses:

1. **Predictable error handling**: try/except pass (errors silenced)
   ```bash
   grep -rn "except.*:\s*$\|except.*:$" --include="*.py" . -A1 | grep "pass"
   ```
2. **Hardcoded defaults**: AI uses common defaults that hackers know
   ```bash
   grep -rn "0\.0\.0\.0\|localhost\|127\.0\.0\.1\|8080\|8000\|5000\|\"admin\"\|\"root\"\|\"password\"" --include="*.py" .
   ```
3. **Missing input validation**: AI trusts user input
   ```bash
   grep -rn "request\.\|input(\|sys.argv\|args\." --include="*.py" . | grep -v "valid\|sanitize\|check\|assert"
   ```
4. **SQL via string formatting**: AI often uses f-strings for SQL
   ```bash
   grep -rn "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE\|\.format.*SELECT" --include="*.py" .
   ```
5. **Exposed debug info**: AI leaves debug prints and verbose errors
   ```bash
   grep -rn "print(.*error\|print(.*exception\|traceback\|debug=True\|DEBUG" --include="*.py" .
   ```

### Phase 3: Authentication & Authorization Attacks

1. **Auth bypass**: Find routes without authentication
2. **Token weaknesses**: Check if tokens are predictable, have no expiry
3. **Session fixation**: Can you reuse someone else's session?
4. **Privilege escalation**: Can a regular user access admin functions?

### Phase 4: Injection Attacks

1. **SQL injection**: Test every database query with user input
2. **Command injection**: Test subprocess calls with user-controlled args
3. **Path traversal**: Test file operations with `../../../etc/passwd`
4. **XSS**: Test HTML output with `<script>` payloads
5. **Prompt injection** (if LLM-powered): Test system prompt extraction

### Phase 5: Infrastructure Attacks

1. **Exposed services**: Check listening ports and accessible endpoints
   ```bash
   ss -tlnp 2>/dev/null | grep LISTEN
   ```
2. **File permissions**: Check .env, database, keys
   ```bash
   find . -name "*.env" -o -name "*.pem" -o -name "*.key" -o -name "*.db" | xargs ls -la 2>/dev/null
   ```
3. **Dependency attacks**: Check for known vulnerable packages
   ```bash
   pip list --outdated 2>/dev/null | head -20
   ```
4. **MCP server poisoning**: Check if any MCP can be exploited
5. **Git history leaks**: Check for secrets in past commits
   ```bash
   git log --diff-filter=D --name-only --pretty=format: | grep -i "env\|key\|secret\|token" | head -10
   ```

### Phase 6: Chained Attack Scenarios

Think multi-step attacks:
- "I found an unauthenticated endpoint → it reads a file → the file path is user-controlled → path traversal → read .env → get API keys → access paid services"
- "I found a SQL injection → dump the database → get admin password hash → crack it → admin access"
- "I found a MCP server with write access → inject malicious content → next session executes it"

## Output Format

Generate: `tasks/audit/red-team-{date}.md`

```markdown
# Red Team Report — {date}
Target: {project path}
Duration: {time spent}
Attacker skill level simulated: {intermediate/advanced/expert}

## Executive Summary
{1-2 sentences: overall security posture}

## Kill Chains Found
### Kill Chain 1: {name}
Step 1: {action} → {result}
Step 2: {action} → {result}
Step 3: {action} → {COMPROMISED: what was accessed}
Severity: CRITICAL/HIGH/MEDIUM
Proof: {exact command or payload that demonstrates the vulnerability}

## Individual Findings
### [RT-001] {title}
- Category: {OWASP category}
- Severity: CRITICAL/HIGH/MEDIUM/LOW
- File: {path}:{line}
- Proof: {command/payload}
- Impact: {what an attacker gains}
- Vibe-coding pattern: {yes/no — is this a known AI-generated pattern?}

## Vibe Coding Score
{Percentage of findings that are attributable to AI-generated code patterns}

## Statistics
Total findings: {N}
Critical: {N} | High: {N} | Medium: {N} | Low: {N}
Kill chains: {N}
Vibe-coding patterns: {N}/{total} ({percentage}%)
```

## Rules

- NEVER actually exploit in production — proof-of-concept only
- NEVER delete data or modify running services
- NEVER exfiltrate real credentials — only prove they are accessible
- Document EVERY finding with a reproducible proof
- If you find a kill chain, document the FULL chain, not just individual links
