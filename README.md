# Tau

Tau is a Python implementation of Pi's minimalist coding-agent harness architecture.

The project is being built in documented phases. Tau currently includes a print-mode CLI
that can run one prompt against an OpenAI-compatible provider.

## Development

```bash
uv sync --dev --group docs
uv run tau --version
OPENAI_API_KEY=... uv run tau "explain this repo"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

# Documentation site
uv run --group docs mkdocs serve
```
