"""
tests/test_dispatch_async.py — async dispatch round-trip (audit 2026-07-05 CRITICAL #1).

The old async design piped raw wrapper stdout over the pending .json file, so
read_result() could never parse it. These tests run dispatch.py as a real
subprocess against a stub wrapper (via DQIII8_ROOT) and assert the full
pending → ok round-trip, plus valid-JSON-at-all-times and read_result behavior.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

DISPATCH = Path(__file__).resolve().parents[1] / "bin" / "core" / "dispatch.py"

STUB_WRAPPER = """\
import argparse, sys

AGENT_ROUTING = {"default": ("stub", "stub-model")}
_PROVIDER_DEFAULT_MODEL = {"stub": "stub-model"}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agent", default="default")
    p.add_argument("--no-enrich", action="store_true")
    p.add_argument("prompt", nargs="?", default=None)
    args = p.parse_args()
    # dispatch.py sends the prompt via stdin (not argv) since 2026-08-13, to
    # avoid MAX_ARG_STRLEN on long prompts — the real wrapper's main() falls
    # back to stdin the same way when no positional prompt is given.
    prompt = args.prompt if args.prompt is not None else sys.stdin.read().strip()
    if prompt == "FAIL":
        sys.exit(1)
    print(f"STUB-RESPONSE:{prompt}")
"""


def _make_fake_root(tmp_path: Path) -> Path:
    core = tmp_path / "bin" / "core"
    core.mkdir(parents=True)
    (tmp_path / "bin" / "__init__.py").write_text("")
    (core / "__init__.py").write_text("")
    (core / "openrouter_wrapper.py").write_text(STUB_WRAPPER)
    return tmp_path


def _dispatch_env(root: Path) -> dict:
    env = {**os.environ, "DQIII8_ROOT": str(root)}
    env.pop("DQIII8_USE_AGNO", None)
    return env


def _run_async(root: Path, prompt: str) -> dict:
    r = subprocess.run(
        [sys.executable, str(DISPATCH), "--agent", "default", "--prompt", prompt, "--async"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_dispatch_env(root),
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _wait_final(result_file: Path, deadline_s: float = 45.0) -> dict:
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        data = json.loads(result_file.read_text())  # must ALWAYS be valid JSON
        if data.get("status") != "pending":
            return data
        time.sleep(0.25)
    raise AssertionError(f"async task never completed: {result_file}")


def test_async_round_trip_ok(tmp_path):
    root = _make_fake_root(tmp_path)
    out = _run_async(root, "hello async world")
    assert out["status"] == "pending"
    assert out["task_id"]

    result_file = Path(out["result_file"])
    assert result_file.exists()

    final = _wait_final(result_file)
    assert final["status"] == "ok"
    assert final["task_id"] == out["task_id"]
    assert "STUB-RESPONSE:hello async world" in final["response"]
    # prompt sidecar file is cleaned up by the worker
    assert not (result_file.parent / f"dispatch-{out['task_id']}.prompt").exists()


def test_async_failure_reported_as_error(tmp_path):
    root = _make_fake_root(tmp_path)
    out = _run_async(root, "FAIL")
    final = _wait_final(Path(out["result_file"]))
    assert final["status"] == "error"


def test_read_result_cli_round_trip(tmp_path):
    root = _make_fake_root(tmp_path)
    out = _run_async(root, "read me back")
    _wait_final(Path(out["result_file"]))

    r = subprocess.run(
        [sys.executable, str(DISPATCH), "--read", out["task_id"]],
        capture_output=True,
        text=True,
        timeout=30,
        env=_dispatch_env(root),
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["status"] == "ok"
    assert "read me back" in data["response"]


def test_sync_mode_unchanged(tmp_path):
    root = _make_fake_root(tmp_path)
    r = subprocess.run(
        [sys.executable, str(DISPATCH), "--agent", "default", "--prompt", "sync hello"],
        capture_output=True,
        text=True,
        timeout=60,
        env=_dispatch_env(root),
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["status"] == "ok"
    assert "STUB-RESPONSE:sync hello" in data["response"]
