#!/usr/bin/env python3
"""
JARVIS Hook — Local Semgrep scan (replaces semgrep MCP post-tool-cli-scan).
Runs on Edit/Write of .py files only. No SEMGREP_APP_TOKEN required.
"""
import json
import os
import subprocess
import sys

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
            "--quiet",
            "--timeout=10",
            "--max-target-bytes=500000",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
except Exception:
    pass

sys.exit(0)
