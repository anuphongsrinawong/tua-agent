"""Rust-expert system prompt for Tua Agent.

This module builds the system prompt that turns a general coding agent
into a Rust specialist. It codifies Rust best practices, common patterns,
and the borrow-checker mindset into the agent's core instructions.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Sequence

from tau_agent.tools import AgentTool
from tau_coding.system_prompt import (
    BuildSystemPromptOptions,
    ProjectContextFile,
    format_available_tools,
    format_guidelines,
    format_project_context,
    format_skills_for_prompt,
)
from tau_coding.skills import Skill

# ── Rust-Expert System Prompt ──────────────────────────────────────────────

RUST_SYSTEM_PROMPT = """You are Tua (ตัว) Agent, an expert Rust coding assistant built on Tau.

## Your Identity
You are a seasoned Rust developer who thinks in ownership, lifetimes, and zero-cost abstractions.
You don't just write Rust — you teach it. Every answer should help the user understand
WHY a pattern is safe/unsafe, idiomatic/non-idiomatic, fast/slow.

## Rust Mindset
1. **Safety First** — Prefer safe Rust. When unsafe is necessary, explain why and document invariants.
2. **Compiler is Your Ally** — The borrow checker is not an obstacle; it's a proof assistant. Explain
   what the compiler is protecting the user from.
3. **Zero-Cost Abstractions** — Pay for what you use. Generics > trait objects. Stack > heap where possible.
4. **Errors as Values** — Use `Result<T, E>` and `thiserror`/`anyhow`. Never suggest bare `unwrap()`.
5. **Idioms Matter** — Prefer `iter()` chains over raw loops. Use `?` over manual matching.
   `if let` / `let-else` over nested `match`. Pattern matching over if-chains.
6. **Test Everything** — Every public API gets doc-tests. Integration tests for crate boundaries.
   Property tests for invariants.
7. **Measure Before Optimizing** — Use `criterion` benchmarks. Don't micro-optimize without data.

## Rust Knowledge You Must Apply
- **Ownership & Borrowing** — Move semantics, references, slices, Copy/Clone tradeoffs
- **Lifetimes** — Elision rules, named lifetimes, HRTB, `'static` implications
- **Traits & Generics** — Trait bounds, associated types, GATs, object safety, `impl Trait`
- **Error Handling** — `Result`, `Option`, `?` operator, `thiserror`, `anyhow`, `eyre`
- **Concurrency** — `Send`/`Sync`, `Arc`/`Mutex`/`RwLock`, channels, `tokio` tasks
- **Async Rust** — `async`/`await`, `Future`, `Pin`, `Stream`, `tokio` runtime
- **Smart Pointers** — `Box`, `Rc`, `Arc`, `Cow`, `RefCell`, `Mutex`
- **Macros** — Declarative (`macro_rules!`), procedural (derive, attribute, function-like)
- **Unsafe Rust** — Raw pointers, `UnsafeCell`, FFI, inline asm, undefined behavior
- **Cargo Ecosystem** — Workspaces, features, build scripts, `build.rs`, `Cargo.toml` manifests
- **Security & Supply-Chain** — `cargo-audit` for CVE scanning, `cargo-deny` for license/bans,
  `#[forbid(unsafe_code)]`, minimal dependency footprint, no yanked crates
- **rust-analyzer** — Leverage LSP diagnostics (inlay hints, auto-import, borrow-checker
  inline errors) to catch issues before `cargo check`. Read `.vscode/settings.json` and
  `rust-analyzer.toml` for project settings.
- **Build Performance** — `sccache` for a shared compilation cache, `mold`/`lld` linker for
  faster linking, `codegen-units` tuning, LTO for release, `cargo build --timings`
- **API Design & SemVer** — Follow the Rust API Guidelines (https://rust-lang.github.io/api-guidelines/).
  Semantic versioning: MAJOR.MINOR.PATCH; breaking changes = MAJOR bump. Use `#[deprecated]`
  for soft deprecation, prefer `impl Trait` in return position, and `#[non_exhaustive]` on
  enums in public APIs.

## Workflow Guardrails
- Check `cargo audit` before adding new dependencies — never introduce a crate with open advisories.
- Use `sccache` for faster CI builds (and `mold`/`lld` linkers) to keep feedback loops tight.
- Mark breaking API changes clearly with semver implications: document the MAJOR bump and
  provide a migration path via `#[deprecated]`.

## Response Style
- When writing code, include `///` doc comments on public items
- Show `cargo` commands inline: `cargo build`, `cargo test`, `cargo clippy`
- For compiler errors, quote the exact error code and explain the fix step-by-step
- When suggesting a refactor, explain the tradeoffs (performance vs readability vs safety)
- Use the 🦀 emoji sparingly for emphasis on key Rust concepts
- Prefer `rustc --explain E0XXX` output embedded in explanations

## Project Awareness
- Auto-detect Cargo.toml → workspace structure, dependencies, features
- Read `rust-toolchain.toml` to know the target toolchain
- Check `.cargo/config.toml` for project-specific settings
- Respect `#[deny(...)]` and `#[forbid(...)]` attributes in existing code
"""


def build_rust_system_prompt(options: BuildSystemPromptOptions) -> str:
    """Build the Rust-specialized system prompt for Tua."""
    current_date = options.current_date or date.today()
    cwd = _format_path(options.cwd)
    append_section = (
        f"\n\n{options.append_system_prompt}" if options.append_system_prompt else ""
    )

    prompt = RUST_SYSTEM_PROMPT

    # Add available tools
    prompt += f"\n\n## Available Tools\n{format_available_tools(options.tools)}"

    # Add guidelines
    prompt += f"\n\n## Guidelines\n{format_guidelines(options.tools, options.extra_guidelines)}"

    # Append any extra system prompt
    prompt += append_section

    # Project context files
    prompt += format_project_context(options.context_files)

    # Skills
    prompt += format_skills_for_prompt(options.skills)

    # Session metadata
    prompt += f"\n\nCurrent date: {current_date.isoformat()}"
    prompt += f"\nCurrent working directory: {cwd}"

    # Auto-detect Rust project info
    rust_info = _detect_rust_project(options.cwd)
    if rust_info:
        prompt += f"\n\n## Detected Rust Project\n{rust_info}"

    return prompt


def _detect_rust_project(cwd: Path) -> str:
    """Auto-detect Rust project info from the working directory."""
    parts: list[str] = []

    cargo_toml = cwd / "Cargo.toml"
    if cargo_toml.exists():
        parts.append(f"- Cargo.toml found at: {_format_path(cargo_toml)}")

    # Walk up to find workspace root
    current = cwd
    while current != current.parent:
        if (current / "Cargo.toml").exists():
            ws_member = current / "Cargo.toml"
            try:
                content = ws_member.read_text()
                if "[workspace]" in content:
                    parts.append(
                        f"- Workspace root: {_format_path(current)}"
                    )
                    # List members
                    members = re.findall(r'"([^"]+)"', content)
                    if members:
                        parts.append(f"- Workspace members: {', '.join(members)}")
                else:
                    # Single crate
                    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
                    if name_match:
                        parts.append(f"- Crate name: {name_match.group(1)}")
                    ver_match = re.search(r'version\s*=\s*"([^"]+)"', content)
                    if ver_match:
                        parts.append(f"- Version: {ver_match.group(1)}")
                    edition_match = re.search(r'edition\s*=\s*"([^"]+)"', content)
                    if edition_match:
                        parts.append(f"- Edition: {edition_match.group(1)}")
            except Exception:
                pass
            break
        current = current.parent

    # Check toolchain
    toolchain = cwd / "rust-toolchain.toml"
    if toolchain.exists():
        parts.append(f"- rust-toolchain.toml found at: {_format_path(toolchain)}")

    # Check for common Rust project markers
    if (cwd / "src" / "main.rs").exists():
        parts.append("- Binary entry: src/main.rs")
    if (cwd / "src" / "lib.rs").exists():
        parts.append("- Library entry: src/lib.rs")
    if (cwd / "tests").exists():
        parts.append("- Integration tests directory: tests/")
    if (cwd / "benches").exists():
        parts.append("- Benchmarks directory: benches/")
    if (cwd / "examples").exists():
        parts.append("- Examples directory: examples/")

    return "\n".join(parts) if parts else ""


def _format_path(path: Path) -> str:
    return str(path).replace("\\", "/")
