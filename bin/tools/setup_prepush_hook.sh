#!/usr/bin/env bash
# Installs a pre-push secret-scan hook on the VPS (Rango 1, 2026-08-19
# red-team audit). Depends on gitleaks already being installed+pinned by
# bin/tools/setup_gitleaks_hook.sh — run that first if gitleaks isn't on
# PATH; this script does not re-download/verify the binary itself.
# Run once from the repo root: bash bin/tools/setup_prepush_hook.sh
set -euo pipefail

HOOK_PATH=".git/hooks/pre-push"

if ! command -v gitleaks &>/dev/null; then
    echo "[prepush-setup] ERROR: gitleaks not found on PATH." >&2
    echo "[prepush-setup] Run bash bin/tools/setup_gitleaks_hook.sh first (installs the pinned binary)." >&2
    exit 1
fi

echo "[prepush-setup] Writing pre-push hook..."
cat > "${HOOK_PATH}" <<'EOF'
#!/usr/bin/env bash
set -e
# DQIII8 pre-push safety net (Rango 1, 2026-08-19 red-team audit): pre-commit's
# gitleaks gate only covers commits made through a session where that hook was
# installed and not bypassed (--no-verify). This is a second, independent scan
# over every commit actually about to leave the machine, at push time —
# secrets (gitleaks) AND BLOCKED_PATHS filenames (check_blocked_paths_diff.py,
# added after the 2026-08-19 decision to also catch a secret-less placeholder
# credential file gitleaks' pattern match would miss).
#
# Known gap (documented, not silently assumed covered): this hook cannot see
# pushes made via the GitHub API (e.g. mcp__github__push_files) — those never
# invoke local git hooks at all — nor a push run with --no-verify. Neither is
# closable from a local git hook; closed instead via GitHub's own server-side
# secret scanning + push protection, enabled on the repo directly (2026-08-19
# decision) — see docs/audits/2026-08-19-context-injection-redteam.md.
REPO_ROOT="$(git rev-parse --show-toplevel)"
zero="0000000000000000000000000000000000000000"
while read -r local_ref local_sha remote_ref remote_sha; do
    [ "$local_sha" = "$zero" ] && continue  # deleting a remote ref — nothing to scan
    if [ "$remote_sha" = "$zero" ]; then
        log_opts="$local_sha"  # new remote branch — scan every commit being pushed
        base_ref=""
    else
        log_opts="${remote_sha}..${local_sha}"
        base_ref="$remote_sha"
    fi
    echo "[pre-push] scanning ${log_opts} for secrets before push to ${remote_ref}..."
    gitleaks detect --source . --log-opts="${log_opts}" --redact --exit-code 1 --config .gitleaks.toml
    echo "[pre-push] scanning ${log_opts} for BLOCKED_PATHS before push to ${remote_ref}..."
    python3 "${REPO_ROOT}/bin/tools/check_blocked_paths_diff.py" "${log_opts}" ${base_ref:+"$base_ref"}
done
EOF
chmod +x "${HOOK_PATH}"

echo "[prepush-setup] Done. Hook active at ${HOOK_PATH}"
echo "[prepush-setup] Test with: git push (should be blocked if the range about to be pushed contains secrets)"
