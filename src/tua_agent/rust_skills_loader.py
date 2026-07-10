"""Rust skills loader for Tua Agent.

Ensures bundled Rust skills are available at runtime regardless of
installation method (dev checkout, pip install, uv tool install).

On first run, copies bundled skills from the package to ~/.tau/skills/.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def ensure_skills_installed() -> list[Path]:
    """Copy bundled skills to ~/.tau/skills/ if missing, return list of SKILL.md paths."""
    user_skills = Path.home() / ".tau" / "skills"
    bundled = _find_bundled_skills()

    installed = []
    for src in bundled:
        skill_name = src.parent.name
        dst_dir = user_skills / skill_name
        dst = dst_dir / "SKILL.md"

        if not dst.exists():
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        installed.append(dst)

    return installed


def _find_bundled_skills() -> list[Path]:
    """Find bundled SKILL.md files in priority order."""
    candidates = []

    # 1. Package data: <package>/data/skills/ (works in dev + wheel installs)
    pkg_skills = Path(__file__).resolve().parent / "data" / "skills"
    if pkg_skills.exists():
        candidates.extend(sorted(pkg_skills.glob("*/SKILL.md")))

    # 3. Already installed: ~/.tau/skills/
    user_skills = Path.home() / ".tau" / "skills"
    if user_skills.exists():
        for d in sorted(user_skills.iterdir()):
            skill_md = d / "SKILL.md"
            if skill_md.exists() and skill_md not in candidates:
                candidates.append(skill_md)

    return candidates


def count_skills() -> int:
    """Return number of available Rust skills."""
    return len(ensure_skills_installed())
