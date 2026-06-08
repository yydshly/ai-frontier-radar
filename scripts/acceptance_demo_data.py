#!/usr/bin/env python3
"""V1.0-alpha.1 acceptance script for demo data.

Validates:
    1. create_demo_data.py creates complete demo data set
    2. Homepage shows demo entry section
    3. Demo data pages are accessible and contain expected content

Usage:
    python scripts/acceptance_demo_data.py --isolated-db
    python scripts/acceptance_demo_data.py --isolated-db --keep-db
"""
import argparse
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V1.0-alpha.1 demo data acceptance test."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_demo_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    """Run the V1.0-alpha.1 demo data acceptance."""
    print("=" * 60)
    print("V1.0-alpha.1 Demo Data Acceptance")
    print("=" * 60)

    # Import create_demo_data functions
    from scripts.create_demo_data import create_demo_data, _delete_demo_data, DEMO_SOURCE_KEY

    from app.db import SessionLocal, init_db
    from app.models import Source, SourceItem, InsightCard, CardDecision, InsightCardBilingualReport

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    demo_card_id = None
    demo_source_item_id = None

    try:
        # Create demo data using the create_demo_data script
        print("\n--- Creating demo data ---")
        result = create_demo_data(DEMO_SOURCE_KEY)

        demo_card_id = result["card_id"]
        demo_source_item_id = result["source_item_id"]

        assert result["card_id"] is not None, "Demo card should be created"
        assert result["source_item_id"] is not None, "Demo source item should be created"
        print(f"[OK] Demo data created: card_id={demo_card_id}, source_item_id={demo_source_item_id}")

        # TestClient
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # GET /
        print("\n--- Step 1: GET / ---")
        response = client.get("/")
        assert response.status_code == 200, f"GET / failed: {response.status_code}"
        text = response.text

        checks_index = [
            ("演示数据入口", "演示数据入口 section"),
            ("查看演示 InsightCard", "查看演示 InsightCard link"),
            ("导出演示完整报告", "导出演示完整报告 link"),
        ]

        for check_text, description in checks_index:
            assert check_text in text, \
                f"Missing on index: {description} ('{check_text}')"
            print(f"[OK] Found on index: {description}")

        # GET /source-items/{id}
        print(f"\n--- Step 2: GET /source-items/{demo_source_item_id} ---")
        response = client.get(f"/source-items/{demo_source_item_id}")
        assert response.status_code == 200, \
            f"GET /source-items/{demo_source_item_id} failed: {response.status_code}"
        print(f"[OK] GET /source-items/{demo_source_item_id} returns 200")

        # GET /cards/{id}
        print(f"\n--- Step 3: GET /cards/{demo_card_id} ---")
        response = client.get(f"/cards/{demo_card_id}")
        assert response.status_code == 200, \
            f"GET /cards/{demo_card_id} failed: {response.status_code}"
        text = response.text

        checks_card = [
            ("中英双语核心理解", "中英双语核心理解 section"),
            ("English Core Summary", "English Core Summary content"),
            ("看完后的判断", "看完后的判断 section"),
        ]

        for check_text, description in checks_card:
            assert check_text in text, \
                f"Missing on /cards/{demo_card_id}: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{demo_card_id}: {description}")

        # GET /cards/{id}/export-report
        print(f"\n--- Step 4: GET /cards/{demo_card_id}/export-report ---")
        response = client.get(f"/cards/{demo_card_id}/export-report")
        assert response.status_code == 200, \
            f"GET /cards/{demo_card_id}/export-report failed: {response.status_code}"
        text = response.text

        checks_report = [
            ("完整报告预览", "完整报告预览 heading"),
        ]

        for check_text, description in checks_report:
            assert check_text in text, \
                f"Missing on /cards/{demo_card_id}/export-report: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{demo_card_id}/export-report: {description}")

        # GET /cards/{id}/export-markdown
        print(f"\n--- Step 5: GET /cards/{demo_card_id}/export-markdown ---")
        response = client.get(f"/cards/{demo_card_id}/export-markdown")
        assert response.status_code == 200, \
            f"GET /cards/{demo_card_id}/export-markdown failed: {response.status_code}"
        text = response.text

        checks_md = [
            ("Markdown 任务", "Markdown 任务 heading"),
        ]

        for check_text, description in checks_md:
            assert check_text in text, \
                f"Missing on /cards/{demo_card_id}/export-markdown: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{demo_card_id}/export-markdown: {description}")

        print("\n" + "=" * 60)
        print("[PASS] ACCEPTANCE PASSED")
        print("=" * 60)

    finally:
        # Cleanup - delete demo data
        if demo_source_item_id:
            try:
                # Delete decisions and reports for demo card
                if demo_card_id:
                    db.query(CardDecision).filter(
                        CardDecision.card_id == demo_card_id
                    ).delete(synchronize_session=False)
                    db.query(InsightCardBilingualReport).filter(
                        InsightCardBilingualReport.card_id == demo_card_id
                    ).delete(synchronize_session=False)
                    db.query(InsightCard).filter(
                        InsightCard.id == demo_card_id
                    ).delete(synchronize_session=False)
                db.query(SourceItem).filter(
                    SourceItem.id == demo_source_item_id
                ).delete(synchronize_session=False)
                db.query(Source).filter(
                    Source.source_key == DEMO_SOURCE_KEY
                ).delete(synchronize_session=False)
                db.commit()
                print(f"[INFO] Cleaned up demo data")
            except Exception as e:
                print(f"[WARN] Could not clean up demo data: {e}")
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_demo_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    _run_acceptance(args)

    if isolated_db_path and not args.keep_db:
        # Dispose engine to release file locks before deletion
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
            # Windows file lock warning - does not affect acceptance result
            print(f"[WARN] Could not remove isolated DB (Windows file lock): {isolated_db_path}: {e}")
            print("[INFO] This is a Windows file lock issue, not an acceptance failure.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
