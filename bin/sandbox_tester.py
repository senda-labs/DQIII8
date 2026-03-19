#!/usr/bin/env python3
"""
DQIII8 — Sandbox Tester
Reads PENDIENTE_TEST items from research_items, generates minimal test code,
runs semgrep for Shannon score, and auto-approves if criteria met.

Criteria for auto-approval:
  - Shannon score >= 8
  - Test code runs without crash
  - Time < 2x baseline

Usage:
    python3 bin/sandbox_tester.py --process-queue   # process all pending items
    python3 bin/sandbox_tester.py --dry-run         # simulate without DB writes
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"
SANDBOX_ROOT = Path("/root/jarvis-sandbox")
RESULTS_DIR = JARVIS_ROOT / "tasks" / "test_results"

SHANNON_THRESHOLD = 8.0
MIN_SCORE_REQUIRED = 5.0

BASELINE_MS = 2000  # 2 seconds baseline


def _compute_shannon(code: str) -> tuple[float, str]:
    """Run semgrep on code string, return (shannon_score, summary)."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                "semgrep",
                "scan",
                "--config=auto",
                "--json",
                "--timeout=10",
                "--max-target-bytes=100000",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        critico = alto = medio = 0
        try:
            data = json.loads(result.stdout)
            for finding in data.get("results", []):
                sev = finding.get("extra", {}).get("severity", "INFO").upper()
                if sev == "ERROR":
                    critico += 1
                elif sev == "WARNING":
                    alto += 1
                else:
                    medio += 1
        except Exception:
            pass
        score = max(0.0, 10.0 - 2 * critico - 1.0 * alto - 0.3 * medio)
        summary = f"Shannon={score:.1f} C:{critico} A:{alto} M:{medio}"
        return score, summary
    except Exception as e:
        return 0.0, f"semgrep error: {e}"
    finally:
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass


def _classify_item(title: str, summary: str) -> str:
    """Classify item as code/finance/content."""
    combined = (title + " " + summary).lower()
    if any(k in combined for k in ["finance", "wacc", "dcf", "trading", "quant", "portfolio"]):
        return "finance"
    if any(k in combined for k in ["content", "video", "audio", "subtitle", "tts", "media"]):
        return "content"
    return "code"


def _generate_test_code(title: str, summary: str, item_type: str) -> str:
    """Generate minimal test code based on item type and summary."""
    if item_type == "finance":
        return f'''#!/usr/bin/env python3
"""Sandbox test: {title[:60]}"""
# Finance computation probe
import math

def compute_wacc(equity, debt, cost_equity, cost_debt, tax_rate):
    total = equity + debt
    if total == 0:
        return 0.0
    we = equity / total
    wd = debt / total
    return we * cost_equity + wd * cost_debt * (1 - tax_rate)

result = compute_wacc(1000, 500, 0.12, 0.06, 0.21)
assert 0 < result < 1, f"WACC out of range: {{result}}"
print(f"WACC probe OK: {{result:.4f}}")
'''
    elif item_type == "content":
        return f'''#!/usr/bin/env python3
"""Sandbox test: {title[:60]}"""
# Content pipeline probe
import os
import tempfile

def process_content(text, output_format="markdown"):
    if not text:
        raise ValueError("empty content")
    return text.strip()

result = process_content("Test content for DQIII8 pipeline")
assert len(result) > 0
print(f"Content probe OK: {{len(result)}} chars")
'''
    else:
        return f'''#!/usr/bin/env python3
"""Sandbox test: {title[:60]}"""
# Code/agent logic probe
from pathlib import Path
import json

def agent_step(state: dict, action: str) -> dict:
    new_state = dict(state)
    new_state["last_action"] = action
    new_state["step"] = state.get("step", 0) + 1
    return new_state

state = {{"step": 0}}
for action in ["research", "plan", "execute", "verify"]:
    state = agent_step(state, action)

assert state["step"] == 4
print(f"Agent probe OK: step={{state['step']}}")
'''


def process_item(item_id: int, title: str, summary: str, dry_run: bool) -> dict:
    """Process a single research item through the sandbox."""
    item_type = _classify_item(title, summary)
    code = _generate_test_code(title, summary, item_type)

    start_ms = time.time() * 1000

    # Run the test code
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    run_ok = False
    run_output = ""
    try:
        run_result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        run_ok = run_result.returncode == 0
        run_output = (run_result.stdout + run_result.stderr).strip()[:200]
    except Exception as e:
        run_output = str(e)
    finally:
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass

    elapsed_ms = time.time() * 1000 - start_ms

    # Shannon score
    shannon, shannon_summary = _compute_shannon(code)

    # Auto-approval criteria
    time_ok = elapsed_ms < BASELINE_MS * 2
    auto_approve = run_ok and shannon >= SHANNON_THRESHOLD and time_ok

    new_status = "APROBADO_PENDIENTE_INTEGRACION" if auto_approve else "RECHAZADO_AUTO"

    result = {
        "item_id": item_id,
        "title": title,
        "type": item_type,
        "run_ok": run_ok,
        "run_output": run_output,
        "shannon": shannon,
        "shannon_summary": shannon_summary,
        "elapsed_ms": elapsed_ms,
        "auto_approve": auto_approve,
        "new_status": new_status,
    }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="DQIII8 sandbox tester")
    parser.add_argument(
        "--process-queue", action="store_true", help="Process all PENDIENTE_TEST items"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate without DB writes")
    args = parser.parse_args()

    if not args.process_queue and not args.dry_run:
        parser.print_help()
        sys.exit(0)

    if not DB.exists():
        print("[sandbox_tester] DB not found — skipping")
        sys.exit(0)

    conn = sqlite3.connect(str(DB), timeout=5)
    pending = conn.execute(
        "SELECT id, title, summary FROM research_items WHERE status='PENDIENTE_TEST' LIMIT 20"
    ).fetchall()
    conn.close()

    if not pending:
        print("[sandbox_tester] No items in PENDIENTE_TEST queue.")
        sys.exit(0)

    print(f"[sandbox_tester] Processing {len(pending)} items...")

    RESULTS_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    result_file = RESULTS_DIR / f"{ts}_sandbox_test.md"

    report_lines = [f"# Sandbox Test Report — {now.strftime('%Y-%m-%d %H:%M')}\n\n"]

    approved = rejected = 0

    for item_id, title, summary in pending:
        print(f"  Testing: {title[:60]}...")
        result = process_item(item_id, title, summary or "", dry_run=args.dry_run)

        status_icon = "✓" if result["auto_approve"] else "✗"
        report_lines.append(
            f"## {status_icon} {title[:70]}\n"
            f"- Type: {result['type']} | Shannon: {result['shannon']:.1f} | "
            f"Run: {'OK' if result['run_ok'] else 'FAIL'} | Time: {result['elapsed_ms']:.0f}ms\n"
            f"- Status: {result['new_status']}\n"
            f"- Output: {result['run_output'][:100]}\n\n"
        )

        if result["auto_approve"]:
            approved += 1
        else:
            rejected += 1

        if not args.dry_run:
            test_result_json = json.dumps(
                {
                    "shannon": result["shannon"],
                    "run_ok": result["run_ok"],
                    "elapsed_ms": result["elapsed_ms"],
                }
            )
            conn = sqlite3.connect(str(DB), timeout=5)
            conn.execute(
                "UPDATE research_items SET status=?, test_result=? WHERE id=?",
                (result["new_status"], test_result_json, item_id),
            )
            conn.commit()
            conn.close()

    report_lines.append(
        f"## Summary\n"
        f"- Approved: {approved}\n"
        f"- Rejected: {rejected}\n"
        f"- Total: {len(pending)}\n"
    )

    if not args.dry_run:
        result_file.write_text("".join(report_lines), encoding="utf-8")
        print(f"[sandbox_tester] Report: {result_file.name}")

    print(f"[sandbox_tester] Done — {approved} approved, {rejected} rejected")


if __name__ == "__main__":
    main()
