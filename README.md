<p align="center">
  <strong>🦀 Tua Agent v0.0.2</strong><br/>
  <em>A Rust-specialized AI coding agent — built on Tau</em>
</p>

---

## What is Tua Agent?

**Tua (ตัว) Agent** is a coding agent that lives in your terminal and *loves Rust*.
Built on [Tau](https://github.com/alejandro-ao/tau)'s minimalist agent harness,
specialized with deep Rust knowledge: ownership, lifetimes, traits, async, macros,
unsafe, cargo, and the entire ecosystem.

Tua is a **real agent** — it reads files, runs cargo commands, writes code,
and validates results autonomously.

```
tua_agent 🦀  →  tau_coding  →  tau_agent  →  tau_ai
(Rust expert)    (CLI/TUI)     (agent brain)  (providers)
```

## Features

| Feature | Details |
|---|---|
| 🧠 **Rust System Prompt** | 4,087 chars, 20/20 Rust topics (ownership to SemVer) |
| 🔧 **14 Rust Tools** | cargo, rustc, rustfmt, clippy, rustup, audit, outdated, udeps, deny, bench, doc, test-doc, wasm-pack, rustc_explain |
| 📋 **8 Profiles** | Ferris, BorrowChecker, Rustacean, CargoCult, UnsafeFerris, TestCrab, DocCrab, Strict |
| 📚 **10 Skills** | Ownership, lifetimes, async, error-handling, macros, testing, smart-pointers, concurrency, cargo-workspace, wasm |
| 🖥️ **TUI** | Textual-based terminal interface with 12 features: chat, syntax highlight, file tree, diff viewer, command palette, multi-session tabs |
| 🔒 **Permissions** | Interactive approve/deny dialog for file & shell operations |
| 🎨 **Diff Viewer** | Line-by-line unified diff with Rust syntax highlighting |
| ⌨️ **Command Palette** | Ctrl+P interactive search/filter for all slash commands |
| 📑 **Multi-Session** | Tab-based sessions (Ctrl+T/W/Tab) — multiple profiles, independent context |
| 🌐 **Dashboard** | Web UI for Rust project health (build status, clippy, LOC) |
| 🐳 **systemd Service** | Auto-start dashboard on boot |
| 🧠 **AI Intelligence** | Self-correction loop, Chain-of-Thought, git checkpointing, token budgeting, prompt caching, multi-agent review |
| 📖 **Full Guide** | [GUIDE.md](GUIDE.md) — complete feature reference, constraints, benchmarks |

---

## Quickstart

### Install

```bash
git clone https://github.com/anuphongsrinawong/tua-agent.git
cd tua-agent
uv sync --dev
```

### Provider Setup (9Router — free)

Tua defaults to 9Router (GLM-5.2). Already configured in `~/.tau/`:

```bash
# Verify
uv run tua --help
```

To use other providers (DeepSeek, OpenAI), set the API key:

```bash
export DEEPSEEK_API_KEY=sk-...
uv run tua -p "run cargo check" --model deepseek-chat
```

---

## Usage

### Interactive TUI

```bash
cd my-rust-project
uv run tua
# Launches Textual TUI with chat, project info, and tool status
```

### One-Shot Agent Mode

```bash
# Ask Tua to do a task — it reads files, uses tools, writes code
uv run tua -p "add serde+toml, write config parser with validation"

# With a specific profile
uv run tua -p "find and fix all clippy warnings" --profile strict

# Use a different model
uv run tua -p "explain this borrow checker error" --model glm/glm-5.2
```

### CLI Commands

```bash
tua dashboard          # Start web dashboard (http://127.0.0.1:8765)
tua profiles           # List all 8 Rust coding profiles
tua check              # Run cargo check
tua fix                # Run cargo clippy --fix
tua fmt                # Run cargo fmt
tua fmt --check        # Check formatting only
tua audit              # Run cargo audit (security)
tua test               # Run cargo test
tua --list-profiles    # Show profile comparison
```

### Profiles

Select a profile to change the agent's Rust coding style:

```bash
tua --profile ferris          # 🦀 Beginner-friendly, patient
tua --profile borrow-checker  # 🔍 Strict lifetime auditing
tua --profile rustacean       # 🚀 Production-grade (default)
tua --profile cargo-cult      # 📦 Dependency expert
tua --profile unsafe-ferris   # ⚡ FFI and unsafe Rust
tua --profile test-crab       # 🧪 Test-obsessed
tua --profile doc-crab        # 📚 Documentation-first
tua --profile strict          # 🛡️ All guardrails enabled
```

---

## Dashboard

```bash
tua dashboard --host 0.0.0.0 --port 8765
# Open http://localhost:8765
```

Shows real-time:
- 📦 Project info (crate name, version, edition, dependencies)
- 🔨 Build status (check, build, test)
- 📐 Code quality (clippy warnings, rustfmt, LOC)
- 🦀 Active Rust profile with guardrails
- 🤖 Agent session status

---

## Rust Coding Profiles

| Profile | Guardrails | Use When |
|---|---|---|
| 🦀 **Ferris** | no-unsafe, doc-tests | Teaching, onboarding |
| 🔍 **BorrowChecker** | clippy-pedantic | Debugging ownership |
| 🚀 **Rustacean** | no-unwrap, doc-tests | Production code |
| 📦 **CargoCult** | (relaxed) | Dependency management |
| ⚡ **UnsafeFerris** | (relaxed) | FFI, embedded |
| 🧪 **TestCrab** | doc-tests | TDD, property testing |
| 📚 **DocCrab** | doc-tests | API design, public crates |
| 🛡️ **Strict** | no-unwrap, no-unsafe, doc-tests, clippy-pedantic | Mission-critical |

---

## Project Structure

```
src/tua_agent/
├── cli.py                 # CLI + Agent loop wiring
├── tui.py                 # Textual TUI (1,489 lines)
├── rust_system_prompt.py  # Rust expert prompt + Thinking Protocol
├── rust_tools.py          # 14 Rust tools + real executors
├── rust_profiles.py       # 8 coding profiles
├── rust_session.py        # Profile → guidelines converter
├── config.py              # .tua/config.toml loader + AI settings
├── dashboard.py           # Web dashboard (http.server)
├── intelligence.py        # AI orchestration (#13, #16, #18, #19)
├── checkpoint.py          # Git checkpoint/rollback helpers (#16)
├── prompt_cache.py        # Prompt cache layout (#18)
└── __init__.py
```

---

## Configuration

Tua reads config from two locations (project overrides global):

```
~/.tua/config.toml              ← User-global defaults
<project>/.tua/config.toml      ← Project-specific overrides
```

### Setup

```bash
tua init                  # Create both global + project config
tua init --global         # User-global only
tua init --project        # Project only
```

### View & Edit

```bash
tua config show                              # Show current config
tua config set profile.default strict        # Change default profile
tua config set tools.timeout 300             # Set tool timeout
tua config set rust.clippy_pedantic true     # Enable pedantic clippy
```

### Config Keys

| Section | Key | Default | Description |
|---|---|---|---|
| `profile` | `default` | `"rustacean"` | Default Rust coding profile |
| `tools` | `timeout` | `600` | Tool execution timeout (seconds) |
| `tools` | `max_output_chars` | `16000` | Max chars in tool output |
| `dashboard` | `host` | `"127.0.0.1"` | Dashboard bind address |
| `dashboard` | `port` | `8765` | Dashboard port |
| `rust` | `edition` | `"2021"` | Default Rust edition |
| `rust` | `clippy_pedantic` | `false` | Enforce clippy pedantic lints |
| `rust` | `require_doc_tests` | `false` | Require doc-tests on public API |
| `ai` | `self_correction` | `true` | Auto cargo-check self-fix loop (#13) |
| `ai` | `max_self_corrections` | `3` | Max correction turns (#13) |
| `ai` | `checkpoint_enabled` | `true` | Git checkpoint on green build (#16) |
| `ai` | `context_limit` | `128000` | Token budget ceiling (#17) |
| `ai` | `prompt_caching` | `true` | Reorder for cache breakpoints (#18) |
| `ai` | `review_enabled` | `true` | Background clippy review (#19) |

### AI Intelligence Flags

```bash
tua -p "add serde" --no-self-correct   # Disable auto-fix loop
tua -p "add serde" --no-checkpoint     # Disable git snapshots
tua -p "add serde" --no-cache          # Disable prompt caching
tua -p "add serde" --no-review         # Disable code review
```

### Provider Config

```bash
tua providers              # Show configured model providers
```

Provider settings live in `~/.tau/` (managed by Tau).


## Benchmarks

Tua Agent produces **production-grade Rust code** vs generic agents:

| Metric | Default Agent | Tua Agent |
|---|---|---|
| `unwrap()` in prod | 5 ❌ | 0 ✅ |
| Doc comments | 0 ❌ | 19-56 ✅ |
| Clippy warnings | 3 ❌ | 0 ✅ |
| Works on real input | PANIC ❌ | 33,719 files ✅ |
| Proper error types | tuples ❌ | enum + thiserror ✅ |

*Full benchmark: see [comparison report](https://github.com/anuphongsrinawong/tua-agent)*

---

## Development

```bash
cd ~/tua-agent
uv sync --dev

# Run tests
PYTHONPATH=src uv run pytest tests/test_tua_agent.py -v
# 30 tests passed

# Lint
uv run ruff check src/tua_agent/
```

## License

MIT — same as Tau upstream.
