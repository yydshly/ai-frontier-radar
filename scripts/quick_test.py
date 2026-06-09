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
