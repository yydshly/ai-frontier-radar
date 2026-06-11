"""Effective fetch-strategy + reliability ranking (S1, pure / read-only).

The project's intent is "RSS first, then other methods by reliability, and
display by the most reliable *available* method". Today that rule lives only as
a comment in config/sources.example.yaml and is enforced by hand. This module
makes it computable, without changing any fetch behavior:

- ``compute_effective_strategy(feed_url, fetch_strategy)`` applies the documented
  rule: a source that has a feed_url should be treated as RSS (the most reliable
  method), regardless of how it was configured.
- ``reliability_rank`` / ``RELIABILITY_ORDER`` express the reliability ordering.
- ``check_strategy_consistency`` flags drift between configured and effective
  strategy so the UI can warn (e.g. a feed_url exists but strategy != rss).

Pure functions only: no DB, no network, no side effects. Fetch-time adoption of
the effective strategy is a later phase (S2); this module is display + guardrail.
"""
from __future__ import annotations

from dataclasses import dataclass

# Reliability ordering, most reliable first. Lower rank index == more reliable.
RELIABILITY_ORDER: tuple[str, ...] = (
    "rss",
    "json_feed",
    "sitemap",
    "api",
    "html_index",
    "single_url",
    "change_detect",
    "crawler",
    "newsletter",
    "pdf",
    "manual",
)

_RANK = {name: i for i, name in enumerate(RELIABILITY_ORDER)}

# Single source of truth for strategies the system can actually fetch *and*
# auto-schedule today. Both the fetch services and due-source scheduling import
# this, so the two no longer drift apart.
SUPPORTED_STRATEGIES: frozenset[str] = frozenset({"rss", "html_index"})


def reliability_rank(strategy: str | None) -> int:
    """Return the reliability rank (lower == more reliable). Unknown -> large."""
    if not strategy:
        return len(RELIABILITY_ORDER) + 1
    return _RANK.get(strategy, len(RELIABILITY_ORDER))


def compute_effective_strategy(feed_url: str | None, fetch_strategy: str | None) -> str:
    """Apply the documented RSS-first rule.

    If a feed_url is present, the effective strategy is ``rss`` (most reliable),
    regardless of the configured ``fetch_strategy``. Otherwise the configured
    strategy is used as-is.

    Behavior matches the inline rule previously duplicated in the routes
    (``"rss" if feed_url else fetch_strategy``).
    """
    if feed_url:
        return "rss"
    return fetch_strategy or ""


@dataclass(frozen=True)
class StrategyConsistency:
    """Result of comparing configured vs effective (most-reliable) strategy."""

    configured: str
    effective: str
    consistent: bool
    message: str | None = None


def check_strategy_consistency(
    feed_url: str | None, fetch_strategy: str | None
) -> StrategyConsistency:
    """Flag drift between the configured strategy and the effective one.

    Inconsistent cases:
    - feed_url present but configured strategy is not ``rss`` (a more reliable
      method is available than the one configured).
    - configured ``rss`` but no feed_url (invalid RSS config).
    """
    configured = (fetch_strategy or "").strip()
    effective = compute_effective_strategy(feed_url, fetch_strategy)
    has_feed = bool(feed_url and str(feed_url).strip())

    message: str | None = None
    consistent = True

    if has_feed and configured != "rss":
        consistent = False
        message = (
            f"该来源有 feed_url，更可靠的 RSS 可用，但配置为 {configured or '(空)'}；"
            "建议改用 RSS。"
        )
    elif configured == "rss" and not has_feed:
        consistent = False
        message = "配置为 RSS 但缺少 feed_url，无法按 RSS 可靠抓取。"

    return StrategyConsistency(
        configured=configured,
        effective=effective,
        consistent=consistent,
        message=message,
    )
