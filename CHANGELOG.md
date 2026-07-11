# v0.0.2 — TUI Feature Pack: Diff Viewer, Permissions, Command Palette, Multi-Session Tabs

*Released: 2026-07-11*

## New Features

### #8 — Real Diff Viewer
- Line-by-line unified diff display for file edits made during a session
- Syntax highlighting for Rust code in diffs
- Tracks multiple edits per session (not just the last one)
- `/diff` — shows summary of all edits in current session
- `/diff <num>` — shows full diff for a specific edit
- `/diff last` — shows the most recent full diff
- Green for additions, red for deletions, blue for context lines

### #9 — DeepSeek API Setup
- `tua setup` command configures AI providers (DeepSeek, OpenAI, Anthropic)
- Credential storage and catalog auto-configuration
- (Already completed in v0.0.1, verified in this release)

### #10 — Permission Dialog
- Interactive modal for confirming file operations before execution
- Three modes: `ask` (show dialog), `auto-approve` (skip), `auto-deny` (block)
- `/permissions` slash command to toggle permission mode
- Permission mode shown in TUI footer bar
- Approve/Deny buttons with keyboard shortcuts (A/D or Enter/Esc)

### #11 — Interactive Command Palette
- Modal overlay with search/filter input
- Lists all slash commands with descriptions
- Type to filter, arrow keys to navigate, Enter to execute
- Ctrl+P keyboard shortcut
- Shows keyboard shortcuts for each command
- Commands: `/help`, `/profile`, `/model`, `/tools`, `/skills`, `/config`, `/resume`, `/diff`, `/clear`, `/permissions`

### #12 — Multi-Session Tabs
- Tab bar at top of TUI showing open sessions
- Each tab = independent chat session (own profile, model, context)
- `Ctrl+T` — create new tab (prompts for session name)
- `Ctrl+W` — close current tab
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — cycle between tabs
- Tab labels show session name + profile emoji
- `/sessions` command to manage tabs (list, switch, close)
- Session state preserved per tab (messages, profile, model, edit history)

## Fixes

- **GLM-5.2 reasoning_content fallback** - reasoning-only models (e.g. GLM-5.2) emit their whole response via reasoning_content deltas and leave content empty. Both the chat-completions and Responses-API stream parsers now fall back to the accumulated thinking text, so the agent receives the real answer instead of an empty string (src/tau_ai/openai_compatible.py).

## All 12 Features Complete

| # | Feature | Status |
|---|---------|:---:|
| 1 | Syntax highlighting | ✅ |
| 2 | Config profile default | ✅ |
| 3 | Token/cost display | ✅ |
| 4 | Friendly errors | ✅ |
| 5 | Session resume (`/resume`) | ✅ |
| 6 | Model switch (`/model`) | ✅ |
| 7 | File tree sidebar | ✅ |
| 8 | Diff viewer | ✅ |
| 9 | DeepSeek API setup | ✅ |
| 10 | Permission dialog | ✅ |
| 11 | Command palette (Ctrl+P) | ✅ |
| 12 | Multi-session tabs | ✅ |
