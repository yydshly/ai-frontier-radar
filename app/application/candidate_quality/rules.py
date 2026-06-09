"""Candidate Quality Rules - V1.0-beta.5 rule engine for candidate quality triage.

This module contains pure functions that evaluate a SourceItem and return a
CandidateQuality result. No external network, no DB, no LLM calls.
"""
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import SourceItem

# ── Interest keywords ──────────────────────────────────────────────────────────
# These represent the user's AI frontier focus areas.
# Matched against title, url, source_key, and raw_metadata_json.
INTEREST_PATTERNS: list[tuple[str, re.Pattern]] = [
    # English keywords
    ("AI coding", re.compile(r"\bAI\s*cod(?:e|ing)\b", re.IGNORECASE)),
    ("coding agent", re.compile(r"\bcoding\s*agent\b", re.IGNORECASE)),
    ("developer tools", re.compile(r"\bdeveloper\s*tool\b", re.IGNORECASE)),
    ("agent", re.compile(r"\bagent\b", re.IGNORECASE)),
    ("multi-agent", re.compile(r"\bmulti[\s-]?agent\b", re.IGNORECASE)),
    ("multi agent", re.compile(r"\bmulti\s*agent\b", re.IGNORECASE)),
    ("workflow", re.compile(r"\bworkflow\b", re.IGNORECASE)),
    ("RAG", re.compile(r"\bRAG\b", re.IGNORECASE)),
    ("retrieval", re.compile(r"\bretrieval\b", re.IGNORECASE)),
    ("knowledge base", re.compile(r"\bknowledge\s*base\b", re.IGNORECASE)),
    ("document understanding", re.compile(r"\bdocument\s*(?:understan|process|extract)\b", re.IGNORECASE)),
    ("PDF", re.compile(r"\bPDF\b", re.IGNORECASE)),
    ("TTS", re.compile(r"\bTTS\b", re.IGNORECASE)),
    ("speech", re.compile(r"\bspeech\b", re.IGNORECASE)),
    ("voice", re.compile(r"\bvoice\b", re.IGNORECASE)),
    ("audio", re.compile(r"\baudio\b", re.IGNORECASE)),
    ("video generation", re.compile(r"\bvideo\s*gen(?:eration|erat)\b", re.IGNORECASE)),
    ("safety", re.compile(r"\bsafety\b", re.IGNORECASE)),
    ("alignment", re.compile(r"\balignment\b", re.IGNORECASE)),
    ("Claude", re.compile(r"\bClaude\b", re.IGNORECASE)),
    ("Anthropic", re.compile(r"\bAnthropic\b", re.IGNORECASE)),
    ("OpenAI", re.compile(r"\bOpenAI\b", re.IGNORECASE)),
    ("Google DeepMind", re.compile(r"\bGoogle\s*DeepMind\b", re.IGNORECASE)),
    ("DeepMind", re.compile(r"\bDeepMind\b", re.IGNORECASE)),
    ("MiniMax", re.compile(r"\bMiniMax\b", re.IGNORECASE)),
    ("Mistral", re.compile(r"\bMistral\b", re.IGNORECASE)),
    ("Hugging Face", re.compile(r"\bHugging\s*Face\b", re.IGNORECASE)),
    ("indie hacker", re.compile(r"\bindie\s*hacker\b", re.IGNORECASE)),
    ("monetization", re.compile(r"\bmonetiz(?:ation|e)\b", re.IGNORECASE)),
    # Chinese keywords
    ("AI 编程", re.compile(r"AI\s*编程", re.IGNORECASE)),
    ("智能体", re.compile(r"智能体", re.IGNORECASE)),
    ("多 Agent", re.compile(r"多\s*Agent", re.IGNORECASE)),
    ("知识库", re.compile(r"知识库", re.IGNORECASE)),
    ("文档理解", re.compile(r"文档理解", re.IGNORECASE)),
    ("语音", re.compile(r"语音", re.IGNORECASE)),
    ("视频生成", re.compile(r"视频生成", re.IGNORECASE)),
    ("AI 安全", re.compile(r"AI\s*安全", re.IGNORECASE)),
    ("独立开发", re.compile(r"独立开发", re.IGNORECASE)),
    ("变现", re.compile(r"变现", re.IGNORECASE)),
]

# ── NOISE URL patterns ────────────────────────────────────────────────────────
# If a URL matches these patterns, it is very likely not an article.
NOISE_URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("listing_page", re.compile(r"/(?:tag|tags|category|categories|search|archive|page/\d+|author|authors|p\d+)/?", re.IGNORECASE)),
    ("career_page", re.compile(r"/(?:careers?|jobs?)/?", re.IGNORECASE)),
    ("pricing_page", re.compile(r"/(?:pricing|plans?|billing|signup|signin|login|register|account|contact|newsletter|events|webinars?|about|privacy|terms|legal)/?", re.IGNORECASE)),
    ("admin_page", re.compile(r"/(?:admin|dashboard|settings|profile|user|auth|oauth)/?", re.IGNORECASE)),
]

# ── Article URL patterns ──────────────────────────────────────────────────────
# These patterns suggest the URL is likely an article or post.
ARTICLE_URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("blog", re.compile(r"/(?:blog|news|research|papers?|reports?|articles?|announcements?|posts?|insights?|whitepapers?)/", re.IGNORECASE)),
    ("deep_path", re.compile(r"/[^/]+/[^/]+/")),  # At least 2 path segments
]

# ── Irrelevant title keywords ─────────────────────────────────────────────────
IRRELEVANT_TITLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("career", re.compile(r"\b(?:careers?|jobs?|hiring|positions?|employe)\b", re.IGNORECASE)),
    ("pricing", re.compile(r"\b(?:pricing|cost|plans?|billing|subscription|free trial)\b", re.IGNORECASE)),
    ("login", re.compile(r"\b(?:sign\s*in|sign\s*up|register|login|log\s*in|create\s*account)\b", re.IGNORECASE)),
    ("privacy", re.compile(r"\b(?:privacy|terms|legal|cookie|policy)\b", re.IGNORECASE)),
    ("subscribe", re.compile(r"\b(?:subscribe|newsletter|email\s*list)\b", re.IGNORECASE)),
]

# ── High-value source keys ─────────────────────────────────────────────────────
HIGH_VALUE_SOURCE_KEYS: set[str] = {
    "openai", "anthropic", "deepmind", "huggingface",
    "mistral", "nvidia", "microsoft", "stanford",
    "mit", "berkeley", "cohere",
}


def _match_interests(text: str) -> list[str]:
    """Return list of matched interest keywords found in text."""
    matched = []
    for keyword, pattern in INTEREST_PATTERNS:
        if pattern.search(text):
            matched.append(keyword)
    return matched


def _get_all_search_text(item: "SourceItem") -> str:
    """Concatenate all searchable text fields from a SourceItem."""
    parts = []
    if item.title:
        parts.append(item.title)
    if item.url:
        parts.append(item.url)
    if item.source_key:
        parts.append(item.source_key)
    if item.raw_metadata_json:
        parts.append(item.raw_metadata_json)
    return " ".join(parts)


def evaluate_candidate_quality(item: "SourceItem") -> "CandidateQuality":
    """Evaluate the quality of a single SourceItem candidate.

    Pure function: no DB, no network, no LLM.

    Args:
        item: SourceItem record

    Returns:
        CandidateQuality with score (0-100), level, recommended action, reasons, etc.
    """
    from app.domain.value_objects.candidate_quality import (
        CandidateQuality,
        CandidateQualityLevel,
        CandidateRecommendedAction,
    )

    score = 50  # Start at neutral
    reasons: list[str] = []
    matched_interests: list[str] = []
    warning_flags: list[str] = []

    search_text = _get_all_search_text(item)
    url_lower = (item.url or "").lower()
    title = item.title or ""

    # ── 1. NOISE URL patterns ──────────────────────────────────────────────
    for flag, pattern in NOISE_URL_PATTERNS:
        if pattern.search(url_lower):
            warning_flags.append(flag)
            # Strong noise signal: push toward noise immediately
            score -= 40
            reasons.append(f"URL 匹配噪音类型：{flag.replace('_', ' ')}")

    # ── 2. Article URL patterns (bonus) ───────────────────────────────────
    for label, pattern in ARTICLE_URL_PATTERNS:
        if pattern.search(url_lower):
            score += 15
            reasons.append(f"URL 特征为文章型：{label}")
            break

    # ── 3. Title quality ───────────────────────────────────────────────────
    if not title or not title.strip():
        warning_flags.append("empty_title")
        score -= 30
        reasons.append("标题为空")
    elif len(title.strip()) < 8:
        warning_flags.append("short_title")
        score -= 15
        reasons.append("标题过短")
    else:
        # Check for irrelevant keywords
        for flag, pattern in IRRELEVANT_TITLE_PATTERNS:
            if pattern.search(title):
                warning_flags.append(flag)
                score -= 20
                reasons.append(f"标题包含无关内容：{flag.replace('_', ' ')}")
                break

    # ── 4. Interest matching ──────────────────────────────────────────────
    interests_found = _match_interests(search_text)
    if interests_found:
        matched_interests.extend(interests_found)
        score += 10 * min(len(interests_found), 3)  # Cap at +30
        for interest in interests_found[:3]:
            reasons.append(f"匹配关注方向：{interest}")

    # ── 5. Time rules ─────────────────────────────────────────────────────
    now = datetime.utcnow()
    published_at = item.published_at

    if published_at:
        try:
            if isinstance(published_at, str):
                # Try parsing common formats
                pub_dt = None
                for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z"):
                    try:
                        pub_dt = datetime.strptime(published_at[:25], fmt)
                        break
                    except (ValueError, IndexError):
                        continue
                if pub_dt is None:
                    # Could not parse, treat as missing
                    warning_flags.append("missing_published_at")
                    published_at = None
                else:
                    published_at = pub_dt

            if published_at:
                age_days = (now - published_at).days
                if 0 <= age_days <= 90:
                    score += 10
                    reasons.append("内容较新（90天内）")
                elif age_days < 0:
                    # Future date - suspicious
                    warning_flags.append("future_date")
                    score -= 10
                elif 90 < age_days <= 180:
                    pass  # Neutral
                elif 180 < age_days <= 365:
                    score -= 10
                    reasons.append("内容较旧（180天以上）")
                elif age_days > 365:
                    score -= 20
                    reasons.append("内容过旧（365天以上）")
                    warning_flags.append("stale_content")
        except Exception:
            # Any parsing error: treat as missing
            warning_flags.append("missing_published_at")
    else:
        warning_flags.append("missing_published_at")

    # ── 6. Source key premium ─────────────────────────────────────────────
    source_key_lower = (item.source_key or "").lower()
    if source_key_lower in HIGH_VALUE_SOURCE_KEYS:
        score += 10
        reasons.append(f"来源：{source_key_lower}（高价值来源）")

    # ── 7. Clamp score ────────────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── 8. Determine level ───────────────────────────────────────────────
    if score >= 75:
        level = CandidateQualityLevel.HIGH
    elif score >= 50:
        level = CandidateQualityLevel.MEDIUM
    elif score >= 25:
        level = CandidateQualityLevel.LOW
    else:
        level = CandidateQualityLevel.NOISE

    # ── 9. Determine recommended action ───────────────────────────────────
    # Special case: empty title → manual_required
    if "empty_title" in warning_flags:
        action = CandidateRecommendedAction.MANUAL_REQUIRED
    elif level == CandidateQualityLevel.HIGH:
        action = CandidateRecommendedAction.COMPILE
    elif level == CandidateQualityLevel.MEDIUM:
        action = CandidateRecommendedAction.REVIEW
    elif level == CandidateQualityLevel.LOW:
        action = CandidateRecommendedAction.IGNORE
    else:  # NOISE
        action = CandidateRecommendedAction.IGNORE

    # If already compiled, don't suggest compile again
    if item.status == "compiled":
        action = CandidateRecommendedAction.REVIEW
    # If already ignored, keep ignore
    elif item.status == "ignored":
        action = CandidateRecommendedAction.IGNORE

    return CandidateQuality(
        score=score,
        level=level,
        recommended_action=action,
        reasons=tuple(reasons),
        matched_interests=tuple(matched_interests),
        warning_flags=tuple(warning_flags),
    )
