"""Candidate Quality Triage - application layer for V1.0-beta.5.

Exports CandidateQualityService and the evaluate_candidate_quality function.
"""
from app.application.candidate_quality.services import CandidateQualityService

__all__ = ["CandidateQualityService"]
