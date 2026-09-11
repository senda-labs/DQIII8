"""Regression test for Rango 1 (2026-08-19 red-team audit): the pre-push
installer's heredoc must stay in sync with the live .git/hooks/pre-push —
mirrors tests/test_setup_gitleaks_hook.py's guard against the same drift
that already bit the pre-commit hook once (2026-08-18, rules-registry gate)."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "bin" / "tools" / "setup_prepush_hook.sh"

EXPECTED_GATE = (
    'gitleaks detect --source . --log-opts="${log_opts}" --redact '
    "--exit-code 1 --config .gitleaks.toml"
)


def _heredoc_body():
    text = INSTALLER.read_text(encoding="utf-8")
    match = re.search(r"<<'EOF'\n(.*?)\nEOF", text, re.DOTALL)
    assert match, "installer heredoc not found (cat > ... <<'EOF' ... EOF block missing)"
    return match.group(1)


def test_installer_heredoc_contains_gitleaks_gate():
    body = _heredoc_body()
    assert EXPECTED_GATE in body


def test_installer_heredoc_skips_deleted_refs():
    body = _heredoc_body()
    assert '[ "$local_sha" = "$zero" ] && continue' in body


def test_installer_heredoc_matches_live_hook():
    live_hook = REPO_ROOT / ".git" / "hooks" / "pre-push"
    if not live_hook.exists():
        return
    live_text = live_hook.read_text(encoding="utf-8")
    assert EXPECTED_GATE in live_text, "live pre-push hook missing expected gitleaks gate"
