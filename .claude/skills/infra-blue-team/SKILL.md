---
name: infra-blue-team
description: Defensive infrastructure audit + reversible remediation on the 2 owned Netcup VPS — diffs live state against infra_baseline.yaml, files findings in infra_findings, applies only safe non-disruptive fixes (ufw deny, cscli ban) over SSH. Never edits local files — every fix is a remote command, audited as such. NEVER auto-invoked.
command: /infra-blue-team
allowed-tools: [Bash, Read, Grep, Glob]
user-invocable: true
disable-model-invocation: true
context: fork
agent: Explore
experimental: true
---

# /infra-blue-team — Defensive Infrastructure Remediation

Reads the latest `/infra-red-team` findings (or runs its own checks directly)
and remediates infrastructure drift. Sibling of `.claude/skills/blue-team/SKILL.md`
(which patches the codebase) — same fix-verify-report discipline, but every
"fix" here is a **remote SSH command**, never a local file edit. This skill
has no `Write`/`Edit` in `allowed-tools` on purpose: infra fixes are actions
against a live remote system, and must be auditable as executed commands
(with real before/after output), not silent diffs to a repo file.

## Usage

```
/infra-blue-team                    # Audit + remediate every target in the allowlist
/infra-blue-team netcup-rs4000      # One target
```

## Target Gate (mandatory, identical to /infra-red-team)

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('infrastructure/redteam_target_allowlist.yaml'))
for t in d['targets']:
    print(t['id'], t['address'], t['scope'])
"
```

Same unconditional rejection message for anything outside the allowlist:

> TARGET FUERA DE ALLOWLIST — añádelo primero en
> `infrastructure/redteam_target_allowlist.yaml` (paso humano aparte), no
> continúo.

No argument → every target in the allowlist.

**Disclosed limitation** (panel-review 2026-09-07, P1 — same finding applies
here): this gate is a markdown instruction read by the model, not a
code-enforced allowlist. See `.claude/skills/infra-red-team/SKILL.md`'s
matching note — the same caution applies to any address surfaced mid-task.

## Pipeline

For each target:

1. **Run the same checks `infrastructure/blueteam_audit.sh` already runs**
   (don't duplicate a different check set — reuse the proven one; this file
   is now versioned in-repo — panel-review 2026-09-07 found the version
   deployed to both VPS via scp had never been committed, so this skill was
   citing a file that existed nowhere in the repo it lives in):
   ```bash
   ssh <target-alias> "cscli decisions list; ufw status verbose; \
     sha256sum /etc/ssh/sshd_config; \
     journalctl -u ssh.service --since '24 hours ago' | grep -iE 'failed|invalid' | tail -30; \
     ss -tlnp; tail -5 /var/log/aide/aide.log 2>/dev/null; \
     grep -i warning /var/log/rkhunter.log 2>/dev/null | tail -10"
   ```

2. **Diff against `infrastructure/infra_baseline.yaml`** for this target:
   - Any listening port not in `expected_open_ports` → candidate finding.
   - `sha256sum` of `sshd_config` not matching `sshd_config_sha256` (if set;
     `null` means "not yet baselined" — record the real hash as an
     `ALREADY_FIXED`-adjacent informational finding, don't treat a `null`
     baseline as drift on first run).
   - Any service in `expected_active_services` not `active` per
     `systemctl is-active <service>` → candidate finding.

3. **Classify each deviation**: `REAL` / `MITIGATED` / `FALSE_POSITIVE` /
   `ALREADY_FIXED` — same vocabulary and duplicate-check as `/infra-red-team`
   (query `infra_findings` for `source IN ('infra-blue-team','infra-red-team')`
   before filing, no `2>/dev/null ||` fallback masking a schema error).

4. **Remediate — only the reversible, non-disruptive class, and NEVER against
   `netcup-viejo` (the production target)**:
   - `target_id == 'netcup-viejo'` → **auto-fix disabled entirely for
     `ufw deny`**, regardless of what the port diff says. This is not a
     judgment call left to the model each run — a baseline gap (a port this
     file hasn't been reconciled to yet, e.g. Caddy's 80/443/8090) is
     structurally indistinguishable from a real unexpected port on first
     read, and `dq-dashboard.service`/`dqiii8-bot.service` are real
     production services with real users. Every deviation on this target is
     `report and STOP`, no exception, even one that looks obviously safe.
   - On any other target (`scope: full`, non-production): unexpected open
     port with no legitimate service behind it →
     `ssh <target> "ufw deny <port>/tcp"` (deny, never delete other rules).
   - Already-detected brute-force IP not yet banned, on any target →
     `ssh <target> "cscli decisions add --ip <ip> --duration 4h --reason 'infra-blue-team remediation'"`
     (bounded duration, not permanent — reversible by design).
   - Everything else (sshd_config drift, a missing baseline service, a
     Docker-published port, any Syncthing config change) → **report and STOP,
     never auto-fix**, on every target.

5. **Verify every fix actually took effect** — re-run the specific check, not
   just trust the command exit code:
   ```bash
   ssh <target-alias> "ufw status verbose | grep <port>"
   ssh <target-alias> "cscli decisions list | grep <ip>"
   ```
   Only mark `resolved=1` in `infra_findings` after this re-check confirms it.

6. **Insert/update `infra_findings`** (`source='infra-blue-team'`) — new
   deviations as `REAL`, fixed ones as `resolved=1` with `resolution`
   containing the exact SSH command run and its output.

## Pre-Report Verification Protocol

Same as `/infra-red-team`:
1. Every check and every fix is a real SSH command — no simulation.
2. Duplicate check against `infra_findings` before filing (loud on error).
3. Classify before reporting; only REAL/MITIGATED in the main findings
   section, rest under CHECKED & SECURE.

## Output Format

Generate `tasks/audit/infra-blue-team-{date}.md`:

```markdown
# Infra Blue Team Report — {date}
Targets: {ids audited}

## Executive Summary
{1-2 sentences}

## Fixes Applied
### [IBT-001] {title}
- Target: {target_id}
- Before: {real command output}
- Fix: {exact SSH command executed}
- After: {real command output confirming the fix}
- infra_findings row: id={N}, resolved=1

## Findings Reported, NOT Auto-Fixed (require human decision)
### [IBT-002] {title}
- Target: {target_id} | Severity: {..}
- Why not auto-fixed: {disruption risk}
- Recommended manual action: {..}

## CHECKED & SECURE
| Check | Classification | Reason |
|-------|---------------|--------|

## Statistics
Total checked: {N} | Fixed: {N} | Reported-only: {N} | FALSE_POSITIVE: {N}
```

## Rules

- NEVER edit a local file as a "fix" — every remediation is a remote command
  over SSH, logged verbatim in the report.
- NEVER apply a fix that can plausibly disrupt `dqiii8-bot.service` or
  `dq-dashboard.service` on `netcup` (the production target) — report those
  instead, always.
- NEVER permanently ban an IP — bounded duration only, reversible.
- NEVER touch `sshd_config` directly — drift there is report-only, a human
  applies the change and re-baselines `infra_baseline.yaml`'s
  `sshd_config_sha256` afterward.
- NEVER run outside the allowlist gate.
