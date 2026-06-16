# 03 — Tools

Tools let the assistant inspect and modify the user's environment through structured calls.

## Core model

`tau_agent` will define provider-neutral tool definitions and structured tool results.
The agent loop will receive a list of tools and execute requested calls without depending on any coding-agent UI.

## Initial coding tools

`tau_coding` now provides the initial coding tool set:

- `read`
- `write`
- `edit`
- `bash`

Use `create_coding_tools()` to register all of them, or create individual tools with `create_read_tool()`, `create_write_tool()`, `create_edit_tool()`, and `create_bash_tool()`.

Important behavior preserved from Pi:

- exact-text replacement for edits
- rollback if a multi-edit operation fails
- output truncation
- bash timeouts
- structured success and error results
