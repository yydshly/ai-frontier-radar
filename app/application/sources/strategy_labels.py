"""User-facing labels for source fetch strategies (P-002 / Phase B).

Translates internal ``fetch_strategy`` keys into Chinese "获取方式" wording for
the source workspace UI. Mirrors the capability matrix in
docs/V1_SOURCE_INGESTION_STRATEGY.md. Read-only / pure — no DB, no side effects.

Shared by the source workspace (P-002) and, later, the custom-source intake
form (P-004) so the strategy vocabulary stays consistent across the product.
"""
from __future__ import annotations

# fetch_strategy key -> user-facing Chinese label.
_FETCH_STRATEGY_LABELS: dict[str, str] = {
    "rss": "RSS 订阅（结构化、低成本）",
    "html_index": "网页索引解析",
    "json_feed": "JSON Feed（预留）",
    "sitemap": "站点地图（预留）",
    "api": "官方 API（预留）",
    "single_url": "单篇文章抓取（预留）",
    "crawler": "渲染型爬虫（后置，需显式开启）",
    "change_detect": "变更检测（后置，需显式开启）",
    "pdf": "PDF 人工录入",
    "newsletter": "邮件订阅转录（人工）",
    "manual": "人工录入",
}


def describe_fetch_strategy(strategy: str | None) -> str:
    """Return a user-facing Chinese label for a fetch_strategy key.

    Unknown or empty strategies fall back to "未配置 / 暂不支持".
    """
    if not strategy:
        return "未配置"
    return _FETCH_STRATEGY_LABELS.get(strategy, f"{strategy}（暂不支持）")
