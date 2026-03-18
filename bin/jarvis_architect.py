#!/usr/bin/env python3
"""
JARVIS — System Architect
Generates an ASCII diagram of the JARVIS system and writes it to tasks/system_diagram.md.

Usage:
    python3 bin/jarvis_architect.py
    python3 bin/jarvis_architect.py --stdout   # print only, no file
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))

DIAGRAM = r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         JARVIS — System Architecture                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                          HOOK PIPELINE                              │    ║
║  │                                                                     │    ║
║  │  pre_tool_use.py ──► [BLOCK/ALLOW] ──► Claude Code Tool Call       │    ║
║  │         │                                       │                   │    ║
║  │         ▼                                       ▼                   │    ║
║  │  jarvis_metrics.db                    post_tool_use.py              │    ║
║  │  (agent_actions INSERT)               (metrics UPDATE +             │    ║
║  │                                        error_log INSERT +           │    ║
║  │                                        Black auto-format)           │    ║
║  │                                                │                   │    ║
║  │                                                ▼                   │    ║
║  │                                        stop.py                     │    ║
║  │                                        ├── lessons capture          │    ║
║  │                                        ├── session DB write         │    ║
║  │                                        ├── handover note            │    ║
║  │                                        ├── SPC audit_trigger        │    ║
║  │                                        └── context-mode sync        │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                       MODEL ROUTING (3 TIERS)                      │    ║
║  │                                                                     │    ║
║  │  Prompt ──► openrouter_wrapper.py classify                         │    ║
║  │                    │                                                │    ║
║  │         ┌──────────┼──────────────┐                                │    ║
║  │         ▼          ▼              ▼                                 │    ║
║  │  Tier 1 (local)  Tier 2 (free)  Tier 3 (paid)                     │    ║
║  │  Ollama          Groq /          Claude API                         │    ║
║  │  qwen2.5-coder   OpenRouter      sonnet-4-6                        │    ║
║  │  :7b             free models     finance/creative/arch             │    ║
║  │                                                                     │    ║
║  │  Fallback chain: Ollama→OpenRouter→Groq→llm7→Pollinations          │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                         AGENT DELEGATION                           │    ║
║  │                                                                     │    ║
║  │  python-specialist ── Ollama:qwen2.5-coder   [py, debug, refactor] │    ║
║  │  git-specialist    ── Ollama:qwen2.5-coder   [commit, branch, PR]  │    ║
║  │  code-reviewer     ── Groq:llama-3.3-70b     [review, after feat]  │    ║
║  │  content-automator ── OpenRouter:nemotron    [video, TTS, reels]   │    ║
║  │  data-analyst      ── Claude:sonnet-4-6      [WACC, DCF, charts]   │    ║
║  │  creative-writer   ── Claude:sonnet-4-6      [novel, xianxia]      │    ║
║  │  auditor           ── Claude:sonnet-4-6      [/audit, metrics]     │    ║
║  │  orchestrator      ── Claude:sonnet-4-6      [/mobilize, 3+ domains]│   ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                      OBSERVABILITY STACK                           │    ║
║  │                                                                     │    ║
║  │  jarvis_metrics.db                                                  │    ║
║  │  ├── agent_actions    (every tool call: success, duration, bytes)  │    ║
║  │  ├── sessions         (per session: lessons, errors, summary)      │    ║
║  │  ├── error_log        (failures with resolution tracking)          │    ║
║  │  ├── audit_reports    (score history, methodology v1.0)            │    ║
║  │  ├── spc_metrics      (SPC trigger log: T1-T5 per session)        │    ║
║  │  ├── vault_memory     (instincts, lessons, SSOT facts)            │    ║
║  │  ├── instincts        (pattern → confidence → action)             │    ║
║  │  └── skill_metrics    (skill success rate, error count)           │    ║
║  │                                                                     │    ║
║  │  audit_trigger.py ── SPC triggers (T1-T5) ── audit_pending.flag   │    ║
║  │  /audit skill      ── auditor agent      ── audit_reports/*.md    │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                      MCP INTEGRATIONS                              │    ║
║  │                                                                     │    ║
║  │  context-mode  ── ctx_batch_execute / ctx_search (context savings) │    ║
║  │  filesystem    ── read/write/tree (VPS filesystem access)          │    ║
║  │  sqlite        ── execute / query (direct DB access)              │    ║
║  │  github        ── search / PR / issues (GitHub API)               │    ║
║  │  exa           ── web search / deep research                       │    ║
║  │  semgrep       ── static analysis / security scan                  │    ║
║  │  episodic-memory── conversation search across sessions             │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                         SPC TRIGGER TABLE                          │    ║
║  │                                                                     │    ║
║  │  T1: success_rate < 95%   (last 50 actions)       → priority HIGH  │    ║
║  │  T2: error_log >= 3       (current session)        → priority HIGH  │    ║
║  │  T3: lessons_added = 0    (last 5 sessions)       → priority MED   │    ║
║  │  T4: 7+ days since audit  (temporal)              → priority MED   │    ║
║  │  T5: Shannon score < 8/10 (last vault scan)       → priority MED   │    ║
║  │                                                                     │    ║
║  │  Any trigger → audit_pending.flag → /audit on next session start   │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


def generate(stdout_only: bool = False) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"# JARVIS System Architecture\n\n_Generated: {ts}_\n\n```\n{DIAGRAM.strip()}\n```\n"

    if stdout_only:
        print(content)
        return

    out = JARVIS_ROOT / "tasks" / "system_diagram.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"[jarvis_architect] Diagram written to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JARVIS system architecture diagram.")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of file")
    args = parser.parse_args()
    generate(stdout_only=args.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
