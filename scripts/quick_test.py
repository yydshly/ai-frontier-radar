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

    # ── 6. Weak title handling ─────────────────────────────────────────────
    print("\n[6] Weak title detection in html_index_probe")
    try:
        from app.sources.html_index_probe import _is_weak_title, _make_url_slug_fallback
    except Exception as e:
        check("html_index_probe imports for weak title helpers", False, str(e))
    else:
        check("'Learn More' is detected as weak title",
              _is_weak_title("Learn More") is True)
        check("'FEATURED' is detected as weak title",
              _is_weak_title("FEATURED") is True)
        check("'Read More' is detected as weak title",
              _is_weak_title("Read More") is True)
        check("'Meta AI MTIA Chip Announcement' is NOT weak",
              _is_weak_title("Meta AI MTIA Chip Announcement") is False)
        slug = _make_url_slug_fallback(
            "https://ai.meta.com/blog/meta-mtia-scale-ai-chips-for-billions/"
        )
        check("URL slug fallback extracts 'meta mtia scale ai chips for billions'",
              slug == "meta mtia scale ai chips for billions", f"got: {repr(slug)}")
        check("Empty string is detected as weak",
              _is_weak_title("") is True)
        check("Whitespace-only string is detected as weak",
              _is_weak_title("   ") is True)

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
