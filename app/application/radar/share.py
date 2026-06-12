"""Public share view (H5) data assembly.

Builds the read-only, shareable picture of a day: a small stats hint line, the
core report, the day's audio, the important articles (those the report
highlighted), and the other articles grouped by source. Exposes ONLY report
content + article titles/summaries/links + audio — never internal run/scheduler/
dev data. Reuses the per-day anchor window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.models import Source
from app.application.radar.daily_report_store import (
    load_daily_report,
    load_final_daily_report,
)
from app.application.radar.history import _valid_items_in_window, _audio_jobs_for

if TYPE_CHECKING:
    from app.application.radar.daily_audio_jobs import DailyAudioJob


@dataclass(frozen=True)
class ShareArticle:
    item_id: int
    title: str
    zh_preview: str | None
    description: str | None
    source_name: str
    url: str | None
    insight_card_id: int | None


@dataclass(frozen=True)
class ShareReference:
    item_id: int
    title: str
    url: str | None
    is_on_page: bool


@dataclass(frozen=True)
class ShareHighlight:
    text: str
    references: list[ShareReference]


@dataclass(frozen=True)
class ShareGroup:
    source_name: str
    items: list[ShareArticle]


@dataclass(frozen=True)
class ShareStats:
    new_items: int      # 新增(纳入今日增量)
    summarized: int     # 已识别(已生成中文摘要)
    pending: int        # 待补(尚无摘要)
    important: int      # 重要(报告高亮)
    sources: int        # 覆盖来源


@dataclass(frozen=True)
class ShareView:
    date_label: str
    report: dict | None
    audio_job: DailyAudioJob | None
    highlights: list[ShareHighlight] = field(default_factory=list)
    important: list[ShareArticle] = field(default_factory=list)
    other_groups: list[ShareGroup] = field(default_factory=list)
    stats: ShareStats | None = None


def _important_ids(report: dict | None) -> set[int]:
    ids: set[int] = set()
    if not report:
        return ids
    for refs in report.get("highlight_references") or []:
        for ref in refs if isinstance(refs, list) else []:
            iid = ref.get("item_id") if isinstance(ref, dict) else None
            if iid:
                ids.add(iid)
    return ids


def _build_highlights(report: dict | None, article_ids: set[int]) -> list[ShareHighlight]:
    if not report:
        return []

    reference_groups = report.get("highlight_references") or []
    highlights: list[ShareHighlight] = []
    for index, text in enumerate(report.get("highlights") or []):
        if not isinstance(text, str) or not text.strip():
            continue
        raw_references = (
            reference_groups[index]
            if index < len(reference_groups) and isinstance(reference_groups[index], list)
            else []
        )
        references: list[ShareReference] = []
        for ref in raw_references:
            if not isinstance(ref, dict):
                continue
            try:
                item_id = int(ref.get("item_id"))
            except (TypeError, ValueError):
                continue
            title = str(ref.get("title") or f"文章 {item_id}").strip()
            url = ref.get("url") if isinstance(ref.get("url"), str) else None
            references.append(ShareReference(
                item_id=item_id,
                title=title,
                url=url,
                is_on_page=item_id in article_ids,
            ))
        highlights.append(ShareHighlight(text=text.strip(), references=references))
    return highlights


def build_share_view(db, date_label: str) -> ShareView:
    from app.application.candidates.display import build_candidate_display_card
    from app.application.radar.daily_audio_jobs import select_daily_audio_job

    report = load_final_daily_report(date_label) or load_daily_report(date_label)
    audio_jobs = _audio_jobs_for(date_label)
    frozen_articles = (
        report.get("articles")
        if report and report.get("report_kind") == "final"
        else None
    )
    items = [] if frozen_articles is not None else _valid_items_in_window(db, date_label)
    article_ids = {
        int(article.get("item_id"))
        for article in frozen_articles or []
        if isinstance(article, dict) and article.get("item_id") is not None
    } if frozen_articles is not None else {it.id for it in items}
    audio_job = select_daily_audio_job(
        audio_jobs,
        date_label=date_label,
        report_version=(report or {}).get("version_id"),
    )
    highlights = _build_highlights(report, article_ids)

    keys = {it.source_key for it in items}
    names = {
        s.source_key: s.name
        for s in db.query(Source).filter(Source.source_key.in_(keys)).all()
    } if keys else {}

    important_ids = _important_ids(report)
    important: list[ShareArticle] = []
    other_grouped: dict[str, list[ShareArticle]] = {}
    summarized = 0

    if frozen_articles is not None:
        for frozen in frozen_articles:
            if not isinstance(frozen, dict):
                continue
            try:
                item_id = int(frozen.get("item_id"))
            except (TypeError, ValueError):
                continue
            zh = str(frozen.get("zh_one_liner") or "").strip() or None
            description = str(frozen.get("zh_summary") or "").strip() or None
            title = str(frozen.get("title") or "无标题").strip()
            if description in {zh, title}:
                description = None
            if zh:
                summarized += 1
            source_key = str(frozen.get("source_key") or "")
            source_name = str(frozen.get("source_name") or source_key)
            names[source_key] = source_name
            article = ShareArticle(
                item_id=item_id,
                title=title,
                zh_preview=zh,
                description=description,
                source_name=source_name,
                url=frozen.get("url"),
                insight_card_id=frozen.get("insight_card_id"),
            )
            if item_id in important_ids:
                important.append(article)
            else:
                other_grouped.setdefault(source_key, []).append(article)
    else:
        for it in items:
            card = build_candidate_display_card(it)
            zh = card.primary_text if card.uses_zh_one_liner else None
            description = card.detail_summary
            if description in {zh, card.title}:
                description = None
            if zh:
                summarized += 1
            article = ShareArticle(
                item_id=it.id,
                title=card.title,
                zh_preview=zh,
                description=description,
                source_name=names.get(it.source_key, it.source_key),
                url=card.url,
                insight_card_id=it.insight_card_id,
            )
            if it.id in important_ids:
                important.append(article)
            else:
                other_grouped.setdefault(it.source_key, []).append(article)

    other_groups = [
        ShareGroup(source_name=names.get(k, k), items=v)
        for k, v in other_grouped.items()
    ]
    stats = ShareStats(
        new_items=len(article_ids),
        summarized=summarized,
        pending=len(article_ids) - summarized,
        important=len(important),
        sources=len({
            article.source_name for article in important
        } | {
            group.source_name for group in other_groups
        }),
    )
    return ShareView(
        date_label=date_label,
        report=report,
        audio_job=audio_job,
        highlights=highlights,
        important=important,
        other_groups=other_groups,
        stats=stats,
    )
