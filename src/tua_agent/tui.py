"""Tua Agent TUI — a Rust-specialized Textual terminal interface.

A dark-themed, two-pane TUI that replaces the "TUI coming next release" placeholder
in ``cli.py``. Left panel: detected Cargo project, active profile + guardrails,
toolchain tool availability, and live session stats. Right panel: scrollable agent
transcript plus a slash-command input.

The palette mirrors the web dashboard (``dashboard.py``): a #0d1117 base with a
#f74c00 Rust accent. No Dhamma / Buddhist content — Tua is a pure Rust companion.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from contextlib import suppress
from os import environ
from pathlib import Path
from time import monotonic

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, RichLog, Static

from tau_agent import (
    AgentEndEvent,
    AgentEvent,
    ErrorEvent,
    MessageDeltaEvent,
    MessageEndEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)

from tua_agent import __version__
from tua_agent.rust_profiles import RustProfile, get_profile, list_profiles
from tua_agent.rust_session import RustSessionConfig
from tua_agent.rust_system_prompt import RUST_SYSTEM_PROMPT
from tua_agent.rust_tools import RUST_TOOLS, get_rust_tools

# ── Theme (mirrors dashboard.py :root) ────────────────────────────────────────

PALETTE: dict[str, str] = {
    "bg": "#0d1117", "card": "#161b22", "border": "#30363d", "text": "#c9d1d9",
    "dim": "#8b949e", "accent": "#f74c00", "rust": "#dea584", "green": "#3fb950",
    "yellow": "#d29922", "red": "#f85149", "blue": "#58a6ff",
}

# Each registered Rust tool → the binary it shells out to, so we can show whether
# the toolchain component is actually on $PATH (✅ installed / ⚠️ missing).
_TOOL_BINARIES: dict[str, str] = {
    "cargo": "cargo", "rustc": "rustc", "rustfmt": "rustfmt", "clippy": "cargo-clippy",
    "rustup": "rustup", "cargo_audit": "cargo-audit", "cargo_outdated": "cargo-outdated",
    "cargo_udep": "cargo-udeps", "cargo_deny": "cargo-deny", "cargo_bench": "cargo",
    "cargo_doc": "cargo", "cargo_test_doc": "cargo", "wasm_pack": "wasm-pack",
}

TUA_CSS = f"""
Screen {{
    background: {PALETTE["bg"]};
    color: {PALETTE["text"]};
}}
#title-bar {{
    height: 1; dock: top; padding: 0 1;
    background: {PALETTE["card"]}; color: {PALETTE["rust"]};
}}
#body {{ height: 1fr; }}
#left-panel {{
    width: 36; padding: 1 1; background: {PALETTE["bg"]};
    border-right: solid {PALETTE["border"]};
}}
#right-panel {{ width: 1fr; background: {PALETTE["bg"]}; }}
#chat {{
    height: 1fr; padding: 0 1; background: {PALETTE["bg"]};
    border: solid {PALETTE["border"]};
}}
#prompt {{
    dock: bottom; height: 3; margin: 1 1 0 1; border: solid {PALETTE["border"]};
}}
#prompt:focus {{ border: solid {PALETTE["accent"]}; }}
#footer-bar {{
    dock: bottom; height: 1; padding: 0 1;
    background: {PALETTE["card"]}; color: {PALETTE["dim"]};
}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _detect_cargo_project(cwd: Path) -> dict[str, object]:
    """Read minimal project metadata from ``Cargo.toml`` (name/version/edition/deps)."""
    info: dict[str, object] = {"name": None, "version": None, "edition": None, "deps": 0}
    cargo_toml = cwd / "Cargo.toml"
    if not cargo_toml.exists():
        return info
    try:
        content = cargo_toml.read_text()
    except OSError:
        return info
    for field, pattern in (
        ("name", r'name\s*=\s*"([^"]+)"'),
        ("version", r'version\s*=\s*"([^"]+)"'),
        ("edition", r'edition\s*=\s*"([^"]+)"'),
    ):
        if match := re.search(pattern, content):
            info[field] = match.group(1)
    info["deps"] = len(re.findall(r"^\s*[a-zA-Z0-9_-]+\s*=\s", content, re.MULTILINE))
    return info


def _count_rust_files(cwd: Path) -> int:
    """Best-effort count of ``.rs`` source files under ``src/``."""
    src = cwd / "src"
    if not src.is_dir():
        return 0
    try:
        return sum(1 for _ in src.rglob("*.rs"))
    except OSError:
        return 0


def _tool_status() -> list[tuple[str, str, bool]]:
    """Return ``(display_name, binary, installed)`` per Rust tool, in registry order."""
    return [
        (tool.name.replace("_", " "), _TOOL_BINARIES.get(tool.name, tool.name),
         shutil.which(_TOOL_BINARIES.get(tool.name, tool.name)) is not None)
        for tool in RUST_TOOLS
    ]


def _active_guardrails(profile: RustProfile) -> list[tuple[str, bool]]:
    """Profile guardrails as ``(label, enabled)`` rows for the sidebar."""
    return [
        ("require cargo check", profile.require_cargo_check),
        ("enforce rustfmt", profile.enforce_rustfmt),
        ("forbid unwrap", profile.forbid_unwrap),
        ("forbid unsafe", profile.forbid_unsafe),
        ("require doc tests", profile.require_doc_tests),
        ("clippy pedantic", profile.enforce_clippy_pedantic),
    ]


def _summarize_args(arguments: Mapping[str, object]) -> str:
    """Render the most relevant argument of a tool call as a short string."""
    if not arguments:
        return ""
    for key in ("subcommand", "command", "action", "file", "path", "crate", "mode"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return _short(value)
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return _short(value)
    return ""


def _short(text: str, limit: int = 48) -> str:
    text = str(text).strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _detect_model() -> str:
    """Pick a model from the environment, mirroring ``cli._detect_model``."""
    if environ.get("DEEPSEEK_API_KEY"):
        return "deepseek-chat"
    if environ.get("ANTHROPIC_API_KEY"):
        return "claude-sonnet-4-20250514"
    if environ.get("OPENAI_API_KEY"):
        return "gpt-4o"
    from tau_coding.provider_config import DEFAULT_MODEL

    return DEFAULT_MODEL


# ── App ───────────────────────────────────────────────────────────────────────


class TuaTuiApp(App):
    """Tua Agent's interactive Rust-specialized terminal interface."""

    CSS = TUA_CSS
    TITLE = "Tua Agent"

    def __init__(
        self, *, profile: str = "rustacean", model: str | None = None, cwd: Path | None = None
    ) -> None:
        super().__init__()
        self.profile: RustProfile = get_profile(profile)
        self.requested_model: str | None = model
        self.cwd: Path = Path(cwd).resolve() if cwd else Path.cwd()
        self.project_info: dict[str, object] = {}
        # Agent backend (built lazily on first prompt).
        self._session = None  # type: ignore[assignment]
        self._provider = None  # type: ignore[assignment]
        self._resolved_model: str | None = None
        # Session stats.
        self._start = monotonic()
        self._messages = 0
        self._tools_run = 0
        self._tokens = 0
        self._assistant_buf = ""

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._render_title(), id="title-bar")
        with Horizontal(id="body"):
            with VerticalScroll(id="left-panel"):
                yield Static(self._render_project(), id="project", markup=True)
                yield Static(self._render_profile(), id="profile", markup=True)
                yield Static(self._render_tools(), id="tools", markup=True)
                yield Static(self._render_stats(), id="stats", markup=True)
            with Vertical(id="right-panel"):
                yield RichLog(id="chat", markup=False, wrap=True, auto_scroll=True, highlight=False)
                yield Input(placeholder="Ask Tua about your Rust project, or type /help …", id="prompt")
        yield Static(
            "  /help   /profile   /tools   /skills   /config   /clear          Ctrl+C to quit",
            id="footer-bar",
        )

    def on_mount(self) -> None:
        self.project_info = _detect_cargo_project(self.cwd)
        self._refresh_sidebar()
        self._welcome()
        self.set_interval(1.0, self._refresh_stats)
        self.query_one("#prompt", Input).focus()

    # ── Sidebar rendering ─────────────────────────────────────────────────────

    def _render_title(self) -> str:
        return f" 🦀 Tua Agent v{__version__}      [Profile: {self.profile.emoji} {self.profile.name}]"

    def _render_project(self) -> str:
        info = self.project_info or _detect_cargo_project(self.cwd)
        dim, rust = PALETTE["dim"], PALETTE["rust"]
        name = info.get("name") or "(no Cargo.toml)"
        lines = [f"[@{PALETTE['accent']} bold]📁 Project[/]"]
        lines.append(f"  [@{dim}]name    :[/] [@{rust}]{_short(str(name))}[/]")
        lines.append(f"  [@{dim}]version :[/] {info.get('version') or '—'}")
        lines.append(f"  [@{dim}]edition :[/] {info.get('edition') or '—'}")
        lines.append(f"  [@{dim}]deps    :[/] {info.get('deps', 0)}")
        lines.append(f"  [@{dim}]files   :[/] {_count_rust_files(self.cwd)} .rs")
        lines.append(f"  [@{dim}]path    :[/] [@{dim}]{_short(str(self.cwd), 28)}[/]")
        return "\n".join(lines)

    def _render_profile(self) -> str:
        dim, rust = PALETTE["dim"], PALETTE["rust"]
        rows = "\n".join(
            f"  [{'✅' if on else '⬜'}] [@{dim}]{label}[/]"
            for label, on in _active_guardrails(self.profile)
        )
        head = (
            f"\n[@{PALETTE['accent']} bold]🛡️ Profile[/]  "
            f"{self.profile.emoji} [@{rust} bold]{self.profile.name}[/]"
        )
        return f"{head}\n{rows}\n  [@{dim}]{_short(self.profile.use_when, 34)}[/]"

    def _render_tools(self) -> str:
        dim, green, yellow = PALETTE["dim"], PALETTE["green"], PALETTE["yellow"]
        status = _tool_status()
        ready = sum(1 for _, _, ok in status if ok)
        lines = [f"\n[@{PALETTE['accent']} bold]🔧 Tools[/]  [@{dim}]({ready}/{len(RUST_TOOLS)} ready)[/]"]
        for display, binary, installed in status:
            mark, colour = ("✅", green) if installed else ("⚠️", yellow)
            lines.append(f"  [{mark}] [@{colour}]{display:<13}[/] [@{dim}]{binary}[/]")
        return "\n".join(lines)

    def _render_stats(self) -> str:
        dim = PALETTE["dim"]
        model = self._resolved_model or self.requested_model or "—"
        elapsed = _format_elapsed(monotonic() - self._start)
        lines = [f"\n[@{PALETTE['accent']} bold]📊 Stats[/]"]
        lines.append(f"  [@{dim}]messages :[/] {self._messages}")
        lines.append(f"  [@{dim}]tools    :[/] {self._tools_run}")
        lines.append(f"  [@{dim}]tokens   :[/] ~{self._tokens or '—'}")
        lines.append(f"  [@{dim}]time     :[/] {elapsed}")
        lines.append(f"  [@{dim}]model    :[/] [@{dim}]{_short(str(model), 22)}[/]")
        # Cost estimate (DeepSeek ~$0.07/M input, ~$0.27/M output)
        if self._tokens:
            est_cost = self._tokens * 0.00000027  # rough blended rate
            lines.append(f"  [@{dim}]est cost :[/] ~${est_cost:.4f}")
        return "\n".join(lines)

    def _refresh_sidebar(self) -> None:
        with suppress(Exception):
            self.query_one("#title-bar", Static).update(self._render_title())
            self.query_one("#project", Static).update(self._render_project())
            self.query_one("#profile", Static).update(self._render_profile())
            self.query_one("#tools", Static).update(self._render_tools())
            self.query_one("#stats", Static).update(self._render_stats())

    def _refresh_stats(self) -> None:
        with suppress(Exception):
            self.query_one("#stats", Static).update(self._render_stats())

    # ── Chat helpers ──────────────────────────────────────────────────────────

    def _chat(self) -> RichLog:
        return self.query_one("#chat", RichLog)

    def _welcome(self) -> None:
        chat = self._chat()
        chat.write(Text(f"🦀 Tua Agent v{__version__} — Rust-specialized coding agent", style=PALETTE["rust"]))
        chat.write(Text(f"   Profile: {self.profile.emoji} {self.profile.name}   ·   cwd: {self.cwd}", style=PALETTE["dim"]))
        chat.write(Text("   Type a Rust question or task, or use /help, /profile, /tools, /skills, /clear.", style=PALETTE["dim"]))

    def _flush_assistant(self) -> None:
        """Write any buffered assistant deltas as one chat block with syntax highlighting."""
        body = self._assistant_buf.strip()
        self._assistant_buf = ""
        if not body:
            return
        self._messages += 1
        self._tokens += len(body) // 4 + 1  # rough estimate: ~4 chars per token
        chat = self._chat()
        # Split markdown code blocks and render with syntax highlighting
        parts = body.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Normal text
                if part.strip():
                    chat.write(Text(part.strip(), style=PALETTE["text"]))
            else:
                # Code block — detect language
                lines = part.split("\n", 1)
                lang = lines[0].strip() if lines else ""
                code = lines[1] if len(lines) > 1 else ""
                if not lang:
                    lang = "rust"  # default for Tua
                try:
                    chat.write(Syntax(code.strip(), lang, theme="monokai", line_numbers=False, word_wrap=True))
                except Exception:
                    chat.write(Text(code.strip(), style=PALETTE["dim"]))
        self._refresh_stats()

    # ── Input handling ────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text.startswith("/"):
            self._handle_command(text)
            return
        self._messages += 1
        self._tokens += len(text) // 4 + 1
        self._chat().write(Text("🧑 ", style=PALETTE["green"]) + Text(text, style=PALETTE["text"]))
        self._refresh_stats()
        self._run_agent(text)

    def _handle_command(self, text: str) -> None:
        chat = self._chat()
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            chat.write(Text("💬 Commands", style=PALETTE["blue"]))
            for line in (
                "   /profile [name]   show or switch the Rust coding profile",
                "   /tools            list Rust toolchain tools + availability",
                "   /skills           list bundled Rust skills",
                "   /clear            clear the chat transcript",
                "   /help             show this help",
                "   Ctrl+C            quit Tua",
            ):
                chat.write(Text(line, style=PALETTE["dim"]))
        elif cmd == "/clear":
            chat.clear()
            self._welcome()
        elif cmd == "/tools":
            chat.write(Text("🔧 Rust toolchain tools", style=PALETTE["blue"]))
            for display, binary, installed in _tool_status():
                mark, colour = ("✅", PALETTE["green"]) if installed else ("⚠️", PALETTE["yellow"])
                chat.write(Text(f"   {mark} {display:<13}", style=colour) + Text(f" {binary}", style=PALETTE["dim"]))
        elif cmd == "/skills":
            self._list_skills()
        elif cmd == "/config":
            self._show_config()
        elif cmd == "/profile":
            self._switch_profile(arg)
        else:
            chat.write(Text(f"Unknown command: {cmd}  (try /help)", style=PALETTE["red"]))

    def _switch_profile(self, arg: str) -> None:
        chat = self._chat()
        if not arg:
            chat.write(Text("🛡️ Available Rust profiles", style=PALETTE["blue"]))
            for profile in list_profiles():
                active = " ←" if profile.name == self.profile.name else ""
                chat.write(
                    Text(f"   {profile.emoji} {profile.name:<15}", style=PALETTE["rust"])
                    + Text(f" {profile.use_when}{active}", style=PALETTE["dim"])
                )
            return
        try:
            new_profile = get_profile(arg)
        except KeyError as exc:
            chat.write(Text(f"❌ {exc}", style=PALETTE["red"]))
            return
        self.profile = new_profile
        self._refresh_sidebar()
        self._invalidate_session()  # system prompt embeds the profile → rebuild next prompt
        chat.write(
            Text(f"✅ Switched to profile {new_profile.emoji} ", style=PALETTE["green"])
            + Text(new_profile.name, style=PALETTE["rust"])
        )

    def _show_config(self) -> None:
        """Display current Tua configuration in chat."""
        from tua_agent.config import TuaConfig
        chat = self._chat()
        cfg = TuaConfig.load(self.cwd)
        chat.write(Text("🦀  Tua Configuration", style=PALETTE["blue"]))
        for section, items in [
            ("Profile", [("default", cfg.default_profile)]),
            ("Tools", [("timeout", str(cfg.tool_timeout)), ("max_output_chars", str(cfg.max_output_chars))]),
            ("Dashboard", [("host", cfg.dashboard_host), ("port", str(cfg.dashboard_port))]),
            ("Rust", [("edition", cfg.rust_edition), ("clippy_pedantic", str(cfg.clippy_pedantic)), ("require_doc_tests", str(cfg.require_doc_tests))]),
        ]:
            chat.write(Text(f"  [{section}]", style=PALETTE["rust"]))
            for k, v in items:
                chat.write(Text(f"    {k} = {v}", style=PALETTE["dim"]))
        chat.write(Text(f"\n  Config files:", style=PALETTE["dim"]))
        chat.write(Text(f"    ~/.tua/config.toml", style=PALETTE["dim"]))
        user_cfg = Path.home() / ".tua" / "config.toml"
        proj_cfg = self.cwd / ".tua" / "config.toml"
        chat.write(Text(f"    {'✅' if user_cfg.exists() else '⬜'} {user_cfg}", style=PALETTE["dim"]))
        chat.write(Text(f"    {'✅' if proj_cfg.exists() else '⬜'} {proj_cfg}", style=PALETTE["dim"]))

    def _list_skills(self) -> None:
        chat = self._chat()
        try:
            from tau_coding.resources import TauResourcePaths
            from tau_coding.skills import load_skills

            skills = load_skills(TauResourcePaths())
        except Exception as exc:  # pragma: no cover - defensive
            chat.write(Text(f"⚠️  Could not load skills: {exc}", style=PALETTE["yellow"]))
            return
        if not skills:
            chat.write(Text("   (no skills bundled)", style=PALETTE["dim"]))
            return
        chat.write(Text(f"📚 Rust skills ({len(skills)})", style=PALETTE["blue"]))
        for skill in skills:
            desc = _short(getattr(skill, "description", None) or "", 44)
            chat.write(
                Text(f"   • {skill.name:<16}", style=PALETTE["rust"])
                + Text(f" {desc}", style=PALETTE["dim"])
            )

    # ── Agent backend ─────────────────────────────────────────────────────────

    async def _close_session(self) -> None:
        if self._session is not None:
            with suppress(Exception):
                await self._session.aclose()
            self._session = None
        if self._provider is not None:
            with suppress(Exception):
                await self._provider.aclose()
            self._provider = None

    def _invalidate_session(self) -> None:
        """Mark the backend stale so it rebuilds (with the new profile) next prompt."""
        self.run_worker(self._close_session(), exclusive=True, name="tua-close")

    async def _ensure_session(self) -> object:
        if self._session is not None:
            return self._session
        await self._close_session()

        from tau_coding.provider_config import load_provider_settings, resolve_provider_selection
        from tau_coding.provider_runtime import create_model_provider
        from tau_coding.resources import TauResourcePaths
        from tau_coding.session import CodingSession, CodingSessionConfig, jsonl_session_storage
        from tau_coding.session_manager import SessionManager
        from tau_coding.shell_config import load_shell_settings
        from tau_coding.thinking import DEFAULT_THINKING_LEVEL
        from tau_coding.tools import create_coding_tools

        settings = load_provider_settings()
        shell_settings = load_shell_settings()
        selection = resolve_provider_selection(settings, model=self.requested_model or _detect_model())
        provider = create_model_provider(
            selection.provider, model=selection.model, thinking_level=DEFAULT_THINKING_LEVEL
        )

        system_prompt = RUST_SYSTEM_PROMPT + "\n\n" + RustSessionConfig(
            profile=self.profile
        ).build_profile_context()

        tools = create_coding_tools(cwd=str(self.cwd), shell_command_prefix=shell_settings.shell_command_prefix)
        tools.extend(get_rust_tools())

        manager = SessionManager()
        record = manager.create_session(cwd=self.cwd, model=selection.model)
        config = CodingSessionConfig(
            provider=provider,
            model=selection.model,
            storage=jsonl_session_storage(record.path),
            cwd=self.cwd,
            custom_system_prompt=system_prompt,
            tools=tools,
            resource_paths=TauResourcePaths(),
            session_id=record.id,
            session_manager=manager,
            provider_name=selection.provider.name,
            provider_settings=settings,
            runtime_provider_config=selection.provider,
            shell_command_prefix=shell_settings.shell_command_prefix,
        )
        self._session = await CodingSession.load(config)
        self._provider = provider
        self._resolved_model = selection.model
        self._refresh_stats()
        return self._session

    @work(exclusive=True, name="tua-agent")
    async def _run_agent(self, prompt_text: str) -> None:
        """Stream one user turn through the Rust-specialized agent into the chat."""
        chat = self._chat()
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = True
        try:
            try:
                session = await self._ensure_session()
            except Exception as exc:
                msg = str(exc)
                chat.write(Text(f"⚠️  {msg}", style=PALETTE["yellow"]))
                if "API key" in msg or "Missing provider" in msg or "credentials" in msg.lower():
                    chat.write(Text("   💡 Run `tua providers` to see configured providers.", style=PALETTE["dim"]))
                    chat.write(Text("   💡 Set your API key: export PROVIDER_API_KEY=sk-...", style=PALETTE["dim"]))
                    chat.write(Text("   💡 Or use 9Router (free): tua config set provider.default 9router", style=PALETTE["dim"]))
                elif "model" in msg.lower():
                    chat.write(Text("   💡 Use `tua providers` to list available models.", style=PALETTE["dim"]))
                    chat.write(Text("   💡 Try: tua --model glm/glm-5.2 -p \"your prompt\"", style=PALETTE["dim"]))
                else:
                    chat.write(Text("   💡 Check `tua config show` and `tua providers` for setup help.", style=PALETTE["dim"]))
                return

            chat.write(Text("🤖 …", style=PALETTE["rust"]))
            assert session is not None
            try:
                async for event in session.prompt(prompt_text):
                    self._render_event(event)
                self._flush_assistant()
            except Exception as exc:
                self._flush_assistant()
                chat.write(Text(f"❌ {exc}", style=PALETTE["red"]))
        finally:
            prompt.disabled = False
            prompt.focus()
            self._refresh_stats()

    def _render_event(self, event: AgentEvent) -> None:
        chat = self._chat()
        if isinstance(event, MessageDeltaEvent):
            self._assistant_buf += event.delta
            return
        # Any non-delta event finalises the current assistant text block first.
        self._flush_assistant()
        if isinstance(event, MessageEndEvent):
            return  # deltas already carried the text
        if isinstance(event, ToolExecutionStartEvent):
            name = event.tool_call.name.replace("_", " ")
            summary = _summarize_args(event.tool_call.arguments)
            detail = Text(f" {summary}", style=PALETTE["dim"]) if summary else Text("")
            chat.write(Text(f"🔧 {name}", style=PALETTE["blue"]) + detail)
        elif isinstance(event, ToolExecutionEndEvent):
            ok = event.result.ok
            mark, colour = ("✅", PALETTE["green"]) if ok else ("⚠️", PALETTE["red"])
            chat.write(Text(f"   {mark} {event.result.name.replace('_', ' ')}", style=colour))
            self._tools_run += 1
        elif isinstance(event, ErrorEvent):
            chat.write(Text(f"❌ {event.message}", style=PALETTE["red"]))
        elif isinstance(event, AgentEndEvent):
            pass

    async def on_unmount(self) -> None:
        await self._close_session()


# ── Entrypoint ────────────────────────────────────────────────────────────────


def run(*, profile: str = "rustacean", model: str | None = None, cwd: Path | None = None) -> None:
    """Launch the Tua Agent TUI (used by ``cli.py`` when no -p prompt is given)."""
    TuaTuiApp(profile=profile, model=model, cwd=cwd).run()


if __name__ == "__main__":  # pragma: no cover
    run()
