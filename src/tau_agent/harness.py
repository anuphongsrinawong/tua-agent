"""Stateful reusable agent harness built on the pure loop."""

from __future__ import annotations

import re
import subprocess
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Literal

from tau_agent.events import AgentEndEvent, AgentEvent, MessageEndEvent, MessageStartEvent, QueueUpdateEvent
from tau_agent.loop import run_agent_loop
from tau_agent.messages import AgentMessage, AssistantMessage, ToolResultMessage, UserMessage
from tau_agent.tools import AgentTool
from tau_ai.provider import ModelProvider

EventListener = Callable[[AgentEvent], Awaitable[None] | None]
QueueMode = Literal["one_at_a_time", "all"]


# ── Self-correction (#13) + multi-agent review (#19) data + defaults ─────────


@dataclass(slots=True)
class CargoCheckResult:
    """Outcome of a `cargo check` run for the self-correction hook (#13)."""

    ok: bool
    output: str


@dataclass(slots=True)
class ReviewFinding:
    """A single finding from the reviewer sub-agent (#19)."""

    severity: str  # "error" | "warning" | "info"
    file: str
    line: int
    message: str


def default_detect_rust_edits(
    messages: Sequence[AgentMessage], since_index: int = 0
) -> list[str]:
    """Return the ``.rs`` paths touched by tool calls since ``since_index``.

    Scans both assistant tool-call requests (their arguments) and tool-result
    messages (their ``data["path"]``) so it works regardless of which provider
    or coding tool made the edit. Duplicates are removed while preserving order.
    """
    seen: set[str] = set()
    paths: list[str] = []
    for message in messages[since_index:]:
        if isinstance(message, AssistantMessage):
            for tool_call in message.tool_calls:
                for value in tool_call.arguments.values():
                    if isinstance(value, str) and value.endswith(".rs"):
                        if value not in seen:
                            seen.add(value)
                            paths.append(value)
        elif isinstance(message, ToolResultMessage):
            data = message.data or {}
            path = data.get("path")
            if isinstance(path, str) and path.endswith(".rs") and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def default_cargo_check(cwd: str | None = None) -> CargoCheckResult:
    """Run ``cargo check`` synchronously and return its pass/fail + output (#13).

    A missing toolchain or a non-Rust directory is treated as *pass* (no errors
    to correct) so the self-correction loop never fires spuriously. The combined
    stdout+stderr is returned so the model can read the compiler diagnostics.
    """
    try:
        process = subprocess.run(  # noqa: S603 - argv is a fixed list
            ["cargo", "check", "--message-format=short"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return CargoCheckResult(ok=True, output="")
    output = f"{process.stdout}{process.stderr}".strip()
    return CargoCheckResult(ok=process.returncode == 0, output=output)


# Clippy short-format lines look like:
#   "src/lib.rs:7:5: error: expected one of ..., found `x`"
#   "src/lib.rs:7:5: warning: ..."  (clippy lints)
_CLIPPY_LINE = re.compile(r"^(.+?):(\d+):(\d+):\s*(error|warning):\s*(.*)$")


def default_review_edits(
    messages: Sequence[AgentMessage],
    since_index: int = 0,
    *,
    cwd: str | None = None,
) -> list[ReviewFinding]:
    """Review the ``.rs`` files edited since ``since_index`` (#19).

    Runs ``cargo clippy`` over the project (best-effort) and layers in a few
    cheap heuristic checks for common Rust anti-patterns (bare ``unwrap``,
    ``todo!``/``unimplemented!``, and ``unsafe`` blocks). Never raises: a missing
    toolchain simply yields the heuristic findings.
    """
    findings: list[ReviewFinding] = []
    edited = default_detect_rust_edits(messages, since_index)

    # ── Clippy (compiler-grade diagnostics) ─────────────────────────────────
    try:
        process = subprocess.run(  # noqa: S603 - fixed argv
            ["cargo", "clippy", "--message-format=short", "--", "-D", "warnings"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
        )
        combined = f"{process.stdout}{process.stderr}"
        for raw in combined.splitlines():
            match = _CLIPPY_LINE.match(raw.strip())
            if not match:
                continue
            file_path, line, _col, severity, message = match.groups()
            findings.append(
                ReviewFinding(
                    severity=severity,
                    file=file_path,
                    line=int(line),
                    message=message,
                )
            )
    except (FileNotFoundError, subprocess.SubprocessError):
        pass  # no toolchain → fall back to heuristics only

    # ── Cheap heuristic checks on the edited files ──────────────────────────
    findings.extend(_heuristic_rust_findings(edited))
    return findings


def _heuristic_rust_findings(paths: Iterable[str]) -> list[ReviewFinding]:
    """Flag obvious Rust anti-patterns (unwrap, todo!, unsafe) by line scan."""
    patterns: tuple[tuple[str, str], ...] = (
        (r"\.unwrap\s*\(", "bare .unwrap() — prefer proper error handling with Result and ?"),
        (r"\.expect\s*\(", "bare .expect() — consider propagating errors with Result and ?"),
        (r"\b(todo|unimplemented|unreachable)!\s*\(", "todo!/unimplemented!/unreachable! left in code"),
        (r"\bunsafe\s+\{", "unsafe block present — document the safety invariant"),
    )
    results: list[ReviewFinding] = []
    for raw_path in paths:
        text = _read_text(raw_path)
        if text is None:
            continue
        for index, line in enumerate(text.splitlines(), start=1):
            for pattern, message in patterns:
                if re.search(pattern, line):
                    results.append(
                        ReviewFinding(severity="warning", file=raw_path, line=index, message=message)
                    )
    return results


def _read_text(path: str) -> str | None:
    """Read a file's text, returning None when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:  # noqa: PTH123
            return handle.read()
    except OSError:
        return None


@dataclass(frozen=True, slots=True)
class QueuedMessages:
    """Snapshot of harness-owned queued user messages."""

    steering: tuple[AgentMessage, ...] = ()
    follow_up: tuple[AgentMessage, ...] = ()

    @property
    def count(self) -> int:
        """Return the total queued message count."""
        return len(self.steering) + len(self.follow_up)


@dataclass(slots=True)
class AgentHarnessConfig:
    """Configuration for an `AgentHarness`."""

    provider: ModelProvider
    model: str
    system: str
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int | None = None
    queue_mode: QueueMode = "one_at_a_time"


class SimpleCancellationToken:
    """Small cancellation token used by the harness and loop."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancelled


class AgentHarness:
    """Reusable stateful agent brain.

    The harness owns the transcript and delegates execution to `run_agent_loop`.
    It remains independent of CLI, Rich, Textual, session files, and coding-agent
    resource loading.
    """

    def __init__(
        self,
        config: AgentHarnessConfig,
        *,
        messages: Sequence[AgentMessage] = (),
    ) -> None:
        self._config = config
        self._messages = list(messages)
        self._listeners: list[EventListener] = []
        self._current_signal: SimpleCancellationToken | None = None
        self._running = False
        self._steering_queue: deque[AgentMessage] = deque()
        self._follow_up_queue: deque[AgentMessage] = deque()

    @property
    def messages(self) -> tuple[AgentMessage, ...]:
        """Return an immutable snapshot of the current transcript."""
        return tuple(self._messages)

    @property
    def config(self) -> AgentHarnessConfig:
        """Return the harness configuration."""
        return self._config

    @property
    def is_running(self) -> bool:
        """Return whether a prompt or continuation is currently active."""
        return self._running

    @property
    def queued_messages(self) -> QueuedMessages:
        """Return a snapshot of queued steering and follow-up messages."""
        return QueuedMessages(
            steering=tuple(self._steering_queue),
            follow_up=tuple(self._follow_up_queue),
        )

    @property
    def pending_message_count(self) -> int:
        """Return the total queued message count."""
        return self.queued_messages.count

    def has_queued_messages(self) -> bool:
        """Return whether either queue has pending messages."""
        return bool(self._steering_queue or self._follow_up_queue)

    def append_message(self, message: AgentMessage) -> None:
        """Append an existing message, useful for restoring session state."""
        self._messages.append(message)

    def replace_messages(self, messages: Sequence[AgentMessage]) -> None:
        """Replace the transcript, useful after durable context reconstruction."""
        self._messages = list(messages)

    def subscribe(self, listener: EventListener) -> Callable[[], None]:
        """Subscribe to streamed events and return an unsubscribe callback."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            with suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe

    def cancel(self) -> None:
        """Request cancellation for the currently running prompt, if any."""
        if self._current_signal is not None:
            self._current_signal.cancel()

    def steer(self, content: str) -> QueueUpdateEvent:
        """Queue a steering message for the active or next run."""
        return self.steer_message(UserMessage(content=content))

    def steer_message(self, message: AgentMessage) -> QueueUpdateEvent:
        """Queue a message to inject after the current turn/tool batch."""
        self._steering_queue.append(message)
        return self.queue_update_event()

    def follow_up(self, content: str) -> QueueUpdateEvent:
        """Queue a follow-up message for when the active run would stop."""
        return self.follow_up_message(UserMessage(content=content))

    def follow_up_message(self, message: AgentMessage) -> QueueUpdateEvent:
        """Queue a message to inject when the current run would otherwise stop."""
        self._follow_up_queue.append(message)
        return self.queue_update_event()

    def clear_queues(self) -> QueuedMessages:
        """Clear all queued messages and return the cleared snapshot."""
        snapshot = self.queued_messages
        self._steering_queue.clear()
        self._follow_up_queue.clear()
        return snapshot

    def pop_latest_follow_up(self) -> AgentMessage | None:
        """Remove and return the most recently queued follow-up message."""
        if not self._follow_up_queue:
            return None
        return self._follow_up_queue.pop()

    def pop_latest_steering(self) -> AgentMessage | None:
        """Remove and return the most recently queued steering message."""
        if not self._steering_queue:
            return None
        return self._steering_queue.pop()

    def queue_update_event(self) -> QueueUpdateEvent:
        """Return the current queue state as a portable agent event."""
        return QueueUpdateEvent(
            steering=tuple(message.content for message in self._steering_queue),
            follow_up=tuple(message.content for message in self._follow_up_queue),
        )

    def prompt(self, content: str) -> AsyncIterator[AgentEvent]:
        """Append a user message and run the agent loop."""
        self._ensure_not_running()
        self._append_interrupted_tool_results()
        self._running = True
        message = UserMessage(content=content)
        self._messages.append(message)
        return self._run(prompt_message=message)

    def continue_(self) -> AsyncIterator[AgentEvent]:
        """Continue the agent loop without appending a new user message."""
        self._ensure_not_running()
        self._append_interrupted_tool_results()
        self._running = True
        return self._run()

    async def _run(self, *, prompt_message: UserMessage | None = None) -> AsyncIterator[AgentEvent]:
        signal = SimpleCancellationToken()
        self._current_signal = signal
        pending_prompt_event = prompt_message
        try:
            async for event in run_agent_loop(
                provider=self._config.provider,
                model=self._config.model,
                system=self._config.system,
                messages=self._messages,
                tools=self._config.tools,
                max_turns=self._config.max_turns,
                signal=signal,
                get_steering_messages=self._drain_steering_messages,
                get_follow_up_messages=self._drain_follow_up_messages,
                get_queue_update=self.queue_update_event,
            ):
                await self._notify(event)
                yield event
                if pending_prompt_event is not None and event.type == "turn_start":
                    start = MessageStartEvent(message_role="user")
                    end = MessageEndEvent(message=pending_prompt_event)
                    for prompt_event in (start, end):
                        await self._notify(prompt_event)
                        yield prompt_event
                    pending_prompt_event = None
        finally:
            if signal.is_cancelled():
                self._append_interrupted_tool_results()
            if self._current_signal is signal:
                self._current_signal = None
            self._running = False

    async def _notify(self, event: AgentEvent) -> None:
        for listener in list(self._listeners):
            result = listener(event)
            if isawaitable(result):
                await result

    def _ensure_not_running(self) -> None:
        if self._running:
            raise RuntimeError(
                "AgentHarness is already running; use steer() or follow_up() to queue messages."
            )

    def _drain_steering_messages(self) -> tuple[AgentMessage, ...]:
        return self._drain_queue(self._steering_queue)

    def _drain_follow_up_messages(self) -> tuple[AgentMessage, ...]:
        return self._drain_queue(self._follow_up_queue)

    def _drain_queue(self, queue: deque[AgentMessage]) -> tuple[AgentMessage, ...]:
        if not queue:
            return ()
        if self._config.queue_mode == "all":
            messages = tuple(queue)
            queue.clear()
            return messages
        return (queue.popleft(),)

    def append_interrupted_tool_results(self) -> int:
        """Repair a transcript left mid-tool-call by an interrupted run.

        Returns the number of synthetic tool results that were appended.
        """
        before_count = len(self._messages)
        self._append_interrupted_tool_results()
        return len(self._messages) - before_count

    def _append_interrupted_tool_results(self) -> None:
        """Repair a transcript left mid-tool-call by an interrupted run.

        OpenAI-compatible providers reject a transcript where an assistant tool
        call has no matching tool result anywhere in the submitted history. If
        the UI cancels the worker while a tool is still running, the normal loop
        may not get a chance to append the cancellation result, so repair that
        gap before the next model request.
        """
        returned_ids = {
            message.tool_call_id
            for message in self._messages
            if isinstance(message, ToolResultMessage)
        }
        for message in tuple(self._messages):
            if not isinstance(message, AssistantMessage):
                continue
            for tool_call in message.tool_calls:
                if tool_call.id in returned_ids:
                    continue
                returned_ids.add(tool_call.id)
                content = "Tool call interrupted by user"
                self._messages.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=content,
                        ok=False,
                        error=content,
                    )
                )
