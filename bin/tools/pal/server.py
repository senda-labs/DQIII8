#!/usr/bin/env python3
"""
PAL MCP Server — Provider Abstraction Layer
Exposes dqiii8 routing pipeline as MCP tools over stdio.
Pattern: calca sqlite_mcp.py (JSON-RPC hand-rolled, no SDK dependency).
"""

import json
import sys
import os
from pathlib import Path

# Ensure bin/ is in sys.path for: from core.openrouter_wrapper import ...
_BIN = Path(__file__).resolve().parents[2]
if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

from tools.pal import engine  # noqa: E402  (after sys.path setup)

TOOLS = [
    {
        "name": "pal_generate",
        "description": (
            "Generate text or code with a cheap/local provider. "
            "Specify 'model' (e.g. 'ollama/qwen2.5-coder:7b', 'groq/llama-3.3-70b-versatile') "
            "OR pass 'task_type' (e.g. 'python-specialist') for auto-routing. "
            "Fallback chain is transparent. Returns text + latency + token metrics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "model": {
                    "type": "string",
                    "description": "provider/model spec. Omit to use task_type routing.",
                },
                "task_type": {
                    "type": "string",
                    "description": "Agent name from AGENT_ROUTING (e.g. 'python-specialist'). Used only if model omitted.",
                },
                "system_prompt": {"type": "string"},
                "max_tokens": {"type": "integer", "default": 2048},
                "allow_fallback": {"type": "boolean", "default": True},
                "strip_fences": {
                    "type": "boolean",
                    "default": False,
                    "description": "Strip markdown code fences (```lang```) from output. Useful for code generation.",
                },
                "project": {
                    "type": "string",
                    "description": "Project slug (my-projects/<slug>) this call should attribute cost/hours to. Omit if not project-scoped.",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "pal_benchmark",
        "description": (
            "Run ONE prompt against multiple models in parallel. "
            "Returns comparison table with latency, tokens, cost. "
            "Optional judge scores quality 1-10 via Groq/Llama."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of provider/model specs. Defaults to ollama+groq+openrouter cheap set.",
                },
                "system_prompt": {"type": "string"},
                "max_tokens": {"type": "integer", "default": 1024},
                "judge": {
                    "type": "boolean",
                    "default": False,
                    "description": "Score each output 1-10 via Groq/Llama. Adds 1 call per model.",
                },
                "timeout_s": {"type": "integer", "default": 90},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "pal_route",
        "description": (
            "Return which provider/model PAL would pick for a task_type or prompt. "
            "Does NOT execute — cheap decision query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {"type": "string"},
                "prompt": {"type": "string"},
            },
        },
    },
    {
        "name": "pal_models",
        "description": (
            "List available providers/models and their default model. "
            "Optional health_check pings each provider endpoint."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "health_check": {"type": "boolean", "default": False},
            },
        },
    },
]


def respond(id_, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": id_}
    if error:
        out["error"] = {"code": -32000, "message": str(error)}
    else:
        out["result"] = result
    print(json.dumps(out), flush=True)


def handle(req):
    method = req.get("method", "")
    params = req.get("params", {})
    id_ = req.get("id")

    if method == "initialize":
        respond(
            id_,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pal", "version": "1.0"},
            },
        )

    elif method == "tools/list":
        respond(id_, {"tools": TOOLS})

    elif method == "tools/call":
        tool = params.get("name")
        args = params.get("arguments", {})
        try:
            result_data = _dispatch(tool, args)
            respond(id_, {"content": [{"type": "text", "text": json.dumps(result_data, ensure_ascii=False)}]})
        except Exception as exc:
            respond(id_, error=str(exc))

    elif method == "notifications/initialized":
        pass

    else:
        respond(id_, error=f"Method not found: {method}")


def _dispatch(tool: str, args: dict):
    if tool == "pal_generate":
        return engine.generate(
            prompt=args["prompt"],
            model=args.get("model"),
            task_type=args.get("task_type"),
            system_prompt=args.get("system_prompt", ""),
            max_tokens=args.get("max_tokens", 2048),
            allow_fallback=args.get("allow_fallback", True),
            strip_fences=args.get("strip_fences", False),
            project=args.get("project"),
        )
    elif tool == "pal_benchmark":
        return engine.benchmark(
            prompt=args["prompt"],
            model_specs=args.get("models"),
            system_prompt=args.get("system_prompt", ""),
            max_tokens=args.get("max_tokens", 1024),
            judge=args.get("judge", False),
            timeout_s=args.get("timeout_s", 90),
        )
    elif tool == "pal_route":
        return engine.route(
            task_type=args.get("task_type"),
            prompt=args.get("prompt"),
        )
    elif tool == "pal_models":
        return engine.models(health_check=args.get("health_check", False))
    else:
        raise ValueError(f"Unknown tool: {tool}")


# ── Main loop ────────────────────────────────────────────────────────────────
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        handle(req)
    except json.JSONDecodeError:
        pass
    except Exception as exc:
        print(
            json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}),
            flush=True,
        )
