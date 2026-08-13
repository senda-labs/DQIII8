#!/usr/bin/env bash
# gitignore invariant: runs before gitleaks in pre-commit. Scans staged files for
# secret-shaped content (IPs, ssh commands, password literals) using the same
# patterns as .gitleaks.toml's generic-credential-literal / generic-vps-ip-literal
# rules. Any staged file that matches gets appended to .gitignore and unstaged —
# .gitignore is the durable fix (prevents recommit), gitleaks below is the final gate.
# Never auto-redacts file content: only removes the file from the commit.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

staged_files=$(git diff --cached --diff-filter=d --name-only -z | tr '\0' '\n')
[ -z "$staged_files" ] && exit 0

flagged=0
# Files that legitimately contain secret-shaped regex patterns (detector definitions,
# not actual secrets) — excluded from scanning to avoid self-triggering false positives.
EXCLUDE_PATHS=(".gitignore" ".gitleaks.toml" ".gitleaksignore" "bin/tools/gitignore_invariant.sh")

while IFS= read -r f; do
    [ -z "$f" ] && continue
    skip=0
    for ex in "${EXCLUDE_PATHS[@]}"; do
        [ "$f" = "$ex" ] && skip=1 && break
    done
    [ "$skip" -eq 1 ] && continue
    content=$(git cat-file -p ":$f" 2>/dev/null || true)
    [ -z "$content" ] && continue

    hit=""
    if echo "$content" | grep -qiP '(?:password|contraseñ\w*|passwd).{0,40}[`'"'"'"][A-Za-z0-9]{6,}[!@#$%^&*][A-Za-z0-9!@#$%^&*]*[`'"'"'"]'; then
        hit="password-literal"
    elif echo "$content" | grep -qiP '(?:ssh\s+root@|ssh\s+\S+@)\s*(?:\d{1,3}\.){3}\d{1,3}'; then
        hit="ssh-ip-command"
    fi

    if [ -n "$hit" ]; then
        if ! grep -qxF "$f" .gitignore 2>/dev/null; then
            echo "$f" >> .gitignore
            echo "gitignore-invariant: added '$f' to .gitignore (reason: $hit)" >&2
        fi
        git reset -q -- "$f"
        echo "gitignore-invariant: unstaged '$f' — redact the secret or confirm it's a false positive, then re-add if safe" >&2
        flagged=1
    fi
done <<< "$staged_files"

if [ "$flagged" -eq 1 ]; then
    git add .gitignore
    echo "gitignore-invariant: .gitignore updated and staged. Commit blocked — review flagged file(s) above." >&2
    exit 1
fi
exit 0
