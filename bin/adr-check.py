#!/usr/bin/env python3
"""
adr-check.py — Active ADR Invariant Checker

Parses ## Invariants YAML blocks from all Accepted ADRs in decisions/
and verifies them against the codebase. Outputs decisions/adr-compliance.json.

Usage:
    python3 bin/adr-check.py [--strict] [--root /path/to/project] [--adr-root /path/to/decisions]

Options:
    --strict    Exit 1 if any invariant fails (default: always exits 0)
    --root      Project root to resolve relative file paths (default: CWD)
    --adr-root  Directory containing ADR markdown files (default: <root>/decisions)

Called by:
    - /audit command
    - auditor agent
    - CI pre-commit hook (with --strict)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Invariant:
    id: str
    description: str
    paths: list[str]
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class ADR:
    path: Path
    number: str
    title: str
    status: str
    project: str
    invariants: list[Invariant]


@dataclass
class InvariantResult:
    invariant_id: str
    adr_number: str
    passed: bool
    violations: list[str]
    checked_files: list[str]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_status(text: str) -> str:
    """Extract Status: value from ADR markdown header."""
    m = re.search(r"\*\*Status:\*\*\s*([^\n|]+)", text)
    if m:
        return m.group(1).strip().split()[0]  # first word: Accepted, Proposed…
    return "Unknown"


def _parse_project(text: str) -> str:
    m = re.search(r"\*\*Project:\*\*\s*([^\n]+)", text)
    return m.group(1).strip() if m else ""


def _parse_adr_number(path: Path) -> str:
    m = re.search(r"ADR-(\d+)", path.stem, re.IGNORECASE)
    return f"ADR-{m.group(1)}" if m else path.stem


def _parse_title(text: str) -> str:
    m = re.match(r"#\s+ADR-\d+\s+[—-]\s+(.+)", text)
    return m.group(1).strip() if m else ""


def _parse_invariants(text: str) -> list[Invariant]:
    """
    Extract YAML blocks inside ## Invariants section.
    Expects format:
        ## Invariants
        ```yaml
        invariants:
          - id: "ADR-XXX-I1"
            ...
        ```
    """
    section_m = re.search(r"##\s+Invariants(.+?)(?=\n##|\Z)", text, re.DOTALL)
    if not section_m:
        return []

    section = section_m.group(1)
    yaml_m = re.search(r"```yaml\s*(.*?)```", section, re.DOTALL)
    if not yaml_m:
        return []

    try:
        data = yaml.safe_load(yaml_m.group(1))
    except yaml.YAMLError:
        return []

    raw_list = data.get("invariants", []) if isinstance(data, dict) else []
    result: list[Invariant] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        result.append(
            Invariant(
                id=str(raw.get("id", "")),
                description=str(raw.get("description", "")),
                paths=raw.get("paths", []),
                must_contain=raw.get("must_contain", []),
                must_not_contain=raw.get("must_not_contain", []),
                message=str(raw.get("message", "")),
            )
        )
    return result


def load_adrs(adr_root: Path) -> list[ADR]:
    adrs: list[ADR] = []
    for md in sorted(adr_root.rglob("ADR-*.md")):
        if md.name == "ADR-template.md":
            continue
        text = md.read_text(encoding="utf-8")
        status = _parse_status(text)
        if status != "Accepted":
            continue
        adrs.append(
            ADR(
                path=md,
                number=_parse_adr_number(md),
                title=_parse_title(text),
                status=status,
                project=_parse_project(text),
                invariants=_parse_invariants(text),
            )
        )
    return adrs


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------


def _read_file_content(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def check_invariant(inv: Invariant, project_root: Path, adr_number: str) -> InvariantResult:
    violations: list[str] = []
    checked: list[str] = []

    for rel_path in inv.paths:
        abs_path = project_root / rel_path
        content = _read_file_content(abs_path)

        if content is None:
            violations.append(f"File not found: {rel_path}")
            continue

        checked.append(rel_path)

        for needle in inv.must_contain:
            if needle not in content:
                violations.append(f"{rel_path}: must contain {needle!r} — not found")

        for needle in inv.must_not_contain:
            if needle in content:
                # find line number for context
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    if needle in line:
                        violations.append(
                            f"{rel_path}:{i}: must NOT contain {needle!r} — found: {line.strip()!r}"
                        )

    return InvariantResult(
        invariant_id=inv.id,
        adr_number=adr_number,
        passed=len(violations) == 0,
        violations=violations,
        checked_files=checked,
    )


def run_checks(
    adrs: list[ADR],
    project_root: Path,
    project_roots: dict[str, Path] | None = None,
) -> list[InvariantResult]:
    """
    Check all invariants across all ADRs.

    project_roots maps ADR project names to filesystem roots, e.g.:
        {"content-automation": Path("/root/content-automation-faceless"),
         "jarvis-core": Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))}
    When provided, each ADR uses the root matching its 'project' field.
    Falls back to project_root if the project name is not in the mapping.
    """
    results: list[InvariantResult] = []
    for adr in adrs:
        root = project_root
        if project_roots:
            root = project_roots.get(adr.project, project_root)
        for inv in adr.invariants:
            results.append(check_invariant(inv, root, adr.number))
    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _build_report(
    adrs: list[ADR],
    results: list[InvariantResult],
) -> dict:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "adrs_checked": len(adrs),
        "invariants_total": len(results),
        "invariants_passed": len(passed),
        "invariants_failed": len(failed),
        "status": "PASS" if not failed else "FAIL",
        "adrs": [
            {
                "number": adr.number,
                "title": adr.title,
                "project": adr.project,
                "invariants_count": len(adr.invariants),
            }
            for adr in adrs
        ],
        "results": [
            {
                "id": r.invariant_id,
                "adr": r.adr_number,
                "passed": r.passed,
                "checked_files": r.checked_files,
                "violations": r.violations,
            }
            for r in results
        ],
        "failures": [
            {
                "id": r.invariant_id,
                "adr": r.adr_number,
                "violations": r.violations,
            }
            for r in failed
        ],
    }


def print_summary(report: dict) -> None:
    status_icon = "✅" if report["status"] == "PASS" else "❌"
    print(f"\nADR COMPLIANCE CHECK {status_icon}")
    print("=" * 40)
    print(f"ADRs checked:   {report['adrs_checked']}")
    print(
        f"Invariants:     {report['invariants_total']} total / "
        f"{report['invariants_passed']} passed / "
        f"{report['invariants_failed']} failed"
    )
    print()

    if report["failures"]:
        print("FAILURES:")
        for f in report["failures"]:
            print(f"  [{f['id']}] ({f['adr']})")
            for v in f["violations"]:
                print(f"    → {v}")
        print()

    print(f"Status: {report['status']}")
    print(f"Report: decisions/adr-compliance.json")


# ---------------------------------------------------------------------------
# Public API — callable by auditor agent
# ---------------------------------------------------------------------------


def run_adr_check(
    project_root: Path | None = None,
    adr_root: Path | None = None,
    project_roots: dict[str, Path] | None = None,
    strict: bool = False,
) -> dict:
    """
    Run all ADR invariant checks. Returns the compliance report dict.

    Args:
        project_root:  Fallback root for resolving relative paths. Defaults to CWD.
        adr_root:      Directory containing ADR markdown files.
                       Defaults to project_root/decisions.
        project_roots: Optional per-project root overrides, keyed by ADR 'project' field.
                       Example: {"content-automation": Path("/root/content-automation-faceless"),
                                 "jarvis-core": Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))}
                       When an ADR's project matches a key, that root is used instead of
                       project_root. Callers (e.g. auditor agent) should pass this.
        strict:        If True, raises SystemExit(1) on any failure.

    Returns:
        dict with keys: status, adrs_checked, invariants_total,
                        invariants_passed, invariants_failed, failures, results
    """
    root = project_root or Path.cwd()
    adr_dir = adr_root or (root / "decisions")

    adrs = load_adrs(adr_dir)
    results = run_checks(adrs, root, project_roots=project_roots)
    report = _build_report(adrs, results)

    # Write JSON output
    out_path = adr_dir / "adr-compliance.json"
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


_DEFAULT_PROJECT_ROOTS: dict[str, Path] = {
    "jarvis-core": Path(os.environ.get("JARVIS_ROOT", "/root/jarvis")),
    "content-automation": Path("/root/content-automation-faceless"),
    "all": Path(os.environ.get("JARVIS_ROOT", "/root/jarvis")),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ADR invariants against the codebase.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any invariant fails",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Fallback project root (default: /root/jarvis)",
    )
    parser.add_argument(
        "--adr-root",
        type=Path,
        default=None,
        help="Directory containing ADR .md files (default: <root>/decisions)",
    )
    parser.add_argument(
        "--roots",
        type=str,
        default=None,
        metavar="JSON",
        help=(
            "JSON mapping of project names to filesystem roots. "
            'Example: \'{"content-automation":"/root/content-automation-faceless"}\''
        ),
    )
    args = parser.parse_args()

    root = args.root or Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
    adr_dir = args.adr_root or (root / "decisions")

    project_roots: dict[str, Path] = dict(_DEFAULT_PROJECT_ROOTS)
    if args.roots:
        try:
            raw = json.loads(args.roots)
            project_roots.update({k: Path(v) for k, v in raw.items()})
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: --roots JSON parse failed: {exc}", file=sys.stderr)
            sys.exit(1)

    report = run_adr_check(
        project_root=root,
        adr_root=adr_dir,
        project_roots=project_roots,
        strict=False,
    )
    print_summary(report)

    if args.strict and report["status"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
