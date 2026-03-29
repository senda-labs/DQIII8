"""
BeeSwarm — Parallel Haiku task decomposition with Sonnet validation.

Pattern: Decompose → Map (Haiku swarm) → Reduce (Haiku) → Validate (Sonnet)

Usage:
    from bee_swarm import BeeSwarm, SwarmTask

    swarm = BeeSwarm()
    result = await swarm.run("review all functions in bin/orchestrator.py for bugs")
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Cost constants (USD per 1M tokens) ─────────────────────────────────────
_COST = {
    "haiku": {"input": 0.80, "output": 4.00},
    "sonnet": {"input": 3.00, "output": 15.00},
}

# ── Decomposition patterns ──────────────────────────────────────────────────

# Tasks that decompose well by file/module
_FILE_DECOMPOSE = frozenset(
    {
        "review",
        "audit",
        "check",
        "analiza",
        "analyze",
        "test",
        "document",
        "lint",
        "busca",
        "find bugs",
    }
)

# Tasks that decompose well by function/class
_FUNC_DECOMPOSE = frozenset(
    {
        "write tests for",
        "generate tests",
        "document functions",
        "type annotate",
        "add docstrings",
    }
)

# Tasks that decompose well by topic/chunk
_CHUNK_DECOMPOSE = frozenset(
    {
        "summarize",
        "translate",
        "extract",
        "classify",
        "categorize",
        "index",
    }
)


@dataclass
class Subtask:
    id: int
    prompt: str
    context: str = ""  # file content / chunk passed to Haiku
    result: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: int = 0
    model: str = "haiku"


@dataclass
class SwarmResult:
    original_prompt: str
    subtasks: list[Subtask]
    reduced: str  # Haiku-aggregated result
    validated: str  # Sonnet-validated final
    sonnet_result: str  # Direct Sonnet answer (for comparison)
    strategy: str  # "file" | "function" | "chunk" | "none"

    # Metrics
    haiku_tokens_in: int = 0
    haiku_tokens_out: int = 0
    sonnet_tokens_in: int = 0
    sonnet_tokens_out: int = 0
    total_duration_ms: int = 0

    @property
    def haiku_cost_usd(self) -> float:
        return (
            self.haiku_tokens_in / 1_000_000 * _COST["haiku"]["input"]
            + self.haiku_tokens_out / 1_000_000 * _COST["haiku"]["output"]
        )

    @property
    def sonnet_cost_usd(self) -> float:
        return (
            self.sonnet_tokens_in / 1_000_000 * _COST["sonnet"]["input"]
            + self.sonnet_tokens_out / 1_000_000 * _COST["sonnet"]["output"]
        )

    @property
    def savings_pct(self) -> float:
        """Estimated % cost saved vs doing everything in Sonnet."""
        swarm_cost = self.haiku_cost_usd + self.sonnet_cost_usd
        # Estimate: if Sonnet had done all the map work
        hypothetical_sonnet = (
            (self.haiku_tokens_in + self.haiku_tokens_out)
            / 1_000_000
            * ((_COST["sonnet"]["input"] + _COST["sonnet"]["output"]) / 2)
        )
        if hypothetical_sonnet == 0:
            return 0.0
        return max(
            0.0, (1 - swarm_cost / (hypothetical_sonnet + self.sonnet_cost_usd)) * 100
        )

    def report(self) -> str:
        lines = [
            f"BeeSwarm Report — strategy={self.strategy}, subtasks={len(self.subtasks)}",
            f"Haiku workers : {len(self.subtasks)} parallel",
            f"Haiku tokens  : {self.haiku_tokens_in:,} in / {self.haiku_tokens_out:,} out",
            f"Sonnet tokens : {self.sonnet_tokens_in:,} in / {self.sonnet_tokens_out:,} out",
            f"Cost (swarm)  : ${self.haiku_cost_usd + self.sonnet_cost_usd:.4f}",
            f"Est. savings  : {self.savings_pct:.1f}% vs pure-Sonnet",
            f"Wall time     : {self.total_duration_ms}ms",
            "",
            "── SWARM RESULT ──",
            self.validated or self.reduced,
            "",
            "── SONNET DIRECT ──",
            self.sonnet_result,
        ]
        return "\n".join(lines)


class BeeSwarm:
    """Orchestrates a swarm of Haiku workers for parallelizable tasks."""

    def __init__(self, root: Path | None = None) -> None:
        import os

        self.root = root or Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self,
        prompt: str,
        target_files: list[Path] | None = None,
        max_workers: int = 6,
        validate: bool = True,
    ) -> SwarmResult:
        """Decompose prompt, run Haiku swarm, reduce, then Sonnet-validate.

        Args:
            prompt: The user's task description.
            target_files: If provided, forces file-based decomposition.
            max_workers: Max parallel Haiku agents (default 6).
            validate: Whether to run Sonnet validation step.
        """
        t0 = time.monotonic()

        strategy, subtasks = self._decompose(prompt, target_files, max_workers)

        if not subtasks:
            # Not decomposable — run directly in Sonnet
            sonnet_ans = await self._call_sonnet(prompt)
            return SwarmResult(
                original_prompt=prompt,
                subtasks=[],
                reduced="",
                validated=sonnet_ans,
                sonnet_result=sonnet_ans,
                strategy="none",
                total_duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # Run Haiku workers + Sonnet baseline in parallel
        haiku_coro = self._run_swarm(subtasks, max_workers)
        sonnet_coro = self._call_sonnet(prompt)

        (completed_subtasks, reduced), sonnet_result = await asyncio.gather(
            haiku_coro, sonnet_coro
        )

        validated = reduced
        sonnet_extra_in = sonnet_extra_out = 0
        if validate and completed_subtasks:
            validated, sonnet_extra_in, sonnet_extra_out = await self._validate(
                prompt, reduced
            )

        total_in = sum(s.tokens_in for s in completed_subtasks)
        total_out = sum(s.tokens_out for s in completed_subtasks)

        return SwarmResult(
            original_prompt=prompt,
            subtasks=completed_subtasks,
            reduced=reduced,
            validated=validated,
            sonnet_result=sonnet_result,
            strategy=strategy,
            haiku_tokens_in=total_in,
            haiku_tokens_out=total_out,
            sonnet_tokens_in=sonnet_extra_in,
            sonnet_tokens_out=sonnet_extra_out,
            total_duration_ms=int((time.monotonic() - t0) * 1000),
        )

    # ── Decomposition ───────────────────────────────────────────────────────

    def _decompose(
        self,
        prompt: str,
        target_files: list[Path] | None,
        max_workers: int,
    ) -> tuple[str, list[Subtask]]:
        """Return (strategy, subtasks). Empty list = not decomposable."""
        lower = prompt.lower()

        # File-based decomposition
        files = target_files or self._infer_files(lower)
        if files:
            subtasks = [
                Subtask(
                    id=i,
                    prompt=f"{prompt}\n\nFocus only on this file:\n{f.name}",
                    context=self._read_file_chunk(f),
                )
                for i, f in enumerate(files[:max_workers])
            ]
            return "file", subtasks

        # Function-based decomposition
        funcs = self._infer_functions(lower)
        if funcs:
            subtasks = [
                Subtask(
                    id=i,
                    prompt=f"{prompt}\n\nFocus only on function: {fn}",
                    context="",
                )
                for i, fn in enumerate(funcs[:max_workers])
            ]
            return "function", subtasks

        # Chunk-based decomposition (long text / log analysis)
        chunks = self._infer_chunks(lower)
        if chunks:
            subtasks = [
                Subtask(id=i, prompt=prompt, context=chunk)
                for i, chunk in enumerate(chunks[:max_workers])
            ]
            return "chunk", subtasks

        return "none", []

    def _infer_files(self, lower: str) -> list[Path]:
        """Find Python files mentioned or implied by the prompt."""
        # Explicit file references
        mentioned = re.findall(r"[\w/]+\.py", lower)
        found = [self.root / p for p in mentioned if (self.root / p).exists()]
        if found:
            return found

        # Directory-level: "review all files in bin/"
        dir_match = re.search(r"(?:in|from|inside)\s+([\w/]+)", lower)
        if dir_match:
            d = self.root / dir_match.group(1)
            if d.is_dir():
                return sorted(d.glob("*.py"))[:6]

        return []

    def _infer_functions(self, lower: str) -> list[str]:
        """Return list of function names if prompt implies per-function work."""
        for trigger in _FUNC_DECOMPOSE:
            if trigger in lower:
                # Try to extract function names from relevant files
                # (simplified: return empty → caller falls through)
                break
        return []

    def _infer_chunks(self, lower: str) -> list[str]:
        """Split large inline text into chunks (not implemented for CLI use)."""
        return []

    def _read_file_chunk(self, path: Path, max_chars: int = 3000) -> str:
        try:
            text = path.read_text(encoding="utf-8")
            return text[:max_chars]
        except Exception:
            return ""

    # ── Execution ───────────────────────────────────────────────────────────

    async def _run_swarm(
        self, subtasks: list[Subtask], max_workers: int
    ) -> tuple[list[Subtask], str]:
        """Run all subtasks in parallel, then reduce."""
        sem = asyncio.Semaphore(max_workers)

        async def _worker(st: Subtask) -> Subtask:
            async with sem:
                return await self._call_haiku(st)

        completed = await asyncio.gather(*[_worker(st) for st in subtasks])
        reduced = await self._reduce(completed)
        return list(completed), reduced

    async def _call_haiku(self, subtask: Subtask) -> Subtask:
        """Call Haiku via Ollama (local, free) or Claude API fallback."""
        t0 = time.monotonic()
        prompt = subtask.prompt
        if subtask.context:
            prompt = f"{prompt}\n\n```\n{subtask.context}\n```"

        result = await self._ollama_generate(prompt)
        if result is None:
            result = await self._claude_api_generate(prompt, model="haiku")

        subtask.result = result or "(no output)"
        subtask.duration_ms = int((time.monotonic() - t0) * 1000)
        # Rough token estimate (4 chars ≈ 1 token)
        subtask.tokens_in = len(prompt) // 4
        subtask.tokens_out = len(subtask.result) // 4
        return subtask

    async def _reduce(self, subtasks: list[Subtask]) -> str:
        """Haiku reduces N results into one coherent answer."""
        if not subtasks:
            return ""
        if len(subtasks) == 1:
            return subtasks[0].result

        combined = "\n\n".join(
            f"[Worker {s.id} — {Path(s.prompt.split(chr(10))[0]).name}]:\n{s.result}"
            for s in subtasks
        )
        reduce_prompt = (
            f"Synthesize these {len(subtasks)} parallel analysis results into "
            f"one concise, coherent summary. Eliminate duplicates. "
            f"Keep all unique findings.\n\n{combined}"
        )
        result = await self._ollama_generate(reduce_prompt)
        return result or combined

    async def _validate(
        self, original_prompt: str, swarm_result: str
    ) -> tuple[str, int, int]:
        """Sonnet validates and optionally corrects the swarm result."""
        val_prompt = (
            f"Original task: {original_prompt}\n\n"
            f"A swarm of fast models produced this result:\n{swarm_result}\n\n"
            f"Validate this result. Fix any errors, fill gaps, improve clarity. "
            f"Return the corrected final answer."
        )
        result = await self._claude_api_generate(val_prompt, model="sonnet")
        tokens_in = len(val_prompt) // 4
        tokens_out = len(result or "") // 4
        return result or swarm_result, tokens_in, tokens_out

    async def _call_sonnet(self, prompt: str) -> str:
        """Direct Sonnet call for comparison baseline."""
        result = await self._claude_api_generate(prompt, model="sonnet")
        return result or "(sonnet unavailable)"

    # ── Model backends ──────────────────────────────────────────────────────

    async def _ollama_generate(
        self, prompt: str, model: str = "qwen2.5-coder:7b"
    ) -> str | None:
        """Non-blocking Ollama call via asyncio subprocess."""
        try:
            import json as _json
            import urllib.request

            def _call() -> str:
                req = urllib.request.Request(
                    "http://localhost:11434/api/generate",
                    data=_json.dumps(
                        {"model": model, "prompt": prompt, "stream": False}
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    return _json.loads(r.read())["response"]

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _call)
        except Exception as e:
            log.debug("Ollama unavailable: %s", e)
            return None

    async def _claude_api_generate(
        self, prompt: str, model: str = "haiku"
    ) -> str | None:
        """Call Claude API via anthropic SDK (non-blocking)."""
        try:
            import anthropic

            MODEL_MAP = {
                "haiku": "claude-haiku-4-5-20251001",
                "sonnet": "claude-sonnet-4-6",
            }

            def _call() -> str:
                client = anthropic.Anthropic()
                msg = client.messages.create(
                    model=MODEL_MAP.get(model, model),
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _call)
        except Exception as e:
            log.debug("Claude API unavailable for %s: %s", model, e)
            return None


# ── CLI smoke test ──────────────────────────────────────────────────────────


async def _smoke_test() -> None:
    """Quick smoke test: review bin/ Python files with swarm vs Sonnet."""
    import os

    root = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
    target_files = sorted((root / "bin").glob("*.py"))[:4]

    swarm = BeeSwarm(root=root)
    prompt = (
        "Find any functions that have no error handling and list them with file:line"
    )

    print(f"Decomposing into {len(target_files)} subtasks (one per file)...")
    print(f"Files: {[f.name for f in target_files]}\n")

    result = await swarm.run(prompt, target_files=target_files, max_workers=4)
    print(result.report())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_smoke_test())
