<p align="center">
  <strong>🦀 Tua Agent</strong><br/>
  <em>A Rust-specialized AI coding agent — built on Tau</em>
</p>

---

## What is Tua Agent?

**Tua (ตัว) Agent** is a coding agent that lives in your terminal and *loves Rust*.
It's built on [Tau](https://github.com/alejandro-ao/tau)'s minimalist agent harness,
specialized with deep Rust knowledge: ownership, lifetimes, traits, async, macros,
unsafe, cargo, and the entire ecosystem.

```text
tua_agent 🦀  →  tau_coding  →  tau_agent  →  tau_ai
(Rust expert)    (CLI/TUI)     (agent brain)  (providers)
```

## Why Tua over vanilla Tau?

| Feature | Tau | Tua Agent |
|---|---|---|
| System prompt | General coding | Rust expert + borrow checker mindset |
| Built-in tools | read, write, edit, bash | + cargo, rustc, clippy, rustfmt, rustup |
| Rust profiles | None | 8 profiles (Ferris, BorrowChecker, Rustacean...) |
| CLI | `tau` | `tua` (auto-detects Rust projects) |
| Dashboard | None | Web dashboard for project health |

## Quickstart

```bash
cd ~/tua-agent
uv sync --dev

# Start Tua in a Rust project
cd my-rust-project
uv run tua

# Or one-shot
uv run tua -p "add unit tests for the auth module"
uv run tua -p "fix all clippy warnings"
uv run tua --profile borrow-checker
```

## Rust-Specific Commands

Inside the Tua TUI:

```
/cargo build          Build the project
/cargo test           Run tests
/cargo clippy         Run clippy lints
/cargo fmt            Format code
/cargo bench          Run benchmarks
/cargo audit          Security audit dependencies
/rustc explain E0502  Explain a compiler error
/profile ferris        Switch to Ferris (beginner-friendly) profile
/profile strict        Switch to Strict (max guardrails) profile
```

## Rust Coding Profiles

| Profile | Best For |
|---|---|
| 🦀 **Ferris** | Teaching Rust, onboarding |
| 🔍 **BorrowChecker** | Debugging ownership |
| 🚀 **Rustacean** | Production code |
| 📦 **CargoCult** | Dependency management |
| ⚡ **UnsafeFerris** | FFI, unsafe blocks |
| 🧪 **TestCrab** | Testing, TDD |
| 📚 **DocCrab** | API design, docs |
| 🛡️ **Strict** | Mission-critical Rust |

## Development

```bash
cd ~/tua-agent
uv sync --dev
uv run pytest
uv run ruff check .
```

## License

MIT — same as Tau upstream.
