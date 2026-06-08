#!/usr/bin/env python3
"""V1.0-alpha.4.1 acceptance script for demo UI links.

Validates:
    1. Demo data is created successfully
    2. GET / shows demo entry without /cards/{id}/export-report placeholder
    3. GET /source-items/{id} works
    4. GET /cards/{id} works
    5. GET /cards/{id}/export-report works
    6. GET /cards/{id}/export-markdown works
    7. Key text content is present on each page

Usage:
    python scripts/acceptance_ui_links.py --isolated-db
    python scripts/acceptance_ui_links.py --isolated-db --keep-db
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V1.0-alpha.4.1 demo UI links acceptance test."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_ui_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    """Run the UI links acceptance."""
    print("=" * 60)
    print("V1.0-alpha.4.1 UI Links Acceptance")
    print("=" * 60)

    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_ui_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    # Import after setting isolated DB
    from scripts.create_demo_data import create_demo_data, DEMO_SOURCE_KEY
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal, init_db

    init_db()
    print("[OK] Database initialized")

    client = TestClient(app)
    demo_source_item_id = None
    demo_card_id = None

    try:
        # Create demo data
        print("\n--- Creating demo data ---")
        result = create_demo_data(DEMO_SOURCE_KEY)
        demo_source_item_id = result.get("source_item_id")
        demo_card_id = result.get("card_id")

        assert demo_source_item_id is not None, "Demo source_item_id should exist"
        assert demo_card_id is not None, "Demo card_id should exist"
        print(f"[OK] Demo data ready: source_item_id={demo_source_item_id}, card_id={demo_card_id}")

        # Step 1: GET /
        print(f"\n--- Step 1: GET / ---")
        response = client.get("/")
        assert response.status_code == 200, f"GET / failed: {response.status_code}"
        text = response.text

        # Check demo entry section exists
        assert "演示数据入口" in text, "Missing '演示数据入口' on index"
        print("[OK] Found '演示数据入口'")

        # Check NOT a placeholder like /cards/{id}/export-report
        import re
        # Match /cards/{some_id}/export-report but not a real id
        placeholder_pattern = re.compile(r"/cards/\{[^}]+\}/export-report")
        matches = placeholder_pattern.findall(text)
        assert not matches, f"Found placeholder links on index: {matches}"
        print("[OK] No /cards/{{id}}/export-report placeholder found")

        # Check key elements exist
        checks_index = [
            ("查看演示 InsightCard", "demo InsightCard link"),
            ("导出演示完整报告", "export full report link"),
            ("推荐主流程", "recommended flow section"),
        ]
        for check_text, description in checks_index:
            if check_text in text:
                print(f"[OK] Found on index: {description}")

        # Check real export links exist on homepage (not placeholders)
        assert f"/cards/{demo_card_id}/export-report" in text, \
            f"Missing real /cards/{demo_card_id}/export-report link on index"
        print(f"[OK] Real /cards/{demo_card_id}/export-report link exists on index")

        assert f"/cards/{demo_card_id}/export-markdown" in text, \
            f"Missing real /cards/{demo_card_id}/export-markdown link on index"
        print(f"[OK] Real /cards/{demo_card_id}/export-markdown link exists on index")

        # Step 2: GET /source-items/{id}
        print(f"\n--- Step 2: GET /source-items/{demo_source_item_id} ---")
        response = client.get(f"/source-items/{demo_source_item_id}")
        assert response.status_code == 200, \
            f"GET /source-items/{demo_source_item_id} failed: {response.status_code}"
        print(f"[OK] GET /source-items/{demo_source_item_id} returns 200")

        # Step 3: GET /cards/{id}
        print(f"\n--- Step 3: GET /cards/{demo_card_id} ---")
        response = client.get(f"/cards/{demo_card_id}")
        assert response.status_code == 200, \
            f"GET /cards/{demo_card_id} failed: {response.status_code}"
        text = response.text

        checks_card = [
            ("中英双语核心理解", "bilingual core understanding section"),
            ("English Core Summary", "English core summary"),
            ("看完后的判断", "decision section"),
        ]
        for check_text, description in checks_card:
            assert check_text in text, f"Missing on /cards/{demo_card_id}: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{demo_card_id}: {description}")

        # Step 4: GET /cards/{id}/export-report
        print(f"\n--- Step 4: GET /cards/{demo_card_id}/export-report ---")
        response = client.get(f"/cards/{demo_card_id}/export-report")
        assert response.status_code == 200, \
            f"GET /cards/{demo_card_id}/export-report failed: {response.status_code}"
        text = response.text

        checks_report = [
            ("完整 Markdown 报告预览", "full markdown report preview heading"),
            ("English Core Summary", "English core summary in report"),
        ]
        for check_text, description in checks_report:
            assert check_text in text, \
                f"Missing on /cards/{demo_card_id}/export-report: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{demo_card_id}/export-report: {description}")

        # Step 5: GET /cards/{id}/export-markdown
        print(f"\n--- Step 5: GET /cards/{demo_card_id}/export-markdown ---")
        response = client.get(f"/cards/{demo_card_id}/export-markdown")
        assert response.status_code == 200, \
            f"GET /cards/{demo_card_id}/export-markdown failed: {response.status_code}"
        text = response.text

        checks_md = [
            ("Markdown 任务", "markdown task heading"),
        ]
        for check_text, description in checks_md:
            assert check_text in text, \
                f"Missing on /cards/{demo_card_id}/export-markdown: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{demo_card_id}/export-markdown: {description}")

        # Step 6: GET /cards/{id}/export-report/download
        print(f"\n--- Step 6: GET /cards/{demo_card_id}/export-report/download ---")
        download_response = client.get(f"/cards/{demo_card_id}/export-report/download")
        assert download_response.status_code == 200, \
            f"GET /cards/{demo_card_id}/export-report/download failed: {download_response.status_code}"
        content_disposition = download_response.headers.get("content-disposition", "")
        assert f"insightcard-{demo_card_id}-report.md" in content_disposition, \
            f"Content-Disposition missing 'insightcard-{demo_card_id}-report.md', got: {content_disposition}"
        print(f"[OK] Full report download returns 200 with correct filename in Content-Disposition")

        print("\n" + "=" * 60)
        print("[PASS] ACCEPTANCE PASSED")
        print("=" * 60)

    finally:
        # Cleanup
        if isolated_db_path and not args.keep_db:
            try:
                from app.db import engine
                engine.dispose()
            except Exception:
                pass
            try:
                if os.path.exists(isolated_db_path):
                    os.remove(isolated_db_path)
                    print(f"[INFO] Cleaned up isolated DB: {isolated_db_path}")
            except OSError as e:
                print(f"[WARN] Could not remove isolated DB: {isolated_db_path}: {e}")


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()
    _run_acceptance(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
