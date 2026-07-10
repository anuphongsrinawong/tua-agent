"""Rust session configuration for Tua Agent.

Converts RustProfile guardrails into concrete system prompt guidelines
without any Dhamma dependencies. Pure Rust coding focus.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tua_agent.rust_profiles import RustProfile, get_profile


@dataclass(frozen=True)
class RustSessionConfig:
    """Wraps a RustProfile and produces system prompt guidelines."""

    profile: RustProfile = field(default_factory=lambda: get_profile("rustacean"))

    def build_guidelines(self) -> list[str]:
        """Build extra system prompt guidelines from the profile's guardrails."""
        guidelines: list[str] = []

        if self.profile.forbid_unwrap:
            guidelines.append(
                "NEVER use .unwrap() or .expect() in production code. "
                "Use proper error handling with Result and the ? operator."
            )

        if self.profile.forbid_unsafe:
            guidelines.append(
                "Do NOT write unsafe blocks. All code must be safe Rust."
            )

        if self.profile.require_doc_tests:
            guidelines.append(
                "Every public function, struct, and trait must have /// doc comments "
                "with examples that serve as doc-tests."
            )

        if self.profile.enforce_clippy_pedantic:
            guidelines.append(
                "Run `cargo clippy -- -W clippy::pedantic` after every code change "
                "and fix all warnings before considering the task complete."
            )

        if self.profile.enforce_rustfmt:
            guidelines.append(
                "Run `cargo fmt` after every code change to ensure consistent formatting."
            )

        if self.profile.require_cargo_check:
            guidelines.append(
                "Always run `cargo check` before suggesting code changes to verify they compile."
            )

        return guidelines

    def build_profile_context(self) -> str:
        """Build a human-readable profile context string for the system prompt."""
        lines = [
            f"## Active Rust Profile: {self.profile.emoji} {self.profile.name}",
            f"  {self.profile.description}",
            "",
            "Profile Guardrails:",
        ]
        if self.profile.forbid_unwrap:
            lines.append("  ❌ .unwrap() / .expect() FORBIDDEN")
        if self.profile.forbid_unsafe:
            lines.append("  ❌ unsafe blocks FORBIDDEN")
        if self.profile.require_doc_tests:
            lines.append("  ✅ Doc-tests REQUIRED on all public API")
        if self.profile.enforce_clippy_pedantic:
            lines.append("  ✅ Clippy pedantic lint level ENFORCED")
        if self.profile.enforce_rustfmt:
            lines.append("  ✅ rustfmt REQUIRED after every change")
        if self.profile.require_cargo_check:
            lines.append("  ✅ cargo check REQUIRED before suggesting changes")

        return "\n".join(lines)
