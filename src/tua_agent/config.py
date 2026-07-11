"""Tua Agent configuration loader.

Reads .tua/config.toml (project) and ~/.tua/config.toml (user-global).
Uses Python 3.11+ tomllib for TOML parsing.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore


@dataclass
class TuaConfig:
    """Tua Agent configuration."""

    # Profile
    default_profile: str = "rustacean"

    # Tools
    tool_timeout: int = 600
    max_output_chars: int = 16000

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8765

    # Rust
    rust_edition: str = "2021"
    clippy_pedantic: bool = False
    require_doc_tests: bool = False

    # AI intelligence (v0.0.2 Phase 2: #13/#16/#17/#18/#19)
    self_correction: bool = True          # #13 auto cargo-check self-fix loop
    max_self_corrections: int = 3         # #13 cap on correction turns
    checkpoint_enabled: bool = True       # #16 git checkpoint on green build
    context_limit: int = 128_000          # #17 token budget ceiling
    prompt_caching: bool = True           # #18 reorder for cache breakpoints
    review_enabled: bool = True           # #19 background clippy + code review

    @classmethod
    def load(cls, project_dir: Path | None = None) -> TuaConfig:
        """Load config from project and user directories."""
        config = cls()

        user_config, project_config = config_paths(project_dir)

        # Load user-global config
        if user_config.exists():
            config._merge(user_config)

        # Load project config (overrides user)
        if project_config.exists():
            config._merge(project_config)

        return config

    def _merge(self, path: Path) -> None:
        """Merge TOML config file into this config."""
        try:
            data = tomllib.loads(path.read_text())
        except Exception:
            return

        if "profile" in data:
            p = data["profile"]
            if "default" in p:
                self.default_profile = p["default"]

        if "tools" in data:
            t = data["tools"]
            if "timeout" in t:
                self.tool_timeout = int(t["timeout"])
            if "max_output_chars" in t:
                self.max_output_chars = int(t["max_output_chars"])

        if "dashboard" in data:
            d = data["dashboard"]
            if "host" in d:
                self.dashboard_host = d["host"]
            if "port" in d:
                self.dashboard_port = int(d["port"])

        if "rust" in data:
            r = data["rust"]
            if "edition" in r:
                self.rust_edition = r["edition"]
            if "clippy_pedantic" in r:
                self.clippy_pedantic = bool(r["clippy_pedantic"])
            if "require_doc_tests" in r:
                self.require_doc_tests = bool(r["require_doc_tests"])

        # AI intelligence settings (v0.0.2 Phase 2)
        if "ai" in data:
            a = data["ai"]
            if "self_correction" in a:
                self.self_correction = bool(a["self_correction"])
            if "max_self_corrections" in a:
                self.max_self_corrections = int(a["max_self_corrections"])
            if "checkpoint_enabled" in a:
                self.checkpoint_enabled = bool(a["checkpoint_enabled"])
            if "context_limit" in a:
                self.context_limit = int(a["context_limit"])
            if "prompt_caching" in a:
                self.prompt_caching = bool(a["prompt_caching"])
            if "review_enabled" in a:
                self.review_enabled = bool(a["review_enabled"])


def load_config(project_dir: Path | None = None) -> TuaConfig:
    """Convenience function to load Tua configuration."""
    return TuaConfig.load(project_dir)


def config_paths(project_dir: Path | None = None) -> tuple[Path, Path]:
    """Return ``(user_global, project)`` config file paths.

    The files may not exist yet — this only reports where Tua looks. The project
    path is ``<project_dir>/.tua/config.toml`` (or the current directory when no
    ``project_dir`` is given); the user-global path is ``~/.tua/config.toml``.
    """
    user_config = Path.home() / ".tua" / "config.toml"
    project_config = (project_dir or Path.cwd()) / ".tua" / "config.toml"
    return user_config, project_config
