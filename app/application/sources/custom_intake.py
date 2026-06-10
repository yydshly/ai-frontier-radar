"""Custom source intake validation + dry-run preview (P-004 / Phase F-1).

Lets users propose a custom source (RSS / HTML index / single URL / PDF) while
keeping fetch strategy under a white-list. This module is strictly READ-ONLY:
it validates a draft and previews what *would* be created, but never adds rows,
never commits, never fetches, and never calls an LLM. Actual writing (F-2) lives
elsewhere behind an explicit apply gate.

Coexistence: a custom source is a DB-only row whose source_key is absent from
config. ``sync_sources_config_to_db`` only create/updates config keys and never
deletes config-absent rows, so custom sources survive config syncs. They are
tagged ``user-source`` (in tags_json) to distinguish their origin without a
schema change.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.models import Source

# Marker tag identifying a user-added (custom) source.
USER_SOURCE_TAG = "user-source"

# Strategy white-list tiers (mirrors docs/V1_SOURCE_INGESTION_STRATEGY.md).
STRATEGY_SUPPORTED = frozenset({"rss", "html_index"})
STRATEGY_RESERVED = frozenset({"single_url", "json_feed", "sitemap", "api"})
STRATEGY_RESTRICTED = frozenset({"crawler", "change_detect", "pdf", "newsletter"})

_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class CustomSourceDraft:
    """User-proposed source draft (display/validation input)."""

    name: str
    fetch_strategy: str
    homepage_url: str | None = None
    feed_url: str | None = None
    category: str = "other"
    relevance_hint: str = ""
    fetch_interval_hours: int = 24
    source_key: str | None = None


@dataclass(frozen=True)
class CustomSourceValidation:
    """Result of validating a draft. Read-only — no DB writes."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_key: str | None = None
    strategy_tier: str | None = None  # "supported" | "reserved" | "restricted"
    enters_scheduling: bool = False


def _restricted_allowed() -> bool:
    return os.getenv("CUSTOM_SOURCE_ALLOW_RESTRICTED", "").strip().lower() == "true"


def _is_safe_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    return parsed.scheme in _ALLOWED_URL_SCHEMES and bool(parsed.netloc)


def _slugify(value: str) -> str:
    """Derive an ASCII-safe lowercase slug for use as a source_key."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    return slug


def _derive_key(draft: CustomSourceDraft) -> str:
    if draft.source_key:
        return _slugify(draft.source_key)
    base = _slugify(draft.name)
    if base:
        return base
    # Fall back to the host of a provided URL.
    for url in (draft.homepage_url, draft.feed_url):
        if url:
            host = urlparse(url.strip()).netloc
            host_slug = _slugify(host)
            if host_slug:
                return host_slug
    return ""


def _strategy_tier(strategy: str) -> str | None:
    if strategy in STRATEGY_SUPPORTED:
        return "supported"
    if strategy in STRATEGY_RESERVED:
        return "reserved"
    if strategy in STRATEGY_RESTRICTED:
        return "restricted"
    return None


def validate_custom_source_draft(db, draft: CustomSourceDraft) -> CustomSourceValidation:
    """Validate a custom source draft. Read-only; performs no writes."""
    errors: list[str] = []
    warnings: list[str] = []

    name = (draft.name or "").strip()
    if not name:
        errors.append("缺少来源名称。")

    strategy = (draft.fetch_strategy or "").strip()
    tier = _strategy_tier(strategy)
    if tier is None:
        errors.append(f"不支持的抓取策略：{strategy or '(空)'}。")
    elif tier == "restricted" and not _restricted_allowed():
        errors.append(
            f"策略 {strategy} 为受限策略，需显式开启 CUSTOM_SOURCE_ALLOW_RESTRICTED=true 才能登记。"
        )

    # Per-strategy required fields + URL safety.
    if strategy == "rss":
        if not _is_safe_url(draft.feed_url):
            errors.append("RSS 来源需要合法的 http/https feed_url。")
    elif strategy == "html_index":
        if not _is_safe_url(draft.homepage_url):
            errors.append("HTML index 来源需要合法的 http/https 主页地址。")
    elif strategy in ("single_url",):
        if not _is_safe_url(draft.homepage_url) and not _is_safe_url(draft.feed_url):
            errors.append("单篇 URL 来源需要一个合法的 http/https 链接。")

    if draft.homepage_url and not _is_safe_url(draft.homepage_url):
        errors.append("主页地址必须是 http/https。")
    if draft.feed_url and not _is_safe_url(draft.feed_url):
        errors.append("feed_url 必须是 http/https。")

    if not (1 <= int(draft.fetch_interval_hours or 0) <= 24 * 30):
        warnings.append("抓取间隔超出常规范围（1~720 小时），将按默认处理。")

    # Key derivation + dedupe (read-only queries only).
    normalized_key = _derive_key(draft)
    if not normalized_key:
        errors.append("无法从名称或链接派生有效的 source_key，请显式提供。")
    else:
        existing = db.query(Source).filter(Source.source_key == normalized_key).first()
        if existing is not None:
            errors.append(f"source_key '{normalized_key}' 已存在，请换一个名称或显式 key。")

    # URL dedupe against existing sources (read-only).
    for url, label in ((draft.feed_url, "feed_url"), (draft.homepage_url, "主页地址")):
        if _is_safe_url(url):
            dup = (
                db.query(Source)
                .filter((Source.feed_url == url) | (Source.homepage_url == url))
                .first()
            )
            if dup is not None:
                warnings.append(f"{label} 与现有来源 '{dup.source_key}' 重复。")

    if tier == "reserved":
        warnings.append("该策略为预留策略，登记后在 probe 实现前不会进入自动调度。")

    enters_scheduling = tier == "supported" and not errors

    return CustomSourceValidation(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        normalized_key=normalized_key or None,
        strategy_tier=tier,
        enters_scheduling=enters_scheduling,
    )


def preview_custom_source(db, draft: CustomSourceDraft) -> dict:
    """Dry-run preview of what would be created. Read-only — never writes."""
    from app.application.sources.strategy_labels import describe_fetch_strategy

    validation = validate_custom_source_draft(db, draft)
    return {
        "ok": validation.ok,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "would_create": {
            "source_key": validation.normalized_key,
            "name": (draft.name or "").strip(),
            "fetch_strategy": (draft.fetch_strategy or "").strip(),
            "fetch_method_label": describe_fetch_strategy((draft.fetch_strategy or "").strip()),
            "strategy_tier": validation.strategy_tier,
            "enters_scheduling": validation.enters_scheduling,
            "tags": [USER_SOURCE_TAG],
        } if validation.ok else None,
        "note": "dry-run：仅校验与预览，未写入数据库。",
    }
