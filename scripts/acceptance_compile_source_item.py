#!/usr/bin/env python3
"""Acceptance test for SourceItem -> InsightCard compilation chain.

Validates:
    SourceItem(discovered)
    -> 手动触发 compile
    -> 调用 compile_url()
    -> 生成 InsightCard(completed/failed)
    -> 回写 SourceItem.insight_card_id
    -> 回写 SourceItem.status = compiled/failed
    -> 重复点击不会无意义重复编译
    -> 失败可重试

Usage:
    python scripts/acceptance_compile_source_item.py --isolated-db --mock-success
    python scripts/acceptance_compile_source_item.py --isolated-db --mock-failed
    python scripts/acceptance_compile_source_item.py --isolated-db --use-existing-item --source-key huggingface_blog
"""
import argparse
import os
import sys
import time
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.3.2 SourceItem compile acceptance test."
    )
    parser.add_argument(
        "--source-key",
        type=str,
        default=None,
        help="If --use-existing-item, filter by this source_key.",
    )
    parser.add_argument(
        "--mock-success",
        action="store_true",
        help="Mock compile_url to return a completed InsightCard.",
    )
    parser.add_argument(
        "--mock-failed",
        action="store_true",
        help="Mock compile_url to return a failed InsightCard.",
    )
    parser.add_argument(
        "--use-existing-item",
        action="store_true",
        help="Use an existing discovered SourceItem (no mocking).",
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_compile.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if not (args.mock_success or args.mock_failed or args.use_existing_item):
        print("[FAIL] Must specify --mock-success, --mock-failed, or --use-existing-item")
        return 1

    # Handle --isolated-db BEFORE importing app modules
    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_compile_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    # Import after env is set
    from datetime import datetime
    from fastapi.testclient import TestClient
    import app.main as main_module
    from app.main import app
    from app.db import SessionLocal, init_db
    from app.models import Source, SourceItem, InsightCard, CardStatus, SourceType

    init_db()
    print("[OK] Database initialized")

    client = TestClient(app)

    # Sync sources to DB so we have a valid source_key
    from app.sources import sync_sources_config_to_db
    db = SessionLocal()
    try:
        sync_sources_config_to_db(db, force_reload=True)
    finally:
        db.close()

    print("=" * 60)
    print("V0.3.2 SourceItem Compile Acceptance")
    print("=" * 60)

    passed = True

    # --- Setup: create or find a SourceItem ---
    db = SessionLocal()
    try:
        if args.use_existing_item:
            # Find an existing discovered SourceItem
            query = db.query(SourceItem).filter(SourceItem.status == "discovered")
            if args.source_key:
                query = query.filter(SourceItem.source_key == args.source_key)
            item = query.first()
            if not item:
                print("[FAIL] No discovered SourceItem found. Run acceptance_probe_sources.py first.")
                return 1
            print(f"[INFO] Using existing SourceItem id={item.id}, source_key={item.source_key}")
        else:
            # Create a test Source and SourceItem
            test_key = f"test_compile_{uuid.uuid4().hex[:8]}"
            src = Source(
                source_key=test_key,
                name="Test Compile Source",
                description="Test source for compile acceptance",
                source_type="html_index",
                homepage_url="https://example.com",
                feed_url=None,
                category="research",
                tags_json='[]',
                enabled=True,
                fetch_strategy="html_index",
                relevance_hint="",
                fetch_interval_hours=24,
            )
            db.add(src)
            db.commit()
            db.refresh(src)

            item = SourceItem(
                source_id=src.id,
                source_key=test_key,
                url="https://example.com/test-article",
                title="Test Article for Compilation",
                status="discovered",
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            print(f"[INFO] Created test SourceItem id={item.id}, source_key={test_key}")

        item_id = item.id

        # Save original compile_url
        original_compile_url = main_module.compile_url

        # Determine mock strategy
        if args.mock_success:
            def fake_compile_url_success(db_session, url):
                card = InsightCard(
                    source_url=url,
                    source_type=SourceType.HTML,
                    source_title="Mock Compiled Card",
                    content_hash="mock-hash-success",
                    status=CardStatus.COMPLETED,
                    summary_zh="Mock summary",
                    relevance_score=85,
                )
                db_session.add(card)
                db_session.commit()
                db_session.refresh(card)
                return card

            main_module.compile_url = fake_compile_url_success
            print("[INFO] Mock mode: success")

        elif args.mock_failed:
            def fake_compile_url_failed(db_session, url):
                card = InsightCard(
                    source_url=url,
                    source_type=SourceType.HTML,
                    source_title="Mock Failed Card",
                    content_hash="mock-hash-failed",
                    status=CardStatus.FAILED,
                    error_message="Mock API key missing",
                )
                db_session.add(card)
                db_session.commit()
                db_session.refresh(card)
                return card

            main_module.compile_url = fake_compile_url_failed
            print("[INFO] Mock mode: failed")

        try:
            # --- Test 1: First compile ---
            print(f"\n[1] First POST /source-items/{item_id}/compile...")
            response = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
            assert response.status_code == 303, f"Expected 303, got {response.status_code}"
            location = response.headers.get("location", "")
            assert f"/source-items/{item_id}" in location, f"Expected redirect to /source-items/{item_id}, got {location}"
            print(f"     [OK] Redirected to {location}")

            # Re-query item
            db.expire_all()
            item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            card_id_after_first = item.insight_card_id

            if args.mock_success:
                if item.status != "compiled":
                    print(f"  [FAIL] Expected status='compiled', got '{item.status}'")
                    passed = False
                else:
                    print(f"  [OK] status='compiled'")
                if item.insight_card_id is None:
                    print(f"  [FAIL] insight_card_id is None")
                    passed = False
                else:
                    print(f"  [OK] insight_card_id={item.insight_card_id}")
                if item.error_message is not None:
                    print(f"  [FAIL] error_message should be None, got '{item.error_message}'")
                    passed = False
                else:
                    print(f"  [OK] error_message=None")

            elif args.mock_failed:
                if item.status != "failed":
                    print(f"  [FAIL] Expected status='failed', got '{item.status}'")
                    passed = False
                else:
                    print(f"  [OK] status='failed'")
                if item.insight_card_id is None:
                    print(f"  [FAIL] insight_card_id is None (should be set even for failed)")
                    passed = False
                else:
                    print(f"  [OK] insight_card_id={item.insight_card_id}")
                if not item.error_message:
                    print(f"  [FAIL] error_message should be set for failed card")
                    passed = False
                else:
                    print(f"  [OK] error_message={item.error_message[:60]}")

            # --- Test 2: Idempotency — second POST on already compiled ---
            print(f"\n[2] Second POST /source-items/{item_id}/compile (idempotency)...")
            call_count = [0]
            original_for_count = main_module.compile_url

            def counting_wrapper(db_session, url):
                call_count[0] += 1
                return original_for_count(db_session, url)

            if args.mock_success:
                main_module.compile_url = counting_wrapper

            response2 = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
            assert response2.status_code == 303
            print(f"     [OK] Redirected (no re-compile)")

            db.expire_all()
            item2 = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            if args.mock_success:
                if call_count[0] > 0:
                    print(f"  [FAIL] compile_url was called {call_count[0]} times on already-compiled item")
                    passed = False
                else:
                    print(f"  [OK] compile_url was NOT called (idempotent)")
                if item2.insight_card_id != card_id_after_first:
                    print(f"  [FAIL] insight_card_id changed: {card_id_after_first} -> {item2.insight_card_id}")
                    passed = False
                else:
                    print(f"  [OK] insight_card_id unchanged")
                if item2.status != "compiled":
                    print(f"  [FAIL] status changed from compiled")
                    passed = False
                else:
                    print(f"  [OK] status still 'compiled'")

            # --- Test 3: Failed item retry (if we did mock-success first) ---
            if args.mock_success:
                # Mark item as failed to test retry
                print(f"\n[3] Testing failed item retry...")
                item.status = "failed"
                item.error_message = "Previous error"
                db.commit()
                db.expire_all()

                def fake_compile_url_success_2(db_session, url):
                    card = InsightCard(
                        source_url=url,
                        source_type=SourceType.HTML,
                        source_title="Retry Success Card",
                        content_hash="mock-hash-retry",
                        status=CardStatus.COMPLETED,
                        summary_zh="Retry summary",
                        relevance_score=90,
                    )
                    db_session.add(card)
                    db_session.commit()
                    db_session.refresh(card)
                    return card

                main_module.compile_url = fake_compile_url_success_2

                response3 = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
                assert response3.status_code == 303

                db.expire_all()
                item3 = db.query(SourceItem).filter(SourceItem.id == item_id).first()
                if item3.status != "compiled":
                    print(f"  [FAIL] After retry, expected status='compiled', got '{item3.status}'")
                    passed = False
                else:
                    print(f"  [OK] After retry, status='compiled'")
                if item3.error_message is not None:
                    print(f"  [FAIL] After retry, error_message should be cleared, got '{item3.error_message}'")
                    passed = False
                else:
                    print(f"  [OK] After retry, error_message cleared")
                if item3.insight_card_id is None:
                    print(f"  [FAIL] After retry, insight_card_id should be set")
                    passed = False
                else:
                    print(f"  [OK] After retry, insight_card_id={item3.insight_card_id}")

        finally:
            main_module.compile_url = original_compile_url

    finally:
        db.close()

    # Cleanup isolated DB
    if isolated_db_path and not args.keep_db:
        try:
            os.remove(isolated_db_path)
            print(f"\n[INFO] Cleaned up isolated DB: {isolated_db_path}")
        except OSError:
            print(f"\n[WARN] Could not remove isolated DB: {isolated_db_path}")

    print()
    if passed:
        print("[PASS] ACCEPTANCE PASSED")
        return 0
    else:
        print("[FAIL] ACCEPTANCE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
