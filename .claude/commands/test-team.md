# /test-team — Agent Team Coordination Test

Direct coordination test between agents using Agent Teams.
Demonstrates that the output of one agent feeds directly into the next.

## Team

**Task**: Implement Kelly Criterion in Python based on prior research.

### Agent 1 — research-analyst (first)

Researches the Kelly Criterion and produces a structured summary with:
- Exact mathematical formula: `f* = (bp - q) / b`
  where `b` = net odds, `p` = win probability, `q` = 1 - p
- Input parameters and their valid ranges
- Half-Kelly variant (f* / 2) and when to prefer it
- Use cases in systematic trading (position sizing)
- Known limitations (sensitivity to p estimation)

Writes result to: `tasks/results/research-kelly-[timestamp].md`

### Agent 2 — python-specialist (after Agent 1)

Reads the research-analyst result from `tasks/results/research-kelly-*.md`
and based on it implements:

```python
def kelly_criterion(win_prob: float, win_loss_ratio: float, half_kelly: bool = True) -> float:
    """
    Calculates the optimal position size according to Kelly Criterion.
    ...
    """
```

Implementation requirements:
- Full type hints
- Input validation (0 < win_prob < 1, win_loss_ratio > 0)
- Half-Kelly support (default True — more conservative)
- Usage example in docstring with real trading values

Writes result to: `tasks/results/python-kelly-[timestamp].md`

## Coordination protocol

```
research-analyst → tasks/results/research-kelly-*.md
                              ↓
python-specialist reads that file → implements function
```

The python-specialist does NOT start until research-analyst has written its result.
This validates sequential coordination of Agent Teams.

## Execution

Launch both agents as a coordinated team. The orchestrator waits for the result
from research-analyst before passing context to python-specialist.

When done, show:
1. Research summary (formula + parameters)
2. Implemented Python code
3. Confirmation: `[TEAM] ✅ Kelly Criterion — research + impl complete`
