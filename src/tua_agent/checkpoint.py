"""Git checkpointing helpers for Tua Agent (#16).

Provides safe git snapshot/rollback operations so sessions can checkpoint
after every successful ``cargo check`` and offer ``/rollback`` / ``/undo``
in the TUI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def is_git_repo(cwd: Path | str | None = None) -> bool:
    """Return ``True`` when the given directory is inside a git work-tree."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def git_is_clean(cwd: Path | str | None = None) -> bool:
    """Return ``True`` when there are no uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return True


def checkpoint(cwd: Path | str | None = None, message: str = "checkpoint: cargo check passed") -> str | None:
    """Stage all changes and create a checkpoint commit.

    Returns the commit hash on success, ``None`` when there is nothing to commit
    or the operation failed.
    """
    if not shutil.which("git"):
        return None
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=cwd,
            capture_output=True,
            timeout=30,
            check=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Extract the commit hash from output
            for line in reversed(result.stdout.splitlines()):
                if line.strip().startswith("[") and "]" in line:
                    commit = result.stdout.strip().split()[-1].rstrip("]")
                    return commit
            rev_parse = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if rev_parse.returncode == 0:
                return rev_parse.stdout.strip()[:8]
        return None
    except subprocess.SubprocessError:
        return None


def rollback(cwd: Path | str | None = None) -> bool:
    """Hard-reset to HEAD~1, discarding the last commit AND working-tree changes."""
    try:
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            cwd=cwd,
            capture_output=True,
            timeout=30,
            check=True,
        )
        return True
    except subprocess.SubprocessError:
        return False


def last_commit_hash(cwd: Path | str | None = None) -> str | None:
    """Return the abbreviated hash of HEAD, or ``None``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
