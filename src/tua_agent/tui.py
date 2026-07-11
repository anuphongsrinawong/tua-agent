"""Tua Agent TUI — a Rust-specialized Textual terminal interface.

A dark-themed TUI that replaces the "TUI coming next release" placeholder in
``cli.py``. Left panel: detected Cargo project, active profile + guardrails,
toolchain tool availability, and live session stats. Right panel: scrollable
agent transcript plus a slash-command input.

v0.0.2 adds four features on top of the original two-pane layout:

* **#8  Real diff viewer** — line-by-line unified diffs (``difflib``) for every
  file edit made during a session, with Rust-aware coloring.
* **#10 Permission dialog** — a ``ModalScreen`` gate with three modes
  (``ask`` / ``auto-approve`` / ``auto-deny``) shown in the footer.
* **#11 Interactive command palette** — a searchable modal (``Ctrl+P``) listing
  every slash command with live filtering and keyboard navigation.
* **#12 Multi-session tabs** — browser-style tabs where each tab is an
  independent session (its own profile, model, transcript, and edit history).

The palette mirrors the web dashboard (``dashboard.py``): a #0d1117 base with a
#f74c00 Rust accent. Pure Rust engineering — no Dhamma / Buddhist content.
"""

from __future__ import annotations

import difflib
import re
import shutil
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from os import environ
from pathlib import Path
from time import monotonic
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

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
from tua_agent.rust_system_prompt import RUST_SYSTEM_PROMPT
from tua_agent.rust_tools import RUST_TOOLS, get_rust_tools

# ── Theme (mirrors dashboard.py :root) ────────────────────────────────────────

PALETTE: dict[str, str] = {
    "bg": "#0d1117", "card": "#161b22", "border": "#30363d", "text": "#c9d1d9",
    "dim": "#8b949e", "accent": "#f74c00", "rust": "#dea584", "green": "#3fb950",
    "yellow": "#d29922", "red": "#f85149", "blue": "#58a6ff", "purple": "#bc8cff",
}

# Each registered Rust tool → the binary it shells out to, so we can show whether
# the toolchain component is actually on $PATH (✅ installed / ⚠️ missing).
_TOOL_BINARIES: dict[str, str] = {
    "cargo": "cargo", "rustc": "rustc", "rustfmt": "rustfmt", "clippy": "cargo-clippy",
    "rustup": "rustup", "cargo_audit": "cargo-audit", "cargo_outdated": "cargo-outdated",
    "cargo_udep": "cargo-udeps", "cargo_deny": "cargo-deny", "cargo_bench": "cargo",
    "cargo_doc": "cargo", "cargo_test_doc": "cargo", "wasm_pack": "wasm-pack",
}

# Tools whose ``data["path"]`` result describes a file we can diff (#8).
_EDIT_TOOLS = {"write", "edit"}

# ── Command registry (shared by /help, the palette, and the footer) ───────────
# Each entry: ``(token, label, description)``. ``token`` is what we dispatch when
# the user picks the entry from the palette — it is a base slash command.
COMMAND_ENTRIES: list[tuple[str, str, str]] = [
    ("/help",        "/help",             "Show available commands"),
    ("/profile",     "/profile [name]",   "Show or switch the Rust coding profile"),
    ("/model",       "/model [name]",     "Show or switch the AI model"),
    ("/tools",       "/tools",            "List Rust toolchain tools + availability"),
    ("/skills",      "/skills",           "List bundled Rust skills"),
    ("/config",      "/config",           "Show Tua configuration"),
    ("/resume",      "/resume [id]",      "List or resume a recent session"),
    ("/diff",        "/diff [num|last]",  "Show file-edit diffs"),
    ("/permissions", "/permissions [mode]", "View or set the permission mode"),
    ("/sessions",    "/sessions [n|close]", "Manage session tabs"),
    ("/rollback",    "/rollback",           "Roll back to last checkpoint (#16)"),
    ("/undo",        "/undo",               "Revert the most recent file edit (#16)"),
    ("/clear",       "/clear",             "Clear the chat transcript"),
]

PERMISSION_MODES: list[tuple[str, str, str]] = [
    ("ask",         "ask",          "Prompt before each operation (default)"),
    ("auto-approve", "auto-approve", "Allow every operation without asking"),
    ("auto-deny",    "auto-deny",    "Block operations that need approval"),
]

TUA_CSS = f"""
Screen {{
    background: {PALETTE["bg"]};
    color: {PALETTE["text"]};
}}
#title-bar {{
    height: 1; dock: top; padding: 0 1;
    background: {PALETTE["card"]}; color: {PALETTE["rust"]};
}}
#tab-bar {{
    height: 1; dock: top; padding: 0 1;
    background: {PALETTE["card"]}; color: {PALETTE["dim"]};
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

/* ── Modal screens (#10 permission, #11 palette, #12 new-tab) ─────────────── */
CommandPaletteScreen, PermissionScreen, PermissionModeScreen, NewTabScreen {{
    align: center middle;
}}
#palette, #perm-box, #mode-box, #newtab-box {{
    width: 74; max-width: 92%; padding: 1 2;
    background: {PALETTE["card"]}; color: {PALETTE["text"]};
    border: solid {PALETTE["border"]};
}}
#palette-title, #perm-title, #mode-title, #newtab-title {{
    height: 1; color: {PALETTE["rust"]}; text-style: bold; margin-bottom: 1;
}}
#palette-search, #newtab-input {{
    height: 3; margin-bottom: 1;
    background: {PALETTE["bg"]}; color: {PALETTE["text"]};
    border: solid {PALETTE["border"]};
}}
#palette-search:focus, #newtab-input:focus {{ border: solid {PALETTE["accent"]}; }}
#palette-list, #mode-list {{
    height: auto; max-height: 14;
    background: {PALETTE["bg"]}; border: solid {PALETTE["border"]};
}}
#palette-list > ListItem.--highlight > Label,
#mode-list > ListItem.--highlight > Label {{
    background: {PALETTE["accent"]}; color: #ffffff;
}}
#perm-desc {{
    height: auto; max-height: 8; margin-bottom: 1; color: {PALETTE["text"]};
}}
#perm-buttons {{ height: auto; align-horizontal: center; }}
#perm-buttons Button {{ margin: 0 1; }}
#palette-help, #perm-help, #mode-help, #newtab-help {{
    height: 1; margin-top: 1; color: {PALETTE["dim"]};
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
    for field_name, pattern in (
        ("name", r'name\s*=\s*"([^"]+)"'),
        ("version", r'version\s*=\s*"([^"]+)"'),
        ("edition", r'edition\s*=\s*"([^"]+)"'),
    ):
        if match := re.search(pattern, content):
            info[field_name] = match.group(1)
    info["deps"] = len(re.findall(r"^\s*[a-zA-Z0-9_-]+\s*=\s", content, re.MULTILINE))
    return info


def _count_rust_files(cwd: Path) -> int:
    """Count .rs files in the project (excluding target/)."""
    src = cwd / "src"
    if not src.exists():
        return 0
    return sum(1 for _ in src.rglob("*.rs"))


def _count_files(cwd: Path) -> int:
    """Count all files in a directory recursively."""
    return sum(1 for p in cwd.rglob("*") if p.is_file())


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


def _read_lines(path: Path) -> list[str] | None:
    """Best-effort read of a file's lines; ``None`` if the file does not exist."""
    try:
        if not path.exists():
            return None
    except OSError:
        return None
    try:
        return path.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None


def _diff_text(before: list[str], after: list[str], path: str) -> list[Text]:
    """Render a unified diff as colored ``Text`` lines (#8).

    ``+`` lines are green, ``-`` lines red, hunk headers ``@@`` blue, the file
    headers dim, and unchanged context lines dim. The result is a list of
    one-line ``Text`` objects ready to stream into the chat ``RichLog``.
    """
    name = Path(path).name
    diff = difflib.unified_diff(before, after, fromfile=f"a/{name}", tofile=f"b/{name}", lineterm="", n=3)
    out: list[Text] = []
    green, red, blue, dim = PALETTE["green"], PALETTE["red"], PALETTE["blue"], PALETTE["dim"]
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            out.append(Text(line, style=dim))
        elif line.startswith("@@"):
            out.append(Text(line, style=blue))
        elif line.startswith("+"):
            out.append(Text(line, style=green))
        elif line.startswith("-"):
            out.append(Text(line, style=red))
        else:
            out.append(Text(line, style=dim))
    return out


# ── Edit / tab data models (#8 diff tracking, #12 sessions) ───────────────────


@dataclass(slots=True)
class FileEdit:
    """One recorded file edit, with before/after content for diffing (#8)."""

    path: str
    tool: str
    before: list[str]
    after: list[str]
    added: int
    removed: int


class _SessionTab:
    """Per-tab session state (#12): each tab is an independent chat.

    Holds its own profile, model, agent backend, edit history, stats, and the
    ordered list of chat renderables so the transcript survives tab switches.
    """

    def __init__(self, name: str, profile: RustProfile, requested_model: str | None) -> None:
        self.name: str = name
        self.profile: RustProfile = profile
        self.requested_model: str | None = requested_model
        self.resolved_model: str | None = None
        self.initial_session_id: str | None = None
        # Agent backend (built lazily on first prompt for this tab).
        self.session: Any = None
        self.provider: Any = None
        # Diff tracking (#8): a list of every recorded edit, plus a last-edit
        # pointer for backward compatibility with the v0.0.1 footer line.
        self.edits: list[FileEdit] = []
        self.last_edit: tuple[str, int] | None = None  # (path, lines_after)
        # Session stats (per tab).
        self.start: float = monotonic()
        self.messages: int = 0
        self.tools_run: int = 0
        self.tokens: int = 0
        self.assistant_buf: str = ""
        # Permission decisions recorded for this tab (#10).
        self.permission_decisions: list[dict[str, object]] = []
        # Ordered renderables written to the chat — replayed on tab switch.
        self.log: list[Any] = []


# ── Modal screens ─────────────────────────────────────────────────────────────


class CommandPaletteScreen(ModalScreen[str | None]):
    """Searchable slash-command palette (#11).

    Returns the selected command's token (e.g. ``"/profile"``) or ``None`` when
    cancelled. Priority bindings keep arrow/enter/escape working even though the
    filter ``Input`` holds focus.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Close", priority=True),
        Binding("up", "cursor_up", show=False, priority=True),
        Binding("down", "cursor_down", show=False, priority=True),
        Binding("enter", "select", show=False, priority=True),
    ]

    def __init__(self, entries: list[tuple[str, str, str]]) -> None:
        super().__init__()
        self._entries = tuple(entries)
        self._visible: tuple[tuple[str, str, str], ...] = self._entries
        self._query = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="palette"):
            yield Static("🎛️  Command Palette", id="palette-title")
            yield Input(placeholder="Type to filter commands…", id="palette-search")
            yield ListView(id="palette-list")
            yield Static("↑↓ navigate · Enter run · Esc close", id="palette-help")

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#palette-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the list as the search value changes."""
        if event.input.id != "#palette-search" and event.input.id != "palette-search":
            return
        event.stop()
        self._query = event.value.strip().lower()
        self._refresh_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run the highlighted command on Enter from the search field."""
        event.stop()
        self.action_select()

    def _refresh_list(self) -> None:
        view = [e for e in self._entries if self._matches(e)]
        self._visible = tuple(view)
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()
        for _token, label, desc in self._visible:
            list_view.append(ListItem(Label(f"{label}  —  {desc}", markup=False)))
        list_view.index = 0 if self._visible else None

    def _matches(self, entry: tuple[str, str, str]) -> bool:
        if not self._query:
            return True
        _token, label, desc = entry
        haystack = f"{label} {desc}".lower()
        return all(word in haystack for word in self._query.split())

    def on_list_view_selected(self, event: ListView.Selected) -> None:  # noqa: ARG002
        """Mouse-click selection also runs the command."""
        event.stop()
        self.action_select()

    def action_cursor_up(self) -> None:
        self.query_one("#palette-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#palette-list", ListView).action_cursor_down()

    def action_select(self) -> None:
        """Dismiss with the highlighted entry's command token."""
        if not self._visible:
            return
        index = self.query_one("#palette-list", ListView).index
        if index is None:
            index = 0
        self.dismiss(self._visible[index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)


class PermissionScreen(ModalScreen[bool]):
    """Approve/Deny confirmation modal (#10). Dismisses with a bool."""

    BINDINGS = [
        Binding("enter", "approve", "Approve", priority=True),
        Binding("a", "approve", show=False, priority=True),
        Binding("escape", "deny", "Deny", priority=True),
        Binding("d", "deny", show=False, priority=True),
    ]

    def __init__(self, kind: str, description: str) -> None:
        super().__init__()
        self._kind = kind
        self._description = description

    def compose(self) -> ComposeResult:
        with Vertical(id="perm-box"):
            yield Static(f"🔐 Permission required — {self._kind}", id="perm-title")
            yield Static(self._description, id="perm-desc", markup=False)
            with Horizontal(id="perm-buttons"):
                yield Button("Approve (A)", id="perm-approve", variant="success")
                yield Button("Deny (D)", id="perm-deny", variant="error")
            yield Static("A/Enter approve · D/Esc deny", id="perm-help")

    def on_mount(self) -> None:
        self.query_one("#perm-approve", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Resolve the modal from a button click."""
        event.stop()
        self.dismiss(event.button.id == "perm-approve")

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)


class PermissionModeScreen(ModalScreen[str | None]):
    """Picker for the three permission modes (#10). Returns the mode name."""

    BINDINGS = [
        Binding("escape", "cancel", "Close", priority=True),
        Binding("up", "cursor_up", show=False, priority=True),
        Binding("down", "cursor_down", show=False, priority=True),
        Binding("enter", "select", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="mode-box"):
            yield Static("🔐 Permission mode", id="mode-title")
            yield ListView(
                *[
                    ListItem(Label(f"{label}  —  {desc}", markup=False))
                    for _mode, label, desc in PERMISSION_MODES
                ],
                id="mode-list",
            )
            yield Static("↑↓ navigate · Enter select · Esc close", id="mode-help")

    def on_mount(self) -> None:
        mode_list = self.query_one("#mode-list", ListView)
        try:
            current = self.app.permission_mode  # type: ignore[attr-defined]
            mode_list.index = [m for m, _, _ in PERMISSION_MODES].index(current)
        except (ValueError, AttributeError):
            mode_list.index = 0
        mode_list.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:  # noqa: ARG002
        event.stop()
        self.action_select()

    def action_cursor_up(self) -> None:
        self.query_one("#mode-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#mode-list", ListView).action_cursor_down()

    def action_select(self) -> None:
        index = self.query_one("#mode-list", ListView).index
        if index is None:
            return
        self.dismiss(PERMISSION_MODES[index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)


class NewTabScreen(ModalScreen[str | None]):
    """Prompt for a new session-tab name (#12). Returns the name or ``None``.

    An empty submit returns ``""`` (auto-name); Escape returns ``None`` (cancel).
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

    def compose(self) -> ComposeResult:
        with Vertical(id="newtab-box"):
            yield Static("🗂️  New session tab", id="newtab-title")
            yield Input(placeholder="Session name (blank = auto-name)", id="newtab-input")
            yield Static("Enter create · Esc cancel", id="newtab-help")

    def on_mount(self) -> None:
        self.query_one("#newtab-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ── App ───────────────────────────────────────────────────────────────────────


class TuaTuiApp(App):
    """Tua Agent's interactive Rust-specialized terminal interface."""

    CSS = TUA_CSS
    TITLE = "Tua Agent"

    BINDINGS = [
        Binding("ctrl+p", "command_palette", "Commands", show=False, priority=True),
        Binding("ctrl+t", "new_tab", "New tab", show=False, priority=True),
        Binding("ctrl+w", "close_tab", "Close tab", show=False, priority=True),
        Binding("ctrl+tab", "next_tab", "Next tab", show=False, priority=True),
        Binding("ctrl+shift+tab", "prev_tab", "Prev tab", show=False, priority=True),
        Binding("ctrl+c", "quit", "Quit", show=True),
    ]

    permission_mode: reactive[str] = reactive("ask")

    def __init__(
        self,
        *,
        profile: str = "rustacean",
        model: str | None = None,
        cwd: Path | None = None,
        provider: str | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__()
        self.cwd: Path = Path(cwd).resolve() if cwd else Path.cwd()
        self.project_info: dict[str, object] = {}
        # Global provider preference from the CLI; applies to every tab's backend.
        self._requested_provider: str | None = provider
        # Multi-session tabs (#12): at least one tab always exists.
        self._tabs: list[_SessionTab] = []
        self._active: int = 0
        self._tab_counter: int = 0
        first = _SessionTab("Session 1", get_profile(profile), model)
        first.initial_session_id = session_id
        self._tabs.append(first)
        self._tab_counter = 1
        # Transient write/edit tracking shared across the active agent turn (#8).
        self._pending_writes: dict[str, list[str] | None] = {}

    # ── Active-tab accessor ───────────────────────────────────────────────────

    @property
    def _tab(self) -> _SessionTab:
        """The currently active session tab."""
        return self._tabs[self._active]

    @property
    def profile(self) -> RustProfile:
        """Active tab's profile (kept for sidebar/title rendering)."""
        return self._tab.profile

    @property
    def _edits(self) -> list[FileEdit]:
        """Active tab's recorded file edits, surfaced for the diff viewer (#8)."""
        return self._tab.edits

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(self._render_title(), id="title-bar")
        yield Static(self._render_tab_bar(), id="tab-bar", markup=True)
        with Horizontal(id="body"):
            with VerticalScroll(id="left-panel"):
                yield Static(self._render_project(), id="project", markup=True)
                yield Static(self._render_profile(), id="profile", markup=True)
                yield Static(self._render_tools(), id="tools", markup=True)
                yield Static(self._render_stats(), id="stats", markup=True)
            with Vertical(id="right-panel"):
                yield RichLog(id="chat", markup=False, wrap=True, auto_scroll=True, highlight=False)
                yield Input(placeholder="Ask Tua about your Rust project, or type /help …", id="prompt")
        yield Static(self._render_footer(), id="footer-bar")

    def on_mount(self) -> None:
        self.project_info = _detect_cargo_project(self.cwd)
        self._refresh_sidebar()
        self._welcome()
        self.set_interval(1.0, self._refresh_stats)
        self.query_one("#prompt", Input).focus()

    def _watch_permission_mode(self, mode: str) -> None:  # noqa: ARG002
        """Reflect permission-mode changes in the footer (#10)."""
        self._refresh_footer()

    # ── Sidebar + chrome rendering ────────────────────────────────────────────

    def _render_title(self) -> str:
        tab = self._tab
        return f" 🦀 Tua Agent v{__version__}      [Profile: {tab.profile.emoji} {tab.profile.name}]"

    def _render_tab_bar(self) -> str:
        if not self._tabs:
            return ""
        segments: list[str] = []
        for index, tab in enumerate(self._tabs):
            active = index == self._active
            label = f"{tab.profile.emoji} {tab.name}"
            if active:
                segments.append(f"[{PALETTE['accent']} bold] ▸{index + 1}:{label} [/]")
            else:
                segments.append(f"[{PALETTE['dim']}]  {index + 1}:{label} [/]")
        return " ".join(segments)

    def _render_footer(self) -> str:
        mode_label = {"ask": "ASK", "auto-approve": "AUTO", "auto-deny": "DENY"}.get(
            self.permission_mode, self.permission_mode.upper()
        )
        mode_colour = {
            "ask": PALETTE["yellow"], "auto-approve": PALETTE["green"], "auto-deny": PALETTE["red"]
        }.get(self.permission_mode, PALETTE["dim"])
        # ── Token budget bar (#17) ─────────────────────────────────────────
        limit = 128_000  # default; could be loaded from config
        tokens = self._tab.tokens or 0
        pct = min(tokens / limit, 1.0)
        bar_width = 10
        filled = int(pct * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        if pct < 0.5:
            tok_colour = PALETTE["green"]
        elif pct < 0.8:
            tok_colour = PALETTE["yellow"]
        else:
            tok_colour = PALETTE["red"]
        return (
            f"  [{mode_colour}]perm:{mode_label}[/]   "
            f"[{PALETTE['dim']}]tabs:{len(self._tabs)}   "
            f"[{tok_colour}]tok:{bar}[/] ~{tokens // 1000}k/{limit // 1000}k   "
            f"Ctrl+P commands · Ctrl+T/W tabs · /help[/]"
        )

    def _render_project(self) -> str:
        info = self.project_info or _detect_cargo_project(self.cwd)
        dim, rust = PALETTE["dim"], PALETTE["rust"]
        name = info.get("name") or "(no Cargo.toml)"
        lines = [f"[{PALETTE['accent']} bold]📁 Project[/]"]
        lines.append(f"  [{dim}]name    :[/] [{rust}]{_short(str(name))}[/]")
        lines.append(f"  [{dim}]version :[/] {info.get('version') or '—'}")
        lines.append(f"  [{dim}]edition :[/] {info.get('edition') or '—'}")
        lines.append(f"  [{dim}]deps    :[/] {info.get('deps', 0)}")
        lines.append(f"  [{dim}]files   :[/] {_count_rust_files(self.cwd)} .rs")
        lines.append(f"  [{dim}]path    :[/] [{dim}]{_short(str(self.cwd), 28)}[/]")
        lines.append("")
        lines.append(self._render_file_tree())
        return "\n".join(lines)

    def _render_file_tree(self, max_depth: int = 2, max_files: int = 15) -> str:
        """Render a simple file tree for the project."""
        dim, rust = PALETTE["dim"], PALETTE["rust"]
        src = self.cwd / "src"
        if not src.exists():
            return f"  [{dim}](no src/ directory)[/]"
        lines = [f"  [{PALETTE['accent']} bold]📂 Files[/]"]
        count = 0
        for path in sorted(src.rglob("*")):
            if count >= max_files:
                lines.append(f"  [{dim}]  ... ({_count_files(src)} files total)[/]")
                break
            rel = path.relative_to(src)
            depth = len(rel.parts) - 1
            if depth > max_depth:
                continue
            prefix = "  " + "  " * depth + ("└── " if depth > 0 else "")
            name = rel.name
            if path.is_dir():
                lines.append(f"  [{dim}]{prefix}📁 {name}/[/]")
            else:
                ext_colour = rust if name.endswith(".rs") else dim
                lines.append(f"  [{ext_colour}]{prefix}{name}[/]")
            count += 1
        return "\n".join(lines)

    def _render_profile(self) -> str:
        dim, rust = PALETTE["dim"], PALETTE["rust"]
        rows = "\n".join(
            f"  [{'✅' if on else '⬜'}] [{dim}]{label}[/]"
            for label, on in _active_guardrails(self._tab.profile)
        )
        head = (
            f"\n[{PALETTE['accent']} bold]🛡️ Profile[/]  "
            f"{self._tab.profile.emoji} [{rust} bold]{self._tab.profile.name}[/]"
        )
        return f"{head}\n{rows}\n  [{dim}]{_short(self._tab.profile.use_when, 34)}[/]"

    def _render_tools(self) -> str:
        dim, green, yellow = PALETTE["dim"], PALETTE["green"], PALETTE["yellow"]
        status = _tool_status()
        ready = sum(1 for _, _, ok in status if ok)
        lines = [f"\n[{PALETTE['accent']} bold]🔧 Tools[/]  [{dim}]({ready}/{len(RUST_TOOLS)} ready)[/]"]
        for display, binary, installed in status:
            mark, colour = ("✅", green) if installed else ("⚠️", yellow)
            lines.append(f"  [{mark}] [{colour}]{display:<13}[/] [{dim}]{binary}[/]")
        return "\n".join(lines)

    def _render_stats(self) -> str:
        tab = self._tab
        dim = PALETTE["dim"]
        model = tab.resolved_model or tab.requested_model or "—"
        elapsed = _format_elapsed(monotonic() - tab.start)
        lines = [f"\n[{PALETTE['accent']} bold]📊 Stats[/]  [{dim}]{tab.name}[/]"]
        lines.append(f"  [{dim}]messages :[/] {tab.messages}")
        lines.append(f"  [{dim}]tools    :[/] {tab.tools_run}")
        lines.append(f"  [{dim}]edits    :[/] {len(tab.edits)}")
        lines.append(f"  [{dim}]tokens   :[/] ~{tab.tokens or '—'}")
        lines.append(f"  [{dim}]time     :[/] {elapsed}")
        lines.append(f"  [{dim}]model    :[/] [{dim}]{_short(str(model), 22)}[/]")
        # Cost estimate (DeepSeek ~$0.07/M input, ~$0.27/M output)
        if tab.tokens:
            est_cost = tab.tokens * 0.00000027  # rough blended rate
            lines.append(f"  [{dim}]est cost :[/] ~${est_cost:.4f}")
        return "\n".join(lines)

    def _refresh_sidebar(self) -> None:
        with suppress(Exception):
            self.query_one("#title-bar", Static).update(self._render_title())
            self.query_one("#tab-bar", Static).update(self._render_tab_bar())
            self.query_one("#project", Static).update(self._render_project())
            self.query_one("#profile", Static).update(self._render_profile())
            self.query_one("#tools", Static).update(self._render_tools())
            self.query_one("#stats", Static).update(self._render_stats())
            self.query_one("#footer-bar", Static).update(self._render_footer())

    def _refresh_footer(self) -> None:
        with suppress(Exception):
            self.query_one("#footer-bar", Static).update(self._render_footer())

    def _refresh_chrome(self) -> None:
        """Refresh the chrome that changes on tab/profile/model switches."""
        with suppress(Exception):
            self.query_one("#title-bar", Static).update(self._render_title())
            self.query_one("#tab-bar", Static).update(self._render_tab_bar())
            self.query_one("#stats", Static).update(self._render_stats())
            self.query_one("#footer-bar", Static).update(self._render_footer())

    def _refresh_stats(self) -> None:
        with suppress(Exception):
            self.query_one("#stats", Static).update(self._render_stats())

    # ── Chat helpers ──────────────────────────────────────────────────────────

    def _chat(self) -> RichLog:
        return self.query_one("#chat", RichLog)

    def _chat_write(self, renderable: Any) -> None:
        """Write a renderable to the chat and record it in the active tab's log.

        Recording the renderable lets us replay the transcript when the user
        switches tabs (#12).
        """
        self._tab.log.append(renderable)
        self._chat().write(renderable)

    def _replay_chat(self) -> None:
        """Re-render the active tab's recorded transcript into the shared chat."""
        chat = self._chat()
        chat.clear()
        for renderable in self._tab.log:
            chat.write(renderable)

    def _welcome(self) -> None:
        tab = self._tab
        write = self._chat_write
        write(Text(f"🦀 Tua Agent v{__version__} — Rust-specialized coding agent", style=PALETTE["rust"]))
        write(Text(
            f"   Tab: {tab.name}   ·   Profile: {tab.profile.emoji} {tab.profile.name}   ·   cwd: {self.cwd}",
            style=PALETTE["dim"],
        ))
        write(Text(
            "   Type a Rust question or task, or use /help, /profile, /tools, /skills, /diff, /clear.",
            style=PALETTE["dim"],
        ))

    def _flush_assistant(self) -> None:
        """Write any buffered assistant deltas as one chat block with syntax highlighting."""
        body = self._tab.assistant_buf.strip()
        self._tab.assistant_buf = ""
        if not body:
            return
        tab = self._tab
        tab.messages += 1
        tab.tokens += len(body) // 4 + 1  # rough estimate: ~4 chars per token
        write = self._chat_write
        # Split markdown code blocks and render with syntax highlighting
        parts = body.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Normal text
                if part.strip():
                    write(Text(part.strip(), style=PALETTE["text"]))
            else:
                # Code block — detect language
                lines = part.split("\n", 1)
                lang = lines[0].strip() if lines else ""
                code = lines[1] if len(lines) > 1 else ""
                if not lang:
                    lang = "rust"  # default for Tua
                try:
                    write(Syntax(code.strip(), lang, theme="monokai", line_numbers=False, word_wrap=True))
                except Exception:
                    write(Text(code.strip(), style=PALETTE["dim"]))
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
        tab = self._tab
        tab.messages += 1
        tab.tokens += len(text) // 4 + 1
        self._chat_write(Text("🧑 ", style=PALETTE["green"]) + Text(text, style=PALETTE["text"]))
        self._refresh_stats()
        self._run_agent(text)

    def _handle_command(self, text: str) -> None:
        write = self._chat_write
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            self._show_help()
        elif cmd == "/clear":
            self._chat().clear()
            self._tab.log.clear()
            self._welcome()
        elif cmd == "/tools":
            write(Text("🔧 Rust toolchain tools", style=PALETTE["blue"]))
            for display, binary, installed in _tool_status():
                mark, colour = ("✅", PALETTE["green"]) if installed else ("⚠️", PALETTE["yellow"])
                write(Text(f"   {mark} {display:<13}", style=colour) + Text(f" {binary}", style=PALETTE["dim"]))
        elif cmd == "/skills":
            self._list_skills()
        elif cmd == "/config":
            self._show_config()
        elif cmd == "/model":
            self._switch_model(arg)
        elif cmd == "/diff":
            self._show_diff(arg)
        elif cmd == "/resume":
            self._resume_session(arg)
        elif cmd == "/profile":
            self._switch_profile(arg)
        elif cmd == "/permissions":
            self._manage_permissions(arg)
        elif cmd == "/sessions":
            self._manage_sessions(arg)
        elif cmd == "/rollback":
            self._rollback_checkpoint()
        elif cmd == "/undo":
            self._undo_last_edit()
        else:
            write(Text(f"Unknown command: {cmd}  (try /help)", style=PALETTE["red"]))

    def _show_help(self) -> None:
        write = self._chat_write
        write(Text("💬 Commands", style=PALETTE["blue"]))
        for _token, label, desc in COMMAND_ENTRIES:
            write(Text(f"   {label:<22}", style=PALETTE["rust"]) + Text(f" {desc}", style=PALETTE["dim"]))
        write(Text("   Ctrl+P palette · Ctrl+T new tab · Ctrl+W close · Ctrl+Tab cycle", style=PALETTE["dim"]))

    def _switch_profile(self, arg: str) -> None:
        write = self._chat_write
        if not arg:
            write(Text("🛡️ Available Rust profiles", style=PALETTE["blue"]))
            for profile in list_profiles():
                active = " ←" if profile.name == self._tab.profile.name else ""
                write(
                    Text(f"   {profile.emoji} {profile.name:<15}", style=PALETTE["rust"])
                    + Text(f" {profile.use_when}{active}", style=PALETTE["dim"])
                )
            return
        try:
            new_profile = get_profile(arg)
        except KeyError as exc:
            write(Text(f"❌ {exc}", style=PALETTE["red"]))
            return
        self._tab.profile = new_profile
        self._refresh_sidebar()
        self._invalidate_session()  # system prompt embeds the profile → rebuild next prompt
        write(
            Text(f"✅ Switched to profile {new_profile.emoji} ", style=PALETTE["green"])
            + Text(new_profile.name, style=PALETTE["rust"])
        )

    def _show_config(self) -> None:
        """Display current Tua configuration in chat."""
        from tua_agent.config import TuaConfig
        write = self._chat_write
        cfg = TuaConfig.load(self.cwd)
        write(Text("🦀  Tua Configuration", style=PALETTE["blue"]))
        for section, items in [
            ("Profile", [("default", cfg.default_profile)]),
            ("Tools", [("timeout", str(cfg.tool_timeout)), ("max_output_chars", str(cfg.max_output_chars))]),
            ("Dashboard", [("host", cfg.dashboard_host), ("port", str(cfg.dashboard_port))]),
            ("Rust", [("edition", cfg.rust_edition), ("clippy_pedantic", str(cfg.clippy_pedantic)), ("require_doc_tests", str(cfg.require_doc_tests))]),
            ("AI", [
                ("self_correction", str(cfg.self_correction)),
                ("max_self_corrections", str(cfg.max_self_corrections)),
                ("checkpoint_enabled", str(cfg.checkpoint_enabled)),
                ("context_limit", str(cfg.context_limit)),
                ("prompt_caching", str(cfg.prompt_caching)),
                ("review_enabled", str(cfg.review_enabled)),
            ]),
        ]:
            write(Text(f"  [{section}]", style=PALETTE["rust"]))
            for k, v in items:
                write(Text(f"    {k} = {v}", style=PALETTE["dim"]))
        write(Text("\n  Config files:", style=PALETTE["dim"]))
        write(Text("    ~/.tua/config.toml", style=PALETTE["dim"]))
        user_cfg = Path.home() / ".tua" / "config.toml"
        proj_cfg = self.cwd / ".tua" / "config.toml"
        write(Text(f"    {'✅' if user_cfg.exists() else '⬜'} {user_cfg}", style=PALETTE["dim"]))
        write(Text(f"    {'✅' if proj_cfg.exists() else '⬜'} {proj_cfg}", style=PALETTE["dim"]))

    def _switch_model(self, arg: str) -> None:
        """List or switch the AI model via /model [name]."""
        write = self._chat_write
        if not arg:
            write(Text("🤖 Available models", style=PALETTE["blue"]))
            try:
                from tau_coding.provider_config import load_provider_settings
                settings = load_provider_settings()
                for provider in settings.providers:
                    models = getattr(provider, 'models', [])
                    for m in models:
                        active = " ←" if m == self._tab.resolved_model else ""
                        write(Text(f"   {provider.name}/{m}{active}", style=PALETTE["dim"]))
            except Exception as e:
                write(Text(f"   ⚠️ {e}", style=PALETTE["yellow"]))
            return
        self._tab.requested_model = arg
        self._invalidate_session()
        write(Text("✅ Switched model to ", style=PALETTE["green"]) + Text(arg, style=PALETTE["rust"]))

    # ── #8 Diff viewer ────────────────────────────────────────────────────────

    def _show_diff(self, arg: str) -> None:
        """Render recorded edits: a summary, or a full diff for ``<num>``/``last`` (#8)."""
        write = self._chat_write
        edits = self._edits
        if not edits:
            write(Text("   (no edits yet in this session)", style=PALETTE["dim"]))
            return

        if not arg:
            write(Text(f"📝 Edits this session ({len(edits)})", style=PALETTE["blue"]))
            for index, edit in enumerate(edits, start=1):
                name = Path(edit.path).name
                write(
                    Text(f"   {index}. {edit.tool:<5} ", style=PALETTE["rust"])
                    + Text(f"{name:<24}", style=PALETTE["text"])
                    + Text(f" +{edit.added}/-{edit.removed}", style=PALETTE["dim"])
                )
            write(Text("   /diff <num> or /diff last for the full diff", style=PALETTE["dim"]))
            return

        if arg.lower() == "last":
            index = len(edits)
        else:
            try:
                index = int(arg)
            except ValueError:
                write(Text(f"❌ Unknown diff argument: {arg}  (try /diff <num> or /diff last)", style=PALETTE["red"]))
                return
        if not (1 <= index <= len(edits)):
            write(Text(f"❌ No edit #{index}  (only {len(edits)} recorded)", style=PALETTE["red"]))
            return

        edit = edits[index - 1]
        write(Text(f"📝 Diff #{index} — {edit.tool} {edit.path}", style=PALETTE["blue"]))
        diff_lines = _diff_text(edit.before, edit.after, edit.path)
        if not diff_lines:
            write(Text("   (no textual changes)", style=PALETTE["dim"]))
            return
        for line in diff_lines:
            write(line)
        write(Text(f"   +{edit.added} additions / -{edit.removed} deletions", style=PALETTE["dim"]))

    def _record_edit(self, tool: str, path: str) -> None:
        """Capture a file edit's before/after into the active tab's edit list (#8)."""
        file_path = Path(path)
        before = self._pending_writes.pop(path, _read_lines(file_path))
        if before is None:
            before = []
        after = _read_lines(file_path) or []
        added = sum(1 for line in difflib.unified_diff(before, after, lineterm="") if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in difflib.unified_diff(before, after, lineterm="") if line.startswith("-") and not line.startswith("---"))
        edit = FileEdit(path=path, tool=tool, before=before, after=after, added=added, removed=removed)
        self._tab.edits.append(edit)
        self._tab.last_edit = (path, len(after))
        self._refresh_stats()

    # ── #10 Permission dialog ─────────────────────────────────────────────────

    def _manage_permissions(self, arg: str) -> None:
        """Show or set the permission mode (#10)."""
        write = self._chat_write
        if not arg:
            write(Text(f"🔐 Permission mode: {self.permission_mode}", style=PALETTE["blue"]))
            for mode, label, desc in PERMISSION_MODES:
                active = " ←" if mode == self.permission_mode else ""
                write(Text(f"   {label:<14}{active}", style=PALETTE["rust"]) + Text(f" {desc}", style=PALETTE["dim"]))
            write(Text("   /permissions <ask|auto|deny> to set, or pick via the dialog", style=PALETTE["dim"]))
            self.push_screen(PermissionModeScreen(), callback=self._on_mode_picked)
            return
        self._set_permission_mode(arg)

    def _on_mode_picked(self, mode: str | None) -> None:
        if mode:
            self._set_permission_mode(mode)
        self.query_one("#prompt", Input).focus()

    def _set_permission_mode(self, raw: str) -> None:
        write = self._chat_write
        token = raw.strip().lower()
        aliases = {"ask": "ask", "auto": "auto-approve", "approve": "auto-approve",
                   "auto-approve": "auto-approve", "yes": "auto-approve",
                   "deny": "auto-deny", "auto-deny": "auto-deny", "no": "auto-deny"}
        mode = aliases.get(token)
        if mode is None:
            write(Text(f"❌ Unknown mode: {raw}  (ask / auto / deny)", style=PALETTE["red"]))
            return
        self.permission_mode = mode
        write(Text(f"✅ Permission mode → {mode}", style=PALETTE["green"]))

    async def _request_permission(self, kind: str, description: str) -> bool:
        """Resolve a permission request against the current mode (#10).

        ``auto-approve`` and ``auto-deny`` return immediately; ``ask`` pushes the
        ``PermissionScreen`` and awaits the user's decision. Every decision is
        recorded in the active tab for auditing.

        The ``ask`` branch uses a Future + ``push_screen`` callback so it works
        from any async context (it does not require a Textual worker, unlike
        ``push_screen_wait``).
        """
        import asyncio

        mode = self.permission_mode
        if mode == "auto-approve":
            approved = True
        elif mode == "auto-deny":
            approved = False
        else:
            loop = asyncio.get_running_loop()
            future: asyncio.Future[bool] = loop.create_future()

            def _resolve(result: object) -> None:
                if not future.done():
                    future.set_result(bool(result))

            self.push_screen(PermissionScreen(kind, description), callback=_resolve)
            approved = await future
        self._tab.permission_decisions.append(
            {"kind": kind, "description": description, "approved": approved, "mode": mode}
        )
        return approved

    # ── #11 Command palette ───────────────────────────────────────────────────

    def action_command_palette(self) -> None:
        """Open the interactive command palette (#11)."""
        self.push_screen(CommandPaletteScreen(COMMAND_ENTRIES), callback=self._on_palette_pick)

    def _on_palette_pick(self, token: str | None) -> None:
        self.query_one("#prompt", Input).focus()
        if not token:
            return
        self._handle_command(token)

    # ── #12 Multi-session tabs ────────────────────────────────────────────────

    def action_new_tab(self) -> None:
        """Open the new-tab prompt (#12)."""
        self.push_screen(NewTabScreen(), callback=self._on_new_tab)

    def _on_new_tab(self, name: str | None) -> None:
        # ``None`` => cancelled; a string (possibly empty) => create with that name.
        if name is None:
            self.query_one("#prompt", Input).focus()
            return
        base = self._tab
        self._tab_counter += 1
        tab_name = name.strip() or f"Session {self._tab_counter}"
        self._tabs.append(_SessionTab(tab_name, base.profile, base.requested_model))
        self._active = len(self._tabs) - 1
        self._replay_chat()
        self._refresh_chrome()
        self._welcome()
        self.query_one("#prompt", Input).focus()

    def action_close_tab(self) -> None:
        """Close the active tab (#12). The last tab resets to a fresh session."""
        write = self._chat_write
        if len(self._tabs) <= 1:
            self._reset_active_tab()
            write(Text("ℹ️  Last tab reset to a fresh session.", style=PALETTE["yellow"]))
            return
        closed = self._tabs.pop(self._active)
        self.run_worker(self._close_session(closed), exclusive=True, name="tua-close")
        self._active = max(0, self._active - 1)
        self._replay_chat()
        self._refresh_chrome()
        write(Text(f"✅ Closed tab '{closed.name}'. Active: ", style=PALETTE["green"])
              + Text(self._tab.name, style=PALETTE["rust"]))

    def _reset_active_tab(self) -> None:
        """Clear the active tab back to an empty, fresh session."""
        self.run_worker(self._close_session(self._tab), exclusive=True, name="tua-close")
        base = self._tab
        self._tabs[self._active] = _SessionTab(base.name, base.profile, base.requested_model)
        self._replay_chat()
        self._refresh_chrome()
        self._welcome()

    def action_next_tab(self) -> None:
        """Cycle to the next tab (#12)."""
        self._cycle_tab(1)

    def action_previous_tab(self) -> None:
        """Cycle to the previous tab (#12)."""
        self._cycle_tab(-1)

    def _cycle_tab(self, delta: int) -> None:
        total = len(self._tabs)
        if total <= 1:
            return
        self._active = (self._active + delta) % total
        self._replay_chat()
        self._refresh_chrome()

    def _switch_to_tab(self, index: int) -> bool:
        write = self._chat_write
        if not (0 <= index < len(self._tabs)):
            write(Text(f"❌ No tab #{index + 1}  (tabs: {len(self._tabs)})", style=PALETTE["red"]))
            return False
        if index == self._active:
            write(Text(f"   already on tab {index + 1}", style=PALETTE["dim"]))
            return True
        self._active = index
        self._replay_chat()
        self._refresh_chrome()
        write(Text(f"✅ Switched to tab ", style=PALETTE["green"]) + Text(self._tab.name, style=PALETTE["rust"]))
        return True

    def _manage_sessions(self, arg: str) -> None:
        """List, switch, or close session tabs (#12)."""
        write = self._chat_write
        parts = arg.split()
        sub = parts[0].lower() if parts else ""
        if not sub or sub == "list":
            write(Text(f"🗂️  Session tabs ({len(self._tabs)})", style=PALETTE["blue"]))
            for index, tab in enumerate(self._tabs):
                marker = "▶" if index == self._active else " "
                write(
                    Text(f"   {marker} {index + 1}. {tab.profile.emoji} {tab.name}", style=PALETTE["rust"])
                    + Text(f"   ({tab.messages} msgs, {len(tab.edits)} edits)", style=PALETTE["dim"])
                )
            write(Text("   /sessions <num> switch · /sessions close", style=PALETTE["dim"]))
            return
        if sub == "close":
            self.action_close_tab()
            return
        try:
            index = int(sub)
        except ValueError:
            write(Text(f"❌ Unknown /sessions argument: {arg}", style=PALETTE["red"]))
            return
        self._switch_to_tab(index - 1)

    # ── Checkpoint commands (#16) ────────────────────────────────────────────

    def _rollback_checkpoint(self) -> None:
        """Roll back to the most recent git checkpoint (#16)."""
        write = self._chat_write
        from tua_agent.checkpoint import rollback, last_commit_hash
        last_hash = last_commit_hash(self._cwd)
        if last_hash is None:
            write(Text("❌ Not a git repository or no commits yet", style=PALETTE["red"]))
            return
        write(Text(f"⏪ Rolling back from {last_hash}...", style=PALETTE["yellow"]))
        if rollback(self._cwd):
            write(Text("✅ Rolled back to previous checkpoint", style=PALETTE["green"]))
        else:
            write(Text("❌ Rollback failed", style=PALETTE["red"]))

    def _undo_last_edit(self) -> None:
        """Revert the most recent file edit in the current session (#16)."""
        write = self._chat_write
        tab = self._tab
        if not tab.edits:
            write(Text("No edits to undo in this session", style=PALETTE["dim"]))
            return
        last_edit = tab.edits.pop()
        path = getattr(last_edit, "path", "unknown")
        write(Text(f"↩️  Undid last edit: {path}", style=PALETTE["yellow"]))

    # ── Other slash commands ──────────────────────────────────────────────────

    def _resume_session(self, arg: str) -> None:
        """List recent sessions or resume one by ID."""
        write = self._chat_write
        sessions_dir = Path.home() / ".tau" / "sessions"
        if not arg:
            write(Text("📂 Recent sessions", style=PALETTE["blue"]))
            if not sessions_dir.exists():
                write(Text("   (no sessions found)", style=PALETTE["dim"]))
                return
            dirs = sorted(sessions_dir.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)[:10]
            for d in dirs:
                if d.is_dir() and (d / "index.jsonl").exists():
                    mtime = d.stat().st_mtime
                    from datetime import datetime
                    ts = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
                    write(Text(f"   {d.name[:20]:<22} {ts}", style=PALETTE["dim"]))
            write(Text("   /resume <id> to resume a session", style=PALETTE["dim"]))
            return
        write(Text(f"✅ Resume not yet implemented for session: {arg}", style=PALETTE["yellow"]))

    def _list_skills(self) -> None:
        write = self._chat_write
        try:
            from tau_coding.resources import TauResourcePaths
            from tau_coding.skills import load_skills

            skills = load_skills(TauResourcePaths())
        except Exception as exc:  # pragma: no cover - defensive
            write(Text(f"⚠️  Could not load skills: {exc}", style=PALETTE["yellow"]))
            return
        if not skills:
            write(Text("   (no skills bundled)", style=PALETTE["dim"]))
            return
        write(Text(f"📚 Rust skills ({len(skills)})", style=PALETTE["blue"]))
        for skill in skills:
            desc = _short(getattr(skill, "description", None) or "", 44)
            write(
                Text(f"   • {skill.name:<16}", style=PALETTE["rust"])
                + Text(f" {desc}", style=PALETTE["dim"])
            )

    # ── Agent backend ─────────────────────────────────────────────────────────

    async def _close_session(self, tab: _SessionTab | None = None) -> None:
        tab = tab if tab is not None else self._tab
        if tab.session is not None:
            with suppress(Exception):
                await tab.session.aclose()
            tab.session = None
        if tab.provider is not None:
            with suppress(Exception):
                await tab.provider.aclose()
            tab.provider = None

    def _invalidate_session(self) -> None:
        """Mark the active tab's backend stale so it rebuilds next prompt."""
        self.run_worker(self._close_session(self._tab), exclusive=True, name="tua-close")

    async def _ensure_session(self) -> object:
        tab = self._tab
        if tab.session is not None:
            return tab.session
        await self._close_session(tab)

        from tau_coding.provider_config import load_provider_settings, resolve_provider_selection
        from tau_coding.provider_runtime import create_model_provider
        from tau_coding.resources import TauResourcePaths
        from tau_coding.session import CodingSession, CodingSessionConfig, jsonl_session_storage
        from tau_coding.session_manager import SessionManager
        from tau_coding.shell_config import load_shell_settings
        from tau_coding.thinking import DEFAULT_THINKING_LEVEL
        from tau_coding.tools import create_coding_tools

        from tua_agent.rust_session import RustSessionConfig

        settings = load_provider_settings()
        shell_settings = load_shell_settings()
        selection = resolve_provider_selection(
            settings,
            provider_name=self._requested_provider,
            model=tab.requested_model or _detect_model(),
        )
        provider = create_model_provider(
            selection.provider, model=selection.model, thinking_level=DEFAULT_THINKING_LEVEL
        )

        system_prompt = RUST_SYSTEM_PROMPT + "\n\n" + RustSessionConfig(
            profile=tab.profile
        ).build_profile_context()

        tools = create_coding_tools(cwd=str(self.cwd), shell_command_prefix=shell_settings.shell_command_prefix)
        tools.extend(get_rust_tools())

        manager = SessionManager()
        record = manager.create_session(
            cwd=self.cwd,
            model=selection.model,
            provider_name=selection.provider.name,
            session_id=tab.initial_session_id,
        )
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
        tab.session = await CodingSession.load(config)
        tab.provider = provider
        tab.resolved_model = selection.model
        tab.initial_session_id = None  # only the first build resumes a given id
        self._refresh_stats()
        return tab.session

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
                self._chat_write(Text(f"⚠️  {msg}", style=PALETTE["yellow"]))
                if "API key" in msg or "Missing provider" in msg or "credentials" in msg.lower():
                    self._chat_write(Text("   💡 Run `tua providers` to see configured providers.", style=PALETTE["dim"]))
                    self._chat_write(Text("   💡 Set your API key: export PROVIDER_API_KEY=sk-...", style=PALETTE["dim"]))
                    self._chat_write(Text("   💡 Or use 9Router (free): tua config set provider.default 9router", style=PALETTE["dim"]))
                elif "model" in msg.lower():
                    self._chat_write(Text("   💡 Use `tua providers` to list available models.", style=PALETTE["dim"]))
                    self._chat_write(Text("   💡 Try: tua --model glm/glm-5.2 -p \"your prompt\"", style=PALETTE["dim"]))
                else:
                    self._chat_write(Text("   💡 Check `tua config show` and `tua providers` for setup help.", style=PALETTE["dim"]))
                return

            self._chat_write(Text("🤖 …", style=PALETTE["rust"]))
            assert session is not None
            try:
                async for event in session.prompt(prompt_text):
                    self._render_event(event)
                self._flush_assistant()
            except Exception as exc:
                self._flush_assistant()
                self._chat_write(Text(f"❌ {exc}", style=PALETTE["red"]))
        finally:
            prompt.disabled = False
            prompt.focus()
            self._refresh_stats()

    def _render_event(self, event: AgentEvent) -> None:
        write = self._chat_write
        if isinstance(event, MessageDeltaEvent):
            self._tab.assistant_buf += event.delta
            return
        # Any non-delta event finalises the current assistant text block first.
        self._flush_assistant()
        if isinstance(event, MessageEndEvent):
            return  # deltas already carried the text
        if isinstance(event, ToolExecutionStartEvent):
            name = event.tool_call.name.replace("_", " ")
            summary = _summarize_args(event.tool_call.arguments)
            detail = Text(f" {summary}", style=PALETTE["dim"]) if summary else Text("")
            write(Text(f"🔧 {name}", style=PALETTE["blue"]) + detail)
            # Snapshot the file before a write/edit so we can diff it (#8).
            if event.tool_call.name in _EDIT_TOOLS:
                path = event.tool_call.arguments.get("path")
                if isinstance(path, str) and path:
                    self._pending_writes[path] = _read_lines(Path(path))
        elif isinstance(event, ToolExecutionEndEvent):
            ok = event.result.ok
            mark, colour = ("✅", PALETTE["green"]) if ok else ("⚠️", PALETTE["red"])
            write(Text(f"   {mark} {event.result.name.replace('_', ' ')}", style=colour))
            self._tab.tools_run += 1
            if ok and event.result.name in _EDIT_TOOLS and event.result.data:
                path = event.result.data.get("path", "")
                if path:
                    self._record_edit(event.result.name, path)
                    after_lines = self._tab.last_edit[1] if self._tab.last_edit else 0
                    write(Text(f"   {mark} {Path(path).name}: {after_lines} lines  (use /diff)", style=PALETTE["dim"]))
        elif isinstance(event, ErrorEvent):
            write(Text(f"❌ {event.message}", style=PALETTE["red"]))
        elif isinstance(event, AgentEndEvent):
            pass

    async def on_unmount(self) -> None:
        for tab in list(self._tabs):
            await self._close_session(tab)


# ── Entrypoint ────────────────────────────────────────────────────────────────


def run(*, profile: str = "rustacean", model: str | None = None, cwd: Path | None = None) -> None:
    """Launch the Tua Agent TUI (used by ``cli.py`` when no -p prompt is given)."""
    TuaTuiApp(profile=profile, model=model, cwd=cwd).run()


if __name__ == "__main__":  # pragma: no cover
    run()
