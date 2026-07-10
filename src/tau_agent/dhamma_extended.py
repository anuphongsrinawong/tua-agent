"""Extended Dhamma principles — 8 additional Buddhist-inspired agent patterns.

These build on the 10 base principles in ``dhamma.py`` for a total of
18 principles covering the full spectrum of Buddhist agent engineering.

New principles:
    11. สมถะ+วิปัสสนา (Samatha+Vipassana) — CalmThenInvestigate
    12. อริยสัจ 4 (Four Noble Truths) — FourNobleTruths
    13. มุทิตา (Mudita) — SympatheticJoy
    14. อุเบกขา (Upekkha) — Equanimity
    15. สัมปชัญญะ (Sampajanna) — ClearComprehension
    16. หิริโอตตัปปะ (Hiri-Ottappa) — MoralRegulator
    17. อิทธิบาท 4 (Iddhipada) — SuccessFramework
    18. กัลยาณมิตร (Kalyanamitta) — GoodCompanion

This module is optional — ``dhamma_profiles.py`` imports it with a try/except
guard so extended profiles (BODHISATTVA, BUDDHA) are available when present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "CalmThenInvestigate",
    "ClearComprehension",
    "ContextAssessment",
    "Diagnosis",
    "Equanimity",
    "FourNobleTruths",
    "GoodCompanion",
    "MaggaStep",
    "MoralRegulator",
    "ReadinessAssessment",
    "SuccessFramework",
    "SympatheticJoy",
]


# ===========================================================================
# 2.11 สมถะ+วิปัสสนา (Samatha+Vipassana) — CalmThenInvestigate
# ===========================================================================


@dataclass(slots=True)
class CalmThenInvestigate:
    """สมถะ+วิปัสสนา: stabilize the mind first, then investigate deeply.

    Two-phase pattern: when the agent is chaotic (high error rate, loops, token
    pressure), first settle into a calm state with safe read-only actions, then
    once stable, proceed with deep investigation.
    """

    error_rate_threshold: float = 0.5
    token_pressure_fraction: float = 0.9
    min_errors_for_calm: int = 3

    def should_calm(self, error_count: int, tool_count: int, tokens_used: int, max_tokens: int) -> bool:
        """True when the agent should pause and stabilize before continuing."""
        if tool_count == 0 and error_count > 0:
            return True
        error_rate = error_count / max(tool_count, 1)
        if error_rate >= self.error_rate_threshold and error_count >= self.min_errors_for_calm:
            return True
        if max_tokens > 0 and tokens_used / max_tokens >= self.token_pressure_fraction:
            return True
        return False

    def calm_down_actions(self) -> list[str]:
        """Safe, lightweight actions to stabilize before deep work."""
        return [
            "read the README or project docs",
            "check git status",
            "list the current directory",
            "review recent session history",
            "verify environment variables",
            "check available tools",
        ]

    def stabilize(self, context: str) -> list[str]:
        """Return stabilizing actions contextualized to the situation."""
        base = self.calm_down_actions()
        if context:
            return [f"{action} (context: {context})" for action in base[:3]]
        return base[:3]

    def investigate(self, problem: str, context: str) -> list[str]:
        """After stabilization, return structured investigation questions."""
        questions = [
            f"What is the root cause of '{problem}'?",
            "What information is missing?",
            "What tools are available to gather that information?",
            "What is the smallest testable hypothesis?",
        ]
        if context:
            questions.insert(0, f"How does '{context}' relate to the problem?")
        return questions


# ===========================================================================
# 2.12 อริยสัจ 4 (Four Noble Truths) — FourNobleTruths
# ===========================================================================


@dataclass(frozen=True, slots=True)
class MaggaStep:
    """One step on the path to resolution."""

    action: str
    tool: str
    expected_outcome: str


@dataclass(slots=True)
class Diagnosis:
    """Dukkha → Samudaya → Nirodha → Magga: a complete failure diagnosis."""

    dukkha: str      # the problem / symptom
    samudaya: str    # root cause
    nirodha: str     # what "fixed" looks like
    magga: list[MaggaStep] = field(default_factory=list)


# Known error → recovery pattern mapping
_KNOWN_PATTERNS: dict[str, Diagnosis] = {
    "FileNotFoundError": Diagnosis(
        dukkha="File not found",
        samudaya="Path is incorrect or file was moved/deleted",
        nirodha="The file exists and can be read",
        magga=[
            MaggaStep("list the parent directory", "bash", "discover correct path"),
            MaggaStep("check for similar filenames", "grep", "find the right file"),
            MaggaStep("verify with user or docs", "read", "confirm path"),
        ],
    ),
    "ModuleNotFoundError": Diagnosis(
        dukkha="Python module not found",
        samudaya="Missing dependency or incorrect import path",
        nirodha="Module imports successfully",
        magga=[
            MaggaStep("check installed packages", "bash", "verify pip list"),
            MaggaStep("run uv sync or pip install", "bash", "install dependency"),
            MaggaStep("verify import path is correct", "read", "confirm module path"),
        ],
    ),
    "timeout": Diagnosis(
        dukkha="Operation timed out",
        samudaya="Network latency or overloaded service",
        nirodha="Operation completes within time limit",
        magga=[
            MaggaStep("wait and retry with backoff", "bash", "transient issue resolved"),
            MaggaStep("reduce request size", "bash", "smaller payload"),
            MaggaStep("check connectivity", "bash", "verify network"),
        ],
    ),
}


@dataclass(slots=True)
class FourNobleTruths:
    """อริยสัจ 4: diagnose → find cause → know fix exists → apply the path."""

    def diagnose(self, failure: str) -> Diagnosis:
        """Diagnose a failure using the four noble truths framework."""
        dukkha = failure[:200]

        # Check known patterns
        for pattern, diagnosis in _KNOWN_PATTERNS.items():
            if pattern.lower() in failure.lower():
                return diagnosis

        # Generic diagnosis
        return Diagnosis(
            dukkha=dukkha,
            samudaya="Unknown — needs investigation",
            nirodha="The operation succeeds without error",
            magga=[
                MaggaStep("read the error message carefully", "read", "understand what failed"),
                MaggaStep("check logs or recent changes", "bash", "find relevant context"),
                MaggaStep("try a smaller, simpler step", "bash", "isolate the problem"),
            ],
        )

    def has_known_pattern(self, error_type: str) -> bool:
        """True if this error type matches a known recovery pattern."""
        return any(p.lower() in error_type.lower() for p in _KNOWN_PATTERNS)

    def apply_magga(self, diagnosis: Diagnosis) -> list[str]:
        """Return the ordered recovery steps."""
        return [
            f"[{i+1}] {step.action} (tool: {step.tool}) → expect: {step.expected_outcome}"
            for i, step in enumerate(diagnosis.magga)
        ]


# ===========================================================================
# 2.13 มุทิตา (Mudita / Sympathetic Joy) — SympatheticJoy
# ===========================================================================


@dataclass(slots=True)
class SympatheticJoy:
    """มุทิตา: celebrate successes, learn from what worked well."""

    _successes: list[tuple[str, str]] = field(default_factory=list)
    _tool_success: dict[str, int] = field(default_factory=dict)
    _tool_total: dict[str, int] = field(default_factory=dict)

    def celebrate_success(self, action: str, result: str) -> None:
        """Log a successful action for pattern extraction."""
        self._successes.append((action, result[:120]))

    def record_tool(self, tool_name: str, ok: bool) -> None:
        """Track per-tool success/failure counts."""
        self._tool_total[tool_name] = self._tool_total.get(tool_name, 0) + 1
        if ok:
            self._tool_success[tool_name] = self._tool_success.get(tool_name, 0) + 1

    def success_rate_by_tool(self, tool_name: str) -> float:
        """Success rate for a specific tool (0-1)."""
        total = self._tool_total.get(tool_name, 0)
        if total == 0:
            return 0.0
        return self._tool_success.get(tool_name, 0) / total

    def success_patterns(self) -> list[str]:
        """Recurring patterns from successful actions."""
        if len(self._successes) < 3:
            return ["Not enough successes to extract patterns yet — keep going!"]
        patterns: list[str] = []
        seen_actions: set[str] = set()
        for action, _ in self._successes:
            if action not in seen_actions:
                seen_actions.add(action)
                if self.success_rate_by_tool(action) >= 0.8:
                    patterns.append(f"✓ '{action}' works reliably — use it when possible")
        if not patterns:
            patterns.append("Successes are scattered — focus on repeatable workflows")
        return patterns

    def encouragement_message(self) -> str:
        """Generate a positive note based on what's been working."""
        total = len(self._successes)
        if total == 0:
            return "Every journey starts with a first step. Let's begin!"
        if total < 5:
            return f"Good progress — {total} successes so far. Building momentum."
        return f"Excellent work — {total} successes! You're on a roll."

    def learn_from_success(self) -> dict[str, Any]:
        """Analyze what worked."""
        return {
            "total_successes": len(self._successes),
            "top_tool": max(self._tool_success, key=lambda k: self._tool_success[k]) if self._tool_success else "none",
            "patterns": self.success_patterns(),
        }


# ===========================================================================
# 2.14 อุเบกขา (Upekkha / Equanimity) — Equanimity
# ===========================================================================


@dataclass(slots=True)
class Equanimity:
    """อุเบกขา: stay steady regardless of outcome — completes the Brahmavihara.

    Together with Metta (loving-kindness), Karuna (compassion), and Mudita
    (sympathetic joy), Upekkha provides the fourth divine abode: equanimity
    in the face of all results.
    """

    window_size: int = 10
    _outcomes: list[bool] = field(default_factory=list)
    _swing_threshold: float = 0.6

    def record_outcome(self, ok: bool) -> None:
        """Record a success (True) or failure (False)."""
        self._outcomes.append(ok)
        if len(self._outcomes) > self.window_size * 2:
            self._outcomes = self._outcomes[-self.window_size:]

    def emotional_state(self) -> Literal["excited", "calm", "frustrated"]:
        """Assess the agent's recent emotional trajectory."""
        if len(self._outcomes) < 3:
            return "calm"
        recent = self._outcomes[-3:]
        if all(recent):
            return "excited"
        if not any(recent):
            return "frustrated"
        return "calm"

    def is_reactive(self) -> bool:
        """True when the agent swings between extremes."""
        if len(self._outcomes) < 4:
            return False
        # Count transitions between success and failure
        swings = sum(
            1 for i in range(1, min(self.window_size, len(self._outcomes)))
            if self._outcomes[i] != self._outcomes[i - 1]
        )
        window = min(self.window_size, len(self._outcomes))
        return (swings / max(window - 1, 1)) >= self._swing_threshold

    def steady_nudge(self) -> str:
        """A calming instruction for when the agent is reactive."""
        state = self.emotional_state()
        if state == "excited":
            return "Success is good — but stay focused. Verify before celebrating."
        if state == "frustrated":
            return "Setbacks happen. Take a breath, re-read the context, try one small step."
        return "Steady and aware. Continue with intention."

    def brahmavihara_balance(self) -> str:
        """Which Brahmavihara quality is most needed right now?"""
        if len(self._outcomes) < 3:
            return "metta"
        recent = self._outcomes[-3:]
        all_ok = sum(recent) / len(recent)
        if all_ok >= 0.8:
            return "mudita"    # things are going well → celebrate
        if all_ok <= 0.2:
            return "karuna"    # things are hard → be compassionate
        if self.is_reactive():
            return "upekkha"  # swinging → need equanimity
        return "metta"         # steady → maintain kindness


# ===========================================================================
# 2.15 สัมปชัญญะ (Sampajanna / Clear Comprehension) — ClearComprehension
# ===========================================================================


@dataclass(slots=True)
class ContextAssessment:
    """Full contextual picture before taking action."""

    goal_clarity: float       # 0-1: how well-defined is the goal?
    tool_readiness: float     # 0-1: are needed tools available?
    context_gaps: list[str]   # what information is missing?
    risk_assessment: str      # structured risk analysis
    recommended_prep: list[str]  # what to do before starting


@dataclass(slots=True)
class ClearComprehension:
    """สัมปชัญญะ: full contextual understanding before acting."""

    _available_tools: list[str] = field(default_factory=list)

    def set_available_tools(self, tools: list[str]) -> None:
        self._available_tools = tools

    def assess_context(self, task: str, environment: str) -> ContextAssessment:
        """Assess whether the context is sufficient to proceed."""
        has_goal = len(task.strip()) > 20
        goal_clarity = 0.9 if has_goal else 0.3

        tool_readiness = min(1.0, len(self._available_tools) / 5.0) if self._available_tools else 0.5

        gaps: list[str] = []
        if not has_goal:
            gaps.append("Goal is vague — need more specifics")
        if not self._available_tools:
            gaps.append("No tools available — cannot take action")
        if "path" not in task.lower() and "file" in task.lower():
            gaps.append("File operation mentioned but no path specified")

        risk = "low"
        if any(word in task.lower() for word in ("delete", "rm", "drop", "overwrite", "force")):
            risk = "high"
        elif any(word in task.lower() for word in ("write", "edit", "bash", "execute")):
            risk = "medium"

        prep: list[str] = []
        if risk != "low":
            prep.append("Make a backup or use version control before changing anything")
        if gaps:
            prep.append("Fill context gaps before proceeding")
        if tool_readiness < 0.5:
            prep.append("Verify tool availability")

        return ContextAssessment(
            goal_clarity=goal_clarity,
            tool_readiness=tool_readiness,
            context_gaps=gaps,
            risk_assessment=risk,
            recommended_prep=prep,
        )

    def context_sufficient(self, assessment: ContextAssessment) -> bool:
        """True if the context is adequate to proceed."""
        return (
            assessment.goal_clarity >= 0.7
            and assessment.tool_readiness >= 0.5
            and len(assessment.context_gaps) == 0
        )

    def fill_gaps(self, assessment: ContextAssessment) -> list[str]:
        """Return ordered info-gathering actions to fill context gaps."""
        actions: list[str] = []
        if assessment.goal_clarity < 0.7:
            actions.append("Ask for clarification on the goal")
        for gap in assessment.context_gaps:
            actions.append(f"Investigate: {gap}")
        if not actions and assessment.risk_assessment == "high":
            actions.append("Create a backup before proceeding")
        return actions


# ===========================================================================
# 2.16 หิริโอตตัปปะ (Hiri-Ottappa / Moral Regulator) — MoralRegulator
# ===========================================================================


@dataclass(frozen=True, slots=True)
class AuditResult:
    """Result of an internal ethical audit."""

    ethical: bool
    reason: str
    alternative: str | None = None


_DESTRUCTIVE_CMDS: tuple[str, ...] = ("rm ", "drop ", "delete ", "truncate ", "mkfs", "dd if=")
_DANGEROUS_FLAGS: tuple[str, ...] = ("-rf", "--force", "-f ", "> /dev/", "| sh")


@dataclass(slots=True)
class MoralRegulator:
    """หิริโอตตัปปะ: internal ethical compass — self-regulation from within."""

    _audit_log: list[AuditResult] = field(default_factory=list)

    def hiri_check(self, action: str) -> tuple[bool, str]:
        """Shame check: would I be ashamed if this went catastrophically wrong?"""
        lowered = action.lower()
        for cmd in _DESTRUCTIVE_CMDS:
            if cmd in lowered:
                return False, f"'{cmd}' is destructive — consider a safer approach"
        for flag in _DANGEROUS_FLAGS:
            if flag in lowered:
                return False, f"'{flag}' is risky — double-check before proceeding"
        return True, "Action appears safe from a hiri (moral shame) perspective"

    def ottappa_check(self, action: str) -> tuple[bool, str]:
        """Fear-of-consequence check: what's the worst that could happen?"""
        lowered = action.lower()
        if any(path in lowered for path in ("/etc/", "/usr/", "/boot/", "/var/", "~/.ssh")):
            return False, "Action targets a system directory — consequences could be severe"
        if any(path in lowered for path in ("/dev/", "/proc/", "/sys/")):
            return False, "Action targets a kernel/device path — irreversible damage possible"
        if "sudo" in lowered or "root" in lowered:
            return False, "Action uses elevated privileges — double-check necessity"
        return True, "Consequences appear manageable from an ottappa perspective"

    def self_audit(self, action: str, context: str) -> AuditResult:
        """Complete ethical audit before executing a potentially harmful action."""
        hiri_ok, hiri_msg = self.hiri_check(action)
        ottappa_ok, ottappa_msg = self.ottappa_check(action)

        if hiri_ok and ottappa_ok:
            result = AuditResult(True, "Action passes hiri-ottappa audit")
        else:
            reasons = []
            if not hiri_ok:
                reasons.append(hiri_msg)
            if not ottappa_ok:
                reasons.append(ottappa_msg)
            reason = "; ".join(reasons)
            alternative = f"Consider a read-only equivalent or ask for confirmation before: {action[:80]}"
            result = AuditResult(False, reason, alternative)

        self._audit_log.append(result)
        return result

    @property
    def audit_log(self) -> list[AuditResult]:
        return list(self._audit_log)


# ===========================================================================
# 2.17 อิทธิบาท 4 (Iddhipada / Success Framework) — SuccessFramework
# ===========================================================================


@dataclass(frozen=True, slots=True)
class ReadinessAssessment:
    """Chanda → Viriya → Citta → Vimamsa: the four bases of success."""

    chanda: float    # will/desire: 0-1 — is this a worthy/desired goal?
    viriya: float    # energy: 0-1 — enough time, budget, stamina?
    citta: float     # focus: 0-1 — can we stay concentrated?
    vimamsa: float   # analysis: 0-1 — enough info to succeed?

    @property
    def weakest(self) -> str:
        """Name of the lowest-scoring base."""
        bases = {"chanda": self.chanda, "viriya": self.viriya, "citta": self.citta, "vimamsa": self.vimamsa}
        return min(bases, key=bases.get)  # type: ignore[arg-type]

    @property
    def overall(self) -> float:
        """Composite readiness score 0-1."""
        return (self.chanda + self.viriya + self.citta + self.vimamsa) / 4.0


@dataclass(slots=True)
class SuccessFramework:
    """อิทธิบาท 4: the four bases of success — will, energy, focus, analysis."""

    def assess_readiness(self, goal: str, budget: int = 10000, elapsed_turns: int = 0) -> ReadinessAssessment:
        """Assess the readiness to pursue a goal across all four bases."""
        # Chanda: is the goal clear and worthwhile?
        chanda = min(1.0, len(goal.strip()) / 80.0) if goal.strip() else 0.2

        # Viriya: enough budget remaining?
        viriya = max(0.0, 1.0 - (elapsed_turns / max(budget, 1)))

        # Citta: focused or scattered? (heuristic: goal keywords)
        focus_keywords = {"refactor", "fix", "add", "implement", "build", "test", "debug", "review"}
        goal_words = set(goal.lower().split())
        focus_score = len(goal_words & focus_keywords) / max(len(goal_words), 1)
        citta = min(1.0, focus_score * 2.0 + 0.2)

        # Vimamsa: enough info?
        vimamsa = 0.5
        if "error" in goal.lower() or "traceback" in goal.lower():
            vimamsa = 0.4  # error context may be incomplete
        if "file" in goal.lower() or "path" in goal.lower():
            vimamsa = 0.3  # file ops need confirmed paths

        return ReadinessAssessment(chanda=round(chanda, 2), viriya=round(viriya, 2),
                                   citta=round(citta, 2), vimamsa=round(vimamsa, 2))

    def boost_weakest(self, assessment: ReadinessAssessment) -> str:
        """Return an action to strengthen the weakest base."""
        actions: dict[str, str] = {
            "chanda": "Clarify the goal: what does success look like? Why is this important?",
            "viriya": "Assess resources: increase token budget or split into smaller tasks.",
            "citta": "Eliminate distractions: focus on one sub-task at a time.",
            "vimamsa": "Gather more information: read relevant files, understand the context.",
        }
        return actions.get(assessment.weakest, "Review the task and try again.")


# ===========================================================================
# 2.18 กัลยาณมิตร (Kalyanamitta / Good Companion) — GoodCompanion
# ===========================================================================


@dataclass(slots=True)
class GoodCompanion:
    """กัลยาณมิตร: agent as a trustworthy friend, not just a tool."""

    trust: float = 0.5
    _interaction_count: int = 0
    _successful_interactions: int = 0

    def record_interaction(self, successful: bool) -> None:
        """Update trust based on interaction outcome."""
        self._interaction_count += 1
        if successful:
            self._successful_interactions += 1
        if self._interaction_count > 0:
            self.trust = self._successful_interactions / self._interaction_count

    @property
    def trust_level(self) -> float:
        """0-1: how much trust has been built."""
        return self.trust

    def build_rapport(self, history_length: int) -> str:
        """Return a rapport-building message based on interaction history."""
        if history_length == 0:
            return "Hello! I'm here to help. What would you like to work on?"
        if history_length < 5:
            return "We're just getting started — feel free to ask anything!"
        if history_length < 20:
            return "We've been working together — I'm getting familiar with your project."
        return "We've built a solid working relationship. I understand your style and preferences."

    def encourage_progress(self, turns: int, errors: int) -> str:
        """Offer genuine encouragement when the agent is struggling."""
        if errors == 0:
            return "Smooth sailing so far — keep up the good work!"
        if errors < 3:
            return f"Minor bumps ({errors}) — perfectly normal. Let's keep going."
        return f"Hit some snags ({errors} errors), but every mistake is a lesson. You've got this."

    def companion_tone(self, text: str) -> str:
        """Rewrite technical text in a friendly, companion-like tone."""
        # Light transformation: add warmth markers
        text = text.strip()
        if text and not text.endswith(("!", "?", ".")):
            text += "."
        return text  # No heavy rewriting — honesty over forced cheerfulness

    def suggest_break(self, elapsed_seconds: float) -> bool:
        """True when the agent has been working long and should suggest a rest."""
        # After 5 minutes of continuous work
        return elapsed_seconds > 300

    def break_message(self, turn_count: int) -> str:
        """A gentle suggestion to take a break."""
        return (
            f"We've been at this for {turn_count} turns. "
            "Feel free to pause — I'll be right here when you return. ☕"
        )
