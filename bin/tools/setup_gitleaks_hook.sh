#!/usr/bin/env bash
# Installs gitleaks as a pre-commit hook on the VPS.
# Run once from the repo root: bash bin/tools/setup_gitleaks_hook.sh
set -euo pipefail

GITLEAKS_VERSION="8.18.4"
INSTALL_DIR="/usr/local/bin"
HOOK_PATH=".git/hooks/pre-commit"

echo "[gitleaks-setup] Checking installation..."

if ! command -v gitleaks &>/dev/null; then
    echo "[gitleaks-setup] Downloading gitleaks v${GITLEAKS_VERSION}..."
    curl -sSLf \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
        -o /tmp/gitleaks.tar.gz
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
# gitleaks pre-commit: blocks commits that contain secrets
gitleaks protect --staged --redact --exit-code 1

# watermark-scan pre-commit: blocks commits with hidden/invisible Unicode
# characters in staged files (Trojan Source, zero-width, BOM). Report-only
# by default — never auto-fixes. Run `python3 bin/tools/watermark_scan.py --fix`
# manually to clean flagged files.
python3 bin/tools/watermark_scan.py
EOF
chmod +x "${HOOK_PATH}"

echo "[gitleaks-setup] Done. Hook active at ${HOOK_PATH}"
echo "[gitleaks-setup] Test with: git commit -m 'test' (should be blocked if staged secrets)"
