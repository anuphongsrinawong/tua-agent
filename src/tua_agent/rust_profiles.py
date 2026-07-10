"""Rust coding profiles for Tua Agent.

Pure Rust development profiles — no Dhamma, no Buddhist principles.
Each profile is a set of Rust-specific guardrails and preferences.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RustProfile:
    """A named coding profile calibrated for a Rust development context."""

    name: str
    emoji: str
    description: str
    use_when: str

    # Rust-specific guardrails
    require_cargo_check: bool = True
    forbid_unwrap: bool = False
    forbid_unsafe: bool = False
    require_doc_tests: bool = False
    enforce_clippy_pedantic: bool = False
    enforce_rustfmt: bool = True


FERRIES = RustProfile(
    name="ferris",
    emoji="🦀",
    description="Friendly, beginner-focused Rust mentor. Patient, explains concepts clearly.",
    use_when="Teaching Rust, onboarding new developers, code reviews for learners",
    forbid_unsafe=True,
    require_doc_tests=True,
)

BORROW_CHECKER = RustProfile(
    name="borrow-checker",
    emoji="🔍",
    description="Strict, lifetime-aware auditor. Catches ownership bugs before they happen.",
    use_when="Debugging ownership issues, reviewing unsafe code, refactoring lifetimes",
    enforce_clippy_pedantic=True,
)

RUSTACEAN = RustProfile(
    name="rustacean",
    emoji="🚀",
    description="Idiomatic, performant Rust engineer. Zero-cost abstractions, fearless concurrency.",
    use_when="Production Rust code, performance optimization, library design",
    forbid_unwrap=True,
    require_doc_tests=True,
)

CARGO_CULT = RustProfile(
    name="cargo-cult",
    emoji="📦",
    description="Dependency-savvy. Knows crates.io, feature flags, semver, supply-chain security.",
    use_when="Adding/updating dependencies, auditing Cargo.toml, workspace management",
)

UNSAFE_FERRIS = RustProfile(
    name="unsafe-ferris",
    emoji="⚡",
    description="Unsafe Rust specialist. FFI, raw pointers, inline asm, with safety invariants documented.",
    use_when="FFI bindings, embedded development, kernel modules, SIMD optimization",
    forbid_unsafe=False,
)

TEST_CRAB = RustProfile(
    name="test-crab",
    emoji="🧪",
    description="Test-obsessed. Property testing, fuzzing, coverage, mutation testing.",
    use_when="Writing tests, setting up CI, improving test coverage, TDD",
    require_doc_tests=True,
)

DOC_CRAB = RustProfile(
    name="doc-crab",
    emoji="📚",
    description="Documentation-first. Every public API gets examples. README-driven development.",
    use_when="API design, public crate releases, writing guides and tutorials",
    require_doc_tests=True,
)

STRICT = RustProfile(
    name="strict",
    emoji="🛡️",
    description="Maximum strictness. All guardrails enabled. For mission-critical Rust.",
    use_when="Safety-critical systems, financial code, cryptographic implementations",
    forbid_unwrap=True,
    forbid_unsafe=True,
    require_doc_tests=True,
    enforce_clippy_pedantic=True,
)


RUST_PROFILES: dict[str, RustProfile] = {
    "ferris": FERRIES,
    "borrow-checker": BORROW_CHECKER,
    "rustacean": RUSTACEAN,
    "cargo-cult": CARGO_CULT,
    "unsafe-ferris": UNSAFE_FERRIS,
    "test-crab": TEST_CRAB,
    "doc-crab": DOC_CRAB,
    "strict": STRICT,
}


def get_profile(name: str) -> RustProfile:
    """Get a Rust profile by name. Raises KeyError if not found."""
    if name not in RUST_PROFILES:
        available = ", ".join(sorted(RUST_PROFILES.keys()))
        raise KeyError(f"Unknown Rust profile '{name}'. Available: {available}")
    return RUST_PROFILES[name]


def list_profiles() -> list[RustProfile]:
    """Return all Rust profiles sorted by name."""
    return sorted(RUST_PROFILES.values(), key=lambda p: p.name)


def profile_guidelines(profile: RustProfile) -> tuple[str, ...]:
    """Translate a profile's guardrails into system-prompt guidelines.

    The returned strings are meant for
    :class:`tau_coding.system_prompt.BuildSystemPromptOptions.extra_guidelines`
    so that ``--profile <name>`` measurably changes the agent's behavior. A
    persona line is always emitted first; each enabled guardrail then adds a
    concrete, actionable rule the agent must follow.
    """
    guidelines: list[str] = [
        f"Active Rust profile: {profile.emoji} {profile.name} — {profile.description} "
        f"(use when: {profile.use_when})."
    ]

    if profile.require_cargo_check:
        guidelines.append(
            "Always verify your changes compile by running `cargo check` (and `cargo test` "
            "for anything that should be tested) before declaring a task complete."
        )
    if profile.enforce_rustfmt:
        guidelines.append(
            "Always run `cargo fmt` (or `rustfmt --check`) before finishing so changes match "
            "the project's formatting."
        )
    if profile.forbid_unwrap:
        guidelines.append(
            "NEVER use `.unwrap()`, `.expect()`, or `panic!()` in suggested code. Propagate "
            "errors with `Result`/`Option` and the `?` operator, or use `thiserror`/`anyhow`."
        )
    if profile.forbid_unsafe:
        guidelines.append(
            "Do NOT introduce `unsafe` blocks. If a situation truly requires unsafe, stop and "
            "explain the constraint and the safety invariants that would be needed instead of "
            "writing the unsafe code."
        )
    if profile.require_doc_tests:
        guidelines.append(
            "Add `///` doc comments with a runnable ```rust example to every public item you "
            "create or modify; doc-tests must pass under `cargo test`."
        )
    if profile.enforce_clippy_pedantic:
        guidelines.append(
            "Hold the code to `clippy::pedantic` standards: run `cargo clippy -- "
            "-W clippy::pedantic` and address or explicitly justify every finding."
        )

    return tuple(guidelines)
