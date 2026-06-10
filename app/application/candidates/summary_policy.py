"""Summary field write policy and display policy — pure functions, no DB, no AI model calls.

This module encodes the rules defined in docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md.
It is intentionally free of database access, AI model calls, and stateful side-effects.
"""
from __future__ import annotations

import re
from typing import Any

# ── Field keys ─────────────────────────────────────────────────────────────────

ZH_ONE_LINER_KEY = "zh_one_liner"
ZH_SUMMARY_KEY = "zh_summary"

# L0: source-provided summaries. These are NEVER AI-generated Chinese summaries.
SOURCE_SUMMARY_KEYS = (
    "detail_description",
    "summary",
    "description",
    "excerpt",
    "content_snippet",
    "og_description",
    "meta_description",
    "rss_summary",
    "rss_description",
)

# ── Detail summary kind constants ────────────────────────────────────────────

SUMMARY_KIND_ZH_SUMMARY = "zh_summary"
SUMMARY_KIND_ZH_ONE_LINER = "zh_one_liner"
SUMMARY_KIND_METADATA = "metadata_summary"
SUMMARY_KIND_ENGLISH_METADATA = "english_metadata_summary"
SUMMARY_KIND_MISSING = "missing"

# ── Detail summary labels ─────────────────────────────────────────────────────

SUMMARY_LABELS: dict[str, str] = {
    SUMMARY_KIND_ZH_SUMMARY: "中文摘要",
    SUMMARY_KIND_ZH_ONE_LINER: "中文概述",
    SUMMARY_KIND_METADATA: "来源摘要",
    SUMMARY_KIND_ENGLISH_METADATA: "英文来源摘要",
    SUMMARY_KIND_MISSING: "内容摘要",
}

# ── Pure helper functions ──────────────────────────────────────────────────────


def normalize_summary_text(
    value: object, *, max_length: int | None = None
) -> str | None:
    """Normalize a summary text value.

    Rules:
    - Non-string → None
    - Empty/whitespace-only → None
    - Strip HTML tags
    - Collapse whitespace
    - Truncate at max_length with "..."
    """
    if not isinstance(value, str):
        return None
    text = re.sub(r"<[^>]+>", "", value)
    text = " ".join(text.strip().split())
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text


def has_cjk(text: str) -> bool:
    """Return True if text contains any CJK (Chinese/Japanese/Korean) character."""
    for ch in text:
        if "一" <= ch <= "鿿":  # CJK Unified Ideographs range
            return True
    return False


def get_first_source_summary(raw_meta: dict[str, Any]) -> str | None:
    """Return the first non-empty L0 source summary, or None."""
    for key in SOURCE_SUMMARY_KEYS:
        value = raw_meta.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def classify_detail_summary_kind(raw_meta: dict[str, Any]) -> str:
    """Classify the detail_summary kind based on raw_metadata_json content.

    Priority:
    1. zh_summary exists → zh_summary (AI Chinese, detailed)
    2. zh_one_liner exists → zh_one_liner (AI Chinese, one-liner)
    3. First available source summary:
       - Contains CJK → metadata_summary (Chinese source summary)
       - No CJK → english_metadata_summary (English source summary)
    4. Nothing available → missing
    """
    if isinstance(raw_meta.get(ZH_SUMMARY_KEY), str) and raw_meta[ZH_SUMMARY_KEY].strip():
        return SUMMARY_KIND_ZH_SUMMARY

    if isinstance(raw_meta.get(ZH_ONE_LINER_KEY), str) and raw_meta[ZH_ONE_LINER_KEY].strip():
        return SUMMARY_KIND_ZH_ONE_LINER

    first_source = get_first_source_summary(raw_meta)
    if first_source is not None:
        if has_cjk(first_source):
            return SUMMARY_KIND_METADATA
        else:
            return SUMMARY_KIND_ENGLISH_METADATA

    return SUMMARY_KIND_MISSING


def get_detail_summary_label(kind: str) -> str:
    """Return the human-readable label for a detail_summary_kind."""
    return SUMMARY_LABELS.get(kind, SUMMARY_LABELS[SUMMARY_KIND_MISSING])


def build_detail_summary(
    raw_meta: dict[str, Any], *, max_length: int = 260
) -> str | None:
    """Build the detail_summary value from raw_metadata_json.

    Priority: zh_summary > zh_one_liner > L0 source summary fallback
    All results are normalized (HTML stripped, whitespace collapsed, truncated).
    """
    # L2: zh_summary (highest priority AI Chinese summary)
    value = raw_meta.get(ZH_SUMMARY_KEY)
    if isinstance(value, str) and value.strip():
        return normalize_summary_text(value, max_length=max_length)

    # L1: zh_one_liner (AI Chinese one-liner, used as fallback for detail view)
    value = raw_meta.get(ZH_ONE_LINER_KEY)
    if isinstance(value, str) and value.strip():
        return normalize_summary_text(value, max_length=max_length)

    # L0: first available source summary
    first_source = get_first_source_summary(raw_meta)
    if first_source is not None:
        return normalize_summary_text(first_source, max_length=max_length)

    return None
