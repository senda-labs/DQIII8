"""Tests for bin/tools/panel_review.py — finding parser, citation gate, degradation flag."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

import panel_review as pr  # noqa: E402

REAL_FILE = "CLAUDE.md"  # exists at repo root, safe to cite in tests


def test_verified_finding_survives_with_real_citation():
    block = (
        f"[CATEGORY: Security] [SEVERITY: P0]\n"
        f"{REAL_FILE}:1\n"
        f"SQL injection via f-string.\n"
        f"Exploit/failure scenario: attacker sends amount=\"0; DROP TABLE users\""
    )
    verified, dropped = pr._parse_findings(block)
    assert len(verified) == 1
    assert verified[0]["category"] == "Security"
    assert verified[0]["severity"] == "P0"
    assert dropped == []


def test_fabricated_path_is_dropped_not_verified():
    block = (
        "[CATEGORY: Correctness] [SEVERITY: P2]\n"
        "src/nonexistent_file.py:15\n"
        "Some plausible-sounding defect.\n"
        "Exploit/failure scenario: hypothetical"
    )
    verified, dropped = pr._parse_findings(block)
    assert verified == []
    assert len(dropped) == 1
    assert dropped[0]["reason"] == "fake_path"


def test_finding_shaped_block_with_no_citation_at_all_is_dropped_with_reason():
    block = (
        "[CATEGORY: Operational] [SEVERITY: P1]\n"
        "No file reference here at all.\n"
        "Exploit/failure scenario: something bad"
    )
    verified, dropped = pr._parse_findings(block)
    assert verified == []
    assert len(dropped) == 1
    assert dropped[0]["reason"] == "no_citation"


def test_considered_no_issues_line_is_not_treated_as_dropped_finding():
    block = "Correctness: considered, no issues found."
    verified, dropped = pr._parse_findings(block)
    assert verified == []
    assert dropped == []


def test_multiline_block_separated_by_blank_lines_parses_as_one_finding():
    text = (
        "Some intro prose from the model.\n"
        "\n"
        f"[CATEGORY: Resilience] [SEVERITY: P1]\n"
        f"{REAL_FILE}:2\n"
        "No rollback path on partial failure.\n"
        "Exploit/failure scenario: crash mid-write leaves inconsistent state\n"
        "\n"
        "Correctness: considered, no issues found.\n"
    )
    verified, dropped = pr._parse_findings(text)
    assert len(verified) == 1
    assert verified[0]["citation"] == f"{REAL_FILE}:2"
    assert dropped == []


def test_citation_exists_checks_real_repo_path():
    assert pr._citation_exists(f"{REAL_FILE}:10") is True
    assert pr._citation_exists("totally/made/up/path.py:1") is False


def test_mark_degradation_flags_provider_mismatch():
    seat = {"provider_intended": "nim", "model_intended": "deepseek-ai/deepseek-v4-flash",
             "provider": "groq", "model": "llama-3.3-70b-versatile"}
    pr._mark_degradation(seat)
    assert seat["degraded"] is True


def test_mark_degradation_clean_when_intended_matches_actual():
    seat = {"provider_intended": "nim", "model_intended": "deepseek-ai/deepseek-v4-flash",
            "provider": "nim", "model": "deepseek-ai/deepseek-v4-flash"}
    pr._mark_degradation(seat)
    assert seat["degraded"] is False


def test_mark_degradation_no_flag_when_intended_missing():
    seat = {"provider": "groq", "model": "llama-3.3-70b-versatile"}
    pr._mark_degradation(seat)
    assert seat["degraded"] is False
