"""Tua Agent CLI — Rust-specialized coding agent entry point.

Usage:
    tua                          Start interactive TUI (Rust mode)
    tua -p "prompt"              One-shot print mode with Rust expert
    tua --profile ferris         Start with a specific Rust profile
    tua --list-profiles          List available Rust profiles
    tua dashboard                Start web dashboard
"""

from __future__ import annotations

import asyncio
import re
import sys
from os import environ
from pathlib import Path

import anyio
import typer

from tau_agent.session import JsonlSessionStorage
from tau_ai import ModelProvider
from tau_ai.env import DEFAULT_OPENAI_COMPATIBLE_BASE_URL
from tau_coding.credentials import FileCredentialStore
from tau_coding.provider_config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER_NAME,
    ProviderSettings,
    load_provider_settings,
    resolve_provider_selection,
)
from tau_coding.provider_runtime import create_model_provider
from tau_coding.rendering import PrintOutputMode, create_event_renderer
from tau_coding.session import (
    CodingSession,
    CodingSessionConfig,
    jsonl_session_storage,
)
from tau_coding.session_manager import SessionManager
from tau_coding.shell_config import load_shell_settings
from tau_coding.thinking import DEFAULT_THINKING_LEVEL

from tua_agent.rust_system_prompt import RUST_SYSTEM_PROMPT, build_rust_system_prompt
from tua_agent.rust_tools import get_rust_tools
from tua_agent.rust_profiles import get_profile, list_profiles
from tua_agent.rust_session import RustSessionConfig

app = typer.Typer(
    name="tua",
    help="🦀 Tua Agent — Rust-specialized AI coding assistant",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str = typer.Option(None, "-p", "--prompt", help="One-shot prompt (non-interactive print mode)"),
    profile: str = typer.Option("rustacean", "--profile", help="Rust coding profile to use"),
    list_profiles_flag: bool = typer.Option(False, "--list-profiles", help="List available profiles"),
    model: str = typer.Option(None, "--model", "-m", help="Model to use"),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory"),
):
    """🦀 Tua Agent — Rust-specialized coding agent."""
    if list_profiles_flag:
        _print_profiles()
        return

    # Resolve profile
    try:
        rust_profile = get_profile(profile)
    except KeyError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

    # Resolve CWD
    work_dir = Path(cwd).resolve() if cwd else Path.cwd()

    typer.echo(f"🦀  Tua Agent v0.1.0 — profile: {rust_profile.emoji} {rust_profile.name}")
    typer.echo(f"    {rust_profile.description}")

    if prompt:
        # ── One-shot print mode ──────────────────────────────────────────
        _detect_and_print_rust_project(work_dir)
        typer.echo(f"\n💬 Running: {prompt[:80]}...")
        try:
            ok = anyio.run(
                _run_print_mode,
                prompt,
                model or _detect_model(),
                work_dir,
                rust_profile,
            )
            if not ok:
                raise typer.Exit(1)
        except (RuntimeError, ValueError) as exc:
            typer.echo(f"❌ Error: {exc}", err=True)
            raise typer.Exit(1)
    else:
        # ── Interactive / Help ───────────────────────────────────────────
        _detect_and_print_rust_project(work_dir)
        typer.echo("\n📟  Interactive TUI coming in next release.")
        typer.echo("    Use -p 'prompt' for one-shot mode in the meantime.")
        typer.echo(f"    Example: tua -p 'run cargo check on this project' --cwd ~/my-rust-project")


@app.command()
def dashboard_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8765, "--port", help="Bind port"),
):
    """Start the Rust project health dashboard (web UI)."""
    from tua_agent.dashboard import run_dashboard
    typer.echo(f"🦀  Tua Dashboard starting at http://{host}:{port}")
    asyncio.run(run_dashboard(host, port))


@app.command()
def profiles():
    """List all available Rust coding profiles."""
    _print_profiles()


# ── Print mode runner ─────────────────────────────────────────────────────


async def _run_print_mode(
    prompt: str,
    model: str,
    cwd: Path,
    rust_profile,
) -> bool:
    """Run a one-shot prompt with Rust-specialized agent."""
    settings = load_provider_settings()
    shell_settings = load_shell_settings()
    selection = resolve_provider_selection(settings, model=model)
    provider = create_model_provider(
        selection.provider,
        model=selection.model,
        thinking_level=DEFAULT_THINKING_LEVEL,
    )

    # Build Rust session config
    session_config = RustSessionConfig(profile=rust_profile)
    guidelines = session_config.build_guidelines()

    # Build Rust system prompt
    from tau_coding.system_prompt import (
        BuildSystemPromptOptions,
        build_system_prompt,
    )
    from tau_coding.skills import load_skills
    from tau_coding.resources import TauResourcePaths
    from tau_coding.tools import create_coding_tools

    # Combine standard Tau tools + Rust tools
    tools = create_coding_tools(cwd=str(cwd), shell_command_prefix=shell_settings.shell_command_prefix)
    tools.extend(get_rust_tools())

    # Get skills
    resource_paths = TauResourcePaths()
    skills = load_skills(resource_paths)

    # Build system prompt — use custom Rust prompt with profile context
    profile_context = session_config.build_profile_context()
    full_system = RUST_SYSTEM_PROMPT + "\n\n" + profile_context

    manager = SessionManager()
    record = manager.create_session(cwd=cwd, model=selection.model)

    try:
        config = CodingSessionConfig(
            provider=provider,
            model=selection.model,
            storage=jsonl_session_storage(record.path),
            cwd=cwd,
            custom_system_prompt=full_system,
            tools=tools,
            resource_paths=resource_paths,
            session_id=record.id,
            session_manager=manager,
            provider_name=selection.provider.name,
            provider_settings=settings,
            runtime_provider_config=selection.provider,
            shell_command_prefix=shell_settings.shell_command_prefix,
        )

        session = await CodingSession.load(config)
        renderer = create_event_renderer(PrintOutputMode.text)

        try:
            async for event in session.prompt(prompt):
                renderer.render(event)
            return renderer.finish()
        finally:
            await session.aclose()
    finally:
        await provider.aclose()


# ── Helpers ───────────────────────────────────────────────────────────────


def _print_profiles() -> None:
    """Print all available Rust profiles in a formatted table."""
    typer.echo("\n🦀  Tua Agent — Rust Coding Profiles\n")
    typer.echo(f"{'Profile':<20} {'Guardrails':<40} {'Use When'}")
    typer.echo("-" * 90)
    for p in list_profiles():
        guards = []
        if p.forbid_unwrap: guards.append("no-unwrap")
        if p.forbid_unsafe: guards.append("no-unsafe")
        if p.require_doc_tests: guards.append("doc-tests")
        if p.enforce_clippy_pedantic: guards.append("clippy-pedantic")
        if not guards: guards.append("(relaxed)")
        guard_str = ", ".join(guards)
        typer.echo(f"{p.emoji} {p.name:<17} {guard_str:<40} {p.use_when[:50]}")
    typer.echo("")


def _detect_and_print_rust_project(cwd: Path) -> None:
    """Detect and print Rust project info."""
    cargo_toml = cwd / "Cargo.toml"
    if cargo_toml.exists():
        typer.echo(f"\n📦 Detected Rust project at: {cargo_toml}")
        try:
            content = cargo_toml.read_text()
            name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if name_match:
                typer.echo(f"   Crate: {name_match.group(1)}")
        except Exception:
            pass
    else:
        typer.echo(f"\n⚠️  No Cargo.toml found in {cwd}")
        typer.echo("   Tua works best inside a Rust project directory.")


def _detect_model() -> str:
    """Detect available model from environment."""
    if environ.get("DEEPSEEK_API_KEY"):
        return "deepseek-chat"
    if environ.get("ANTHROPIC_API_KEY"):
        return "claude-sonnet-4-20250514"
    if environ.get("OPENAI_API_KEY"):
        return "gpt-4o"
    return DEFAULT_MODEL


if __name__ == "__main__":
    app()
