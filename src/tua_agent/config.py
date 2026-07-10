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

    @classmethod
    def load(cls, project_dir: Path | None = None) -> TuaConfig:
        """Load config from project and user directories."""
        config = cls()

        # Load user-global config
        user_config = Path.home() / ".tua" / "config.toml"
        if user_config.exists():
            config._merge(user_config)

        # Load project config (overrides user)
        if project_dir:
            project_config = project_dir / ".tua" / "config.toml"
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


def load_config(project_dir: Path | None = None) -> TuaConfig:
    """Convenience function to load Tua configuration."""
    return TuaConfig.load(project_dir)
