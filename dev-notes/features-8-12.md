# Features #8-12: TUI Enhancements (v0.0.2)

## Overview

This phase completes all 12 planned TUI features for Tua Agent. Features #8-12 add
real diff viewing, permission controls, an interactive command palette, and
multi-session tab support.

## #8 — Real Diff Viewer

### What it does
Shows actual line-by-line diffs for file edits made during a coding session,
with Rust syntax highlighting.

### Why it exists
The previous `/diff` command was a stub — it only showed "Last edit: path (N lines)".
A real diff viewer lets developers review AI-generated code changes before accepting them,
critical for trust and code review workflows.

### How it maps to Tau's architecture
- `_show_diff()` in `src/tua_agent/tui.py` — handles `/diff` command
- Uses Python `difflib.unified_diff` for diff generation
- Integrates with session edit tracking (stores list of edits per session)

### How to test
```bash
tua -p "write a small Rust function to src/lib.rs"
# In TUI: /diff       → shows edit summary
# In TUI: /diff last  → shows full diff with colors
# In TUI: /diff 1     → shows edit #1
```

---

## #10 — Permission Dialog

### What it does
Interactive confirmation modal before the agent executes file or shell operations.
Three modes: ask (default), auto-approve (development), auto-deny (locked).

### Why it exists
AI agents that can write files and run commands need safety controls. The
permission dialog gives users explicit control over what the agent can do,
preventing accidental or unwanted modifications.

### How it maps to Tau's architecture
- `PermissionScreen` ModalScreen in `src/tua_agent/tui.py`
- `/permissions` command handler in `_handle_slash_command()`
- Footer bar shows current permission mode
- Modes stored in session attribute

### How to test
```bash
tua
# /permissions          → shows current mode and options
# /permissions ask      → set to ask mode
# /permissions auto     → set to auto-approve
# /permissions deny     → set to auto-deny
# When agent tries to write: modal appears with Approve/Deny
```

---

## #11 — Interactive Command Palette

### What it does
Modal overlay with search/filter input listing all slash commands.
Type to filter, arrow keys to navigate, Enter to execute.
Triggered by Ctrl+P or `/help`.

### Why it exists
As the number of slash commands grows (now 10+), users need a discoverable way
to find and execute commands without memorizing them all. The interactive palette
is a standard UX pattern (VS Code, Sublime Text, etc.).

### How it maps to Tau's architecture
- `CommandPaletteScreen` ModalScreen in `src/tua_agent/tui.py`
- `action_command_palette()` binds to Ctrl+P
- Integrates with existing `_handle_slash_command()` dispatch

### How to test
```bash
tua
# Ctrl+P                  → opens command palette
# Type "pro"              → filters to /profile
# Arrow keys + Enter      → executes selected command
```

---

## #12 — Multi-Session Tabs

### What it does
Browser-style tab bar showing open sessions. Each tab is an independent chat
with its own profile, model, and context. Keyboard shortcuts for tab management.

### Why it exists
Developers often work on multiple Rust projects or need to compare approaches.
Multi-session tabs let you switch contexts without restarting the TUI or losing
conversation history.

### How it maps to Tau's architecture
- `SessionTab` widget and tab bar in `src/tua_agent/tui.py`
- `action_new_tab()` (Ctrl+T), `action_close_tab()` (Ctrl+W)
- `action_next_tab()` / `action_previous_tab()` (Ctrl+Tab / Ctrl+Shift+Tab)
- `/sessions` command handler
- Session state per tab (messages, profile, model, edit tracking)

### How to test
```bash
tua
# Ctrl+T          → new tab opens
# Ctrl+Tab        → cycle to next tab
# Ctrl+W          → close current tab
# /sessions       → list all open tabs
# /sessions 2     → switch to tab 2
```
