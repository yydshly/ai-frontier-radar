"""Candidate status enum for the candidate pool domain."""
from enum import Enum


class CandidateStatus(str, Enum):
    """Status values for items in the candidate pool.

    These are domain-level status values that map to SourceItem.status
    string field. We do NOT use SQLAlchemy Enum here to avoid breaking
    existing SourceItem.status data.
    """
    DISCOVERED = "discovered"
    IGNORED = "ignored"
    COMPILING = "compiling"
    COMPILED = "compiled"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"
