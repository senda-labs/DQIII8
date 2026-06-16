#!/usr/bin/env python3
"""UserPromptSubmit hook — appends a compiled execution plan as additionalContext.

OPT-IN: does nothing unless DQ_COMPILE_HOOK=1 in the environment.
Fires only for prompts > 100 chars. Never blocks; failures are silent.
NOT registered in settings.json — see DQIII8_TRANSFORMATION_REPORT_2026-06-10.md.
"""
import json
import os
import sys
from pathlib import Path


def main() -> None:
    if os.environ.get("DQ_COMPILE_HOOK") != "1":
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
        prompt = payload.get("prompt", "") or payload.get("user_prompt", "")
        if len(prompt) <= 100:
            sys.exit(0)
        root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(root / "bin" / "agents"))
        from plan_compiler import dq_compile

        plan = dq_compile(prompt)
        if plan.confidence < 0.34:  # <1 keyword hit — don't inject noise
            sys.exit(0)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": plan.render(),
            }
        }))
    except Exception:
        sys.exit(0)  # never block the user's prompt


if __name__ == "__main__":
    main()
