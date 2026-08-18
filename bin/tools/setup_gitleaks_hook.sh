#!/usr/bin/env bash
# Installs gitleaks as a pre-commit hook on the VPS.
# Run once from the repo root: bash bin/tools/setup_gitleaks_hook.sh
set -euo pipefail

GITLEAKS_VERSION="8.18.4"
GITLEAKS_SHA256="ba6dbb656933921c775ee5a2d1c13a91046e7952e9d919f9bac4cec61d628e7d"
INSTALL_DIR="/usr/local/bin"
HOOK_PATH=".git/hooks/pre-commit"

echo "[gitleaks-setup] Checking installation..."

if ! command -v gitleaks &>/dev/null; then
    echo "[gitleaks-setup] Downloading gitleaks v${GITLEAKS_VERSION}..."
    curl -sSLf \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        -o /tmp/gitleaks.tar.gz
    echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tar.gz" | sha256sum -c - || {
        echo "[gitleaks-setup] ERROR: checksum mismatch for downloaded gitleaks tarball — aborting" >&2
        rm -f /tmp/gitleaks.tar.gz
        exit 1
    }
    tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks
    mv /tmp/gitleaks "${INSTALL_DIR}/gitleaks"
    chmod +x "${INSTALL_DIR}/gitleaks"
    echo "[gitleaks-setup] Installed to ${INSTALL_DIR}/gitleaks"
else
    echo "[gitleaks-setup] Already installed: $(gitleaks version)"
fi

echo "[gitleaks-setup] Writing pre-commit hook..."
cat > "${HOOK_PATH}" <<'EOF'
#!/usr/bin/env bash
set -e
# gitignore-invariant: runs first — scans staged files for secret-shaped
# content (IPs, ssh commands, password literals) and unstages+ignores any hit
# before gitleaks ever sees it, since it's the durable fix (prevents recommit).
bash bin/tools/gitignore_invariant.sh

# gitleaks pre-commit: blocks commits that contain secrets
gitleaks protect --staged --redact --exit-code 1 --config .gitleaks.toml

# watermark-scan pre-commit: blocks commits with hidden/invisible Unicode
# characters in staged files (Trojan Source, zero-width, BOM). Report-only
# by default — never auto-fixes. Run `python3 bin/tools/watermark_scan.py --fix`
# manually to clean flagged files.
python3 bin/tools/watermark_scan.py

# hooks-config pre-commit: blocks commits that break .claude/settings.json's
# hooks block (invalid JSON or a dangling script path) — that file is a
# single point of failure for all hook-driven telemetry (agent_actions,
# error_log), so a break there must be caught before it lands, not discovered
# later via silence.
python3 bin/tools/validate_hooks_config.py

# rules-registry pre-commit: blocks commits that break the rules/routing
# governance surface — an orphaned/dangling `_REGISTRY` alias, a token-budget
# range that no longer agrees across the dispatcher docstring + DYNAMIC.md +
# 02_hooks_and_permissions.md (x2), a routing table citing an agent that does
# not exist, or a rule file presenting a model slug the wrapper never routes
# to. Every one of these drifted silently in the 2026-08-17 audit; the token
# range drifted twice in that single day. --staged so it gates the index, not
# the worktree. Warnings are printed and ignored; only problems exit 1.
python3 bin/tools/validate_rules_registry.py --staged
EOF
chmod +x "${HOOK_PATH}"

# This installer must produce a hook with exactly these 5 gates, in this
# order: gitignore_invariant.sh, gitleaks, watermark_scan.py,
# validate_hooks_config.py, validate_rules_registry.py --staged. The live
# hook and this heredoc drifted once already (2026-08-18: the rules-registry
# gate existed live but was never added here, so re-running this installer
# would have silently deleted it on next provisioning — cat-4 finding B,
# 2026-08-17 re-audit). tests/test_setup_gitleaks_hook.py asserts this
# invariant against a scratch hook path; keep both in sync by hand until
# then, and never remove a gate here without removing it from that test too.
echo "[gitleaks-setup] Done. Hook active at ${HOOK_PATH}"
echo "[gitleaks-setup] Test with: git commit -m 'test' (should be blocked if staged secrets)"
