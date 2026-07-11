"""Tua Agent intelligence layer (v0.0.2 Phase 2: #13 / #16 / #18 / #19).

Wraps a ``CodingSession`` run with Rust-aware post-turn intelligence that the
generic ``tau_agent`` harness intentionally does not know about:

* **#13 self-correction** — after the agent edits a ``.rs`` file, run
  ``cargo check`` and, on failure, feed the compiler errors back to the agent as
  a fresh user turn so it fixes its own mistakes before reporting completion.
  Capped at ``max_self_corrections`` turns to prevent infinite loops.
* **#16 checkpointing** — once the build is green, snapshot the working tree with
  a git "checkpoint" commit so ``/rollback`` can undo a whole turn.
* **#18 prompt caching** — report the size of the stable cacheable prefix so UIs
  can show cache savings (providers with automatic prefix caching benefit from a
  stable system + tools + static-context prefix).
* **#19 multi-agent review** — run ``cargo clippy`` plus cheap anti-pattern
  checks over the edited files and collect the findings for the UI to render.

The cargo/clippy mechanics live in ``tau_agent.harness`` (the ``default_*``
helpers); this module owns the *orchestration* around a session run, keeping the
upstream library generic. Pure Rust engineering — no Dhamma / philosophy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tau_agent.events import AgentEvent
from tau_agent.harness import (
    CargoCheckResult,
    ReviewFinding,
    default_cargo_check,
    default_detect_rust_edits,
    default_review_edits,
)

from tua_agent.checkpoint import checkpoint as git_checkpoint
from tua_agent.config import TuaConfig


@dataclass(slots=True)
class IntelligenceReport:
    """Outcome of one intelligence-augmented agent turn."""

    corrections_made: int = 0
    checkpoint: str | None = None
    review_findings: list[ReviewFinding] = field(default_factory=list)
    cache_prefix_messages: int = 0

    @property
    def review_error_count(self) -> int:
        """Number of error-severity review findings."""
        return sum(1 for f in self.review_findings if f.severity == "error")

    @property
    def review_warning_count(self) -> int:
        """Number of warning-severity review findings."""
        return sum(1 for f in self.review_findings if f.severity == "warning")


def _cwd_str(cwd: Path | str | None) -> str | None:
    """Normalize a cwd value to the ``str | None`` the subprocess helpers expect."""
    return str(cwd) if cwd is not None else None


def correction_text(result: CargoCheckResult, attempt: int, max_attempts: int) -> str:
    """Build the self-correction user message that feeds cargo errors back (#13)."""
    return (
        f"cargo check found errors (self-correction {attempt}/{max_attempts}). "
        "Fix every error below, then confirm the build is green before finishing:\n\n"
        f"{result.output}"
    )


async def drive_agent_with_intelligence(
    *,
    session: Any,
    prompt_text: str,
    config: TuaConfig,
    cwd: Path | str | None = None,
    render_event: Callable[[AgentEvent], None] | None = None,
) -> IntelligenceReport:
    """Run one user turn, then apply the #13/#16/#18/#19 intelligence hooks.

    Streams the session's events through ``render_event`` (when given). After the
    agent settles, returns an :class:`IntelligenceReport` describing the
    self-correction turns taken, any checkpoint created, and the review findings.

    With every intelligence feature disabled this is equivalent to a single
    ``session.prompt(prompt_text)`` call — it never runs cargo/git/clippy.
    """
    report = IntelligenceReport()
    cwd_s = _cwd_str(cwd)
    original_start = len(session.messages)

    # #18 — the cacheable prefix is the stable history that precedes this turn.
    if config.prompt_caching:
        report.cache_prefix_messages = original_start

    corrections = 0
    last_check: CargoCheckResult | None = None
    next_prompt: str | None = prompt_text
    while True:
        run_start = len(session.messages)
        async for event in session.prompt(next_prompt):
            if render_event is not None:
                render_event(event)
        next_prompt = None

        edited_this_run = default_detect_rust_edits(session.messages, run_start)

        # #13 — only self-correct when .rs files actually changed this run.
        if not (config.self_correction and edited_this_run):
            break
        last_check = default_cargo_check(cwd_s)
        if last_check.ok or not last_check.output:
            break
        if corrections >= config.max_self_corrections:
            break
        corrections += 1
        next_prompt = correction_text(last_check, corrections, config.max_self_corrections)

    report.corrections_made = corrections

    edited_any = bool(default_detect_rust_edits(session.messages, original_start))

    # #16 — snapshot a checkpoint once the build is green.
    if config.checkpoint_enabled and edited_any:
        if last_check is None:
            last_check = default_cargo_check(cwd_s)
        if last_check.ok:
            try:
                report.checkpoint = git_checkpoint(cwd=cwd_s)
            except Exception:  # noqa: BLE001 - checkpointing must never break a run
                report.checkpoint = None

    # #19 — review the settled code (clippy + heuristic anti-pattern checks).
    if config.review_enabled and edited_any:
        try:
            report.review_findings = default_review_edits(
                session.messages, original_start, cwd=cwd_s
            )
        except Exception:  # noqa: BLE001 - review is best-effort
            report.review_findings = []

    return report
