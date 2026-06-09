#!/usr/bin/env python3
"""
quick_test.py — Development fast-check suite for AI Frontier Radar.

Run during active development instead of the full smoke_test.py.

Scope:
- app.main can be imported
- TestClient can be created
- Core GET endpoints return 200
- Core service classes are importable
- Core template keywords are present

Smoke-test / acceptance scripts are NOT run here — those belong to
smoke_test.py (PR-ready full regression) and acceptance_demo_*.py
(full user-flow / data validation).

Usage:
    python -m compileall app scripts
    python scripts/quick_test.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

PASS = 0
FAIL = 0


def print_fatal_and_exit(message: str) -> None:
    print(f"\n[FATAL] {message}")
    sys.exit(1)


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {name}")
        PASS += 1
    else:
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAIL += 1


def main():
    global PASS, FAIL
    print("\n=== quick_test.py: Development Fast-Check ===\n")

    # ── 1. app.main import ────────────────────────────────────────────────
    print("[1] app.main import")
    try:
        from app import main as app_module
        check("app.main imports without error", True)
    except Exception as e:
        check("app.main imports without error", False, str(e))
        print_fatal_and_exit("Cannot proceed — app.main failed to import")

    # ── 2. TestClient creation ────────────────────────────────────────────
    print("\n[2] TestClient creation")
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        check("TestClient can be instantiated", True)
    except Exception as e:
        check("TestClient can be instantiated", False, str(e))
        print_fatal_and_exit("Cannot proceed — TestClient creation failed")

    # ── 3. Core GET endpoints ─────────────────────────────────────────────
    print("\n[3] Core GET endpoints")
    endpoints = [
        ("/", "GET /"),
        ("/sources", "GET /sources"),
        ("/fetch-runs", "GET /fetch-runs"),
        ("/candidate-pool", "GET /candidate-pool"),
        ("/generation-queue", "GET /generation-queue"),
        ("/cards", "GET /cards"),
    ]
    for path, label in endpoints:
        try:
            response = client.get(path)
            check(f"{label} returns 200", response.status_code == 200, f"status={response.status_code}")
        except Exception as e:
            check(f"{label} returns 200", False, str(e))

    # ── 4. Core service imports ──────────────────────────────────────────
    print("\n[4] Core service imports")
    service_checks = [
        ("app.application.sources.fetch_service", "SourceFetchService"),
        ("app.application.fetch_runs.delta", "FetchDeltaDigestService"),
        ("app.application.source_items.background_compile", "BackgroundCompileService"),
        ("app.application.candidate_quality.services", "CandidateQualityService"),
        ("app.application.source_items.compile_service", "SourceItemCompileService"),
    ]
    for module_path, class_name in service_checks:
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            check(f"{class_name} is importable", cls is not None)
        except Exception as e:
            check(f"{class_name} is importable", False, str(e))

    # ── 5. Template keyword presence ────────────────────────────────────────
    print("\n[5] Template keyword presence")
    templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    keyword_templates = {
        "信息来源": ["index.html", "sources.html"],
        "运行记录": ["fetch_runs.html", "fetch_run_detail.html"],
        "候选池": ["candidate_pool.html"],
        "生成队列": ["generation_queue.html"],
        "InsightCard": ["cards.html", "card_detail.html"],
    }
    for keyword, expected_files in keyword_templates.items():
        found = False
        for fname in expected_files:
            fpath = templates_dir / fname
            if fpath.exists():
                try:
                    content = fpath.read_text(encoding="utf-8")
                    if keyword in content:
                        found = True
                        break
                except Exception:
                    pass
        check(f"Template keyword '{keyword}' found", found, f"checked: {expected_files}")

    # ── 6. Weak title detection (case-insensitive) ─────────────────────────
    print("\n[6] Weak title detection in html_index_probe")
    try:
        from app.sources.html_index_probe import (
            _is_weak_title, _make_url_slug_fallback, choose_candidate_title,
            _should_update_title, MAX_DETAIL_FETCHES_PER_SOURCE,
        )
    except Exception as e:
        check("html_index_probe imports for weak title helpers", False, str(e))
    else:
        # Case-insensitive weak title detection
        check("'Learn More' is detected as weak title",
              _is_weak_title("Learn More") is True)
        check("'FEATURED' is detected as weak title",
              _is_weak_title("FEATURED") is True)
        check("'featured' (lowercase) is detected as weak title",
              _is_weak_title("featured") is True)
        check("'Read More' is detected as weak title",
              _is_weak_title("Read More") is True)
        check("'Meta AI MTIA Chip Announcement' is NOT weak",
              _is_weak_title("Meta AI MTIA Chip Announcement") is False)
        check("Empty string is detected as weak",
              _is_weak_title("") is True)
        check("Whitespace-only string is detected as weak",
              _is_weak_title("   ") is True)

        # URL slug fallback
        slug = _make_url_slug_fallback(
            "https://ai.meta.com/blog/meta-mtia-scale-ai-chips-for-billions/"
        )
        check("URL slug fallback extracts 'meta mtia scale ai chips for billions'",
              slug == "meta mtia scale ai chips for billions", f"got: {repr(slug)}")

        # ── choose_candidate_title priority rules ────────────────────────
        # 1. detail_metadata.title (if not weak) wins over link_text
        detail_good = {"title": "Segment Anything Model 3", "title_source": "detail_og_title"}
        title, src = choose_candidate_title("Learn More",
                                            "https://ai.meta.com/blog/segment-anything-model-3/",
                                            detail_good)
        check("detail_metadata.title takes priority over weak link_text",
              title == "Segment Anything Model 3" and src == "detail_og_title",
              f"got: {title!r}, {src}")

        # 2. weak link_text → detail title used if available
        title2, src2 = choose_candidate_title("FEATURED",
                                              "https://ai.meta.com/blog/meta-mtia/",
                                              detail_good)
        check("detail_og_title used when link_text is weak 'FEATURED'",
              title2 == "Segment Anything Model 3" and src2 == "detail_og_title",
              f"got: {title2!r}, {src2}")

        # 3. no detail title + good link_text → link_text used
        detail_empty: dict = {}
        title3, src3 = choose_candidate_title("Meta AI MTIA Announcement",
                                              "https://ai.meta.com/blog/xyz/",
                                              detail_empty)
        check("good link_text used when no detail title available",
              title3 == "Meta AI MTIA Announcement" and src3 == "link_text",
              f"got: {title3!r}, {src3}")

        # 4. no detail title + weak link_text → URL slug fallback
        title4, src4 = choose_candidate_title("Learn More",
                                              "https://ai.meta.com/blog/tribe-v2-brain/",
                                              detail_empty)
        check("URL slug fallback used when link_text is weak and no detail title",
              title4 == "tribe v2 brain" and src4 == "url_slug",
              f"got: {title4!r}, {src4}")

        # 5. good link_text beats weak detail title (unlikely but tested)
        detail_weak = {"title": "More", "title_source": "detail_h1"}
        title5, src5 = choose_candidate_title("Meta AI Tribe V2 Paper",
                                              "https://ai.meta.com/blog/tribe/",
                                              detail_weak)
        check("good link_text used over weak detail_h1 title",
              title5 == "Meta AI Tribe V2 Paper" and src5 == "link_text",
              f"got: {title5!r}, {src5}")

        # ── MAX_DETAIL_FETCHES_PER_SOURCE constant ─────────────────────────
        check("MAX_DETAIL_FETCHES_PER_SOURCE is 15",
              MAX_DETAIL_FETCHES_PER_SOURCE == 15)

        # ── _should_update_title existing-item title protection ─────────────
        # a) url_slug must NOT overwrite a good existing title
        c_good_existing = {"title": "Real Article Title", "title_source": "url_slug"}
        check("url_slug does NOT overwrite good existing title",
              _should_update_title("Real Article Title", c_good_existing) is False,
              f"got: {_should_update_title('Real Article Title', c_good_existing)}")

        # b) url_slug CAN fix a weak existing title
        check("url_slug CAN overwrite weak existing title",
              _should_update_title("Learn More", c_good_existing) is True)

        # c) detail title always overwrites (even good existing)
        c_detail = {"title": "Segment Anything 3", "title_source": "detail_og_title"}
        check("detail title overwrites good existing title",
              _should_update_title("Real Article Title", c_detail) is True)
        check("detail title overwrites weak existing title",
              _should_update_title("FEATURED", c_detail) is True)

        # d) good link_text can fix weak existing
        c_linktext = {"title": "Meta AI MTIA", "title_source": "link_text"}
        check("good link_text overwrites weak existing",
              _should_update_title("Learn More", c_linktext) is True)
        check("good link_text keeps good existing (no update)",
              _should_update_title("Real Article Title", c_linktext) is False)

        # e) url_slug with no existing title (None/empty) → allowed
        check("url_slug allowed when existing is None",
              _should_update_title(None, c_good_existing) is True)

        # ── fetch_article_metadata: title fallback chain + description ─────────
        from unittest.mock import patch, MagicMock
        from app.sources.html_index_probe import fetch_article_metadata

        # 1. og:title takes highest priority
        mock_response = MagicMock()
        mock_response.text = """<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="OG Title Here">
<meta property="og:description" content="OG description.">
<meta name="twitter:title" content="Twitter Title Here">
</head>
<body><title>HTML Title</title><h1>H1 Title</h1></body>
</html>"""
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response):
            meta = fetch_article_metadata("https://example.com/article")
        check("og:title used when present",
              meta["title"] == "OG Title Here" and meta["title_source"] == "detail_og_title")
        check("description extracted even when og:title present",
              meta["description"] == "OG description.",
              f"got: {meta.get('description')!r}")

        # 2. twitter:title fallback when og:title absent
        mock_response2 = MagicMock()
        mock_response2.text = """<!DOCTYPE html>
<html>
<head>
<meta name="twitter:title" content="Twitter Fallback Title">
<meta property="og:description" content="OG Desc.">
</head>
<body><title>HTML Title</title><h1>H1 Title</h1></body>
</html>"""
        mock_response2.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response2):
            meta2 = fetch_article_metadata("https://example.com/article2")
        check("twitter:title used when og:title absent",
              meta2["title"] == "Twitter Fallback Title" and meta2["title_source"] == "detail_twitter_title")

        # 3. <title> fallback when og:title and twitter:title absent
        mock_response3 = MagicMock()
        mock_response3.text = """<!DOCTYPE html>
<html>
<head>
<meta property="og:description" content="OG Desc.">
</head>
<body><title>HTML Title Fallback</title><h1>H1 Title</h1></body>
</html>"""
        mock_response3.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response3):
            meta3 = fetch_article_metadata("https://example.com/article3")
        check("<title> used when og:title and twitter:title absent",
              meta3["title"] == "HTML Title Fallback" and meta3["title_source"] == "detail_title")

        # 4. <h1> fallback when og:title, twitter:title, <title> all absent
        mock_response4 = MagicMock()
        mock_response4.text = """<!DOCTYPE html>
<html>
<head>
<meta property="og:description" content="OG Desc.">
</head>
<body><h1>H1 Fallback Title</h1></body>
</html>"""
        mock_response4.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response4):
            meta4 = fetch_article_metadata("https://example.com/article4")
        check("<h1> used when og:title, twitter:title, <title> all absent",
              meta4["title"] == "H1 Fallback Title" and meta4["title_source"] == "detail_h1")

    # ── 7. generation_queue.html section-header renaming ───────────────────
    print("\n[7] generation_queue.html section renaming")
    tpl_path = templates_dir / "generation_queue.html"
    try:
        content = tpl_path.read_text(encoding="utf-8")
    except Exception as e:
        check("generation_queue.html is readable", False, str(e))
    else:
        check("'可加入生成的候选项' is in generation_queue.html",
              "可加入生成的候选项" in content)
        check("'更多候选请前往' note is in generation_queue.html",
              "更多候选请前往" in content)
        check("'discovered_items[:20]' slice limit is in generation_queue.html",
              "discovered_items[:20]" in content)
        check("'未处理' is NOT used as section header (renamed)",
              "🆕 未处理 (" not in content)

    # ── 8. Candidate pool display improvements ─────────────────────────────
    print("\n[8] Candidate pool display improvements")

    # 8a. extract_lightweight_summary prioritises detail_description
    try:
        from app.application.fetch_runs.delta import extract_lightweight_summary
        from app.models import SourceItem
        from dataclasses import dataclass
        from datetime import datetime
        from unittest.mock import MagicMock

        # Mock a SourceItem with detail_description in raw_metadata_json
        mock_item = MagicMock(spec=SourceItem)
        mock_item.raw_metadata_json = '{"detail_description": "This is from the article detail page."}'
        mock_item.title = "Learn More"
        mock_item.source_key = "meta_ai_blog"
        summary = extract_lightweight_summary(mock_item)
        check("detail_description is extracted (priority over link_text)",
              "article detail page" in summary,
              f"got: {summary!r}")
    except Exception as e:
        check("extract_lightweight_summary handles detail_description", False, str(e))

    # 8b. build_candidate_display_card weak title handling
    try:
        from app.application.candidates.display import build_candidate_display_card, _is_weak_title
    except Exception as e:
        check("candidates.display imports", False, str(e))
    else:
        check("'Learn More' is weak title (display module)",
              _is_weak_title("Learn More") is True)
        check("'FEATURED' is weak title (display module)",
              _is_weak_title("FEATURED") is True)
        check("'featured' (lowercase) is weak title",
              _is_weak_title("featured") is True)
        check("'Real Article Title' is NOT weak",
              _is_weak_title("Real Article Title") is False)
        # Whitespace normalization: tabs, newlines, multiple spaces collapsed
        check("'LEARN   MORE' (multi-space) is weak",
              _is_weak_title("LEARN   MORE") is True)
        check("'Learn\\nMore' (newline) is weak",
              _is_weak_title("Learn\nMore") is True)
        check("' FEATURED ' (surrounding spaces) is weak",
              _is_weak_title(" FEATURED ") is True)

    # 8c. Weak title summary fallback protection
    try:
        from app.application.candidates.display import build_candidate_display_card
    except Exception as e:
        check("build_candidate_display_card is importable", False, str(e))
    else:
        # Mock SourceItem with weak title but NO detail_description → fallback fires
        mock_item2 = MagicMock(spec=SourceItem)
        mock_item2.id = 999
        mock_item2.title = "Learn More"
        mock_item2.raw_metadata_json = "{}"
        mock_item2.source_key = "meta_ai_blog"
        mock_item2.status = "discovered"
        mock_item2.insight_card_id = None
        mock_item2.published_at = None
        mock_item2.first_seen_at = datetime(2026, 6, 1, 12, 0, 0)
        mock_item2.canonical_url = None
        mock_item2.url = "https://ai.meta.com/blog/tribe-v2/"
        card = build_candidate_display_card(mock_item2)
        check("weak title + no summary → display.summary does not expose weak title",
              "Learn More" not in card.summary and "标题待修复" not in card.summary,
              f"got: {card.summary!r}")
        check("weak title shows display.title as '标题待修复'",
              card.title == "标题待修复")

        # Mock SourceItem with metadata published_at → time_label shows 发布于
        mock_item3 = MagicMock(spec=SourceItem)
        mock_item3.id = 1000
        mock_item3.title = "Real Article Title"
        mock_item3.raw_metadata_json = '{"published_at": "2026-06-01T10:00:00"}'
        mock_item3.source_key = "meta_ai_blog"
        mock_item3.status = "discovered"
        mock_item3.insight_card_id = None
        mock_item3.published_at = None          # DB field empty
        mock_item3.first_seen_at = datetime(2026, 6, 1, 12, 0, 0)
        mock_item3.canonical_url = None
        mock_item3.url = "https://ai.meta.com/blog/xyz/"
        card3 = build_candidate_display_card(mock_item3)
        check("raw_metadata_json.published_at → 发布于",
              card3.time_label == "发布于 2026-06-01",
              f"got: {card3.time_label!r}")

        # Mock SourceItem with article_published_time → also 发布于
        mock_item4 = MagicMock(spec=SourceItem)
        mock_item4.id = 1001
        mock_item4.title = "Another Article"
        mock_item4.raw_metadata_json = '{"article_published_time": "2026-05-20T08:30:00"}'
        mock_item4.source_key = "meta_ai_blog"
        mock_item4.status = "discovered"
        mock_item4.insight_card_id = None
        mock_item4.published_at = None
        mock_item4.first_seen_at = datetime(2026, 6, 1, 12, 0, 0)
        mock_item4.canonical_url = None
        mock_item4.url = "https://ai.meta.com/blog/abc/"
        card4 = build_candidate_display_card(mock_item4)
        check("raw_metadata_json.article_published_time → 发布于",
              card4.time_label == "发布于 2026-05-20",
              f"got: {card4.time_label!r}")

        # Mock SourceItem with NO published_at anywhere → shows 发现于
        mock_item5 = MagicMock(spec=SourceItem)
        mock_item5.id = 1002
        mock_item5.title = "Yet Another"
        mock_item5.raw_metadata_json = "{}"
        mock_item5.source_key = "meta_ai_blog"
        mock_item5.status = "discovered"
        mock_item5.insight_card_id = None
        mock_item5.published_at = None
        mock_item5.first_seen_at = datetime(2026, 6, 9, 8, 0, 0)
        mock_item5.canonical_url = None
        mock_item5.url = "https://ai.meta.com/blog/123/"
        card5 = build_candidate_display_card(mock_item5)
        check("no pub date anywhere → shows 发现于",
              card5.time_label == "发现于 2026-06-09",
              f"got: {card5.time_label!r}")
    tpl_path2 = templates_dir / "candidate_pool.html"
    try:
        content2 = tpl_path2.read_text(encoding="utf-8")
    except Exception as e:
        check("candidate_pool.html is readable", False, str(e))
    else:
        check("candidate_pool.html uses display_map",
              "{% set display = display_map.get(item.id) %}" in content2)
        check("candidate_pool.html shows '标题待修复' for weak titles",
              "标题待修复" in content2)
        check("candidate_pool.html shows weak title raw hint",
              "原始标题：" in content2)
        check("candidate_pool.html shows candidate-summary div",
              "candidate-summary" in content2)
        check("candidate_pool.html shows display.time_label (published vs discovered)",
              "display.time_label" in content2)
        check("candidate_pool.html de-emphasises #ID (small muted)",
              "candidate-id" in content2 or "#{{ item.id }}" in content2)

    # ── 9. generation_queue display improvements ────────────────────────────
    print("\n[9] generation_queue display improvements")
    tpl_gq = templates_dir / "generation_queue.html"
    try:
        content_gq = tpl_gq.read_text(encoding="utf-8")
    except Exception as e:
        check("generation_queue.html is readable", False, str(e))
    else:
        check("generation_queue.html uses display_map for card display",
              "{% set display = display_map.get(item.id) %}" in content_gq)
        check("generation_queue.html shows '标题待修复' for weak titles",
              "标题待修复" in content_gq)
        check("generation_queue.html shows candidate-summary div (summary field)",
              "candidate-summary" in content_gq)
        check("generation_queue.html shows safe_external_url (原文链接)",
              "safe_external_url" in content_gq)
        check("generation_queue.html shows display.time_label (time field)",
              "display.time_label" in content_gq)
        check("generation_queue.html has 加入生成 POST form in discovered section",
              'method="post" action="/source-items/{{ item.id }}/enqueue-compile"' in content_gq)
        check("generation_queue.html has 重试生成 POST form in failed section",
              "重试生成" in content_gq and 'method="post"' in content_gq)
        check("generation_queue.html preserves section headers (compiling/compiled/failed/discovered)",
              "生成中" in content_gq and "已完成" in content_gq and "失败" in content_gq and "可加入生成的候选项" in content_gq)
        check("generation_queue.html uses candidate-card class",
              "candidate-card" in content_gq)
        check("generation_queue.html has weak title hint for discovered items",
              "原始标题：" in content_gq)

    # ── 10. FetchRun detail display improvements ────────────────────────────
    print("\n[10] FetchRun detail display improvements")

    # 10a. FetchDeltaItem dataclass has display fields
    try:
        from app.application.fetch_runs.delta import FetchDeltaItem
        delta_fields = [f.name for f in FetchDeltaItem.__dataclass_fields__.values()]
        check("FetchDeltaItem has display_title field",
              "display_title" in delta_fields)
        check("FetchDeltaItem has is_title_weak field",
              "is_title_weak" in delta_fields)
        check("FetchDeltaItem has raw_title field",
              "raw_title" in delta_fields)
        check("FetchDeltaItem has time_label field",
              "time_label" in delta_fields)
    except Exception as e:
        check("FetchDeltaItem display fields exist", False, str(e))

    # 10b. _enrich_display sets display_title correctly
    try:
        from app.application.fetch_runs.delta import FetchDeltaDigestService, FetchDeltaItem
        from unittest.mock import MagicMock
        from datetime import datetime

        # Mock SourceItem with weak title
        mock_item = MagicMock()
        mock_item.id = 1
        mock_item.title = "Learn More"
        mock_item.raw_metadata_json = "{}"
        mock_item.source_key = "test_blog"
        mock_item.status = "discovered"
        mock_item.insight_card_id = None
        mock_item.published_at = None
        mock_item.first_seen_at = datetime(2026, 6, 1, 12, 0, 0)
        mock_item.canonical_url = None
        mock_item.url = "https://example.com/article"

        service = FetchDeltaDigestService(db=None)
        delta = FetchDeltaItem(
            item_id=1, title="Learn More", url="https://example.com/article",
            source_key="test_blog", published_at=None,
            summary="Some summary", status="discovered",
            insight_card_id=None, delta_type="new",
        )
        service._enrich_display(delta, mock_item)
        check("weak title → display_title is '标题待修复'",
              delta.display_title == "标题待修复")
        check("weak title → is_title_weak is True",
              delta.is_title_weak is True)
        check("weak title → raw_title is original title",
              delta.raw_title == "Learn More")
        check("weak title → time_label shows 发现于",
              "发现于" in delta.time_label)
    except Exception as e:
        check("_enrich_display weak title handling", False, str(e))

    # 10b. Failed delta items have display defaults (no SourceItem backing)
    try:
        from app.db import SessionLocal
        from app.application.fetch_runs.delta import FetchDeltaDigestService, FetchDeltaDigest
        from unittest.mock import MagicMock

        # Mock FetchRun with failed_urls
        mock_run = MagicMock()
        mock_run.id = 999
        mock_run.source_key = "test_source"
        mock_run.started_at = MagicMock()
        mock_run.finished_at = MagicMock()
        mock_run.metadata_json = '{"delta":{"failed_urls":[{"url":"https://fail.example.com","error":"timeout"}]}}'

        # Need real db session because build_for_run also queries SourceItem table
        db_session = SessionLocal()
        try:
            service = FetchDeltaDigestService(db=db_session)
            digest = service.build_for_run(mock_run)

            check("failed_count is 1 for failed_urls entry",
                  digest.failed_count == 1,
                  f"got {digest.failed_count}")
            check("failed item display_title == '抓取失败'",
                  digest.failed_items[0].display_title == "抓取失败",
                  f"got {digest.failed_items[0].display_title!r}")
            check("failed item time_label == '时间未知'",
                  digest.failed_items[0].time_label == "时间未知",
                  f"got {digest.failed_items[0].time_label!r}")
            check("failed item is_title_weak is False",
                  digest.failed_items[0].is_title_weak is False,
                  f"got {digest.failed_items[0].is_title_weak}")
            check("failed item raw_title is None",
                  digest.failed_items[0].raw_title is None,
                  f"got {digest.failed_items[0].raw_title!r}")
        finally:
            db_session.close()
    except Exception as e:
        check("failed delta item display defaults", False, str(e))

    # 10c. fetch_run_detail.html uses candidate-card layout and display fields
    tpl_frd = templates_dir / "fetch_run_detail.html"
    try:
        content_frd = tpl_frd.read_text(encoding="utf-8")
    except Exception as e:
        check("fetch_run_detail.html is readable", False, str(e))
    else:
        check("fetch_run_detail.html uses candidate-card class",
              "candidate-card" in content_frd)
        check("fetch_run_detail.html shows candidate-summary",
              "candidate-summary" in content_frd)
        check("fetch_run_detail.html shows candidate-url",
              "candidate-url" in content_frd)
        check("fetch_run_detail.html shows candidate-meta (time_label)",
              "candidate-meta" in content_frd)
        check("fetch_run_detail.html shows '标题待修复' for weak titles",
              "标题待修复" in content_frd)
        check("fetch_run_detail.html shows run_error_display failure banner",
              "run-failure-banner" in content_frd)
        check("fetch_run_detail.html shows 失败原因 in banner",
              "失败原因" in content_frd)
        check("fetch_run_detail.html shows 建议 in banner",
              "建议" in content_frd)
        check("fetch_run_detail.html has 加入生成 POST form",
              'method="post" action="/fetch-runs/{{ run.id }}/source-items/' in content_frd)
        check("fetch_run_detail.html has candidate-title-row for display_title",
              "candidate-title-row" in content_frd)
        check("fetch_run_detail.html has candidate-weak-title-hint",
              "candidate-weak-title-hint" in content_frd)
        check("fetch_run_detail.html shows '探测运行中' banner for running status",
              "探测运行中" in content_frd)
        check("fetch_run_detail.html shows refresh button for running status",
              "刷新结果" in content_frd)

    # ── 11. Background source fetch service ───────────────────────────────
    print("\n[11] Background source fetch service")
    try:
        from app.application.sources.background_fetch import (
            SourceFetchBackgroundService,
            SourceFetchEnqueueResult,
            run_source_fetch_in_background,
        )
        check("SourceFetchBackgroundService is importable", True)
        check("SourceFetchEnqueueResult is importable", True)
        check("run_source_fetch_in_background is importable", True)
    except Exception as e:
        check("Background fetch imports", False, str(e))

    # enqueue_source with non-existent source
    try:
        from app.application.sources.background_fetch import SourceFetchBackgroundService
        svc = SourceFetchBackgroundService()
        result = svc.enqueue_source("nonexistent_source_xyz")
        check("enqueue_source for non-existent source returns accepted=False",
              result.accepted is False)
        check("enqueue_source for non-existent source returns status=not_found",
              result.status == "not_found")
        check("enqueue_source for non-existent source returns run_id=None",
              result.run_id is None)
    except Exception as e:
        check("enqueue_source not-found handling", False, str(e))

    # enqueue_source with background_tasks=None runs synchronously (no permanent running)
    try:
        from app.db import SessionLocal
        from app.models import Source, FetchRun
        import uuid
        from app.application.sources.background_fetch import SourceFetchBackgroundService

        db_session = SessionLocal()
        test_key = f"test_sync_enq_{uuid.uuid4().hex[:8]}"
        try:
            src = Source(
                source_key=test_key, name="Test Sync", description="Test",
                source_type="rss", homepage_url="https://example.com",
                feed_url="https://example.com/rss.xml", category="research",
                tags_json='[]', enabled=True, fetch_strategy="rss",
                relevance_hint="", fetch_interval_hours=24,
            )
            db_session.add(src)
            db_session.commit()

            svc = SourceFetchBackgroundService()
            # No background_tasks → runs synchronously
            result = svc.enqueue_source(test_key)

            # FetchRun should NOT stay in running state after synchronous call
            run = db_session.query(FetchRun).filter(FetchRun.id == result.run_id).first()
            check("enqueue_source (sync) does not leave FetchRun in 'running'",
                  run.status != "running",
                  f"got status={run.status!r}")
            check("enqueue_source (sync) FetchRun has final status",
                  run.status in ("success", "failed"),
                  f"got status={run.status!r}")
        finally:
            db_session.rollback()
            db_session.close()
    except Exception as e:
        check("enqueue_source synchronous fallback", False, str(e))

    # run_source_fetch_in_background does not re-raise
    try:
        from app.application.sources.background_fetch import run_source_fetch_in_background
        # Calling with a non-existent ID should not raise
        try:
            run_source_fetch_in_background(999999999)
            check("run_source_fetch_in_background with bad ID does not raise", True)
        except Exception as e:
            check("run_source_fetch_in_background with bad ID does not raise", False, str(e))
    except Exception as e:
        check("run_source_fetch_in_background non-raising", False, str(e))

    # _finish_run_as_failed handles source=None gracefully
    try:
        from app.application.sources.background_fetch import _finish_run_as_failed
        from app.models import FetchRun
        from app.db import SessionLocal
        from datetime import datetime
        import json

        db_session = SessionLocal()
        try:
            # Create a FetchRun with no associated Source
            orphaned = FetchRun(
                source_id=99999,  # non-existent source
                source_key="orphan_key",
                run_type="manual",
                status="running",
                started_at=datetime.utcnow(),
            )
            db_session.add(orphaned)
            db_session.commit()
            db_session.refresh(orphaned)

            # Should not raise even though source=None
            try:
                _finish_run_as_failed(
                    db_session, orphaned, source=None,
                    error_message="test error"
                )
                check("_finish_run_as_failed with source=None does not raise", True)
            except Exception as inner_e:
                check("_finish_run_as_failed with source=None does not raise", False, str(inner_e))

            db_session.refresh(orphaned)
            check("_finish_run_as_failed with source=None sets status=failed",
                  orphaned.status == "failed",
                  f"got status={orphaned.status!r}")
        finally:
            db_session.rollback()
            db_session.close()
    except Exception as e:
        check("_finish_run_as_failed source=None safety", False, str(e))

    # ── 12. FetchRun display polish: test-source hiding and error display ──
    print("\n[12] FetchRun display polish")

    # 12a. is_test_source_key helper
    try:
        from app.routes.fetch_runs import is_test_source_key
        check("is_test_source_key('orphan_key') is True",
              is_test_source_key("orphan_key") is True)
        check("is_test_source_key('test_sync_enq_xxx') is True",
              is_test_source_key("test_sync_enq_xxx") is True)
        check("is_test_source_key('test_abc') is True",
              is_test_source_key("test_abc") is True)
        check("is_test_source_key('openai_news') is False",
              is_test_source_key("openai_news") is False)
        check("is_test_source_key(None) is False",
              is_test_source_key(None) is False)
        check("is_test_source_key('') is False",
              is_test_source_key("") is False)
        check("is_test_source_key('arXiv_cs_ai') is False",
              is_test_source_key("arXiv_cs_ai") is False)
    except Exception as e:
        check("is_test_source_key helper", False, str(e))

    # 12b. get_fetch_run_error_display helper — uses a mock-like object
    try:
        from app.routes.fetch_runs import get_fetch_run_error_display
        from dataclasses import dataclass

        @dataclass
        class MockRun:
            status: str
            error_message: str | None

        r1 = MockRun(status="failed", error_message="HTTP 404")
        check("error_message present → returned as-is",
              get_fetch_run_error_display(r1) == "HTTP 404")

        r2 = MockRun(status="failed", error_message=None)
        check("failed + no error_message → fallback msg",
              "失败原因缺失" in get_fetch_run_error_display(r2))

        r3 = MockRun(status="partial_failed", error_message=None)
        check("partial_failed + no error_message → partial fallback",
              "部分失败原因缺失" in get_fetch_run_error_display(r3))

        r4 = MockRun(status="success", error_message=None)
        check("success + no error_message → '-'",
              get_fetch_run_error_display(r4) == "-")

        r5 = MockRun(status="running", error_message=None)
        check("running + no error_message → '-'",
              get_fetch_run_error_display(r5) == "-")
    except Exception as e:
        check("get_fetch_run_error_display helper", False, str(e))

    # 12c. get_fetch_run_error_hint helper
    try:
        from app.routes.fetch_runs import get_fetch_run_error_hint

        check("HTTP 404 → URL expired hint",
              "URL" in get_fetch_run_error_hint("HTTP 404 Not Found") and "失效" in get_fetch_run_error_hint("HTTP 404 Not Found"))
        check("Timeout → timeout hint",
              "超时" in get_fetch_run_error_hint("Connection Timeout"))
        check("No candidate article links found → no articles hint",
              "文章链接" in get_fetch_run_error_hint("No candidate article links found on page"))
        check("unsupported fetch_strategy → strategy hint",
              "抓取策略" in get_fetch_run_error_hint("unsupported fetch_strategy"))
        check("unknown error → None (no specific hint)",
              get_fetch_run_error_hint("Some unknown error") is None)
        check("None input → None",
              get_fetch_run_error_hint(None) is None)
    except Exception as e:
        check("get_fetch_run_error_hint helper", False, str(e))

    # 12d. Repository list_runs excludes test sources by default
    try:
        from app.db import SessionLocal
        from app.models import FetchRun, Source
        from datetime import datetime

        db_session = SessionLocal()
        try:
            # Create a real Source to satisfy source_id NOT NULL constraint
            import uuid
            test_real_key = f"test_real_filter_{uuid.uuid4().hex[:8]}"
            src = Source(
                source_key=test_real_key,
                name="Test Real Source",
                description="Test",
                source_type="rss",
                homepage_url="https://example.com/news",
                feed_url="https://example.com/news/rss",
                category="test",
                tags_json="[]",
                enabled=True,
                fetch_strategy="rss",
                relevance_hint="",
                fetch_interval_hours=24,
            )
            db_session.add(src)
            db_session.commit()
            db_session.refresh(src)

            # Create test FetchRuns
            test_run = FetchRun(
                source_id=src.id,
                source_key="test_abc123",
                run_type="manual",
                status="success",
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
            )
            orphan_run = FetchRun(
                source_id=src.id,
                source_key="orphan_key",
                run_type="manual",
                status="success",
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
            )
            real_run = FetchRun(
                source_id=src.id,
                source_key=test_real_key,
                run_type="manual",
                status="success",
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
            )
            db_session.add_all([test_run, orphan_run, real_run])
            db_session.commit()

            from app.infrastructure.repositories.fetch_run_repository import FetchRunRepository
            repo = FetchRunRepository(db_session)

            # exclude_test_sources=True (default) → test sources excluded
            result = repo.list_runs(exclude_test_sources=True)
            source_keys = {r.source_key for r in result.items}
            check("exclude_test_sources=True hides test_*",
                  all(not k.startswith("test_") for k in source_keys),
                  f"got: {source_keys}")
            check("exclude_test_sources=True hides orphan_key",
                  "orphan_key" not in source_keys,
                  f"got: {source_keys}")
            # Verify some non-test source keys are present (DB already has real sources)
            non_test_keys = {k for k in source_keys if k != "orphan_key" and not k.startswith("test_")}
            check("exclude_test_sources=True keeps non-test sources",
                  len(non_test_keys) > 0,
                  f"got: {source_keys}")

            # exclude_test_sources=False → all included
            result2 = repo.list_runs(exclude_test_sources=False)
            source_keys2 = {r.source_key for r in result2.items}
            check("exclude_test_sources=False includes test_*",
                  any(k.startswith("test_") for k in source_keys2))
            check("exclude_test_sources=False includes orphan_key",
                  "orphan_key" in source_keys2)
        finally:
            db_session.rollback()
            db_session.close()
    except Exception as e:
        check("Repository exclude_test_sources filtering", False, str(e))

    # 12e. TestClient: /fetch-runs defaults to hiding test records
    try:
        resp = client.get("/fetch-runs")
        check("GET /fetch-runs returns 200", resp.status_code == 200)
        check("/fetch-runs default hides test records (shows banner)",
              "已隐藏测试运行记录" in resp.text or "显示测试记录" in resp.text)
    except Exception as e:
        check("/fetch-runs default hides test records", False, str(e))

    # 12f. TestClient: /fetch-runs?include_test=1 shows test records
    try:
        resp2 = client.get("/fetch-runs?include_test=1")
        check("GET /fetch-runs?include_test=1 returns 200", resp2.status_code == 200)
        check("include_test=1 shows test records banner",
              "包括测试运行记录" in resp2.text or "隐藏测试记录" in resp2.text)
    except Exception as e:
        check("/fetch-runs?include_test=1 shows test records", False, str(e))

    # ── 13. validate_sources_live.py — unit-testable helpers ──────────────
    print("\n[13] validate_sources_live helpers")

    # 13a. Script is importable
    try:
        import scripts.validate_sources_live as val_live
        check("validate_sources_live.py is importable", True)
    except Exception as e:
        check("validate_sources_live.py is importable", False, str(e))

    # 13b. is_weak_title — case and whitespace normalization
    try:
        check("'Learn More' is weak (case-insensitive)",
              val_live.is_weak_title("Learn More") is True)
        check("'LEARN MORE' is weak",
              val_live.is_weak_title("LEARN MORE") is True)
        check("'  Learn   More  ' is weak (whitespace collapsed)",
              val_live.is_weak_title("  Learn   More  ") is True)
        check("'LEARN\\nMORE' is weak (newline normalized)",
              val_live.is_weak_title("LEARN\nMORE") is True)
        check("' FEATURED ' is weak (surrounding spaces)",
              val_live.is_weak_title(" FEATURED ") is True)
        check("'Meta AI MTIA Chip' is NOT weak",
              val_live.is_weak_title("Meta AI MTIA Chip Announcement") is False)
        check("None title is weak",
              val_live.is_weak_title(None) is True)
        check("empty string is weak",
              val_live.is_weak_title("") is True)
        check("whitespace-only is weak",
              val_live.is_weak_title("   \n  ") is True)
    except Exception as e:
        check("is_weak_title helpers", False, str(e))

    # 13c. Coverage helpers
    try:
        items = [
            {"title": "Real Title", "summary": "Some summary", "published_at": "2024-01-01"},
            {"title": "Learn More", "summary": None, "published_at": None},
            {"title": "Featured", "summary": "", "published_at": ""},
            {"title": "Another Real", "summary": "Desc", "published_at": "2024-01-02"},
        ]
        check("title_coverage 2/4 = 50%",
              val_live.title_coverage(items) == 0.5)
        check("summary_coverage 2/4 = 50%",
              val_live.summary_coverage(items) == 0.5)
        check("published_coverage 2/4 = 50%",
              val_live.published_coverage(items) == 0.5)
        check("title_coverage empty = 0",
              val_live.title_coverage([]) == 0.0)
        check("extract_validation_summary prefers zh_one_liner",
              val_live.extract_validation_summary({
                  "summary": "Fallback summary",
                  "zh_one_liner": "  中文一句话  ",
              }) == "中文一句话")
        check("extract_validation_summary reads detail_description",
              val_live.extract_validation_summary({
                  "detail_description": "  Detail   description\ntext  ",
              }) == "Detail description text")
        check("extract_validation_summary reads rss_summary",
              val_live.extract_validation_summary({
                  "rss_summary": "RSS summary",
              }) == "RSS summary")
        expanded_items = [
            {"summary": val_live.extract_validation_summary({"detail_description": "Detail text"})},
            {"summary": val_live.extract_validation_summary({"rss_summary": "RSS text"})},
            {"summary": val_live.extract_validation_summary({"zh_one_liner": "One liner"})},
            {"summary": val_live.extract_validation_summary({"summary": ""})},
        ]
        check("summary_coverage uses expanded summary field",
              val_live.summary_coverage(expanded_items) == 0.75)
    except Exception as e:
        check("coverage helpers", False, str(e))

    # 13c-2. _items_for_source metadata extraction
    try:
        import json
        import uuid
        from datetime import datetime
        from app.db import SessionLocal as _SL
        from app.models import Source, SourceItem

        db_session = _SL()
        test_key = f"test_live_validation_{uuid.uuid4().hex[:8]}"
        try:
            source = Source(
                source_key=test_key,
                name="Test Live Validation Metadata",
                description="Test",
                source_type="rss",
                category="test",
                tags_json="[]",
                fetch_strategy="rss",
                relevance_hint="",
                fetch_interval_hours=24,
                homepage_url="https://example.com",
                feed_url="https://example.com/feed.xml",
                enabled=True,
            )
            db_session.add(source)
            db_session.commit()
            db_session.refresh(source)
            item = SourceItem(
                source_id=source.id,
                source_key=test_key,
                url="https://example.com/article",
                title="Article",
                status="discovered",
                raw_metadata_json=json.dumps({
                    "rss_summary": "RSS summary body",
                    "article_published_time": "2026-06-09T00:00:00Z",
                }),
                last_seen_at=datetime.utcnow(),
            )
            db_session.add(item)
            db_session.commit()

            extracted = val_live._items_for_source(db_session, test_key)
            check("_items_for_source reads rss_summary",
                  extracted[0]["summary"] == "RSS summary body")
            check("_items_for_source reads raw article_published_time",
                  extracted[0]["published_at"] == "2026-06-09T00:00:00Z")
        finally:
            db_session.query(SourceItem).filter(SourceItem.source_key == test_key).delete(synchronize_session=False)
            db_session.query(Source).filter(Source.source_key == test_key).delete(synchronize_session=False)
            db_session.commit()
            db_session.close()
    except Exception as e:
        check("_items_for_source metadata extraction", False, str(e))

    # 13d. Verdict logic — PASS / WARN / FAIL
    try:
        # FAIL: error + 0 items
        v, s = val_live.make_verdict("HTTP 404", 0, 0.0, 0.0, 0.0, 0)
        check("FAIL: error with 0 items", v == "FAIL")

        # FAIL: no items
        v, s = val_live.make_verdict(None, 0, 0.0, 0.0, 0.0, 0)
        check("FAIL: no items found", v == "FAIL")

        # FAIL: timeout
        v, s = val_live.make_verdict("Timeout fetching feed after 20s", 0, 0.0, 0.0, 0.0, 0)
        check("FAIL: timeout", v == "FAIL")

        # FAIL: HTTP 404
        v, s = val_live.make_verdict("HTTP 404: Not Found", 0, 0.0, 0.0, 0.0, 0)
        check("FAIL: HTTP 404", v == "FAIL")

        # WARN: low summary coverage
        v, s = val_live.make_verdict(None, 5, 1.0, 0.3, 1.0, 0)
        check("WARN: low summary coverage", v == "WARN")

        # WARN: low published coverage
        v, s = val_live.make_verdict(None, 5, 1.0, 1.0, 0.3, 0)
        check("WARN: low published coverage", v == "WARN")

        # WARN: weak titles present
        v, s = val_live.make_verdict(None, 5, 0.8, 1.0, 1.0, 2)
        check("WARN: weak titles", v == "WARN")

        # PASS: healthy source
        v, s = val_live.make_verdict(None, 10, 1.0, 1.0, 1.0, 0)
        check("PASS: healthy source", v == "PASS")
    except Exception as e:
        check("verdict logic", False, str(e))

    # 13e. Markdown report generation with mock data
    try:
        mock_results = [{
            "source_key": "openai_news",
            "name": "OpenAI News",
            "fetch_strategy": "html_index",
            "homepage_url": "https://openai.com/news/",
            "feed_url": None,
            "status": "success",
            "items_found": 10,
            "items_new": 5,
            "items_updated": 3,
            "items_failed": 2,
            "error_message": None,
            "title_coverage": 0.9,
            "summary_coverage": 0.7,
            "published_coverage": 0.6,
            "weak_title_count": 1,
            "sample_titles": ["OpenAI Announces GPT-5", "AI Safety Update"],
            "sample_urls": ["https://openai.com/news/1", "https://openai.com/news/2"],
            "verdict": "WARN",
            "suggestion": "1 weak title(s) detected — check detail page title extraction.",
        }]
        md = val_live.build_markdown(mock_results, total=1, passed=0, warned=1, failed=0)
        check("Markdown report contains source name", "OpenAI News" in md)
        check("Markdown report contains verdict", "WARN" in md)
        check("Markdown report contains items_found", "10" in md)
        check("Markdown report contains suggestion", "weak title" in md)
        check("Markdown report contains summary coverage criteria",
              "summary coverage fields" in md and "zh_one_liner" in md and "rss_summary" in md)
        check("Markdown report contains published coverage criteria",
              "published coverage fields" in md and "metadata.article_published_time" in md)
    except Exception as e:
        check("markdown report generation", False, str(e))

    # ── 14. SourceFetchService error_message write-through guarantee ────────
    print("\n[14] SourceFetchService error_message write-through")

    # 14a. error_message written to FetchRun when probe returns error_message
    try:
        import uuid
        from app.db import SessionLocal as _SL
        import app.application.sources.fetch_service as fetch_service_mod
        from app.application.sources.fetch_service import SourceFetchService
        from app.models import Source, SourceItem
        from datetime import datetime

        db_session = _SL()
        original_probe = fetch_service_mod.probe_rss_source
        keys_to_cleanup = []
        try:
            # Case 1: probe returns error_message and items_found == 0 -> failed with error.
            test_key_1 = f"test_err_zero_{uuid.uuid4().hex[:8]}"
            keys_to_cleanup.append(test_key_1)
            test_src_1 = Source(
                source_key=test_key_1,
                name="Test Error Source",
                description="Test source for error_message write-through validation",
                source_type="rss",
                category="test",
                tags_json="[]",
                fetch_strategy="rss",
                relevance_hint="",
                fetch_interval_hours=24,
                homepage_url="http://example.com",
                feed_url="http://example.com/nonexistent.rss",
                enabled=True,
            )
            db_session.add(test_src_1)
            db_session.commit()

            def fake_probe_failed(db, source, timeout_seconds=20):
                return {
                    "source_key": source.source_key,
                    "items_found": 0,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_failed": 0,
                    "error_message": "mock probe failed",
                }

            fetch_service_mod.probe_rss_source = fake_probe_failed
            svc = SourceFetchService(db_session)
            result = svc.run_source(test_key_1, timeout_seconds=5)

            check("error_message write-through failed: FetchRun.status == failed",
                  result.fetch_run.status == "failed")
            check("error_message write-through failed: result.error_message written",
                  result.error_message == "mock probe failed")
            check("error_message write-through failed: fetch_run.error_message written",
                  result.fetch_run.error_message == "mock probe failed")

            # Case 2: probe returns error_message and items_found > 0 -> partial_failed with error.
            test_key_2 = f"test_err_partial_{uuid.uuid4().hex[:8]}"
            keys_to_cleanup.append(test_key_2)
            test_src_2 = Source(
                source_key=test_key_2,
                name="Test Partial Error Source",
                description="Test partial error_message write-through validation",
                source_type="rss",
                category="test",
                tags_json="[]",
                fetch_strategy="rss",
                relevance_hint="",
                fetch_interval_hours=24,
                homepage_url="http://example.com",
                feed_url="http://example.com/feed.rss",
                enabled=True,
            )
            db_session.add(test_src_2)
            db_session.commit()
            db_session.refresh(test_src_2)

            def fake_probe_partial(db, source, timeout_seconds=20):
                item = SourceItem(
                    source_id=source.id,
                    source_key=source.source_key,
                    url=f"https://example.com/{uuid.uuid4().hex[:8]}",
                    title="Mock Article",
                    status="discovered",
                    last_seen_at=datetime.utcnow(),
                )
                db.add(item)
                db.commit()
                return {
                    "source_key": source.source_key,
                    "items_found": 1,
                    "items_new": 1,
                    "items_updated": 0,
                    "items_failed": 1,
                    "error_message": "mock partial probe error",
                }

            fetch_service_mod.probe_rss_source = fake_probe_partial
            result2 = svc.run_source(test_key_2, timeout_seconds=5)
            check("error_message write-through partial: FetchRun.status == partial_failed",
                  result2.fetch_run.status == "partial_failed")
            check("error_message write-through partial: result.error_message written",
                  result2.error_message == "mock partial probe error")
            check("error_message write-through partial: fetch_run.error_message written",
                  result2.fetch_run.error_message == "mock partial probe error")
        finally:
            fetch_service_mod.probe_rss_source = original_probe
            db_session.query(SourceItem).filter(SourceItem.source_key.in_(keys_to_cleanup)).delete(synchronize_session=False)
            db_session.query(Source).filter(Source.source_key.in_(keys_to_cleanup)).delete(synchronize_session=False)
            db_session.commit()
            db_session.close()
    except Exception as e:
        check("SourceFetchService error_message write-through", False, str(e))

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print(f"\nFailed checks — fix before continuing.")
        sys.exit(1)
    else:
        print("\nAll quick checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
