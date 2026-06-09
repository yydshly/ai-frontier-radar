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
