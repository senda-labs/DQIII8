#!/usr/bin/env python3
"""
DQIII8 Hook — Local Semgrep scan + Shannon score sync.
Runs on Edit/Write of .py files only. No SEMGREP_APP_TOKEN required.

Actions:
  1. Run semgrep --json on the edited file
  2. Parse severity counts (ERROR=CRITICO, WARNING=ALTO, INFO=MEDIO)
  3. Compute Shannon score: 10 - 2*CRITICO - 1*ALTO - 0.3*MEDIO (min 0)
  4. Upsert vault_memory WHERE subject='shannon_score'
  5. Print human-readable summary to stdout (visible in Claude context)
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

DQIII8_ROOT = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
DB = Path(DQIII8_ROOT) / "database" / "dqiii8.db"

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

inp = data.get("tool_input", {})
path = inp.get("file_path", inp.get("path", ""))

if not path or not path.endswith(".py"):
    sys.exit(0)

if not os.path.isfile(path):
    sys.exit(0)

try:
    result = subprocess.run(
        [
            "semgrep",
            "scan",
            "--config=auto",
            "--json",
            "--timeout=10",
            "--max-target-bytes=500000",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Parse JSON output
    critico = alto = medio = 0
    findings_summary = []
    try:
        scan_data = json.loads(result.stdout)
        for finding in scan_data.get("results", []):
            sev = finding.get("extra", {}).get("severity", "INFO").upper()
            msg = finding.get("extra", {}).get("message", "")[:80]
            line = finding.get("start", {}).get("line", "?")
            if sev == "ERROR":
                critico += 1
                findings_summary.append(f"  CRITICO L{line}: {msg}")
            elif sev == "WARNING":
                alto += 1
                findings_summary.append(f"  ALTO    L{line}: {msg}")
            else:
                medio += 1
                findings_summary.append(f"  MEDIO   L{line}: {msg}")
    except (json.JSONDecodeError, AttributeError):
        # semgrep not available or parse error — skip score update silently
        sys.exit(0)

    # Compute Shannon score
    score = max(0.0, 10.0 - 2 * critico - 1.0 * alto - 0.3 * medio)

    # Print summary to stdout (visible in Claude context)
    short = os.path.basename(path)
    status = "OK" if score >= 8 else ("WARN" if score >= 6 else "CRITICO")
    print(
        f"[Shannon] {short} — score {score:.1f}/10 [{status}] " f"| C:{critico} A:{alto} M:{medio}"
    )
    for line in findings_summary[:5]:  # cap at 5 lines
        print(line)

    # Upsert vault_memory.shannon_score
    if DB.exists():
        try:
            conn = sqlite3.connect(str(DB), timeout=2)
            # Delete old entry (object changes each scan, UNIQUE won't match)
            conn.execute("DELETE FROM vault_memory WHERE subject='shannon_score'")
            conn.execute(
                "INSERT INTO vault_memory "
                "(subject, predicate, object, source, last_seen, entry_type) "
                "VALUES ('shannon_score', 'is', ?, 'semgrep_scan', "
                "datetime('now'), 'checkpoint')",
                (str(round(score, 1)),),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # never block on logging failure

except Exception:
    pass

sys.exit(0)
