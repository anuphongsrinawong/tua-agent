"""Canonical filesystem paths for Tau user and project data."""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TauPaths:
    """Resolved Tau filesystem locations.

    Tau keeps durable application data under the user's home directory while also
    loading project-local resources from the active working directory.
    """

    home: Path = field(default_factory=lambda: Path.home() / ".tau")
    agents_home: Path = field(default_factory=lambda: Path.home() / ".agents")

    @property
    def sessions_dir(self) -> Path:
        """Return the user-level session directory."""
        return self.home / "sessions"

    @property
    def user_skills_dir(self) -> Path:
        """Return Tau's user-level skills directory."""
        return self.home / "skills"

    @property
    def user_prompts_dir(self) -> Path:
        """Return Tau's user-level prompt templates directory."""
        return self.home / "prompts"

    @property
    def user_agents_skills_dir(self) -> Path:
        """Return the user-level `.agents/skills` directory."""
        return self.agents_home / "skills"

    @property
    def user_agents_prompts_dir(self) -> Path:
        """Return the user-level `.agents/prompts` directory."""
        return self.agents_home / "prompts"

    def project_tau_dir(self, cwd: Path) -> Path:
        """Return the project-local Tau resource directory."""
        return cwd / ".tau"

    def project_agents_dir(self, cwd: Path) -> Path:
        """Return the project-local `.agents` resource directory."""
        return cwd / ".agents"

    def project_skills_dir(self, cwd: Path) -> Path:
        """Return the project-local Tau skills directory."""
        return self.project_tau_dir(cwd) / "skills"

    def project_prompts_dir(self, cwd: Path) -> Path:
        """Return the project-local Tau prompt templates directory."""
        return self.project_tau_dir(cwd) / "prompts"

    def project_agents_skills_dir(self, cwd: Path) -> Path:
        """Return the project-local `.agents/skills` directory."""
        return self.project_agents_dir(cwd) / "skills"

    def project_agents_prompts_dir(self, cwd: Path) -> Path:
        """Return the project-local `.agents/prompts` directory."""
        return self.project_agents_dir(cwd) / "prompts"

    def project_session_dir(self, cwd: Path) -> Path:
        """Return the user-home session directory for a project cwd."""
        digest = sha256(str(cwd.resolve()).encode("utf-8")).hexdigest()[:16]
        return self.sessions_dir / digest

    def default_session_path(self, cwd: Path) -> Path:
        """Return the default JSONL session path for a project cwd."""
        path = self.project_session_dir(cwd) / "default.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
