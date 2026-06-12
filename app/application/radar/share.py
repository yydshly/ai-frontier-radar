"""Public share view (H5) data assembly.

Builds the read-only, shareable picture of a day: a small stats hint line, the
core report, the day's audio, the important articles (those the report
highlighted), and the other articles grouped by source. Exposes ONLY report
content + article titles/summaries/links + audio — never internal run/scheduler/
dev data. Reuses the per-day anchor window.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Source
from app.application.radar.daily_report_store import load_daily_report
from app.application.radar.history import _valid_items_in_window, _audio_jobs_for


@dataclass(frozen=True)
class ShareArticle:
    item_id: int
    title: str
    zh_preview: str | None
    source_name: str
    url: str | None
    insight_card_id: int | None


@dataclass(frozen=True)
class ShareGroup:
    source_name: str
    items: list  # list[ShareArticle]


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
    audio_jobs: list
    important: list = field(default_factory=list)      # list[ShareArticle]
    other_groups: list = field(default_factory=list)   # list[ShareGroup]
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


def build_share_view(db, date_label: str) -> ShareView:
    from app.application.candidates.display import build_candidate_display_card

    report = load_daily_report(date_label)
    audio_jobs = _audio_jobs_for(date_label)
    items = _valid_items_in_window(db, date_label)

    keys = {it.source_key for it in items}
    names = {
        s.source_key: s.name
        for s in db.query(Source).filter(Source.source_key.in_(keys)).all()
    } if keys else {}

    important_ids = _important_ids(report)
    important: list[ShareArticle] = []
    other_grouped: dict[str, list[ShareArticle]] = {}
    summarized = 0

    for it in items:
        card = build_candidate_display_card(it)
        zh = card.primary_text if card.uses_zh_one_liner else None
        if zh:
            summarized += 1
        article = ShareArticle(
            item_id=it.id,
            title=card.title,
            zh_preview=zh,
            source_name=names.get(it.source_key, it.source_key),
            url=it.url,
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
        new_items=len(items),
        summarized=summarized,
        pending=len(items) - summarized,
        important=len(important),
        sources=len(names),
    )
    return ShareView(
        date_label=date_label,
        report=report,
        audio_jobs=audio_jobs,
        important=important,
        other_groups=other_groups,
        stats=stats,
    )
