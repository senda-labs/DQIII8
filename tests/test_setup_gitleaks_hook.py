"""Regression test for RC10/cat-4 finding B: setup_gitleaks_hook.sh's heredoc
must stay in sync with the live 5-gate .git/hooks/pre-commit. Re-running the
installer with a stale heredoc would silently delete whichever gate was
missing from it — this happened once already (2026-08-18, rules-registry gate)."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "bin" / "tools" / "setup_gitleaks_hook.sh"

EXPECTED_GATES = [
    "bash bin/tools/gitignore_invariant.sh",
    "gitleaks protect --staged --redact --exit-code 1 --config .gitleaks.toml",
    "python3 bin/tools/watermark_scan.py",
    "python3 bin/tools/validate_hooks_config.py",
    "python3 bin/tools/validate_rules_registry.py --staged",
]


def _heredoc_body():
    text = INSTALLER.read_text(encoding="utf-8")
    match = re.search(r"<<'EOF'\n(.*?)\nEOF", text, re.DOTALL)
    assert match, "installer heredoc not found (cat > ... <<'EOF' ... EOF block missing)"
    return match.group(1)


def test_installer_heredoc_contains_all_five_gates_in_order():
    body = _heredoc_body()
    positions = [body.index(gate) for gate in EXPECTED_GATES]
    assert positions == sorted(positions), (
        "gates present but out of order — live pre-commit hook runs them in a "
        "specific sequence (gitignore_invariant first, gitleaks second, etc.)"
    )


def test_installer_heredoc_matches_live_hook_gate_count():
    live_hook = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    if not live_hook.exists():
        return
    live_text = live_hook.read_text(encoding="utf-8")
    for gate in EXPECTED_GATES:
        assert gate in live_text, f"live hook missing expected gate: {gate}"
