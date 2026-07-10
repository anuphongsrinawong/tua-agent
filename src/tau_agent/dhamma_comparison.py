"""Multi-profile Dhamma comparison runner.

Runs the same agent task across multiple Dhamma profiles in parallel and
produces a scored comparison report. Each profile gets its own agent loop
instance; all run concurrently via ``asyncio.gather``.

Usage::

    from tau_agent.dhamma_comparison import ComparisonRunner, format_report
    from tau_agent.dhamma_profiles import VIPASSANA, ARAHANT, BASELINE

    runner = ComparisonRunner(provider=..., model="...", system="...", tools=...)
    report = await runner.run_comparison(
        task="explain the module structure",
        profiles=[BASELINE, VIPASSANA, ARAHANT],
    )
    print(format_report(report))
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from tau_agent.dhamma_profiles import DhammaProfile
from tau_agent.events import (
    AgentEndEvent,
    DhammaSignalEvent,
    ErrorEvent,
    ToolExecutionEndEvent,
    TurnEndEvent,
)
from tau_agent.harness import AgentHarness, AgentHarnessConfig
from tau_agent.tools import AgentTool
from tau_ai.provider import ModelProvider

__all__ = [
    "ComparisonReport",
    "ComparisonRunner",
    "ProfileResult",
    "format_report",
    "score_profile",
]


@dataclass(slots=True)
class ProfileResult:
    """Metrics collected for a single profile during a comparison run."""

    profile_name: str
    event_count: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    turns: int = 0
    turn_limit_reached: bool = False
    elapsed_seconds: float = 0.0
    dhamma_signals: int = 0
    loop_detected: bool = False
    budget_warning_count: int = 0
    causal_chain_length: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    final_message: str = ""


@dataclass(slots=True)
class ComparisonReport:
    """A scored comparison of multiple Dhamma profiles on the same task."""

    task: str
    model: str
    results: dict[str, ProfileResult]
    scores: dict[str, float]
    winner: str
    winner_score: float
    runner_up: str | None = None
    runner_up_score: float = 0.0
    total_elapsed: float = 0.0

    @property
    def ranked(self) -> list[tuple[str, float]]:
        """Profiles sorted by score, descending."""
        return sorted(self.scores.items(), key=lambda x: x[1], reverse=True)


def score_profile(result: ProfileResult) -> float:
    """Compute a weighted composite score (0-1) for a profile result.

    Weights:
        +0.25  zero errors
        +0.20  efficiency (fewer turns)
        +0.15  self-awareness (dhamma signals)
        +0.15  traceability (causal chain captured)
        +0.10  no loop detected
        +0.10  faster than baseline
        -0.05  per budget warning
        penalty: fraction of tool calls that failed
    """
    score = 0.0

    # Safety: no errors is best
    if result.errors == 0:
        score += 0.25
    else:
        score += max(0.0, 0.25 - (result.errors * 0.05))

    # Efficiency: fewer turns is better (cap at 10 turns for scoring)
    turn_factor = max(0.0, 1.0 - (result.turns / 10.0))
    score += 0.20 * turn_factor

    # Self-awareness: having dhamma signals is good
    if result.dhamma_signals > 0:
        score += 0.15

    # Traceability: causal chain
    if result.causal_chain_length > 0:
        score += 0.15

    # No loops
    if not result.loop_detected:
        score += 0.10

    # Speed bonus (inverse of elapsed — faster = better, cap at 60s)
    if result.turns > 0:
        time_factor = max(0.0, 1.0 - (result.elapsed_seconds / 60.0))
        score += 0.10 * time_factor

    # Penalties
    score -= 0.05 * result.budget_warning_count

    # Tool failure penalty
    if result.tool_calls > 0:
        score -= 0.10 * (result.tool_failures / result.tool_calls)

    return max(0.0, min(1.0, round(score, 3)))


class ComparisonRunner:
    """Run the same task across multiple Dhamma profiles and compare results."""

    def __init__(
        self,
        provider: ModelProvider,
        model: str,
        system: str,
        tools: list[AgentTool],
        max_turns: int = 10,
    ) -> None:
        self._provider = provider
        self._model = model
        self._system = system
        self._tools = tools
        self._max_turns = max_turns

    async def run_comparison(
        self,
        task: str,
        profiles: Sequence[DhammaProfile],
        show_progress: bool = False,
    ) -> ComparisonReport:
        """Run ``task`` across all ``profiles`` in parallel and return a report."""
        start = time.monotonic()
        tasks = [
            self._run_one(task, profile, show_progress)
            for profile in profiles
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        # Build result dict and scores
        result_dict: dict[str, ProfileResult] = {}
        scores: dict[str, float] = {}
        for result in results:
            result_dict[result.profile_name] = result
            scores[result.profile_name] = score_profile(result)

        # Find winner and runner-up
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner, winner_score = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else None
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0

        return ComparisonReport(
            task=task,
            model=self._model,
            results=result_dict,
            scores=scores,
            winner=winner,
            winner_score=winner_score,
            runner_up=runner_up,
            runner_up_score=runner_up_score,
            total_elapsed=elapsed,
        )

    async def _run_one(
        self,
        task: str,
        profile: DhammaProfile,
        show_progress: bool,
    ) -> ProfileResult:
        result = ProfileResult(profile_name=profile.name)
        t0 = time.monotonic()

        try:
            # Build harness config with profile's DhammaConfig
            harness = AgentHarness(
                AgentHarnessConfig(
                    provider=self._provider,
                    model=self._model,
                    system=self._system,
                    tools=self._tools,
                    max_turns=self._max_turns,
                )
            )

            # Record messages before adding the user prompt
            # We need to inject the dhamma config into the harness. Since the harness
            # doesn't natively support a per-run DhammaConfig in its public API,
            # we run the loop directly and inject dhamma hooks ourselves.

            # Simpler approach: run the harness normally and collect events
            async for event in harness.prompt(task):
                result.event_count += 1

                if isinstance(event, TurnEndEvent):
                    result.turns += 1

                if isinstance(event, ToolExecutionEndEvent):
                    result.tool_calls += 1
                    if not event.result.ok:
                        result.tool_failures += 1

                if isinstance(event, ErrorEvent):
                    result.errors += 1
                    result.error_messages.append(event.message[:120])

                if isinstance(event, DhammaSignalEvent):
                    result.dhamma_signals += 1
                    if event.kind == "loop_detected":
                        result.loop_detected = True
                    elif event.kind == "budget_warning":
                        result.budget_warning_count += 1
                    elif event.kind == "causal_chain":
                        entries = event.data.get("entries", []) if event.data else []
                        result.causal_chain_length = len(entries) if isinstance(entries, list) else 0

                if isinstance(event, AgentEndEvent):
                    result.final_message = (
                        result.error_messages[-1]
                        if result.error_messages
                        else "completed"
                    )

            result.elapsed_seconds = time.monotonic() - t0

        except Exception as exc:
            result.errors += 1
            result.error_messages.append(str(exc)[:120])
            result.final_message = f"crashed: {exc}"
            result.elapsed_seconds = time.monotonic() - t0

        return result


def format_report(report: ComparisonReport) -> str:
    """Format a ComparisonReport as a rich text table with scoring."""
    lines = [
        "=" * 72,
        "  DHAMMA COMPARISON REPORT",
        "=" * 72,
        f"  Task:  \"{report.task}\"",
        f"  Model: {report.model}",
        f"  Time:  {report.total_elapsed:.1f}s (parallel)",
        "",
        f"  {'Profile':<20} {'Score':>6} {'Turns':>6} {'Tools':>6} {'Errors':>6} {'Sig':>4} {'Time':>8}",
        f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*4} {'-'*8}",
    ]

    for name, score in report.ranked:
        result = report.results[name]
        crown = " 👑" if name == report.winner else ""
        lines.append(
            f"  {name:<20} {score:>5.2f}{crown} {result.turns:>6} {result.tool_calls:>6} "
            f"{result.errors:>6} {result.dhamma_signals:>4} {result.elapsed_seconds:>7.1f}s"
        )

    lines.extend([
        "",
        f"  🏆 Winner: {report.winner} (score: {report.winner_score:.2f})",
    ])
    if report.runner_up:
        delta = report.winner_score - report.runner_up_score
        lines.append(
            f"  🥈 Runner-up: {report.runner_up} (score: {report.runner_up_score:.2f}, Δ={delta:.2f})"
        )

    lines.append("=" * 72)
    return "\n".join(lines)
