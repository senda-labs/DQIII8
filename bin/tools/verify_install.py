#!/usr/bin/env python3
"""Post-installation security verification for DQIII8."""
import os
import re
import subprocess
import sys
from pathlib import Path

JARVIS = Path(
    os.environ.get(
        "JARVIS_ROOT",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
)

checks_passed = 0
checks_failed = 0
warnings = 0


def check(name: str, condition: bool, fix: str = "") -> bool:
    global checks_passed, checks_failed
    if condition:
        print(f"  OK  {name}")
        checks_passed += 1
        return True
    else:
        print(f"  FAIL {name}")
        if fix:
            print(f"    Fix: {fix}")
        checks_failed += 1
        return False


def warn(name: str, message: str) -> None:
    global warnings
    print(f"  WARN {name}: {message}")
    warnings += 1


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=str(JARVIS)
    )


def main() -> int:
    print("=== DQIII8 Security Verification ===\n")

    # ── 1. File permissions ──────────────────────────────────────────────────
    print("[1/7] File permissions")
    env_file = JARVIS / ".env"
    if env_file.exists():
        mode = oct(env_file.stat().st_mode)[-3:]
        check(".env permissions <= 600", int(mode) <= 600, f"chmod 600 {env_file}")
    else:
        warn(".env", "File not found — copy from config/.env.example")

    db_path = JARVIS / "database" / "jarvis_metrics.db"
    if db_path.exists():
        mode = oct(db_path.stat().st_mode)[-3:]
        check("DB permissions <= 600", int(mode) <= 600, f"chmod 600 {db_path}")

    # ── 2. No secrets in tracked files ──────────────────────────────────────
    print("\n[2/7] Secret scanning")
    ls_result = _git("ls-files")
    if ls_result.returncode == 0:
        # Patterns for real credentials (not placeholder examples)
        secret_patterns = {
            "GitHub PAT": r"ghp_[a-zA-Z0-9]{36}",
            "Anthropic key": r"sk-ant-[a-zA-Z0-9-]{40,}",
            "Groq key": r"gsk_[a-zA-Z0-9]{20,}",
            "OpenAI key": r"sk-[a-zA-Z0-9]{20,}",
        }
        found_secrets = False
        for f in ls_result.stdout.strip().split("\n"):
            fpath = JARVIS / f
            if not fpath.exists() or fpath.suffix in (".db", ".json", ".lock", ".pyc"):
                continue
            try:
                content = fpath.read_text(errors="ignore")
                for sname, pattern in secret_patterns.items():
                    if re.search(pattern, content):
                        print(f"  FAIL CRITICAL: {sname} found in {f}")
                        found_secrets = True
                        global checks_failed
                        checks_failed += 1
            except Exception:
                pass
        if not found_secrets:
            check("No secrets in tracked files", True)

    # ── 3. Git safety ────────────────────────────────────────────────────────
    print("\n[3/7] Git safety")
    check(
        ".env not tracked by git",
        _git("ls-files", ".env").stdout.strip() == "",
        "git rm --cached .env && echo '.env' >> .gitignore",
    )
    check(
        ".mcp.json not tracked by git",
        _git("ls-files", ".mcp.json").stdout.strip() == "",
    )

    # ── 4. Network security ──────────────────────────────────────────────────
    print("\n[4/7] Network security")
    try:
        curl_result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", "3", "http://localhost:11434/api/version"],
            capture_output=True, text=True, timeout=5,
        )
        check("Ollama reachable on localhost", curl_result.stdout.strip() == "200")
    except Exception:
        warn("Ollama", "Not running — start with: ollama serve")

    try:
        ss_result = subprocess.run(
            ["ss", "-tlnp"], capture_output=True, text=True, timeout=5
        )
        exposed = "0.0.0.0:11434" in ss_result.stdout or ":::11434" in ss_result.stdout
        check(
            "Ollama not exposed externally",
            not exposed,
            "Set OLLAMA_HOST=127.0.0.1:11434 in Ollama config",
        )
    except Exception:
        warn("Network check", "ss command unavailable")

    # ── 5. Dependencies ──────────────────────────────────────────────────────
    print("\n[5/7] Dependencies")
    req_file = JARVIS / "requirements.txt"
    if req_file.exists():
        deps = [
            line.strip().split("==")[0].split(">=")[0].split("~=")[0]
            for line in req_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        check(f"requirements.txt has {len(deps)} dependencies (< 20)", len(deps) < 20)
        # Known malicious/backdoored packages (historical incidents)
        known_bad = {"ctx", "phpass", "loglib-modules", "aioconsole-ng"}
        found_bad = set(d.lower() for d in deps) & known_bad
        check("No known malicious packages", len(found_bad) == 0)
    else:
        warn("requirements.txt", "File not found")

    # ── 6. Hook safety ───────────────────────────────────────────────────────
    print("\n[6/7] Hook safety")
    hooks_dir = JARVIS / ".claude" / "hooks"
    if hooks_dir.exists():
        for hook in sorted(hooks_dir.glob("*.py")):
            content = hook.read_text(errors="ignore")
            has_shell_true = "shell=True" in content
            if has_shell_true:
                warn(hook.name, "uses shell=True — verify input is not user-controlled")
            else:
                check(f"{hook.name}: no shell=True", True)
    else:
        warn("Hooks", ".claude/hooks/ not found")

    # ── 7. Autonomous mode safety ────────────────────────────────────────────
    print("\n[7/7] Autonomous mode")
    loop_sh = JARVIS / "bin" / "autonomous_loop.sh"
    if loop_sh.exists():
        content = loop_sh.read_text()
        check("MAX_ITER limit exists", "MAX_ITER" in content,
              "Add MAX_ITER to autonomous_loop.sh to prevent runaway loops")
        check("Stop flag check exists",
              "stop_flag" in content.lower() or "STOP_FLAG" in content,
              "Add a stop flag mechanism to autonomous_loop.sh")
    else:
        check("No autonomous_loop.sh (not running headless)", True)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n=== Results: {checks_passed} passed, {checks_failed} failed, {warnings} warnings ===")
    if checks_failed > 0:
        print("\n  Fix the failed checks before running in production.")
        return 1
    elif warnings > 0:
        print("\n  All checks passed with warnings. Review warnings above.")
        return 0
    else:
        print("\n  All security checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
