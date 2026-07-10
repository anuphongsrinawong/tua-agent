"""Dhamma-inspired agent engineering layer for Tau.

This module is an *optional* companion to the core agent loop. It reinterprets
ten Buddhist principles (ธรรมะ) as concrete, well-typed agent-engineering
patterns:

* **สติ** (Sati / Mindfulness)        -> state tracking
* **มัชฌิมาปฏิปทา** (Middle Way)        -> balanced retry policy
* **อนิจจัง** (Impermanence)           -> graceful degradation
* **โยนิโสมนสิการ** (Systematic Attention) -> think before acting
* **สัมมาวายามะ** (Right Effort)        -> quality guardrails
* **อิทัปปัจจยตา** (Dependent Origination) -> causal tracing
* **ขันติ** (Patience)                 -> patient execution
* **เมตตา + กรุณา** (Loving-kindness + Compassion) -> helpful output
* **วิมุตติ** (Non-attachment)         -> adaptive strategy
* **กุศล / อกุศล** (Skillful / Unskillful) -> context judgment

Nothing here is imported by the agent loop unless a caller explicitly opts in by
passing a :class:`DhammaConfig`. See ``dev-notes/dhamma-principles.md`` for the
full principle-to-pattern mapping.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, TypeVar

from tau_agent.tools import ToolCall

__all__ = [
    "AdaptiveStrategy",
    "AgentStateTracker",
    "BalancedRetryPolicy",
    "BeneficialOutput",
    "CausalLog",
    "CausalTrace",
    "ContextFactors",
    "ContextJudgment",
    "DhammaConfig",
    "ErrorCategory",
    "Expertise",
    "GracefulDegradation",
    "GuardResult",
    "PatientExecutor",
    "QualityGuard",
    "ReasonBeforeAct",
    "RetryDecision",
    "ToolAvailability",
    "ToolCallValidation",
    "Urgency",
]


# ``T`` is the result type of a wrapped coroutine.
T = TypeVar("T")

# PEP 695 aliases shared by the context-judgment component.
type Expertise = Literal["beginner", "intermediate", "expert"]
type Urgency = Literal["low", "medium", "high"]

# Tools whose successful use counts as "having looked before acting".
_READ_ONLY_TOOLS: frozenset[str] = frozenset({"read", "grep", "find", "ls"})


# --------------------------------------------------------------------------- #
# 1.1 สติ (Sati / Mindfulness) — AgentStateTracker                            #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class AgentStateTracker:
    """สติ (Sati / Mindfulness): live awareness of the agent's own state.

    The loop records turns, tool calls, token usage and errors here so the
    agent can notice when it is stuck, over budget, or failing repeatedly.
    """

    max_tokens: int | None = None
    max_error_rate: float = 0.5
    no_progress_turns_limit: int = 3
    token_reserve_fraction: float = 0.1

    _turn_count: int = 0
    _tools_called: list[str] = field(default_factory=list)
    _tokens_used: int = 0
    _error_count: int = 0
    _turns_since_progress: int = 0
    _last_tool: str | None = None
    _last_tool_ok: bool = True
    _last_tool_repeats: int = 0
    _has_recent_read: bool = False
    _start_time: float = field(default_factory=time.monotonic)

    # -- recording -------------------------------------------------------- #
    def record_turn(self) -> None:
        """Advance the turn counter (a turn with no progress is stagnant)."""
        self._turn_count += 1
        self._turns_since_progress += 1

    def record_progress(self) -> None:
        """Mark that meaningful progress happened this turn."""
        self._turns_since_progress = 0

    def record_tokens(self, tokens: int) -> None:
        """Accumulate an estimated token usage figure."""
        if tokens > 0:
            self._tokens_used += tokens

    def record_tool_call(self, name: str, *, ok: bool = True) -> None:
        """Record a tool call and its outcome, updating derived awareness."""
        self._tools_called.append(name)
        if name == self._last_tool:
            self._last_tool_repeats += 1
        else:
            self._last_tool = name
            self._last_tool_repeats = 1
        self._last_tool_ok = ok
        if not ok:
            self._error_count += 1
        if ok and name in _READ_ONLY_TOOLS:
            self._has_recent_read = True

    # -- read-only views -------------------------------------------------- #
    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def tool_call_count(self) -> int:
        return len(self._tools_called)

    @property
    def tokens_used(self) -> int:
        return self._tokens_used

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def error_rate(self) -> float:
        """Fraction of recorded tool calls that failed."""
        if not self._tools_called:
            return 0.0
        return self._error_count / len(self._tools_called)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def last_tool(self) -> str | None:
        return self._last_tool

    @property
    def last_tool_ok(self) -> bool:
        return self._last_tool_ok

    @property
    def has_recent_read(self) -> bool:
        return self._has_recent_read

    # -- awareness -------------------------------------------------------- #
    def detect_loop(self) -> bool:
        """True when the agent looks stuck (repetition or stagnation)."""
        repeated = self._last_tool_repeats >= 3
        stagnant = self._turns_since_progress >= self.no_progress_turns_limit
        return repeated or stagnant

    def should_pause(self) -> bool:
        """True when token budget is nearly spent or errors dominate."""
        if self.max_tokens is not None:
            limit = self.max_tokens * (1.0 - self.token_reserve_fraction)
            if self._tokens_used >= limit:
                return True
        return self.error_rate > self.max_error_rate

    def status_report(self) -> str:
        """Compact one-line summary of the agent's current state."""
        budget = (
            f"{self._tokens_used}/{self.max_tokens}"
            if self.max_tokens is not None
            else str(self._tokens_used)
        )
        return (
            f"turn={self._turn_count} tools={len(self._tools_called)} "
            f"tokens={budget} errors={self._error_count} "
            f"elapsed={self.elapsed_seconds:.1f}s"
        )


# --------------------------------------------------------------------------- #
# 1.2 มัชฌิมาปฏิปทา (Middle Way) — BalancedRetryPolicy                       #
# --------------------------------------------------------------------------- #


class ErrorCategory(StrEnum):
    """How retryable an error is, between the extremes of panic and denial."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Outcome of a retry consultation: whether, how long to wait, and why."""

    retry: bool
    delay_seconds: float
    reason: str


_TRANSIENT_HINTS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "connection",
    "connect",
    "reset",
    "temporar",
    "throttl",
    "network",
    "unavailable",
    "busy",
    "again",
    "retry",
)
_PERMANENT_HINTS: tuple[str, ...] = (
    "auth",
    "unauthor",
    "forbidden",
    "permission",
    "invalid",
    "not found",
    "no such",
    "401",
    "403",
    "404",
    "422",
    "denied",
    "unsupported",
)
_AMBIGUOUS_HINTS: tuple[str, ...] = (
    "500",
    "502",
    "503",
    "504",
    "internal",
    "server",
    "unknown",
    "unexpected",
    "5xx",
)


@dataclass(slots=True)
class BalancedRetryPolicy:
    """มัชฌิมาปฏิปทา (Middle Way): retry, but never veer into either extreme.

    Avoids the extreme of giving up immediately *and* the extreme of retrying
    forever. Transient errors are retried, permanent errors are not, and
    ambiguous errors are retried with caution.
    """

    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0

    def categorize(self, error_type: str) -> ErrorCategory:
        """Classify an error message into a retry category."""
        lowered = error_type.lower()
        if any(hint in lowered for hint in _PERMANENT_HINTS):
            return ErrorCategory.PERMANENT
        if any(hint in lowered for hint in _TRANSIENT_HINTS):
            return ErrorCategory.TRANSIENT
        if any(hint in lowered for hint in _AMBIGUOUS_HINTS):
            return ErrorCategory.AMBIGUOUS
        # Unknown errors default to the cautious middle path.
        return ErrorCategory.AMBIGUOUS

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff delay for a 1-indexed ``attempt``, capped."""
        exponent = self.backoff_factor ** max(0, attempt - 1)
        return min(self.max_delay, self.base_delay * exponent)

    def should_retry(self, error_type: str, attempt: int) -> RetryDecision:
        """Decide whether to retry after ``attempt`` failed with ``error_type``."""
        category = self.categorize(error_type)
        if attempt >= self.max_retries:
            return RetryDecision(False, 0.0, f"reached max_retries={self.max_retries}")
        if category is ErrorCategory.PERMANENT:
            return RetryDecision(False, 0.0, "permanent error — not retryable")
        if category is ErrorCategory.TRANSIENT:
            return RetryDecision(True, self.delay_for(attempt), "transient error — retrying")
        return RetryDecision(
            True, self.delay_for(attempt), "ambiguous error — retrying with caution"
        )


# --------------------------------------------------------------------------- #
# 1.3 อนิจจัง (Impermanence) — GracefulDegradation                            #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ToolAvailability:
    """Registry tracking which tools have been succeeding or failing lately."""

    failure_threshold: int = 3
    _failures: dict[str, int] = field(default_factory=dict)
    _successes: dict[str, int] = field(default_factory=dict)

    def record_success(self, tool_name: str) -> None:
        """A success clears recent failures for the tool."""
        self._successes[tool_name] = self._successes.get(tool_name, 0) + 1
        self._failures.pop(tool_name, None)

    def record_failure(self, tool_name: str) -> None:
        """A failure bumps the recent failure count for the tool."""
        self._failures[tool_name] = self._failures.get(tool_name, 0) + 1
        self._successes.pop(tool_name, None)

    def failure_count(self, tool_name: str) -> int:
        return self._failures.get(tool_name, 0)

    def is_available(self, tool_name: str) -> bool:
        """A tool is available while its recent failures stay under threshold."""
        return self.failure_count(tool_name) < self.failure_threshold

    def failed_tools(self) -> list[str]:
        return list(self._failures)

    def reset(self, tool_name: str) -> None:
        """Forget the recent history for a single tool."""
        self._failures.pop(tool_name, None)
        self._successes.pop(tool_name, None)


_DEFAULT_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "read": ("grep", "find", "ls"),
    "grep": ("find", "bash"),
    "find": ("grep", "bash"),
    "ls": ("find", "bash"),
    "bash": ("read", "grep"),
    "write": ("edit",),
    "edit": ("write",),
    "web_fetch": ("web_search",),
    "web_search": ("web_fetch",),
}


@dataclass(slots=True)
class GracefulDegradation:
    """อนิจจัง (Impermanence): keep working as tools and conditions change."""

    availability: ToolAvailability = field(default_factory=ToolAvailability)
    alternatives: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(_DEFAULT_ALTERNATIVES)
    )

    def degraded_tools(self) -> list[str]:
        """Tools that should be skipped because they keep failing."""
        return [
            name
            for name in self.availability.failed_tools()
            if not self.availability.is_available(name)
        ]

    def suggest_alternative(self, failed_tool_name: str) -> tuple[str, ...]:
        """Suggest alternative tools for one that has become unreliable."""
        return self.alternatives.get(failed_tool_name, ())

    async def with_timeout(self, coro: Coroutine[Any, Any, T], seconds: float) -> T:
        """Run ``coro`` with a hard deadline, raising ``TimeoutError`` if exceeded."""
        return await asyncio.wait_for(coro, timeout=seconds)


# --------------------------------------------------------------------------- #
# 1.4 โยนิโสมนสิการ (Systematic Attention) — ReasonBeforeAct                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ToolCallValidation:
    """Result of sanity-checking a tool call before executing it."""

    valid: bool
    reason: str


_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({"write", "edit", "bash", "delete", "rm"})
_BASE_UTILITY: dict[str, float] = {
    "read": 0.9,
    "grep": 0.9,
    "find": 0.85,
    "ls": 0.9,
    "edit": 0.7,
    "write": 0.6,
    "bash": 0.6,
}


@dataclass(slots=True)
class ReasonBeforeAct:
    """โยนิโสมนสิการ (Systematic Attention): reason about a tool call first."""

    def validate_tool_call(
        self, tool_call: ToolCall, state: AgentStateTracker
    ) -> ToolCallValidation:
        """Reject tool calls that don't make sense given the current state."""
        name = tool_call.name
        if name in {"write", "edit"} and not state.has_recent_read:
            return ToolCallValidation(
                False, "write/edit before any successful read — verify the target first"
            )
        if name == state.last_tool and not state.last_tool_ok:
            return ToolCallValidation(
                False, f"repeating '{name}' which just failed — change approach"
            )
        return ToolCallValidation(True, "ok")

    def pre_tool_checklist(self, tool_call: ToolCall) -> list[str]:
        """Verification questions the agent should consider before acting."""
        name = tool_call.name
        if name in {"write", "edit"}:
            return [
                "Have I read the target file recently?",
                "Am I overwriting unsaved or shared work?",
                "Is the target path correct?",
            ]
        if name == "bash":
            return [
                "Is this command reversible?",
                "Could it affect files outside the current scope?",
                "Do I understand every flag in this command?",
            ]
        if name in {"read", "grep", "find"}:
            return ["Is the path or pattern specific enough?", "Does this advance the goal?"]
        return ["Does this tool call advance the current goal?"]

    def cost_benefit_heuristic(self, tool_call: ToolCall, state: AgentStateTracker) -> float:
        """Score a tool call 0..1 for whether it is worth the tokens."""
        name = tool_call.name
        score = _BASE_UTILITY.get(name, 0.7)
        if name == state.last_tool:
            score -= 0.3  # diminishing returns from repetition
        if name in _DESTRUCTIVE_TOOLS and not state.has_recent_read:
            score -= 0.25  # acting blind is risky
        return max(0.0, min(1.0, score))


# --------------------------------------------------------------------------- #
# 1.5 สัมมาวายามะ (Right Effort) — QualityGuard                              #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class GuardResult:
    """Outcome of a quality / safety check."""

    safe: bool
    reason: str
    severity: Literal["ok", "warning", "danger"] = "ok"


_DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-\w*[rf]\w*\s+(/|~|\*|\.(?:\s|$))"),
    re.compile(r"\bdrop\s+(table|database|schema)\b", re.IGNORECASE),
    re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=.*of=/dev/(sd|nvme|hd)"),
    re.compile(r">\s*/dev/(sd|nvme|hd)"),
    re.compile(r"\bchmod\s+-R\s+777\s+/"),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:\}"),  # fork bomb
    re.compile(r"\bgit\s+push\s+(-f|--force)\b", re.IGNORECASE),
    re.compile(r"\b(shutdown|reboot|halt)\b", re.IGNORECASE),
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style key
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),  # GitHub token
)

_PLACEHOLDER_PATH = re.compile(r"/?(?:path|file)/to/|<your[_ -]?path>|your_(?:path|file)_here")


def _looks_like_loop(text: str) -> bool:
    """Heuristic: the same non-empty line repeated many times (loop signature)."""
    lines = text.splitlines()
    if len(lines) < 6:
        return False
    counts: dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if stripped:
            counts[stripped] = counts.get(stripped, 0) + 1
    return bool(counts) and max(counts.values()) >= 6


@dataclass(slots=True)
class QualityGuard:
    """สัมมาวายามะ (Right Effort): prevent errors and harm before they happen."""

    def validate_input(self, user_message: str) -> GuardResult:
        """Reject dangerous or invalid user input before it reaches the agent."""
        if "\x00" in user_message:
            return GuardResult(False, "null byte in input", "danger")
        for pattern in _DESTRUCTIVE_PATTERNS:
            if pattern.search(user_message):
                return GuardResult(False, "destructive pattern in user input", "danger")
        return GuardResult(True, "input accepted", "ok")

    def validate_output(self, assistant_message: str) -> GuardResult:
        """Flag low-quality output: leaked secrets, placeholders, or loops."""
        for pattern in _SECRET_PATTERNS:
            if pattern.search(assistant_message):
                return GuardResult(False, "possible secret leaked in output", "danger")
        if _PLACEHOLDER_PATH.search(assistant_message):
            return GuardResult(False, "output contains a placeholder path", "warning")
        if _looks_like_loop(assistant_message):
            return GuardResult(False, "output repeats the same line (possible loop)", "warning")
        return GuardResult(True, "output accepted", "ok")

    def guardrail_check(self, action: str) -> GuardResult:
        """Safety check before a destructive operation."""
        for pattern in _DESTRUCTIVE_PATTERNS:
            if pattern.search(action):
                return GuardResult(False, f"destructive action blocked: {action.strip()}", "danger")
        return GuardResult(True, "action within guardrails", "ok")


# --------------------------------------------------------------------------- #
# 1.6 อิทัปปัจจยตา (Dependent Origination) — CausalTrace                     #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class CausalLog:
    """อิทัปปัจจยตา (Dependent Origination): one link in a cause -> effect chain."""

    turn: int
    trigger: str
    action: str
    result: str
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class CausalTrace:
    """Record and replay the chain of causes behind every output."""

    _entries: list[CausalLog] = field(default_factory=list)

    def log_cause(self, turn: int, trigger: str, action: str, result: str) -> CausalLog:
        """Append a cause -> effect link and return it."""
        entry = CausalLog(turn=turn, trigger=trigger, action=action, result=result)
        self._entries.append(entry)
        return entry

    @property
    def entries(self) -> list[CausalLog]:
        """A defensive copy of the recorded causal links."""
        return list(self._entries)

    def traceback_decision(self, result: str) -> list[CausalLog]:
        """Trace what caused a result: each match preceded by its immediate cause."""
        chain: list[CausalLog] = []
        for index, entry in enumerate(self._entries):
            if result not in entry.result:
                continue
            if index > 0 and self._entries[index - 1] not in chain:
                chain.append(self._entries[index - 1])
            chain.append(entry)
        return chain

    def format_causal_chain(self) -> str:
        """Pretty-print the full causal chain for debugging."""
        if not self._entries:
            return "(no causal history yet)"
        lines = ["causal chain:"]
        for entry in self._entries:
            lines.append(
                f"  turn {entry.turn}: {entry.trigger} -> {entry.action} -> {entry.result}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 1.7 ขันติ (Patience) — PatientExecutor                                      #
# --------------------------------------------------------------------------- #


_SLOW_TOOL_HINTS: frozenset[str] = frozenset(
    {
        "bash",
        "build",
        "make",
        "test",
        "pytest",
        "npm",
        "pnpm",
        "yarn",
        "pip",
        "uv",
        "cargo",
        "docker",
        "compile",
    }
)


@dataclass(slots=True)
class PatientExecutor:
    """ขันติ (Patience): wait well and report progress while waiting."""

    slow_tools: frozenset[str] = field(default_factory=lambda: frozenset(_SLOW_TOOL_HINTS))
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    progress_interval: float = 1.0

    def is_long_running(self, tool_name: str) -> bool:
        """True for tools known to be slow (builds, large file ops, installs)."""
        return tool_name in self.slow_tools

    def wait_with_backoff(self, attempt: int) -> float:
        """Increasing wait for a 1-indexed ``attempt``, capped at ``max_delay``."""
        exponent = self.backoff_factor ** max(0, attempt - 1)
        return min(self.max_delay, self.base_delay * exponent)

    async def wait_with_backoff_async(self, attempt: int) -> float:
        """Sleep for the backoff delay and return how long we waited."""
        delay = self.wait_with_backoff(attempt)
        await asyncio.sleep(delay)
        return delay

    async def execute_with_patience(
        self,
        coro: Coroutine[Any, Any, T],
        progress_callback: Callable[[float], None] | None = None,
    ) -> T:
        """Run ``coro`` to completion, emitting periodic progress updates."""
        task = asyncio.ensure_future(coro)
        elapsed = 0.0
        try:
            while True:
                done, _pending = await asyncio.wait({task}, timeout=self.progress_interval)
                if done:
                    return task.result()
                elapsed += self.progress_interval
                if progress_callback is not None:
                    progress_callback(elapsed)
        except BaseException:
            if not task.done():
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
            raise


# --------------------------------------------------------------------------- #
# 1.8 เมตตา + กรุณา (Loving-kindness + Compassion) — BeneficialOutput        #
# --------------------------------------------------------------------------- #


def _error_suggestion(message: str) -> str:
    """Pick an actionable fix hint based on keywords in the error message."""
    lowered = message.lower()
    if "filenotfound" in lowered or "no such file" in lowered:
        return "Check that the path exists and is relative to the working directory."
    if "timeout" in lowered or "timed out" in lowered:
        return "Retry after a short wait, or reduce the size of the request."
    if "permission" in lowered or "denied" in lowered or "forbidden" in lowered:
        return "Check file permissions or credentials."
    if "syntax" in lowered:
        return "Review the syntax near the reported location."
    if "import" in lowered or "modulenotfound" in lowered:
        return "Check that the dependency is installed and the import path is correct."
    return "Inspect the inputs and retry; if it persists, try a smaller step."


@dataclass(slots=True)
class BeneficialOutput:
    """เมตตา + กรุณา (Loving-kindness + Compassion): make output helpful and kind."""

    guard: QualityGuard = field(default_factory=QualityGuard)

    def format_error_helpfully(self, error: str | BaseException, context: str = "") -> str:
        """Turn a raw error into a clear message with an actionable fix."""
        message = str(error).strip() or "an unexpected error occurred"
        parts = [f"What happened: {message}"]
        if context.strip():
            parts.append(f"Context: {context.strip()}")
        parts.append(f"Likely cause / fix: {_error_suggestion(message)}")
        return "\n".join(parts)

    def suggest_next_steps(self, state: AgentStateTracker) -> list[str]:
        """After trouble, suggest concrete things to try next."""
        steps: list[str] = []
        if state.detect_loop():
            steps.append("You appear stuck in a loop — try a different tool or restate the goal.")
        if state.should_pause():
            steps.append("Budget or error limits are close — pause, summarize, and reconsider.")
        if state.error_count > 0:
            steps.append("Recent errors occurred — re-read the inputs and verify assumptions.")
        if not steps:
            steps.append("Continue with the next concrete step toward the goal.")
        return steps

    def check_harmful_output(self, text: str) -> bool:
        """True if the text contains secrets, placeholders, or loop-like output."""
        return not self.guard.validate_output(text).safe

    def summarize_for_human(self, technical_output: str) -> str:
        """Make a technical blob accessible to a non-expert reader."""
        if "Traceback (most recent call last)" in technical_output:
            last_line = technical_output.strip().splitlines()[-1]
            return f"Something went wrong: {last_line}"
        for line in technical_output.strip().splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:280]
        return ""


# --------------------------------------------------------------------------- #
# 1.9 วิมุตติ (Non-attachment) — AdaptiveStrategy                            #
# --------------------------------------------------------------------------- #


_STRATEGIES: dict[str, tuple[str, ...]] = {
    "debug": (
        "read_logs",
        "reproduce_minimally",
        "bisect_history",
        "add_logging",
        "isolate_component",
    ),
    "refactor": ("extract_function", "inline", "rename", "introduce_abstraction", "rewrite"),
    "test": ("write_unit_tests", "write_integration_tests", "property_tests", "snapshot_tests"),
    "explore": ("grep", "read", "find", "ask_user"),
    "build": ("clean_build", "incremental_build", "fix_imports", "downgrade_dep"),
    "default": ("restate_goal", "gather_context", "make_a_small_change", "verify"),
}


@dataclass(slots=True)
class AdaptiveStrategy:
    """วิมุตติ (Non-attachment): let go of a strategy that isn't working."""

    failure_threshold: int = 3
    stagnation_turns: int = 5
    _history: dict[str, list[bool]] = field(default_factory=dict)

    def should_change_approach(self, failure_count: int, elapsed_turns: int) -> bool:
        """True when enough has failed or enough time has passed without progress."""
        return failure_count >= self.failure_threshold or elapsed_turns >= self.stagnation_turns

    def available_strategies(self, task_type: str) -> list[str]:
        """Alternative approaches available for a kind of task."""
        return list(_STRATEGIES.get(task_type, _STRATEGIES["default"]))

    def record_attempt(self, strategy: str, outcome: bool) -> None:
        """Log whether a strategy attempt succeeded, for future decisions."""
        self._history.setdefault(strategy, []).append(outcome)

    def success_rate(self, strategy: str) -> float:
        """Observed success rate of a strategy (0.0 if never tried)."""
        outcomes = self._history.get(strategy)
        if not outcomes:
            return 0.0
        return sum(1 for ok in outcomes if ok) / len(outcomes)

    def best_strategy(self, task_type: str) -> str | None:
        """Most successful tried strategy for a task type, or ``None`` if none tried."""
        tried = [name for name in self.available_strategies(task_type) if name in self._history]
        if not tried:
            return None
        return max(tried, key=lambda name: (self.success_rate(name), -len(self._history[name])))


# --------------------------------------------------------------------------- #
# 1.10 กุศล / อกุศล (Skillful / Unskillful) — ContextJudgment                #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ContextFactors:
    """กุศล / อกุศล context inputs that shape a skillful judgment."""

    project_type: str = "unknown"
    user_expertise: Expertise = "intermediate"
    time_pressure: Urgency = "medium"
    risk_level: Urgency = "medium"

    def as_dict(self) -> dict[str, str]:
        return {
            "project_type": self.project_type,
            "user_expertise": self.user_expertise,
            "time_pressure": self.time_pressure,
            "risk_level": self.risk_level,
        }


@dataclass(slots=True)
class ContextJudgment:
    """กุศล / อกุศล (Skillful / Unskillful): choose what the situation calls for."""

    factors: ContextFactors = field(default_factory=ContextFactors)

    def context_factors(self) -> dict[str, str]:
        """Return the current context factors as a plain dict."""
        return self.factors.as_dict()

    def is_skillful_action(self, tool_name: str, context: ContextFactors | None = None) -> bool:
        """True when ``tool_name`` is appropriate for the (given or default) context."""
        ctx = context if context is not None else self.factors
        if tool_name in {"bash", "write", "edit"} and ctx.risk_level == "high":
            return False
        return not (tool_name == "bash" and ctx.user_expertise == "beginner")

    def recommend_approach(self, goal: str, context: ContextFactors | None = None) -> str:
        """Recommend the most skillful approach for a goal under some context."""
        ctx = context if context is not None else self.factors
        parts: list[str] = []
        if ctx.risk_level == "high":
            parts.append("make a backup or branch first, then prefer reversible read-only steps")
        if ctx.user_expertise == "beginner":
            parts.append("explain each step and prefer safe read-only tools before any change")
        if ctx.time_pressure == "high":
            parts.append("take the fastest reliable path and skip deep exploration")
        if not parts:
            parts.append("gather a little context, make a small reversible change, then verify")
        prefix = f"For the goal '{goal.strip()}': " if goal.strip() else "Recommended approach: "
        return prefix + "; ".join(parts) + "."


# --------------------------------------------------------------------------- #
# Configuration                                                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DhammaConfig:
    """Opt-in flags for the dhamma agent layer.

    Every flag defaults to a safe, non-intrusive value. Passing a
    :class:`DhammaConfig` to :func:`tau_agent.loop.run_agent_loop` activates the
    enabled principles; passing ``None`` leaves the loop untouched and identical
    to plain Tau.
    """

    # Observation-only — never alter control flow.
    enable_mindfulness: bool = True  # สติ — AgentStateTracker
    enable_causal_trace: bool = True  # อิทัปปัจจยตา — CausalTrace
    enable_non_attachment: bool = True  # วิมุตติ — AdaptiveStrategy (advisory)
    enable_beneficial_output: bool = True  # เมตตา+กรุณา — error formatting
    # Advisory helpers.
    enable_middle_way: bool = False  # มัชฌิมาปฏิปทา — retry classification
    enable_impermanence: bool = False  # อนิจจัง — tool availability tracking
    # Active gates — opt-in, these can change control flow.
    enable_systematic_attention: bool = False  # โยนิโสมนสิการ — validate before acting
    enable_right_effort: bool = False  # สัมมาวายามะ — input/output guardrails
    enable_patience: bool = False  # ขันติ — patient execution
    enable_context_judgment: bool = False  # กุศล/อกุศล — context-aware choice
    enable_iddhipada: bool = False  # อิทธิบาท 4 — readiness tracking (จะ+วิริยะ+จิตตะ+วิมังสา)

    token_budget: int | None = None
    retry_policy: BalancedRetryPolicy = field(default_factory=BalancedRetryPolicy)
