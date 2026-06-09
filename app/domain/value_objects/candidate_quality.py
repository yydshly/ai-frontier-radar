"""Candidate Quality value objects for V1.0-beta.5 candidate quality triage."""
from dataclasses import dataclass, field
from enum import Enum


class CandidateQualityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOISE = "noise"


class CandidateRecommendedAction(str, Enum):
    COMPILE = "compile"
    REVIEW = "review"
    IGNORE = "ignore"
    MANUAL_REQUIRED = "manual_required"


# Chinese display labels
QUALITY_LEVEL_LABELS = {
    CandidateQualityLevel.HIGH: "高",
    CandidateQualityLevel.MEDIUM: "中",
    CandidateQualityLevel.LOW: "低",
    CandidateQualityLevel.NOISE: "噪音",
}

RECOMMENDED_ACTION_LABELS = {
    CandidateRecommendedAction.COMPILE: "建议生成",
    CandidateRecommendedAction.REVIEW: "人工复核",
    CandidateRecommendedAction.IGNORE: "建议忽略",
    CandidateRecommendedAction.MANUAL_REQUIRED: "需人工判断",
}


@dataclass(frozen=True)
class CandidateQuality:
    """Result of candidate quality evaluation.

    score: 0-100 quality score
    level: HIGH / MEDIUM / LOW / NOISE
    recommended_action: COMPILE / REVIEW / IGNORE / MANUAL_REQUIRED
    reasons: human-readable Chinese short descriptions of why this level was assigned
    matched_interests: list of user interest keywords that matched
    warning_flags: list of risk flags (e.g. listing_page, empty_title, stale_content)
    """
    score: int
    level: CandidateQualityLevel
    recommended_action: CandidateRecommendedAction
    reasons: tuple[str, ...] = field(default_factory=tuple)
    matched_interests: tuple[str, ...] = field(default_factory=tuple)
    warning_flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        # Clamp score to 0-100
        object.__setattr__(self, "score", max(0, min(100, self.score)))

    @property
    def score_display(self) -> int:
        """Display score (clamped 0-100)."""
        return self.score

    @property
    def level_label(self) -> str:
        """Chinese label for quality level."""
        return QUALITY_LEVEL_LABELS.get(self.level, self.level.value)

    @property
    def action_label(self) -> str:
        """Chinese label for recommended action."""
        return RECOMMENDED_ACTION_LABELS.get(self.recommended_action, self.recommended_action.value)

    def reasons_list(self) -> list[str]:
        return list(self.reasons)

    def matched_interests_list(self) -> list[str]:
        return list(self.matched_interests)

    def warning_flags_list(self) -> list[str]:
        return list(self.warning_flags)
