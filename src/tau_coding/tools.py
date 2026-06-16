"""Built-in coding tools for Tau sessions and CLIs."""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from time import monotonic

from tau_agent.tools import AgentTool, AgentToolResult
from tau_agent.types import JSONValue

DEFAULT_MAX_OUTPUT_BYTES = 50 * 1024
DEFAULT_MAX_OUTPUT_LINES = 2_000
DEFAULT_BASH_TIMEOUT_SECONDS = 30.0


class ToolInputError(ValueError):
    """Raised when a tool receives invalid structured arguments."""


def create_coding_tools(*, cwd: str | Path | None = None) -> list[AgentTool]:
    """Create Tau's default coding tools rooted at `cwd` or the current directory."""
    root = Path.cwd() if cwd is None else Path(cwd)
    return [
        create_read_tool(cwd=root),
        create_write_tool(cwd=root),
        create_edit_tool(cwd=root),
        create_bash_tool(cwd=root),
    ]


def create_read_tool(*, cwd: str | Path | None = None) -> AgentTool:
    """Create a tool that reads text files."""
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(arguments: Mapping[str, JSONValue]) -> AgentToolResult:
        path = _path_arg(arguments, "path", cwd=root)
        offset = _optional_int_arg(arguments, "offset")
        limit = _optional_int_arg(arguments, "limit")

        if offset is not None and offset < 1:
            raise ToolInputError("offset must be at least 1")
        if limit is not None and limit < 1:
            raise ToolInputError("limit must be at least 1")
        if not path.exists():
            raise ToolInputError(f"File not found: {path}")
        if path.is_dir():
            raise ToolInputError(f"Path is a directory: {path}")

        text = path.read_text()
        lines = text.splitlines(keepends=True)
        start = 0 if offset is None else offset - 1
        selected = lines[start : None if limit is None else start + limit]
        content = "".join(selected)
        truncated = len(selected) < len(lines[start:])
        content, output_truncated = truncate_text(content)
        if truncated or output_truncated:
            content = append_status_line(content, "[truncated]")

        return AgentToolResult(
            tool_call_id="",
            name="read",
            ok=True,
            content=content,
            data={"path": str(path), "truncated": truncated or output_truncated},
        )

    return AgentTool(
        name="read",
        description=(
            "Read a UTF-8 text file. Arguments: path, optional 1-indexed offset, "
            "optional line limit."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
        },
        executor=execute,
    )


def create_write_tool(*, cwd: str | Path | None = None) -> AgentTool:
    """Create a tool that writes complete text files."""
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(arguments: Mapping[str, JSONValue]) -> AgentToolResult:
        path = _path_arg(arguments, "path", cwd=root)
        content = _str_arg(arguments, "content")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

        return AgentToolResult(
            tool_call_id="",
            name="write",
            ok=True,
            content=f"Wrote {len(content)} characters to {path}",
            data={"path": str(path), "characters": len(content)},
        )

    return AgentTool(
        name="write",
        description="Write a complete UTF-8 text file, creating parent directories when needed.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        executor=execute,
    )


def create_edit_tool(*, cwd: str | Path | None = None) -> AgentTool:
    """Create a tool that performs exact text replacements with rollback-on-failure."""
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(arguments: Mapping[str, JSONValue]) -> AgentToolResult:
        path = _path_arg(arguments, "path", cwd=root)
        edits = _edits_arg(arguments)

        if not path.exists():
            raise ToolInputError(f"File not found: {path}")
        if path.is_dir():
            raise ToolInputError(f"Path is a directory: {path}")

        original = path.read_text()
        spans: list[tuple[int, int, str]] = []
        for index, edit in enumerate(edits, start=1):
            old_text = edit["oldText"]
            new_text = edit["newText"]
            if old_text == "":
                raise ToolInputError(f"Edit {index} oldText must not be empty")
            first = original.find(old_text)
            if first < 0:
                raise ToolInputError(f"Edit {index} oldText was not found")
            second = original.find(old_text, first + len(old_text))
            if second >= 0:
                raise ToolInputError(f"Edit {index} oldText matched more than once")
            spans.append((first, first + len(old_text), new_text))

        _validate_non_overlapping(spans)
        updated = original
        for start, end, new_text in sorted(spans, reverse=True):
            updated = f"{updated[:start]}{new_text}{updated[end:]}"

        path.write_text(updated)
        return AgentToolResult(
            tool_call_id="",
            name="edit",
            ok=True,
            content=f"Applied {len(edits)} edit(s) to {path}",
            data={"path": str(path), "edits": len(edits)},
        )

    return AgentTool(
        name="edit",
        description=(
            "Replace exact text in a UTF-8 file. Every oldText must match exactly once; "
            "multi-edit failures leave the file unchanged."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {"type": "string"},
                            "newText": {"type": "string"},
                        },
                        "required": ["oldText", "newText"],
                    },
                    "minItems": 1,
                },
            },
            "required": ["path", "edits"],
        },
        executor=execute,
    )


def create_bash_tool(*, cwd: str | Path | None = None) -> AgentTool:
    """Create a tool that executes shell commands with timeout and truncation."""
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(arguments: Mapping[str, JSONValue]) -> AgentToolResult:
        command = _str_arg(arguments, "command")
        timeout_seconds = _optional_float_arg(arguments, "timeout_seconds")
        if timeout_seconds is None:
            timeout_seconds = DEFAULT_BASH_TIMEOUT_SECONDS
        if timeout_seconds <= 0:
            raise ToolInputError("timeout_seconds must be greater than 0")

        start = monotonic()
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        output = _format_bash_output(stdout=stdout, stderr=stderr)
        output, truncated = truncate_text(output)
        exit_code = process.returncode
        if timed_out:
            output = append_status_line(output, f"Command timed out after {timeout_seconds:g}s")
        if truncated:
            output = append_status_line(output, "[truncated]")

        ok = exit_code == 0 and not timed_out
        return AgentToolResult(
            tool_call_id="",
            name="bash",
            ok=ok,
            content=output,
            error=None if ok else f"Command failed with exit code {exit_code}",
            data={
                "command": command,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_seconds": round(monotonic() - start, 3),
                "truncated": truncated,
            },
        )

    return AgentTool(
        name="bash",
        description=(
            "Execute a shell command in the working directory. Arguments: command, "
            "optional timeout_seconds."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
            "required": ["command"],
        },
        executor=execute,
    )


def append_status_line(text: str, status: str) -> str:
    """Append a status line without introducing an extra blank line."""
    separator = "" if text.endswith("\n") or not text else "\n"
    return f"{text}{separator}{status}"


def truncate_text(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_lines: int = DEFAULT_MAX_OUTPUT_LINES,
) -> tuple[str, bool]:
    """Return text truncated by line and UTF-8 byte limits."""
    lines = text.splitlines(keepends=True)
    truncated = len(lines) > max_lines
    limited = "".join(lines[:max_lines])
    encoded = limited.encode()
    if len(encoded) <= max_bytes:
        return limited, truncated

    truncated = True
    clipped = encoded[:max_bytes]
    return clipped.decode(errors="ignore"), truncated


def _format_bash_output(*, stdout: str, stderr: str) -> str:
    parts: list[str] = []
    if stdout:
        parts.append(f"stdout:\n{stdout.rstrip()}")
    if stderr:
        parts.append(f"stderr:\n{stderr.rstrip()}")
    return "\n\n".join(parts) if parts else "Command completed with no output."


def _str_arg(arguments: Mapping[str, JSONValue], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ToolInputError(f"{name} must be a string")
    return value


def _path_arg(arguments: Mapping[str, JSONValue], name: str, *, cwd: Path) -> Path:
    value = _str_arg(arguments, name)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path


def _optional_int_arg(arguments: Mapping[str, JSONValue], name: str) -> int | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer")
    return value


def _optional_float_arg(arguments: Mapping[str, JSONValue], name: str) -> float | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ToolInputError(f"{name} must be a number")
    return float(value)


def _edits_arg(arguments: Mapping[str, JSONValue]) -> list[dict[str, str]]:
    value = arguments.get("edits")
    if not isinstance(value, list) or not value:
        raise ToolInputError("edits must be a non-empty array")

    edits: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ToolInputError(f"Edit {index} must be an object")
        old_text = item.get("oldText")
        new_text = item.get("newText")
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise ToolInputError(f"Edit {index} oldText and newText must be strings")
        edits.append({"oldText": old_text, "newText": new_text})
    return edits


def _validate_non_overlapping(spans: list[tuple[int, int, str]]) -> None:
    sorted_spans = sorted(spans)
    previous_end = -1
    for start, end, _new_text in sorted_spans:
        if start < previous_end:
            raise ToolInputError("Edits must not overlap")
        previous_end = end
