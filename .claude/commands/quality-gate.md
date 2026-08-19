# /quality-gate — On-Demand Quality Pipeline

> **SSOT: `.claude/skills/quality-gate/SKILL.md`.** This command file is a
> pointer only — read the skill for the full 5-phase pipeline, its usage
> (`/quality-gate [path|.] [--fix] [--strict]`) and its output format. It
> previously carried a duplicate copy whose Phase 3 ran a strictly weaker lint
> gate (`ruff check --select E,F,W`, dropping `PLE2510-PLE2515` — the
> hidden/invalid-Unicode-control-character family, i.e. the trojan-source
> defense) and still reported PASS. Reconciled 2026-08-18 (F2): the skill's
> ruleset is canonical, and this file no longer restates it.
