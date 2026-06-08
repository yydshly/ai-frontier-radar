"""User decision constants and helpers for InsightCard (V0.4).

After reading a Chinese InsightCard, the user marks it with their own
judgment. The decision values are stable strings stored in the
CardDecision.decision column.
"""
from __future__ import annotations


# Stable string values for CardDecision.decision
ALLOWED_CARD_DECISIONS: dict[str, str] = {
    "worth_attention": "值得关注",
    "related_to_me": "与我有关",
    "read_later": "稍后再看",
    "ignore": "暂时忽略",
    "to_action": "转成行动",
}


def get_decision_label(value: str | None) -> str:
    """Return the Chinese label for a decision value.

    Unknown / None values return "未处理" (unhandled) instead of raising,
    so templates and routes can call this safely on any input.
    """
    if not value:
        return "未处理"
    return ALLOWED_CARD_DECISIONS.get(value, "未处理")


def is_valid_decision(value: str | None) -> bool:
    """Return True if the given value is a known decision value."""
    if not value:
        return False
    return value in ALLOWED_CARD_DECISIONS
