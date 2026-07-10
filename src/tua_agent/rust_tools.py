"""Rust-specific agent tools for Tua Agent.

These tools give the agent direct access to the Rust toolchain:
cargo build, cargo test, cargo clippy, rustfmt, rustc, and rustup.
Each tool is a standard Tau AgentTool that can be registered with the harness.

The executors shell out to the real Rust toolchain via ``asyncio`` subprocesses
so the agent can actually build, test, lint, explain, and format Rust code.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from tau_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from tau_agent.types import JSONValue

# Keep tool output bounded so the agent's context window stays manageable.
_MAX_OUTPUT_CHARS = 16_000
# How long a single toolchain command may run before it is killed (seconds).
# Cargo builds on a cold dependency cache can be slow, so this is generous.
# Override with the ``TUA_TOOL_TIMEOUT`` environment variable.
_DEFAULT_TOOL_TIMEOUT = float(os.environ.get("TUA_TOOL_TIMEOUT", "600"))


# ── Argument Helpers ────────────────────────────────────────────────────────

def _str_arg(arguments: Mapping[str, JSONValue], name: str) -> str:
    """Return a required string argument or raise ValueError."""
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string argument: {name!r}")
    return value.strip()


def _opt_str(arguments: Mapping[str, JSONValue], name: str) -> str | None:
    """Return an optional string argument as a stripped value or None."""
    value = arguments.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _bool_arg(arguments: Mapping[str, JSONValue], name: str, *, default: bool = False) -> bool:
    value = arguments.get(name)
    return bool(value) if value is not None else default


def _str_list(arguments: Mapping[str, JSONValue], name: str) -> list[str]:
    value = arguments.get(name)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


# ── Shared Subprocess Runner ────────────────────────────────────────────────

def _result(
    name: str,
    *,
    ok: bool,
    content: str,
    error: str | None = None,
    data: dict[str, JSONValue] | None = None,
) -> AgentToolResult:
    return AgentToolResult(
        tool_call_id="",
        name=name,
        ok=ok,
        content=content,
        error=error,
        data=data,
    )


def _format_output(command: str, stdout: str, stderr: str, exit_code: int | None) -> str:
    """Render combined subprocess output for the model to read."""
    body = stdout.rstrip()
    stderr_text = stderr.rstrip()
    if stderr_text:
        body = f"{body}\n{stderr_text}".strip() if body else stderr_text
    lines = [f"$ {command}", body or "(no output)", f"[exit code: {exit_code}]"]
    return "\n".join(lines)


def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """Kill a process; try its group on POSIX so shell-spawned children die too."""
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), os.SIGKILL)
        else:  # pragma: no cover - non-POSIX fallback
            process.kill()
    except (ProcessLookupError, OSError):
        pass


def _truncate(text: str) -> str:
    """Tail-truncate output, leaving a marker so truncation is never silent."""
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    half = _MAX_OUTPUT_CHARS // 2
    dropped = len(text) - _MAX_OUTPUT_CHARS
    return (
        text[:half]
        + f"\n\n[… {dropped} characters omitted (output truncated) …]\n\n"
        + text[-half:]
    )


async def _run_subprocess(
    argv: list[str],
    *,
    name: str,
    cwd: str | None = None,
    timeout: float = _DEFAULT_TOOL_TIMEOUT,
    stdin: bytes | None = None,
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``argv`` as a subprocess and capture combined stdout/stderr.

    The executable is resolved against ``PATH`` so a missing toolchain yields a
    helpful "install rustup" error instead of an opaque spawn failure. On POSIX
    the process runs in its own session so a timeout or cancellation kills
    shell-spawned children too. ``ok`` is ``True`` only when the process exits 0.
    """
    if signal is not None and signal.is_cancelled():
        return _result(name, ok=False, content="Command cancelled", error="cancelled")

    command_display = " ".join(argv)
    program = shutil.which(argv[0]) if os.path.dirname(argv[0]) == "" else argv[0]
    if not program:
        return _result(
            name,
            ok=False,
            content=(
                f"`{argv[0]}` was not found on PATH. Install the Rust toolchain "
                f"from https://rustup.rs before using the {name} tool."
            ),
            error="executable_not_found",
            data={"command": command_display},
        )
    full_argv = [program, *argv[1:]]

    spawn_kwargs: dict[str, object] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if stdin is not None:
        spawn_kwargs["stdin"] = asyncio.subprocess.PIPE
    if cwd is not None:
        spawn_kwargs["cwd"] = cwd
    if os.name == "posix":
        spawn_kwargs["start_new_session"] = True

    try:
        process = await asyncio.create_subprocess_exec(*full_argv, **spawn_kwargs)
    except OSError as exc:
        return _result(
            name,
            ok=False,
            content=f"Failed to spawn `{argv[0]}`: {exc}",
            error="spawn_failed",
            data={"command": command_display},
        )

    cancelled = False
    timed_out = False
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    communicate_task = asyncio.ensure_future(process.communicate(input=stdin))
    while True:
        if signal is not None and signal.is_cancelled():
            cancelled = True
            _kill_process_tree(process)
            break
        remaining = deadline - loop.time()
        if remaining <= 0:
            timed_out = True
            _kill_process_tree(process)
            break
        done, _ = await asyncio.wait(
            {communicate_task}, timeout=min(0.25, remaining)
        )
        if done:
            break

    stdout_b, stderr_b = await communicate_task
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    exit_code = process.returncode

    if cancelled:
        return _result(
            name,
            ok=False,
            content=_truncate(
                f"$ {command_display}\n{stdout.rstrip() or '(no output)'}\n[cancelled]"
            ),
            error="cancelled",
            data={"command": command_display, "exit_code": exit_code},
        )
    if timed_out:
        return _result(
            name,
            ok=False,
            content=_truncate(
                f"$ {command_display}\n{stdout.rstrip() or '(no output)'}\n"
                f"[timed out after {timeout:g}s]"
            ),
            error="timeout",
            data={"command": command_display, "timeout": timeout, "exit_code": exit_code},
        )

    ok = exit_code == 0
    content = _truncate(_format_output(command_display, stdout, stderr, exit_code))
    return _result(
        name,
        ok=ok,
        content=content,
        error=None if ok else f"exit code {exit_code}",
        data={
            "command": command_display,
            "exit_code": exit_code,
            "stdout_bytes": len(stdout_b),
            "stderr_bytes": len(stderr_b),
            "truncated": len(stdout) + len(stderr) > _MAX_OUTPUT_CHARS,
        },
    )


# ── Real Tool Executors ─────────────────────────────────────────────────────

CARGO_SUBCOMMANDS = {
    "build", "test", "check", "clippy", "fmt", "bench", "doc", "audit",
    "update", "tree", "add", "remove", "run", "clean", "fix",
}


async def _cargo_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo <subcommand> [args...]`` and return the combined output."""
    subcommand = _str_arg(arguments, "subcommand")
    if subcommand not in CARGO_SUBCOMMANDS:
        known = ", ".join(sorted(CARGO_SUBCOMMANDS))
        return _result(
            "cargo",
            ok=False,
            content=f"Unknown cargo subcommand: {subcommand!r}. Known: {known}.",
            error="invalid_subcommand",
        )
    extra_args = _str_list(arguments, "args")
    cwd = _opt_str(arguments, "cwd")
    argv = ["cargo", subcommand, *extra_args]
    return await _run_subprocess(argv, name="cargo", cwd=cwd, signal=signal)


async def _rustc_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``rustc`` to explain an error code, check a file, or report versions."""
    action = _str_arg(arguments, "action")
    target = _opt_str(arguments, "target")

    if action == "explain":
        if not target:
            return _result(
                "rustc",
                ok=False,
                content="`explain` requires a `target` error code (e.g. E0502).",
                error="missing_target",
            )
        argv = ["rustc", "--explain", target]
        return await _run_subprocess(argv, name="rustc", signal=signal)
    if action == "version":
        argv = ["rustc", "--version", "--verbose"]
        return await _run_subprocess(argv, name="rustc", signal=signal)
    if action == "check":
        if not target:
            return _result(
                "rustc",
                ok=False,
                content="`check` requires a `target` path to a .rs file.",
                error="missing_target",
            )
        # --emit=metadata type-checks the file without emitting a binary.
        argv = ["rustc", "--edition", "2021", "--emit=metadata", target]
        return await _run_subprocess(argv, name="rustc", signal=signal)
    if action == "edition":
        edition = target or "2021"
        # Validate the edition by compiling a trivial program; rustc rejects
        # unknown editions only when it actually compiles something.
        return await _check_edition(edition, signal=signal)
    return _result(
        "rustc",
        ok=False,
        content=f"Unknown rustc action: {action!r}. Use explain/check/version/edition.",
        error="invalid_action",
    )


async def _check_edition(
    edition: str, *, signal: ToolCancellationToken | None = None
) -> AgentToolResult:
    """Compile a trivial program under ``edition`` to confirm rustc accepts it."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".rs", delete=False, encoding="utf-8"
    ) as handle:
        handle.write("fn main() {}\n")
        probe_path = handle.name
    try:
        argv = ["rustc", "--edition", edition, "--emit=metadata", probe_path]
        return await _run_subprocess(
            argv,
            name="rustc",
            signal=signal,
        )
    finally:
        with contextlib_suppress():
            os.unlink(probe_path)


async def _rustfmt_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``rustfmt`` to check or format the given files."""
    check = _bool_arg(arguments, "check")
    files = _str_list(arguments, "files")
    cwd = _opt_str(arguments, "cwd")
    if not files:
        return _result(
            "rustfmt",
            ok=False,
            content="rustfmt requires one or more `files` to format.",
            error="missing_files",
        )
    argv = ["rustfmt"]
    if check:
        argv.append("--check")
    argv.extend(files)
    return await _run_subprocess(argv, name="rustfmt", cwd=cwd, signal=signal)


async def _clippy_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo clippy`` with optional lint flags."""
    deny_warnings = _bool_arg(arguments, "deny_warnings", default=True)
    allow = _str_list(arguments, "allow")
    fix = _bool_arg(arguments, "fix")

    argv: list[str] = ["cargo", "clippy"]
    if fix:
        argv += ["--fix", "--allow-dirty", "--allow-no-vcs", "--allow-staged"]
    lint_flags: list[str] = []
    if deny_warnings:
        lint_flags += ["-D", "warnings"]
    for lint in allow:
        lint_flags += ["-A", lint]
    if lint_flags:
        argv += ["--", *lint_flags]
    return await _run_subprocess(argv, name="clippy", signal=signal)


async def _rustup_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``rustup`` to inspect or manage installed toolchains."""
    action = _str_arg(arguments, "action")
    target = _opt_str(arguments, "target")

    if action == "show":
        argv = ["rustup", "show"]
    elif action == "update":
        argv = ["rustup", "update", *([target] if target else [])]
    elif action == "check":
        argv = ["rustup", "check"]
    elif action == "target":
        argv = ["rustup", "target", "add", target] if target else ["rustup", "target", "list"]
    elif action == "component":
        argv = (
            ["rustup", "component", "add", target]
            if target
            else ["rustup", "component", "list"]
        )
    elif action == "toolchain":
        argv = (
            ["rustup", "toolchain", "install", target]
            if target
            else ["rustup", "toolchain", "list"]
        )
    elif action == "default":
        if not target:
            return _result(
                "rustup",
                ok=False,
                content="`default` requires a `target` toolchain name.",
                error="missing_target",
            )
        argv = ["rustup", "default", target]
    else:
        return _result(
            "rustup",
            ok=False,
            content=(
                f"Unknown rustup action: {action!r}. Use "
                "show/update/check/target/component/default/toolchain."
            ),
            error="invalid_action",
        )
    return await _run_subprocess(argv, name="rustup", signal=signal)


# ── JSON Schema Definitions ────────────────────────────────────────────────

CARGO_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "subcommand": {
            "type": "string",
            "description": "Cargo subcommand: build, test, check, clippy, fmt, bench, doc, audit, update, tree, add, remove",
            "enum": [
                "build", "test", "check", "clippy", "fmt", "bench",
                "doc", "audit", "update", "tree", "add", "remove",
                "run", "clean", "fix",
            ],
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional arguments passed to the cargo subcommand",
        },
        "cwd": {
            "type": "string",
            "description": "Working directory (defaults to project root)",
        },
    },
    "required": ["subcommand"],
}

RUSTC_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "Action: explain (error code), check (compile single file), version",
            "enum": ["explain", "check", "version", "edition"],
        },
        "target": {
            "type": "string",
            "description": "For explain: error code (e.g., E0502). For check: path to .rs file.",
        },
    },
    "required": ["action"],
}

RUSTFMT_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "check": {
            "type": "boolean",
            "description": "Check formatting without modifying files",
            "default": False,
        },
        "files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific files to format (defaults to all .rs files)",
        },
    },
    "required": [],
}

CLIPPY_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "deny_warnings": {
            "type": "boolean",
            "description": "Treat all warnings as errors (-D warnings)",
            "default": True,
        },
        "allow": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lint names to allow (e.g., clippy::too_many_arguments)",
        },
        "fix": {
            "type": "boolean",
            "description": "Auto-fix suggestions where possible (--fix)",
            "default": False,
        },
    },
    "required": [],
}

RUSTUP_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "rustup action",
            "enum": ["show", "update", "check", "target", "component", "default", "toolchain"],
        },
        "target": {
            "type": "string",
            "description": "Target name, component name, or toolchain version",
        },
    },
    "required": ["action"],
}


# ── Tool Definitions ───────────────────────────────────────────────────────

CARGO_TOOL = AgentTool(
    name="cargo",
    description="Run cargo commands: build, test, check, clippy, fmt, bench, doc, and more",
    input_schema=CARGO_SCHEMA,
    executor=_cargo_executor,
    prompt_snippet="cargo <subcommand> [args...] — Rust's build system and package manager",
    prompt_guidelines=(
        "Always run `cargo check` before suggesting code changes to verify they compile",
        "Use `cargo test` to run tests after making changes",
        "Use `cargo clippy` to catch common mistakes and non-idiomatic code",
        "Use `cargo fmt` to ensure consistent code formatting",
        "Use `cargo bench` for benchmarking",
        "Use `cargo doc --open` to build and view documentation",
    ),
)

RUSTC_TOOL = AgentTool(
    name="rustc",
    description="Run the Rust compiler directly — check syntax, explain errors, verify editions",
    input_schema=RUSTC_SCHEMA,
    executor=_rustc_executor,
    prompt_snippet="rustc <action> [args...] — Direct Rust compiler access",
    prompt_guidelines=(
        "Use `rustc --explain E0XXX` to get detailed compiler error explanations",
        "Use `rustc --edition 2021` to check edition-specific syntax",
        "Prefer `cargo check` for project compilation; use `rustc` for isolated checks",
    ),
)

RUSTFMT_TOOL = AgentTool(
    name="rustfmt",
    description="Format Rust code according to style guidelines (rustfmt)",
    input_schema=RUSTFMT_SCHEMA,
    executor=_rustfmt_executor,
    prompt_snippet="rustfmt [--check] [files...] — Format Rust source files",
    prompt_guidelines=(
        "Run `rustfmt` after editing Rust files to ensure consistent style",
        "Use `rustfmt --check` to verify formatting without changing files",
        "Respect project-specific `rustfmt.toml` configuration",
    ),
)

CLIPPY_TOOL = AgentTool(
    name="clippy",
    description="Run Clippy — Rust linter with 550+ lint rules for catching mistakes and improving code",
    input_schema=CLIPPY_SCHEMA,
    executor=_clippy_executor,
    prompt_snippet="clippy [--deny-warnings] [--fix] — Rust linter",
    prompt_guidelines=(
        "Always run `clippy` after making changes — treat warnings as errors",
        "Use `clippy -- -D warnings` to deny all warnings",
        "Explain WHY a clippy lint fires, not just WHAT the fix is",
        "For pedantic lints, mention they are optional style preferences",
    ),
)

RUSTUP_TOOL = AgentTool(
    name="rustup",
    description="Manage Rust toolchains — check, install, update, switch targets and components",
    input_schema=RUSTUP_SCHEMA,
    executor=_rustup_executor,
    prompt_snippet="rustup <action> [target] — Manage Rust toolchain",
    prompt_guidelines=(
        "Check `rustup show` to see active toolchain and installed targets",
        "Use `rustup target add` to add cross-compilation targets",
        "Use `rustup component add` to install components (clippy, rustfmt, rust-analyzer)",
    ),
)


CARGO_AUDIT_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "fix": {
            "type": "boolean",
            "description": "Attempt to fix vulnerabilities automatically",
            "default": False,
        },
    },
    "required": [],
}

CARGO_OUTDATED_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "workspace": {
            "type": "boolean",
            "description": "Check every crate in the workspace",
            "default": True,
        },
    },
    "required": [],
}

CARGO_UDEP_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {},
    "required": [],
}

CARGO_DENY_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "check": {
            "type": "string",
            "description": "What to check: advisories, bans, licenses, or sources",
            "enum": ["advisories", "bans", "licenses", "sources"],
            "default": "advisories",
        },
    },
    "required": [],
}

CARGO_BENCH_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional arguments (e.g. a benchmark name filter, --bench <name>, -- --save-baseline)",
        },
        "cwd": {
            "type": "string",
            "description": "Working directory (defaults to project root)",
        },
    },
    "required": [],
}

CARGO_DOC_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "open": {
            "type": "boolean",
            "description": "Open the generated docs in a browser (--open)",
            "default": False,
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional arguments (e.g. --no-deps, --document-private-items)",
        },
        "cwd": {
            "type": "string",
            "description": "Working directory (defaults to project root)",
        },
    },
    "required": [],
}

CARGO_TEST_DOC_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "package": {
            "type": "string",
            "description": "Restrict doc-tests to a specific package (-p <name>)",
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional arguments passed to `cargo test --doc`",
        },
        "cwd": {
            "type": "string",
            "description": "Working directory (defaults to project root)",
        },
    },
    "required": [],
}

WASM_PACK_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "subcommand": {
            "type": "string",
            "description": "wasm-pack subcommand",
            "enum": ["build", "test", "pack", "new"],
            "default": "build",
        },
        "target": {
            "type": "string",
            "description": "Build target for `wasm-pack build` (web, bundler, nodejs, deno)",
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional arguments (e.g. --release, --dev)",
        },
        "cwd": {
            "type": "string",
            "description": "Working directory (defaults to project root)",
        },
    },
    "required": [],
}


async def _cargo_audit_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo audit`` to check for security vulnerabilities."""
    argv = ["cargo", "audit"]
    if arguments.get("fix"):
        argv.append("--fix")
    try:
        return await _run_subprocess(argv, name="cargo_audit", signal=signal)
    except FileNotFoundError:
        return _result(
            "cargo_audit",
            ok=False,
            content="cargo-audit not installed. Install: cargo install cargo-audit",
            error="executable_not_found",
        )


async def _cargo_outdated_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo outdated`` to find outdated dependencies."""
    argv = ["cargo", "outdated"]
    if arguments.get("workspace", True):
        argv.append("--workspace")
    try:
        return await _run_subprocess(argv, name="cargo_outdated", signal=signal)
    except FileNotFoundError:
        return _result(
            "cargo_outdated",
            ok=False,
            content="cargo-outdated not installed. Install: cargo install cargo-outdated",
            error="executable_not_found",
        )


async def _cargo_udep_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo udeps`` to detect unused dependencies."""
    argv = ["cargo", "udeps"]
    try:
        return await _run_subprocess(argv, name="cargo_udep", signal=signal)
    except FileNotFoundError:
        return _result(
            "cargo_udep",
            ok=False,
            content="cargo-udeps not installed. Install: cargo install cargo-udeps",
            error="executable_not_found",
        )


async def _cargo_deny_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo deny check`` for supply-chain auditing."""
    check = _opt_str(arguments, "check") or "advisories"
    argv = ["cargo", "deny", "check", check]
    try:
        return await _run_subprocess(argv, name="cargo_deny", signal=signal)
    except FileNotFoundError:
        return _result(
            "cargo_deny",
            ok=False,
            content="cargo-deny not installed. Install: cargo install cargo-deny",
            error="executable_not_found",
        )


# ── New Tool Executors (bench, doc, doc-tests, wasm-pack) ───────────────────

async def _cargo_bench_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo bench`` and capture criterion/benchmark output."""
    extra_args = _str_list(arguments, "args")
    cwd = _opt_str(arguments, "cwd")
    argv = ["cargo", "bench", *extra_args]
    return await _run_subprocess(argv, name="cargo_bench", cwd=cwd, signal=signal)


async def _cargo_doc_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo doc`` and report whether the docs build."""
    extra_args = _str_list(arguments, "args")
    cwd = _opt_str(arguments, "cwd")
    argv = ["cargo", "doc"]
    if _bool_arg(arguments, "open"):
        argv.append("--open")
    argv.extend(extra_args)
    return await _run_subprocess(argv, name="cargo_doc", cwd=cwd, signal=signal)


async def _cargo_test_doc_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``cargo test --doc`` to verify doc-tests."""
    extra_args = _str_list(arguments, "args")
    cwd = _opt_str(arguments, "cwd")
    argv = ["cargo", "test", "--doc"]
    package = _opt_str(arguments, "package")
    if package:
        argv += ["-p", package]
    argv.extend(extra_args)
    return await _run_subprocess(argv, name="cargo_test_doc", cwd=cwd, signal=signal)


WASM_PACK_SUBCOMMANDS = {"build", "test", "pack", "new"}


async def _wasm_pack_executor(
    arguments: Mapping[str, JSONValue],
    signal: ToolCancellationToken | None = None,
) -> AgentToolResult:
    """Run ``wasm-pack build/test/pack/new`` for WebAssembly targets."""
    subcommand = _opt_str(arguments, "subcommand") or "build"
    if subcommand not in WASM_PACK_SUBCOMMANDS:
        known = ", ".join(sorted(WASM_PACK_SUBCOMMANDS))
        return _result(
            "wasm_pack",
            ok=False,
            content=f"Unknown wasm-pack subcommand: {subcommand!r}. Known: {known}.",
            error="invalid_subcommand",
        )
    extra_args = _str_list(arguments, "args")
    cwd = _opt_str(arguments, "cwd")
    target = _opt_str(arguments, "target")
    argv = ["wasm-pack", subcommand]
    if subcommand == "build" and target:
        argv += ["--target", target]
    argv.extend(extra_args)
    try:
        return await _run_subprocess(argv, name="wasm_pack", cwd=cwd, signal=signal)
    except FileNotFoundError:
        return _result(
            "wasm_pack",
            ok=False,
            content="wasm-pack not installed. Install: cargo install wasm-pack",
            error="executable_not_found",
        )


# ── Extended Tool Definitions ──────────────────────────────────────────────

CARGO_AUDIT_TOOL = AgentTool(
    name="cargo_audit",
    description="Run cargo audit to check dependencies for known security vulnerabilities (RustSec advisory database)",
    input_schema=CARGO_AUDIT_SCHEMA,
    executor=_cargo_audit_executor,
    prompt_snippet="cargo audit [--fix] — Scan dependencies for known CVEs and security advisories",
    prompt_guidelines=(
        "Run `cargo audit` to check for known vulnerabilities in dependencies",
    ),
)

CARGO_OUTDATED_TOOL = AgentTool(
    name="cargo_outdated",
    description="Run cargo outdated to display dependencies that have newer versions available",
    input_schema=CARGO_OUTDATED_SCHEMA,
    executor=_cargo_outdated_executor,
    prompt_snippet="cargo outdated [--workspace] — Find dependencies with newer versions",
    prompt_guidelines=(
        "Run `cargo outdated` to identify dependencies that lag behind their latest published versions",
        "Use `cargo outdated --workspace` to check every crate in the workspace",
    ),
)

CARGO_UDEP_TOOL = AgentTool(
    name="cargo_udep",
    description="Run cargo udeps to detect unused dependencies in Cargo.toml",
    input_schema=CARGO_UDEP_SCHEMA,
    executor=_cargo_udep_executor,
    prompt_snippet="cargo udeps — Find dependencies declared but never used",
    prompt_guidelines=(
        "Run `cargo udeps` to find dependencies declared in Cargo.toml that are not actually used",
        "Remove unused dependencies to speed up builds and reduce the attack surface",
    ),
)

CARGO_DENY_TOOL = AgentTool(
    name="cargo_deny",
    description="Run cargo deny to check for license violations, security advisories, banned crates, and disallowed sources",
    input_schema=CARGO_DENY_SCHEMA,
    executor=_cargo_deny_executor,
    prompt_snippet="cargo deny check <advisories|bans|licenses|sources> — Supply-chain linting",
    prompt_guidelines=(
        "Run `cargo deny check advisories` to scan for security advisories across the dependency graph",
        "Use `cargo deny check licenses` to enforce license compliance",
        "Use `cargo deny check bans` to detect duplicated or banned crates",
        "Use `cargo deny check sources` to ensure dependencies come from allowed registries",
    ),
)


# ── New Tool Definitions ────────────────────────────────────────────────────

CARGO_BENCH_TOOL = AgentTool(
    name="cargo_bench",
    description="Run cargo bench to execute criterion/other benchmarks and capture timing output",
    input_schema=CARGO_BENCH_SCHEMA,
    executor=_cargo_bench_executor,
    prompt_snippet="cargo bench [args...] — Run benchmarks (criterion) and report timings",
    prompt_guidelines=(
        "Use `cargo bench` to measure performance before and after a change",
        "Prefer criterion for statistical rigor — compare baselines rather than a single run",
    ),
)

CARGO_DOC_TOOL = AgentTool(
    name="cargo_doc",
    description="Run cargo doc to build API documentation and report whether it builds successfully",
    input_schema=CARGO_DOC_SCHEMA,
    executor=_cargo_doc_executor,
    prompt_snippet="cargo doc [--open] [args...] — Build and optionally view API docs",
    prompt_guidelines=(
        "Run `cargo doc` to confirm public API docs build without warnings",
        "Use `cargo doc --no-deps` to build only your crate's docs",
        "Use `cargo doc --document-private-items` for internal documentation",
    ),
)

CARGO_TEST_DOC_TOOL = AgentTool(
    name="cargo_test_doc",
    description="Run cargo test --doc to compile and execute doc-tests embedded in rustdoc comments",
    input_schema=CARGO_TEST_DOC_SCHEMA,
    executor=_cargo_test_doc_executor,
    prompt_snippet="cargo test --doc [-p <pkg>] [args...] — Run doc-tests",
    prompt_guidelines=(
        "Run `cargo test --doc` to verify that code blocks in `///` doc comments compile and pass",
        "Keep doc-test examples minimal, self-contained, and runnable",
    ),
)

WASM_PACK_TOOL = AgentTool(
    name="wasm_pack",
    description="Run wasm-pack to build, test, pack, or scaffold Rust code targeting WebAssembly (wasm32-unknown-unknown)",
    input_schema=WASM_PACK_SCHEMA,
    executor=_wasm_pack_executor,
    prompt_snippet="wasm-pack <build|test|pack|new> [--target web|bundler|nodejs|deno] — Rust→Wasm toolchain",
    prompt_guidelines=(
        "Use `wasm-pack build --target web` for native ES-module browser output",
        "Use `wasm-pack test --headless` to run wasm-bindgen-test in a headless browser",
        "Add the `wasm32-unknown-unknown` target with `rustup target add` before building",
    ),
)


# ── Tool Registry ──────────────────────────────────────────────────────────

RUST_TOOLS: list[AgentTool] = [
    CARGO_TOOL,
    RUSTC_TOOL,
    RUSTFMT_TOOL,
    CLIPPY_TOOL,
    RUSTUP_TOOL,
    CARGO_AUDIT_TOOL,
    CARGO_OUTDATED_TOOL,
    CARGO_UDEP_TOOL,
    CARGO_DENY_TOOL,
    CARGO_BENCH_TOOL,
    CARGO_DOC_TOOL,
    CARGO_TEST_DOC_TOOL,
    WASM_PACK_TOOL,
]


def get_rust_tools() -> list[AgentTool]:
    """Return the full set of Rust-specific agent tools."""
    return RUST_TOOLS


def get_rust_tool_names() -> set[str]:
    """Return just the tool names for quick membership checks."""
    return {tool.name for tool in RUST_TOOLS}


# Small stand-in for contextlib.suppress used by the edition probe cleanup. Kept
# local to avoid pulling contextlib into the hot import path elsewhere.
class contextlib_suppress:
    def __enter__(self) -> "contextlib_suppress":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return True
