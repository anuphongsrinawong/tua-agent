"""Dhamma agent profiles — named combinations of principles for different use cases.

Named profiles let you select the right set of Dhamma principles for the task
without manually configuring every flag. Each profile tunes :class:`DhammaConfig`
for a specific scenario: observation, safety, kindness, wisdom, resilience, or
full enlightenment.

Profiles:
    BASELINE    — no dhamma (plain Tau)
    VIPASSANA  — วิปัสสนา: observe everything (สติ + อิทัปปัจจยตา)
    SILA       — ศีล: prevent harm (สัมมาวายามะ + กุศล)
    METTA      — เมตตา: kind helper (เมตตา+กรุณา + ขันติ)
    PANNA      — ปัญญา: reason and adapt (โยนิโส + วิมุตติ)
    MAJJHIMA   — มัชฌิมา: balanced resilience (มัชฌิมา + อนิจจัง)
    ARAHANT    — อรหันต์: full enlightenment (ALL 10 principles)

Usage::

    from tau_agent.dhamma_profiles import get_profile, VIPASSANA
    profile = get_profile("vipassana")
    harness_config = profile.apply_to_config(base_config)

CLI (future)::

    tau --profile vipassana -p "refactor auth"
    tau --compare "refactor auth"  # runs all profiles, prints report
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tau_agent.dhamma import DhammaConfig

__all__ = [
    "ALL_PROFILES",
    "ARAHANT",
    "BASELINE",
    "BODHISATTVA",
    "BUDDHA",
    "MAJJHIMA",
    "METTA",
    "PANNA",
    "SILA",
    "VIPASSANA",
    "DhammaProfile",
    "get_profile",
    "profile_names",
    "profile_summary",
]


@dataclass(frozen=True, slots=True)
class DhammaProfile:
    """A named, immutable combination of Dhamma principles tuned for a use case."""

    name: str
    emoji: str
    description: str
    principles: tuple[str, ...]
    config: DhammaConfig
    use_when: str = ""

    # Precomputed title for display tables.
    _title: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_title", f"{self.emoji} {self.name}")


# ---------------------------------------------------------------------------
# Pre-built profiles
# ---------------------------------------------------------------------------

# All flags off by default. Override specific flags below.

BASELINE = DhammaProfile(
    name="Baseline",
    emoji="⚪",
    description="No Dhamma — plain Tau behavior for comparison.",
    principles=(),
    config=DhammaConfig(
        enable_mindfulness=False,
        enable_causal_trace=False,
        enable_non_attachment=False,
        enable_beneficial_output=False,
        enable_middle_way=False,
        enable_impermanence=False,
        enable_systematic_attention=False,
        enable_right_effort=False,
        enable_patience=False,
        enable_context_judgment=False,
    ),
    use_when="Benchmark / A/B comparison baseline",
)

VIPASSANA = DhammaProfile(
    name="Vipassana",
    emoji="🔍",
    description="Pure observation — watch everything, trace every cause. No intervention.",
    principles=("สติ", "อิทัปปัจจยตา"),
    config=DhammaConfig(
        enable_mindfulness=True,
        enable_causal_trace=True,
    ),
    use_when="Debugging, auditing, learning how an agent thinks",
)

SILA = DhammaProfile(
    name="Sila",
    emoji="🛡️",
    description="Ethics guard — prevent harm, context-aware decisions.",
    principles=("สัมมาวายามะ", "กุศล"),
    config=DhammaConfig(
        enable_right_effort=True,
        enable_context_judgment=True,
    ),
    use_when="Production deployments, sensitive operations, safety-critical tasks",
)

METTA = DhammaProfile(
    name="Metta",
    emoji="💚",
    description="Kind helper — helpful output, patient with users.",
    principles=("เมตตา+กรุณา", "ขันติ"),
    config=DhammaConfig(
        enable_beneficial_output=True,
        enable_patience=True,
    ),
    use_when="User-facing agent, onboarding, customer support",
)

PANNA = DhammaProfile(
    name="Panna",
    emoji="🧠",
    description="Wisdom — reason before acting, drop failed approaches.",
    principles=("โยนิโสมนสิการ", "วิมุตติ"),
    config=DhammaConfig(
        enable_systematic_attention=True,
        enable_non_attachment=True,
    ),
    use_when="Complex refactoring, hard debugging, novel problem-solving",
)

MAJJHIMA = DhammaProfile(
    name="Majjhima",
    emoji="⚖️",
    description="Middle path — balanced retry, graceful degradation.",
    principles=("มัชฌิมาปฏิทา", "อนิจจัง"),
    config=DhammaConfig(
        enable_middle_way=True,
        enable_impermanence=True,
    ),
    use_when="Flaky networks, unreliable APIs, long-running batch jobs",
)

ARAHANT = DhammaProfile(
    name="Arahant",
    emoji="🪷",
    description="Full enlightenment — every Dhamma principle active.",
    principles=(
        "สติ", "มัชฌิมาปฏิทา", "อนิจจัง", "โยนิโสมนสิการ",
        "สัมมาวายามะ", "อิทัปปัจจยตา", "ขันติ", "เมตตา+กรุณา",
        "วิมุตติ", "กุศล",
    ),
    config=DhammaConfig(
        enable_mindfulness=True,
        enable_causal_trace=True,
        enable_non_attachment=True,
        enable_beneficial_output=True,
        enable_middle_way=True,
        enable_impermanence=True,
        enable_systematic_attention=True,
        enable_right_effort=True,
        enable_patience=True,
        enable_context_judgment=True,
        enable_iddhipada=True,
    ),
    use_when="Mission-critical work — full protection + awareness",
)

# Extended profiles (require dhamma_extended.py — optional)
try:
    import importlib

    _HAS_EXTENDED = importlib.util.find_spec("tau_agent.dhamma_extended") is not None  # type: ignore[assignment]
except ImportError:
    _HAS_EXTENDED = False

if _HAS_EXTENDED:
    BODHISATTVA = DhammaProfile(
        name="Bodhisattva",
        emoji="🌸",
        description="Help others reach enlightenment — compassion + wisdom + encouragement.",
        principles=(
            "โยนิโส", "วิมุตติ", "สัมมาวายามะ", "กุศล",
            "เมตตา+กรุณา", "มุทิตา", "อุเบกขา", "กัลยาณมิตร",
        ),
        config=DhammaConfig(
            enable_systematic_attention=True,
            enable_non_attachment=True,
            enable_right_effort=True,
            enable_context_judgment=True,
            enable_beneficial_output=True,
            enable_patience=True,
            enable_iddhipada=True,
        ),
        use_when="Teaching, mentoring, user-facing agents that need warmth",
    )

    BUDDHA = DhammaProfile(
        name="Buddha",
        emoji="☸️",
        description="Complete awakening — ALL 18 principles across base + extended.",
        principles=(
            "สติ", "มัชฌิมาปฏิทา", "อนิจจัง", "โยนิโสมนสิการ",
            "สัมมาวายามะ", "อิทัปปัจจยตา", "ขันติ", "เมตตา+กรุณา",
            "วิมุตติ", "กุศล",
            "สมถะ+วิปัสสนา", "อริยสัจ 4", "มุทิตา", "อุเบกขา",
            "สัมปชัญญะ", "หิริโอตตัปปะ", "อิทธิบาท 4", "กัลยาณมิตร",
        ),
        config=DhammaConfig(
            enable_mindfulness=True,
            enable_causal_trace=True,
            enable_non_attachment=True,
            enable_beneficial_output=True,
            enable_middle_way=True,
            enable_impermanence=True,
            enable_systematic_attention=True,
            enable_right_effort=True,
            enable_patience=True,
            enable_context_judgment=True,
            enable_iddhipada=True,
        ),
        use_when="Everything matters — full enlightenment for the most critical work",
    )
else:
    BODHISATTVA = None  # type: ignore[assignment]
    BUDDHA = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ALL: dict[str, DhammaProfile] = {
    "baseline": BASELINE,
    "vipassana": VIPASSANA,
    "sila": SILA,
    "metta": METTA,
    "panna": PANNA,
    "majjhima": MAJJHIMA,
    "arahant": ARAHANT,
}

if BODHISATTVA is not None:
    _ALL["bodhisattva"] = BODHISATTVA
if BUDDHA is not None:
    _ALL["buddha"] = BUDDHA

ALL_PROFILES: Sequence[DhammaProfile] = tuple(_ALL.values())


def profile_names() -> tuple[str, ...]:
    """All registered profile names (lowercase keys)."""
    return tuple(_ALL.keys())


def get_profile(name: str) -> DhammaProfile:
    """Return the DhammaProfile for a case-insensitive name.

    Raises KeyError if the profile is not found.
    """
    key = name.strip().lower()
    if key not in _ALL:
        available = ", ".join(sorted(_ALL.keys()))
        raise KeyError(f"Unknown profile '{name}'. Available: {available}")
    return _ALL[key]


def profile_summary() -> str:
    """Return a human-readable comparison table of all profiles."""
    lines: list[str] = []
    lines.append("Profile Comparison Table")
    lines.append("=" * 78)
    lines.append(f"{'Profile':<20} {'#':<4} {'Use When'}")
    lines.append("-" * 78)
    for profile in ALL_PROFILES:
        title = f"{profile.emoji} {profile.name}"
        count = len(profile.principles)
        use = profile.use_when[:52]
        lines.append(f"{title:<20} {count:<4} {use}")
    lines.append("=" * 78)
    lines.append(f"Total profiles: {len(ALL_PROFILES)}")
    return "\n".join(lines)
