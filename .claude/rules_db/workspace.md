# DQIII8 — Workspace Layouts (tmux + Yazi)

Scripts in `bin/workspace/`. Launch from any terminal with the aliases.

## Layouts

| Alias | Script | Use case |
|-------|--------|----------|
| `workspace` | `launch_swarm.sh` | Main session: Claude Code + Yazi + bot logs + htop |
| `beeswarm` | `launch_beeswarm.sh` | BeeSwarm: Sonnet planner + 3 Haiku workers + Yazi |
| `monitor` | `launch_monitor.sh` | Monitoring: tokens + logs + Yazi + continuous tests |

## When to suggest

- User asks for parallel work, BeeSwarm, or multi-agent tasks →
  suggest: `bash bin/workspace/launch_beeswarm.sh`
- User wants to monitor the system, check logs, or watch tests →
  suggest: `bash bin/workspace/launch_monitor.sh`
- User starts a new dev session on VPS →
  suggest: `bash bin/workspace/launch_swarm.sh`

Yazi opens in `$DQIII8` or the active project dir; config `~/.config/yazi/yazi.toml`.
(Its keybindings are a human-TUI concern, not an agent one — not documented here.)

## Session management

```bash
tmux ls                          # list active sessions
tmux attach -t dqiii8-swarm      # reattach main session
tmux kill-session -t SESSION     # terminate a session
```
