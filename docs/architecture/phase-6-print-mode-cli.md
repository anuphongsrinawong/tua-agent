# Phase 6: Non-interactive Print-mode CLI

Phase 6 wires Tau's provider layer, agent harness, and built-in coding tools into a usable non-interactive CLI.

The CLI entry point lives in:

```text
src/tau_coding/cli.py
```

## What was added

The `tau` command can now run a single prompt in print mode:

```bash
tau "explain this repo"
tau -p "write tests for main.py"
tau --model gpt-4.1-mini "summarize README.md"
```

The command:

1. loads OpenAI-compatible provider settings from the environment
2. creates Tau's built-in coding tools
3. builds a minimal default system prompt
4. creates an `AgentHarness`
5. streams assistant text to stdout
6. prints tool execution summaries to stderr

## Provider configuration

Print mode currently uses the OpenAI-compatible provider.

Required environment:

```bash
export OPENAI_API_KEY="..."
```

Optional environment:

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

The default model is currently:

```text
gpt-4.1-mini
```

Use `--model` to choose another model supported by the configured endpoint.

## Working directory

Tools are rooted at the current working directory by default.

Use `--cwd` to run tools somewhere else:

```bash
tau --cwd /path/to/project "inspect the tests"
```

## Minimal system prompt

Full Pi-style system prompt assembly is planned for a later phase. For now, print mode builds a small prompt containing:

- Tau's identity
- the list of available tools
- each tool's `prompt_snippet`
- each tool's `prompt_guidelines`

This gives the model enough guidance to use the Phase 5 tools while keeping the richer prompt/resource system out of the core harness.

## Boundary

The CLI lives in `tau_coding`. It depends on providers, tools, and the harness, but the reusable `tau_agent` package still has no CLI, Rich, Textual, config-file, or session-storage dependency.

## Tests

The phase is covered by `tests/test_cli.py`, including:

- `tau --version`
- no-prompt hint output
- default system prompt contents
- print-mode streaming with a fake provider

## Next phase

The next roadmap phase is append-only session tree persistence.
