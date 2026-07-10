"""Tua Agent CLI — Rust-specialized coding agent entry point.

Usage:
    tua                          Start interactive TUI (Rust mode)
    tua -p "prompt"              One-shot print mode with Rust expert
    tua --profile ferris         Start with a specific Rust profile
    tua --list-profiles          List available Rust profiles
    tua dashboard                Start web dashboard
    tua new <name>               Scaffold a new Rust project with Tua defaults
"""

from __future__ import annotations

import asyncio
import re
from os import environ
from pathlib import Path

import anyio
import typer

from tau_coding.provider_config import (
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
from tua_agent import __version__
from tua_agent.rust_profiles import get_profile, list_profiles
from tua_agent.rust_session import RustSessionConfig
from tua_agent.rust_system_prompt import RUST_SYSTEM_PROMPT
from tua_agent.rust_tools import get_rust_tools

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
    # If a subcommand was invoked, don't run main logic
    if ctx.invoked_subcommand is not None:
        return

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
    
    # Load config for defaults
    from tua_agent.config import TuaConfig
    tua_cfg = TuaConfig.load(work_dir)
    
    # Use config default profile if not explicitly set
    if profile == "rustacean" and tua_cfg.default_profile != "rustacean":
        profile = tua_cfg.default_profile

    typer.echo(f"🦀  Tua Agent v{__version__} — profile: {rust_profile.emoji} {rust_profile.name}")
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
        # ── Interactive TUI ───────────────────────────────────────────
        _detect_and_print_rust_project(work_dir)
        typer.echo("🖥️  Launching Tua TUI...")
        from tua_agent.tui import TuaTuiApp
        app = TuaTuiApp(profile=rust_profile.name, model=model, cwd=work_dir)
        app.run()


@app.command(name="dashboard")
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


@app.command()
def config(
    action: str = typer.Argument("show", help="show | set <key> <value>"),
    key: str | None = typer.Argument(None, help="Config key (e.g. profile.default, tools.timeout)"),
    value: str | None = typer.Argument(None, help="New value"),
):
    """View or edit Tua configuration."""
    from tua_agent.config import TuaConfig
    
    cfg = TuaConfig.load(Path.cwd())
    
    if action == "show":
        typer.echo("🦀  Tua Configuration\n")
        typer.echo(f"  [profile]")
        typer.echo(f"    default = \"{cfg.default_profile}\"")
        typer.echo(f"  [tools]")
        typer.echo(f"    timeout = {cfg.tool_timeout}")
        typer.echo(f"    max_output_chars = {cfg.max_output_chars}")
        typer.echo(f"  [dashboard]")
        typer.echo(f"    host = \"{cfg.dashboard_host}\"")
        typer.echo(f"    port = {cfg.dashboard_port}")
        typer.echo(f"  [rust]")
        typer.echo(f"    edition = \"{cfg.rust_edition}\"")
        typer.echo(f"    clippy_pedantic = {str(cfg.clippy_pedantic).lower()}")
        typer.echo(f"    require_doc_tests = {str(cfg.require_doc_tests).lower()}")
        typer.echo(f"\n  Config files:")
        typer.echo(f"    ~/.tua/config.toml          (user-global)")
        typer.echo(f"    <project>/.tua/config.toml  (project override)")
    elif action == "set" and key and value is not None:
        _set_config(Path.cwd(), key, value)
    else:
        typer.echo("Usage: tua config [show] | tua config set <key> <value>", err=True)
        raise typer.Exit(1)


@app.command()
def providers():
    """Show configured model providers."""
    from tau_coding.provider_config import load_provider_settings
    settings = load_provider_settings()
    typer.echo(f"🦀  Default provider: {settings.default_provider}")
    typer.echo(f"   Available providers:")
    for provider in settings.providers:
        model = getattr(provider, 'default_model', '?')
        active = " ←" if provider.name == settings.default_provider else ""
        typer.echo(f"     {provider.name}: {model}{active}")


def _set_config(project_dir: Path, key: str, value: str) -> None:
    """Set a config value in the project's .tua/config.toml."""
    import tomllib
    config_path = project_dir / ".tua" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    data: dict = {}
    if config_path.exists():
        try:
            data = tomllib.loads(config_path.read_text())
        except Exception:
            pass
    
    parts = key.split(".")
    if len(parts) != 2:
        typer.echo(f"❌ Key format: section.key (e.g. profile.default)", err=True)
        raise typer.Exit(1)
    
    section, field = parts
    data.setdefault(section, {})[field] = value
    
    # Write back as TOML
    lines = []
    for sec, fields in data.items():
        lines.append(f"[{sec}]")
        for k, v in fields.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif isinstance(v, str) and v.lower() in ("true", "false"):
                lines.append(f"{k} = {v.lower()}")
            else:
                lines.append(f'{k} = "{v}"')
        lines.append("")
    
    config_path.write_text("\n".join(lines))
    typer.echo(f"✅ {key} = {value}")
    typer.echo(f"   Saved to {config_path}")


@app.command()
def check(
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory"),
):
    """Run cargo check on the current Rust project."""
    _run_cargo("check", cwd)


@app.command()
def fix(
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory"),
):
    """Run cargo clippy --fix to auto-fix warnings."""
    _run_cargo("clippy", cwd, extra_args=["--fix", "--allow-dirty"])


@app.command()
def fmt(
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory"),
    check_only: bool = typer.Option(False, "--check", help="Only check formatting"),
):
    """Run cargo fmt on the current Rust project."""
    args = ["--check"] if check_only else []
    _run_cargo("fmt", cwd, extra_args=args)


@app.command()
def audit(
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory"),
):
    """Run cargo audit to check for security vulnerabilities."""
    _run_cargo("audit", cwd)


@app.command()
def test(
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory"),
):
    """Run cargo test on the current Rust project."""
    _run_cargo("test", cwd)


@app.command()
def new(
    name: str = typer.Argument(".", help="Project name or path ('.' for the current directory)"),
    bin: bool = typer.Option(True, "--bin/--lib", help="Create a binary crate (default) or a library crate"),
    edition: str = typer.Option("2021", "--edition", help="Rust edition to target"),
):
    """Scaffold a new Rust project with Tua defaults."""
    _new_project(name=name, binary=bin, edition=edition)


def _run_cargo(subcommand: str, cwd: str | None = None, extra_args: list[str] | None = None):
    """Run a cargo subcommand and stream output."""
    import subprocess
    work_dir = Path(cwd) if cwd else Path.cwd()
    cmd = ["cargo", subcommand] + (extra_args or [])
    typer.echo(f"🦀  Running: {' '.join(cmd)}")
    typer.echo(f"    in: {work_dir}")
    typer.echo("-" * 60)
    try:
        result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, timeout=120)
        if result.stdout:
            typer.echo(result.stdout)
        if result.stderr:
            typer.echo(result.stderr, err=True)
        if result.returncode == 0:
            typer.echo(f"\n✅ cargo {subcommand} passed")
        else:
            typer.echo(f"\n❌ cargo {subcommand} failed (exit {result.returncode})")
            raise typer.Exit(result.returncode)
    except FileNotFoundError:
        typer.echo("❌ cargo not found. Is Rust installed?")
        raise typer.Exit(1)


# ── `tua new` scaffolding ──────────────────────────────────────────────────

_CARGO_TOML_TEMPLATE = """\
[package]
name = "{crate_name}"
version = "0.1.0"
edition = "{edition}"
description = "A Rust project scaffolded by Tua Agent"
license = "MIT OR Apache-2.0"
rust-version = "1.74"

[dependencies]
anyhow = "1"
serde = { version = "1", features = ["derive"] }
toml = "0.8"
{clap_line}
[profile.release]
lto = true
codegen-units = 1
strip = true
"""

_MAIN_RS_TEMPLATE = """\
//! {display} — a Rust project scaffolded by Tua Agent.

use anyhow::Result;
use clap::Parser;

/// Command-line interface for {display}.
#[derive(Parser, Debug)]
#[command(name = "{crate_name}", version, about)]
struct Cli {
    /// Name to greet.
    #[arg(default_value = "world")]
    name: String,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    println!("Hello, {}! 🦀", cli.name);
    Ok(())
}
"""

_LIB_RS_TEMPLATE = """\
//! {display} — a Rust library scaffolded by Tua Agent.

use anyhow::Result;

/// Return a friendly greeting.
pub fn greet(name: &str) -> Result<String> {
    Ok(format!("Hello, {}! 🦀", name))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn greet_world() {
        assert_eq!(greet("world").unwrap(), "Hello, world! 🦀");
    }
}
"""

_RUSTFMT_TOML_TEMPLATE = """\
# rustfmt configuration — Tua defaults
edition = "{edition}"
max_width = 100
tab_spaces = 4
use_field_init_shorthand = true
use_try_shorthand = true
newline_style = "Unix"
"""

_TUA_CONFIG_TEMPLATE = """\
# Tua Agent project configuration
# Generated by `tua new`

[profile]
default = "rustacean"

[tools]
timeout = 600
max_output_chars = 16000

[dashboard]
host = "127.0.0.1"
port = 8765

[rust]
edition = "{edition}"
clippy_pedantic = false
require_doc_tests = false
"""

_GITIGNORE_TEMPLATE = """\
# Rust build artifacts
/target
debug/
**/*.rs.bk

# Tua Agent
.tua/cache/
.tua/logs/

# Environment
.env
.env.local

# Editor / IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store
"""


def _render(template: str, **fields: str) -> str:
    """Replace {placeholder} tokens without interpreting other braces."""
    out = template
    for key, value in fields.items():
        out = out.replace("{" + key + "}", value)
    return out


def _read_crate_name(cargo_toml: Path) -> str | None:
    """Extract the package name from a Cargo.toml, if present."""
    try:
        text = cargo_toml.read_text()
    except OSError:
        return None
    match = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def _new_project(name: str, binary: bool, edition: str) -> None:
    """Scaffold a new Rust project: run `cargo init`, then apply Tua defaults."""
    import subprocess

    cwd = Path.cwd()
    project_dir = cwd if name == "." else (cwd / name).resolve()

    # Refuse to clobber an existing Cargo project.
    if (project_dir / "Cargo.toml").exists():
        typer.echo(f"❌ Cargo.toml already exists in {project_dir}", err=True)
        typer.echo("   `tua new` won't overwrite an existing project.", err=True)
        raise typer.Exit(1)

    # Create the target directory for named projects.
    if name != ".":
        try:
            project_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            typer.echo(f"❌ Directory already exists: {project_dir}", err=True)
            raise typer.Exit(1)

    # Lay down the base crate with `cargo init`.
    cargo_cmd = ["cargo", "init", "--bin" if binary else "--lib", "--edition", edition]
    typer.echo(f"🦀  Running: {' '.join(cargo_cmd)}")
    typer.echo(f"    in: {project_dir}")
    try:
        result = subprocess.run(cargo_cmd, cwd=project_dir, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        typer.echo("❌ cargo not found. Is Rust installed? (https://rustup.rs)", err=True)
        raise typer.Exit(1)

    if result.returncode != 0:
        if result.stdout:
            typer.echo(result.stdout)
        if result.stderr:
            typer.echo(result.stderr, err=True)
        typer.echo(f"❌ cargo init failed (exit {result.returncode})", err=True)
        raise typer.Exit(result.returncode)

    # Use the name cargo validated (falls back to the directory name).
    crate_name = _read_crate_name(project_dir / "Cargo.toml") or project_dir.name

    # Apply Tua defaults over the generated files.
    clap_line = 'clap = { version = "4", features = ["derive"] }\n' if binary else ""
    display = crate_name.replace("-", " ")
    (project_dir / "Cargo.toml").write_text(
        _render(_CARGO_TOML_TEMPLATE, crate_name=crate_name, edition=edition, clap_line=clap_line)
    )
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    if binary:
        (src_dir / "main.rs").write_text(
            _render(_MAIN_RS_TEMPLATE, crate_name=crate_name, display=display)
        )
    else:
        (src_dir / "lib.rs").write_text(
            _render(_LIB_RS_TEMPLATE, crate_name=crate_name, display=display)
        )
    (project_dir / "rustfmt.toml").write_text(_render(_RUSTFMT_TOML_TEMPLATE, edition=edition))
    tua_config = project_dir / ".tua" / "config.toml"
    tua_config.parent.mkdir(parents=True, exist_ok=True)
    tua_config.write_text(_render(_TUA_CONFIG_TEMPLATE, edition=edition))
    (project_dir / ".gitignore").write_text(_GITIGNORE_TEMPLATE)

    typer.echo(f"\n✅ Created Rust project: {crate_name}")
    typer.echo(f"   in: {project_dir}")
    typer.echo("\n   Next steps:")
    if name != ".":
        typer.echo(f"     cd {name}")
    typer.echo("     cargo build")
    typer.echo("     tua        # start coding with Tua")


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
    from tau_coding.resources import TauResourcePaths
    from tau_coding.skills import load_skills
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
    """Detect available model from environment or provider defaults."""
    # Check explicit API keys first
    if environ.get("DEEPSEEK_API_KEY"):
        return "deepseek-chat"
    if environ.get("ANTHROPIC_API_KEY"):
        return "claude-sonnet-4-20250514"
    if environ.get("OPENAI_API_KEY"):
        return "gpt-4o"
    # Fall back to 9Router default model (free, already configured)
    try:
        settings = load_provider_settings()
        if settings.default_provider:
            prefs = settings.provider_preferences.get(settings.default_provider, {})
            return prefs.get("default_model", "glm/glm-5.2")
    except Exception:
        pass
    return "glm/glm-5.2"


if __name__ == "__main__":
    app()
