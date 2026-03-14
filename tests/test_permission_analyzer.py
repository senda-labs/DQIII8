"""Tests para PermissionAnalyzer v2 — ALLOWED_DELETIONS + ESCALATE."""

import os
import sys
from pathlib import Path

# Asegurar que el módulo es importable desde tests/
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks"))

from permission_analyzer import PermissionAnalyzer

analyzer = PermissionAnalyzer()


# ── MEJORA B — ALLOWED_DELETIONS ────────────────────────────────────────────


def test_allowed_deletion_node_modules():
    """rm -rf node_modules debe aprobarse."""
    r = analyzer.evaluate("Bash", {"command": "rm -rf node_modules"})
    assert r["decision"] == "APPROVE"


def test_allowed_deletion_pycache():
    """rm -rf __pycache__ debe aprobarse."""
    r = analyzer.evaluate(
        "Bash",
        {"command": "find . -type d -name __pycache__ -exec rm -rf {} +"},
    )
    assert r["decision"] == "APPROVE"


def test_allowed_deletion_dist():
    """rm -rf dist debe aprobarse."""
    r = analyzer.evaluate("Bash", {"command": "rm -rf dist"})
    assert r["decision"] == "APPROVE"


def test_allowed_deletion_pytest_cache():
    """rm -rf .pytest_cache debe aprobarse."""
    r = analyzer.evaluate("Bash", {"command": "rm -rf .pytest_cache"})
    assert r["decision"] == "APPROVE"


# ── MEJORA B — Comandos críticos siguen bloqueados ──────────────────────────


def test_deny_rm_rf_root():
    """rm -rf / sigue siendo CRITICAL."""
    r = analyzer.evaluate("Bash", {"command": "rm -rf /"})
    assert r["decision"] == "DENY"
    assert r["risk_level"] == "CRITICAL"


def test_deny_rm_rf_home():
    """rm -rf /root debe denegarse."""
    r = analyzer.evaluate("Bash", {"command": "rm -rf /root"})
    assert r["decision"] == "DENY"


def test_deny_rm_rf_tilde():
    """rm -rf ~ debe denegarse."""
    r = analyzer.evaluate("Bash", {"command": "rm -rf ~"})
    assert r["decision"] == "DENY"


def test_deny_drop_table():
    """DROP TABLE debe denegarse."""
    r = analyzer.evaluate("Bash", {"command": "sqlite3 db.sqlite 'DROP TABLE sessions'"})
    assert r["decision"] == "DENY"


# ── MEJORA A — Paths bloqueados en escritura ────────────────────────────────


def test_deny_write_to_env():
    """Escribir a .env debe denegarse."""
    r = analyzer.evaluate("Write", {"file_path": "/root/jarvis/.env"})
    assert r["decision"] == "DENY"
    assert r["risk_level"] == "CRITICAL"


def test_deny_edit_claude_md():
    """Editar CLAUDE.md debe denegarse."""
    r = analyzer.evaluate("Edit", {"file_path": "/root/jarvis/CLAUDE.md"})
    assert r["decision"] == "DENY"


def test_deny_write_to_db():
    """Escribir a jarvis_metrics.db debe denegarse."""
    r = analyzer.evaluate("Write", {"file_path": "database/jarvis_metrics.db"})
    assert r["decision"] == "DENY"


# ── Paths normales aprobados ─────────────────────────────────────────────────


def test_approve_normal_python_file():
    """Editar un .py normal debe aprobarse."""
    r = analyzer.evaluate("Edit", {"file_path": "bin/analytics_collector.py"})
    assert r["decision"] == "APPROVE"


def test_approve_normal_bash():
    """Comandos bash seguros deben aprobarse."""
    r = analyzer.evaluate("Bash", {"command": "python3 -m pytest tests/ -v"})
    assert r["decision"] == "APPROVE"


def test_approve_git_status():
    """git status debe aprobarse."""
    r = analyzer.evaluate("Bash", {"command": "git status"})
    assert r["decision"] == "APPROVE"


# ── MEJORA C — estructura del resultado ESCALATE ────────────────────────────


def test_escalate_result_has_required_keys():
    """Si _check_repeat_rejections retorna algo, debe tener las keys correctas."""
    # Verificar la estructura sin simular la BD
    expected_keys = {"decision", "reason", "risk_level", "rule_triggered", "suggested_fix"}
    deny_result = analyzer._deny("Bash", "rm -rf /", "test", "CRITICAL", "rule", "fix")
    assert set(deny_result.keys()) == expected_keys
    assert deny_result["decision"] == "DENY"
