"""Candidate Quality Service - V1.0-beta.5 application service for candidate quality triage.

Provides quality evaluation for SourceItem records without calling LLM or network.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import SourceItem

from app.domain.value_objects.candidate_quality import CandidateQuality
from app.application.candidate_quality.rules import evaluate_candidate_quality


class CandidateQualityService:
    """Application service for candidate quality triage.

    All methods are pure rule evaluation - no DB writes, no external calls.
    """

    def evaluate(self, item: "SourceItem") -> CandidateQuality:
        """Evaluate the quality of a single SourceItem.

        Args:
            item: SourceItem record to evaluate

        Returns:
            CandidateQuality with score, level, recommended action, reasons, etc.
        """
        try:
            return evaluate_candidate_quality(item)
        except Exception:
            # Defensive: return a neutral quality on any error
            from app.domain.value_objects.candidate_quality import (
                CandidateQuality,
                CandidateQualityLevel,
                CandidateRecommendedAction,
            )
            return CandidateQuality(
                score=0,
                level=CandidateQualityLevel.LOW,
                recommended_action=CandidateRecommendedAction.IGNORE,
                reasons=("评估过程出错",),
                matched_interests=(),
                warning_flags=("evaluation_error",),
            )

    def evaluate_many(self, items: list["SourceItem"]) -> dict[int, CandidateQuality]:
        """Evaluate quality for multiple SourceItems.

        Args:
            items: List of SourceItem records to evaluate

        Returns:
            Dict mapping SourceItem.id -> CandidateQuality
        """
        result = {}
        for item in items:
            if item and item.id is not None:
                try:
                    result[item.id] = evaluate_candidate_quality(item)
                except Exception:
                    from app.domain.value_objects.candidate_quality import (
                        CandidateQuality,
                        CandidateQualityLevel,
                        CandidateRecommendedAction,
                    )
                    result[item.id] = CandidateQuality(
                        score=0,
                        level=CandidateQualityLevel.LOW,
                        recommended_action=CandidateRecommendedAction.IGNORE,
                        reasons=("评估过程出错",),
                        matched_interests=(),
                        warning_flags=("evaluation_error",),
                    )
        return result
