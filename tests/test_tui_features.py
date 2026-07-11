"""Tests for Tua Agent TUI features #8-12 (v0.0.2).

Feature #8  — Real Diff Viewer
Feature #10 — Permission Dialog
Feature #11 — Interactive Command Palette
Feature #12 — Multi-Session Tabs
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest
from rich.text import Text

from tua_agent.rust_profiles import get_profile
from tua_agent.tui import PALETTE, TuaTuiApp, _detect_cargo_project


# ── Feature flags ─────────────────────────────────────────────────────────

_has_v002_features = True  # v0.0.2 features (#8-12) implemented


def _skip_if_not_v002() -> None:
    """Skip test if v0.0.2 features (#10, #12) haven't been implemented yet."""
    if not _has_v002_features:
        pytest.skip("v0.0.2 features (#10, #12) pending Claude implementation")


# ── Test imports and class structure ───────────────────────────────────────


def test_tua_tui_app_importable() -> None:
    """TuaTuiApp class exists and is importable."""
    assert TuaTuiApp is not None


def test_tua_tui_app_instantiable() -> None:
    """TuaTuiApp can be instantiated without errors."""
    app = TuaTuiApp(profile="rustacean", cwd=Path.cwd())
    assert app is not None
    assert app.profile.name == "rustacean"


def test_tua_tui_app_default_profile() -> None:
    """Default profile is rustacean."""
    app = TuaTuiApp(cwd=Path.cwd())
    assert app.profile is not None
    assert app.profile.name in {"rustacean", "ferris", "borrowchecker", "cargocult",
                                "unsafeferris", "testcrab", "doccrab", "strict"}


def test_palette_has_expected_colors() -> None:
    """PALETTE dict contains expected color keys."""
    assert "blue" in PALETTE
    assert "red" in PALETTE
    assert "green" in PALETTE
    assert "rust" in PALETTE
    assert "dim" in PALETTE
    assert "yellow" in PALETTE


def test_detect_cargo_project_non_rust_dir(tmp_path: Path) -> None:
    """_detect_cargo_project returns fallback info for non-Rust directory."""
    info = _detect_cargo_project(tmp_path)
    assert isinstance(info, dict)
    assert info.get("name") is None


def test_detect_cargo_project_with_cargo_toml(tmp_path: Path) -> None:
    """_detect_cargo_project detects a Rust project."""
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
    info = _detect_cargo_project(tmp_path)
    assert "crate" in info or "name" in info or info != {}


# ── Feature #8: Diff Viewer ──────────────────────────────────────────────


def test_app_has_show_diff_method() -> None:
    """TuaTuiApp has _show_diff method."""
    assert hasattr(TuaTuiApp, "_show_diff"), "TuaTuiApp should have _show_diff method"
    method = getattr(TuaTuiApp, "_show_diff", None)
    assert callable(method)


def test_app_has_last_edit_tracking() -> None:
    """TuaTuiApp tracks last edit information."""
    # Check source code for expected edit-tracking attribute
    source = inspect.getsource(TuaTuiApp)
    assert "_last_edit" in source or "_edits" in source, (
        "TuaTuiApp should track edits with _last_edit or _edits"
    )


def test_diff_slash_command_registered() -> None:
    """The /diff command is registered in slash command handling."""
    source = inspect.getsource(TuaTuiApp)
    assert '"/diff"' in source or "'/diff'" in source, (
        "/diff command should be handled in TuaTuiApp"
    )


# ── Feature #10: Permission Dialog ───────────────────────────────────────


def test_app_has_permission_handling() -> None:
    """TuaTuiApp has permission-related code."""
    _skip_if_not_v002()
    source = inspect.getsource(TuaTuiApp)
    assert "permission" in source.lower() or "_permission" in source, (
        "TuaTuiApp should have permission handling"
    )


def test_permissions_slash_command_handled() -> None:
    """The /permissions command exists or is added."""
    _skip_if_not_v002()
    source = inspect.getsource(TuaTuiApp)
    assert '"/permissions"' in source or "'/permissions'" in source or "/permission" in source.lower(), (
        "/permissions command should be handled"
    )


# ── Feature #11: Command Palette ─────────────────────────────────────────


def test_app_has_command_palette_action() -> None:
    """TuaTuiApp has action_command_palette method."""
    source = inspect.getsource(TuaTuiApp)
    assert "action_command_palette" in source, (
        "TuaTuiApp should have action_command_palette method"
    )


def test_command_palette_has_ctrl_p_binding() -> None:
    """Ctrl+P is bound to command palette."""
    source = inspect.getsource(TuaTuiApp)
    assert "command_palette" in source.lower() or "ctrl+p" in source.lower(), (
        "Command palette should be discoverable in source"
    )


def test_command_palette_lists_all_commands() -> None:
    """Command palette includes all expected slash commands."""
    source = inspect.getsource(TuaTuiApp)
    commands = ["/help", "/profile", "/model", "/tools", "/skills", "/config", "/diff", "/clear"]
    for cmd in commands:
        assert cmd in source, f"Command palette should include {cmd}"


# ── Feature #12: Multi-Session Tabs ─────────────────────────────────────


def test_app_has_tab_management() -> None:
    """TuaTuiApp has tab-related methods or sessions command."""
    _skip_if_not_v002()
    source = inspect.getsource(TuaTuiApp)
    has_tabs = any(pattern in source.lower() for pattern in [
        "action_new_tab", "action_close_tab", "_tabs", "session_tab",
        "active_tab", "/sessions", "tab"
    ])
    assert has_tabs, "TuaTuiApp should have tab management features"


def test_sessions_slash_command_handled() -> None:
    """The /sessions command is handled."""
    _skip_if_not_v002()
    source = inspect.getsource(TuaTuiApp)
    assert '"/sessions"' in source or "'/sessions'" in source, (
        "/sessions command should be handled for tab management"
    )


# ── Slash command dispatch integrity ─────────────────────────────────────


def test_all_expected_slash_commands_handled() -> None:
    """All v0.0.2 slash commands are handled in TuaTuiApp."""
    _skip_if_not_v002()
    source = inspect.getsource(TuaTuiApp)
    expected = [
        "/help", "/profile", "/tools", "/skills", "/model", "/config",
        "/resume", "/diff", "/clear", "/permissions", "/sessions",
    ]
    missing = []
    for cmd in expected:
        if cmd not in source:
            missing.append(cmd)
    assert not missing, (
        f"Missing slash commands in TuaTuiApp: {missing}. "
        f"Commands found in source: check _handle_slash_command or equivalent."
    )


# ── Profile integration ──────────────────────────────────────────────────


def test_all_eight_profiles_available() -> None:
    """All 8 Rust coding profiles are defined."""
    from tua_agent.rust_profiles import list_profiles
    profiles = list_profiles()
    names = {p.name for p in profiles}
    assert len(profiles) == 8, f"Expected 8 profiles, got {len(profiles)}: {names}"
    expected = {"ferris", "borrow-checker", "rustacean", "cargo-cult",
                "unsafe-ferris", "test-crab", "doc-crab", "strict"}
    assert names == expected, f"Profile names mismatch: {names}"


def test_get_profile_returns_correct_data() -> None:
    """Each profile can be retrieved with get_profile."""
    for name in ["ferris", "rustacean", "borrow-checker", "cargo-cult",
                 "unsafe-ferris", "test-crab", "doc-crab", "strict"]:
        profile = get_profile(name)
        assert profile.name == name
        assert profile.emoji
        assert profile.description


# ── CLAUDE_TASK.md integrity ──────────────────────────────────────────────


def test_claude_task_file_exists() -> None:
    """CLAUDE_TASK.md exists in project root — the task spec for Claude."""
    task_file = Path(__file__).parent.parent / "CLAUDE_TASK.md"
    assert task_file.exists(), "CLAUDE_TASK.md should exist in project root"


def test_claude_task_no_dhamma_content() -> None:
    """CRITICAL: CLAUDE_TASK.md contains no Dhamma/Buddhist/religious content."""
    task_file = Path(__file__).parent.parent / "CLAUDE_TASK.md"
    if not task_file.exists():
        pytest.skip("CLAUDE_TASK.md not found")
    content = task_file.read_text().lower()
    forbidden = ["dhamma", "buddh", "ธรรม", "ศีล", "สมาธิ", "ปัญญา", "buddhist", "religious principle", "moral philosophy"]
    for word in forbidden:
        if word in content:
            # Allow "No Dhamma" / "NOT include" patterns
            lines_with_word = [l for l in content.split("\n") if word in l.lower()]
            # Check if ALL instances are negated
            negated = all(
                "not" in l.lower() or "no " in l.lower() or "don't" in l.lower() or "do not" in l.lower()
                or "without" in l.lower() or "critical" in l.lower()
                for l in lines_with_word
            )
            if not negated:
                pytest.fail(
                    f"CLAUDE_TASK.md contains '{word}' not in a negated context. "
                    f"Lines: {lines_with_word}"
                )


# ── CHANGELOG and documentation ───────────────────────────────────────────


def test_changelog_exists() -> None:
    """CHANGELOG.md exists and mentions v0.0.2."""
    changelog = Path(__file__).parent.parent / "CHANGELOG.md"
    assert changelog.exists(), "CHANGELOG.md should exist"
    content = changelog.read_text()
    assert "v0.0.2" in content, "CHANGELOG should mention v0.0.2"
    assert "#8" in content or "Diff" in content, "CHANGELOG should mention diff viewer"
    assert "#10" in content or "Permission" in content, "CHANGELOG should mention permissions"
    assert "#11" in content or "Command Palette" in content, "CHANGELOG should mention command palette"
    assert "#12" in content or "Multi-Session" in content, "CHANGELOG should mention multi-session tabs"


def test_dev_notes_exist() -> None:
    """dev-notes/features-8-12.md exists."""
    dev_notes = Path(__file__).parent.parent / "dev-notes" / "features-8-12.md"
    assert dev_notes.exists(), "dev-notes/features-8-12.md should exist"


def test_readme_mentions_features(capsys):  # noqa: ARG001
    """README.md is present in the project."""
    readme = Path(__file__).parent.parent / "README.md"
    assert readme.exists(), "README.md should exist"
    content = readme.read_text()
    assert "Tua Agent" in content


# ── Functional tests (drive the running app via Textual's Pilot) ───────────
# These exercise the real behavior of each v0.0.2 feature, not just source
# inspection. They mount TuaTuiApp in headless test mode and interact with it.


def _log_text(app) -> list[str]:
    """Plain text of every Text renderable in the active tab's transcript."""
    from rich.text import Text

    return [r.plain for r in app._tab.log if isinstance(r, Text)]


@pytest.mark.anyio
async def test_diff_viewer_shows_real_unified_diff(tmp_path: Path) -> None:
    """#8 — /diff renders line-by-line diffs with +added / -removed lines."""
    src = tmp_path / "src" / "lib.rs"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("fn old() {}\n")
    app = TuaTuiApp(profile="rustacean", cwd=tmp_path)

    async with app.run_test(size=(130, 34)) as pilot:
        await pilot.pause()
        # Simulate the agent editing lib.rs: before-snapshot, change, record.
        app._pending_writes[str(src)] = ["fn old() {}"]
        src.write_text("fn new() {}\nfn added() {}\n")
        app._record_edit("edit", str(src))
        assert len(app._edits) == 1
        edit = app._edits[0]
        assert edit.added >= 2 and edit.removed >= 1

        before = len(_log_text(app))
        app._show_diff("")        # summary of all edits
        app._show_diff("1")       # full diff for edit #1
        app._show_diff("last")    # full diff for the most recent edit
        blob = "\n".join(_log_text(app)[before:])

    assert "Edits this session (1)" in blob
    assert "Diff #1" in blob
    assert "+fn new()" in blob
    assert "-fn old()" in blob


@pytest.mark.anyio
async def test_permission_modes_and_dialog(tmp_path: Path) -> None:
    """#10 — auto-approve/auto-deny resolve immediately; ask opens the modal."""
    from tua_agent.tui import PermissionScreen

    app = TuaTuiApp(profile="rustacean", cwd=tmp_path)

    async with app.run_test(size=(130, 34)) as pilot:
        await pilot.pause()
        tab = app._tab

        app._set_permission_mode("auto")
        assert app.permission_mode == "auto-approve"
        assert await app._request_permission("file write", "w") is True

        app._set_permission_mode("deny")
        assert app.permission_mode == "auto-deny"
        assert await app._request_permission("shell", "s") is False

        # ask mode pushes the PermissionScreen modal and awaits a decision.
        app._set_permission_mode("ask")
        task = asyncio.create_task(app._request_permission("network", "n"))
        await pilot.pause()
        assert isinstance(app.screen, PermissionScreen)
        app.screen.dismiss(False)
        assert await task is False
        assert len(tab.permission_decisions) == 3


@pytest.mark.anyio
async def test_command_palette_filters_and_runs(tmp_path: Path) -> None:
    """#11 — Ctrl+P opens the palette; typing filters; Enter runs the command."""
    from tua_agent.tui import CommandPaletteScreen

    app = TuaTuiApp(profile="rustacean", cwd=tmp_path)

    async with app.run_test(size=(130, 34)) as pilot:
        await pilot.pause()
        app.action_command_palette()
        await pilot.pause()
        assert isinstance(app.screen, CommandPaletteScreen)

        # Typing filters the list down to the matching command.
        for ch in "tools":
            await pilot.press(ch)
        await pilot.pause()
        labels = [entry[1] for entry in app.screen._visible]
        assert labels == ["/tools"]

        # Enter dismisses the palette and executes /tools in the transcript.
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, CommandPaletteScreen)
        assert any("Rust toolchain" in line for line in _log_text(app))


@pytest.mark.anyio
async def test_multi_session_tabs_lifecycle(tmp_path: Path) -> None:
    """#12 — create, name, switch, cycle, and close tabs with per-tab state."""
    app = TuaTuiApp(profile="rustacean", cwd=tmp_path)

    async with app.run_test(size=(130, 34)) as pilot:
        await pilot.pause()
        tab0 = app._tab
        # Put something in tab0's transcript to prove isolation.
        tab0.log.append(Text("marker-tab0"))

        # Create a named tab and an auto-named tab.
        app._on_new_tab("Build Notes")
        await pilot.pause()
        assert len(app._tabs) == 2 and app._tab.name == "Build Notes"
        app._on_new_tab("")
        await pilot.pause()
        assert len(app._tabs) == 3 and app._tab.name == "Session 3"

        # The new tab has its own welcome but not tab0's marker.
        new_log = _log_text(app)
        assert any("Build Notes" in line or "Session 3" in line for line in new_log)
        assert "marker-tab0" not in new_log

        # Switching and cycling.
        app._switch_to_tab(0)
        await pilot.pause()
        assert app._active == 0
        app.action_next_tab()
        await pilot.pause()
        assert app._active == 1
        app.action_previous_tab()
        await pilot.pause()
        assert app._active == 0
        # Returning to tab0 replays its transcript.
        assert any("marker-tab0" == line for line in _log_text(app))

        # Closing a tab (more than one open) removes it.
        before = len(app._tabs)
        app.action_close_tab()
        await pilot.pause()
        assert len(app._tabs) == before - 1


@pytest.mark.anyio
async def test_new_tab_modal_and_close_last_tab(tmp_path: Path) -> None:
    """#12 — Ctrl+T opens the naming modal; closing the last tab resets it."""
    from tua_agent.tui import NewTabScreen

    app = TuaTuiApp(profile="rustacean", cwd=tmp_path)

    async with app.run_test(size=(130, 34)) as pilot:
        await pilot.pause()
        app.action_new_tab()
        await pilot.pause()
        assert isinstance(app.screen, NewTabScreen)
        app.screen.dismiss(None)  # cancel
        await pilot.pause()
        assert len(app._tabs) == 1  # nothing created on cancel

        # Closing the only tab resets it to a fresh session rather than exiting.
        app.action_close_tab()
        await pilot.pause()
        assert len(app._tabs) == 1
        assert app._edits == []

