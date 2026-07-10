# Tua Agent Instructions

🦀 **Tua Agent** is a Rust-specialized coding agent built on Tau's minimalist harness architecture.
It is designed to be the best AI pair-programmer for Rust development — from writing safe code
to debugging borrow-checker errors, from refactoring to benchmarking.

## Mission

**Make Rust development joyful and safe.** Tua understands ownership, lifetimes, traits,
async Rust, unsafe boundaries, macro magic, and the entire cargo ecosystem. It doesn't just
write Rust — it teaches Rust.

## Architecture

Tua extends Tau's three-layer architecture with a Rust-specialization layer:

```text
tua_agent    🦀 Rust CLI, system prompt, tools, skills, profiles
  └─ tau_coding  CLI app, TUI, sessions
       └─ tau_agent  portable agent harness, loop, events
            └─ tau_ai  provider/model streaming
```

Key additions over vanilla Tau:

| Component | Purpose |
|---|---|
| `tua_agent/rust_system_prompt.py` | Rust-expert system prompt — covers ownership, lifetimes, cargo, clippy |
| `tua_agent/rust_tools.py` | Rust-specific tools: cargo build/test/clippy, rustc, rustfmt, rustup |
| `tua_agent/rust_profiles.py` | Rust coding profiles (Ferris, BorrowChecker, Rustacean, etc.) |
| `tua_agent/dashboard.py` | Web dashboard for Rust project health monitoring |
| `tua_agent/cli.py` | `tua` CLI command — drop-in with Rust defaults |

## Rust-First Principles

1. **Safety by default** — Prefer safe Rust; mark unsafe blocks clearly with justification
2. **Zero-cost abstractions** — Don't box unless necessary; use generics over trait objects
3. **Compile-first** — Run `cargo check` before suggesting edits; never ship broken code
4. **Clippy is law** — Every suggestion must pass `cargo clippy` without warnings
5. **Tests are documentation** — Write doc-tests and integration tests for every public API
6. **Error handling is explicit** — Use `Result<T, E>` and `thiserror`/`anyhow`; never `unwrap()` in production
7. **Borrow checker as teacher** — Explain WHY the borrow checker rejects code, not just HOW to fix it

## Rust Coding Profiles

| Profile | Focus | Use When |
|---|---|---|
| 🦀 Ferris | Friendly, beginner-friendly | Teaching Rust, onboarding |
| 🔍 BorrowChecker | Strict, lifetime-aware | Debugging ownership issues |
| 🚀 Rustacean | Idiomatic, performant | Production Rust code |
| 📦 CargoCult | Dependency-smart | Crate selection, feature flags |
| ⚡ UnsafeFerris | Unsafe-aware | FFI, embedded, kernel |
| 🧪 TestCrab | Test-obsessed | Property testing, fuzzing |
| 📚 DocCrab | Documentation-first | API design, public crates |
| 🛡️ Strict | Maximum guardrails | Mission-critical Rust |

## Development Workflow

- Work in small, documented phases.
- Every Rust-related change must pass `cargo check` / `cargo test` / `cargo clippy`.
- Run Python tests through `uv` (e.g., `uv run pytest`).
- Keep commits atomic: one coherent Rust feature, fix, or doc update per commit.

## Documentation Expectations

Each substantial phase should leave behind beginner-friendly notes under `dev-notes/`:
- what was added (Rust feature, tool, or profile)
- why it exists (which Rust pain point it solves)
- how it maps to Tau's architecture
- how to test or use it
