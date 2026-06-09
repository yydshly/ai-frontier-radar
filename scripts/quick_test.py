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
