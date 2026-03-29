"""Tests for BeeSwarm — task decomposition + Haiku swarm."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))

from bee_swarm import BeeSwarm, Subtask, SwarmResult

# ── Fixtures ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent


@pytest.fixture
def swarm():
    return BeeSwarm(root=ROOT)


def _fake_subtask(
    id: int, result: str = "ok", tokens_in: int = 100, tokens_out: int = 50
) -> Subtask:
    return Subtask(
        id=id, prompt="test", result=result, tokens_in=tokens_in, tokens_out=tokens_out
    )


# ── Unit: decomposition ──────────────────────────────────────────────────────


class TestDecomposition:
    def test_file_decompose_explicit_path(self, swarm):
        """Explicit .py file in prompt triggers file strategy."""
        strategy, subtasks = swarm._decompose(
            "review bin/orchestrator.py for bugs", None, 6
        )
        assert strategy == "file"
        assert len(subtasks) == 1
        assert "orchestrator.py" in subtasks[0].prompt

    def test_file_decompose_target_files(self, swarm):
        """target_files override forces file strategy."""
        files = list((ROOT / "bin").glob("*.py"))[:3]
        strategy, subtasks = swarm._decompose("review for bugs", files, 6)
        assert strategy == "file"
        assert len(subtasks) == len(files)

    def test_no_decompose_simple_prompt(self, swarm):
        """Short prompt with no files → strategy=none."""
        strategy, subtasks = swarm._decompose("what is 2+2", None, 6)
        assert strategy == "none"
        assert subtasks == []

    def test_max_workers_cap(self, swarm):
        """Never creates more subtasks than max_workers."""
        files = list((ROOT / "bin").glob("*.py"))
        strategy, subtasks = swarm._decompose("review", files, 2)
        assert len(subtasks) <= 2

    def test_file_context_loaded(self, swarm):
        """Each file subtask loads the file content as context."""
        files = [ROOT / "bin" / "orchestrator.py"]
        _, subtasks = swarm._decompose("review", files, 6)
        assert len(subtasks[0].context) > 0


# ── Unit: SwarmResult metrics ────────────────────────────────────────────────


class TestSwarmResultMetrics:
    def test_haiku_cost_calculation(self):
        r = SwarmResult(
            original_prompt="test",
            subtasks=[],
            reduced="",
            validated="",
            sonnet_result="",
            strategy="file",
            haiku_tokens_in=1_000_000,
            haiku_tokens_out=500_000,
        )
        # 1M input @ $0.80 + 0.5M output @ $4.00 = $0.80 + $2.00 = $2.80
        assert abs(r.haiku_cost_usd - 2.80) < 0.01

    def test_savings_pct_positive(self):
        r = SwarmResult(
            original_prompt="test",
            subtasks=[],
            reduced="",
            validated="",
            sonnet_result="",
            strategy="file",
            haiku_tokens_in=100_000,
            haiku_tokens_out=50_000,
            sonnet_tokens_in=10_000,
            sonnet_tokens_out=5_000,
        )
        # Haiku is cheaper than Sonnet → savings should be > 0
        assert r.savings_pct > 0

    def test_savings_pct_no_haiku_work(self):
        r = SwarmResult(
            original_prompt="test",
            subtasks=[],
            reduced="",
            validated="",
            sonnet_result="",
            strategy="none",
            haiku_tokens_in=0,
            haiku_tokens_out=0,
        )
        assert r.savings_pct == 0.0

    def test_report_contains_sections(self):
        r = SwarmResult(
            original_prompt="test",
            subtasks=[_fake_subtask(0)],
            reduced="reduced output",
            validated="validated output",
            sonnet_result="sonnet output",
            strategy="file",
            haiku_tokens_in=1000,
            haiku_tokens_out=500,
        )
        report = r.report()
        assert "SWARM RESULT" in report
        assert "SONNET DIRECT" in report
        assert "strategy=file" in report


# ── Unit: reduce ────────────────────────────────────────────────────────────


class TestReduce:
    def test_reduce_single_subtask(self, swarm):
        """Single subtask → result returned directly without LLM call."""
        st = _fake_subtask(0, result="found bug at line 42")
        reduced = asyncio.get_event_loop().run_until_complete(swarm._reduce([st]))
        assert reduced == "found bug at line 42"

    def test_reduce_empty(self, swarm):
        reduced = asyncio.get_event_loop().run_until_complete(swarm._reduce([]))
        assert reduced == ""


# ── Integration: run() with mocked backends ──────────────────────────────────


class TestSwarmRun:
    @pytest.mark.asyncio
    async def test_run_no_decompose_calls_sonnet(self, swarm):
        """Non-decomposable prompt routes directly to Sonnet."""
        with patch.object(swarm, "_call_sonnet", new_callable=AsyncMock) as mock_sonnet:
            mock_sonnet.return_value = "42"
            result = await swarm.run("what is 2+2")
        assert result.strategy == "none"
        assert result.validated == "42"
        mock_sonnet.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_file_strategy_parallel(self, swarm):
        """File strategy runs one worker per file and reduces."""
        files = list((ROOT / "bin").glob("*.py"))[:3]

        async def fake_haiku(st: Subtask) -> Subtask:
            st.result = f"file {st.id} ok"
            st.tokens_in = 100
            st.tokens_out = 50
            return st

        with (
            patch.object(swarm, "_call_haiku", side_effect=fake_haiku),
            patch.object(
                swarm, "_ollama_generate", new_callable=AsyncMock
            ) as mock_ollama,
            patch.object(swarm, "_call_sonnet", new_callable=AsyncMock) as mock_sonnet,
            patch.object(swarm, "_validate", new_callable=AsyncMock) as mock_validate,
        ):
            mock_ollama.return_value = "synthesized"
            mock_sonnet.return_value = "sonnet direct"
            mock_validate.return_value = ("validated", 50, 25)

            result = await swarm.run("review for bugs", target_files=files)

        assert result.strategy == "file"
        assert len(result.subtasks) == len(files)
        assert result.sonnet_result == "sonnet direct"
        assert result.validated == "validated"

    @pytest.mark.asyncio
    async def test_swarm_faster_than_sequential(self, swarm):
        """Parallel execution is faster than sequential for multiple files."""
        import time

        files = list((ROOT / "bin").glob("*.py"))[:4]
        call_count = 0

        async def slow_haiku(st: Subtask) -> Subtask:
            nonlocal call_count
            await asyncio.sleep(0.05)  # simulate 50ms per file
            call_count += 1
            st.result = "ok"
            return st

        with (
            patch.object(swarm, "_call_haiku", side_effect=slow_haiku),
            patch.object(
                swarm, "_ollama_generate", new_callable=AsyncMock, return_value="sum"
            ),
            patch.object(
                swarm, "_call_sonnet", new_callable=AsyncMock, return_value="baseline"
            ),
            patch.object(
                swarm, "_validate", new_callable=AsyncMock, return_value=("v", 10, 5)
            ),
        ):
            t0 = time.monotonic()
            result = await swarm.run("review", target_files=files)
            elapsed = time.monotonic() - t0

        # 4 files × 50ms sequential = 200ms; parallel should be ~50ms
        assert elapsed < 0.15, f"Expected < 150ms parallel, got {elapsed*1000:.0f}ms"
        assert call_count == len(files)


# ── Benchmark: cost comparison ────────────────────────────────────────────────


class TestCostComparison:
    def test_haiku_swarm_cheaper_than_sonnet(self):
        """For equivalent token volume, Haiku swarm costs ~80% less than Sonnet."""
        tokens_in, tokens_out = 500_000, 200_000

        haiku_cost = tokens_in / 1e6 * 0.80 + tokens_out / 1e6 * 4.00
        sonnet_cost = tokens_in / 1e6 * 3.00 + tokens_out / 1e6 * 15.00
        savings = (1 - haiku_cost / sonnet_cost) * 100

        assert savings > 70, f"Expected >70% savings, got {savings:.1f}%"
        print(
            f"\nHaiku: ${haiku_cost:.3f} | Sonnet: ${sonnet_cost:.3f} | Savings: {savings:.1f}%"
        )
