"""Custom source intake validation + dry-run preview (P-004 / Phase F-1.1).

This module is strictly read-only. It validates a draft and previews what would
be created, but it does not write database rows, start background work, probe
URLs, or call an LLM. Actual persistence is reserved for a later apply-gated
phase.
"""
from __future__ import annotations

import ipaddress
import os
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.models import Source
from app.sources.config_loader import list_sources

USER_SOURCE_TAG = "user-source"

STRATEGY_SUPPORTED = frozenset({"rss", "html_index"})
STRATEGY_RESERVED = frozenset({"single_url", "json_feed", "sitemap", "api"})
STRATEGY_RESTRICTED = frozenset({"crawler", "change_detect", "pdf", "newsletter"})

SCHEDULING_NOTE = (
    "当前为 DB-only 预览，不会自动进入今日雷达调度；"
    "F-2 需选择写入 config 或扩展 due-source。"
)


@dataclass(frozen=True)
class CustomSourceDraft:
    """User-proposed source draft."""

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
    """Result of validating a draft. Read-only: no DB writes."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_key: str | None = None
    strategy_tier: str | None = None
    strategy_supported: bool = False
    enters_scheduling_now: bool = False
    scheduling_note: str = SCHEDULING_NOTE
    # Compatibility field: F-1/F-1.1 previews never promise automatic scheduling.
    enters_scheduling: bool = False


def _restricted_allowed() -> bool:
    return os.getenv("CUSTOM_SOURCE_ALLOW_RESTRICTED", "").strip().lower() == "true"


def _is_public_http_url(value: str | None) -> bool:
    """Allow only public http(s) URLs using static checks, without DNS lookup."""
    if not value:
        return False
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}:
        return False
    if host.endswith(".local"):
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True

    return bool(ip.is_global)


def _is_safe_url(value: str | None) -> bool:
    """Backward-compatible alias for the stricter public URL validator."""
    return _is_public_http_url(value)


def _slugify(value: str) -> str:
    """Derive an ASCII-safe lowercase slug for use as a source_key."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()


def _derive_key(draft: CustomSourceDraft) -> str:
    if draft.source_key:
        return _slugify(draft.source_key)
    base = _slugify(draft.name)
    if base:
        return base
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


def _config_sources_by_key() -> dict[str, object]:
    try:
        return {s.source_key: s for s in list_sources(include_disabled=True)}
    except Exception:
        return {}


def _config_source_with_url(url: str | None, config_sources: dict[str, object]) -> str | None:
    if not url:
        return None
    for source_key, source in config_sources.items():
        if getattr(source, "feed_url", None) == url or getattr(source, "homepage_url", None) == url:
            return source_key
    return None


def _has_any_public_url(draft: CustomSourceDraft) -> bool:
    return _is_public_http_url(draft.homepage_url) or _is_public_http_url(draft.feed_url)


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
            f"策略 {strategy} 为受限策略，需显式开启 CUSTOM_SOURCE_ALLOW_RESTRICTED=true 才能预览。"
        )

    if strategy == "rss":
        if not _is_public_http_url(draft.feed_url):
            errors.append("RSS 来源需要合法的公网 http/https feed_url。")
    elif strategy == "html_index":
        if not _is_public_http_url(draft.homepage_url):
            errors.append("HTML index 来源需要合法的公网 http/https 主页 URL。")
    elif strategy == "single_url":
        if not _has_any_public_url(draft):
            errors.append("single_url 需要一个合法的公网 http/https homepage_url 或 feed_url。")
        warnings.append("single_url 更适合进入手动内容导入，不一定适合作为长期 Source。")
    elif strategy in {"json_feed", "sitemap"}:
        if not _has_any_public_url(draft):
            errors.append(f"{strategy} 需要一个合法的公网 http/https feed_url 或 homepage_url。")
    elif strategy == "api":
        if not _is_public_http_url(draft.homepage_url):
            errors.append("api 来源需要合法的公网 http/https homepage_url。")
    elif strategy == "pdf":
        warnings.append("pdf 暂不建议作为长期 Source 写入，默认不会进入调度。")

    if draft.homepage_url and not _is_public_http_url(draft.homepage_url):
        errors.append("主页 URL 必须是公网 http/https，不能是 localhost、内网或 metadata 地址。")
    if draft.feed_url and not _is_public_http_url(draft.feed_url):
        errors.append("feed_url 必须是公网 http/https，不能是 localhost、内网或 metadata 地址。")

    try:
        interval = int(draft.fetch_interval_hours or 0)
    except (TypeError, ValueError):
        interval = 0
    if not (1 <= interval <= 24 * 30):
        warnings.append("抓取间隔超出常规范围（1~720 小时），后续写入阶段需按默认值处理。")

    config_sources = _config_sources_by_key()
    normalized_key = _derive_key(draft)
    if not normalized_key:
        errors.append("无法从名称或链接派生有效的 source_key，请显式提供。")
    else:
        if db.query(Source).filter(Source.source_key == normalized_key).first() is not None:
            errors.append(f"source_key '{normalized_key}' 已存在于数据库，请换一个名称或 key。")
        if normalized_key in config_sources:
            errors.append(f"source_key '{normalized_key}' 已存在于 config sources，请换一个名称或 key。")

    for url, label in ((draft.feed_url, "feed_url"), (draft.homepage_url, "homepage_url")):
        if _is_public_http_url(url):
            dup = (
                db.query(Source)
                .filter((Source.feed_url == url) | (Source.homepage_url == url))
                .first()
            )
            if dup is not None:
                errors.append(f"{label} 与数据库来源 '{dup.source_key}' 重复。")
            config_dup = _config_source_with_url(url, config_sources)
            if config_dup is not None:
                errors.append(f"{label} 与 config 来源 '{config_dup}' 重复。")

    if tier == "reserved":
        warnings.append("该策略为预留策略，当前只做 dry-run 预览，不承诺自动调度。")

    strategy_supported = tier == "supported"

    return CustomSourceValidation(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        normalized_key=normalized_key or None,
        strategy_tier=tier,
        strategy_supported=strategy_supported,
        enters_scheduling_now=False,
        scheduling_note=SCHEDULING_NOTE,
        enters_scheduling=False,
    )


def preview_custom_source(db, draft: CustomSourceDraft) -> dict:
    """Dry-run preview of what would be created. Read-only: never writes."""
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
            "strategy_supported": validation.strategy_supported,
            "enters_scheduling_now": False,
            "scheduling_note": validation.scheduling_note,
            "enters_scheduling": False,
            "tags": [USER_SOURCE_TAG],
        } if validation.ok else None,
        "note": "dry-run：仅校验与预览，未写入数据库。",
    }
