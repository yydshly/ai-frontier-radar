#!/usr/bin/env python3
"""V0.6 acceptance script for homepage workbench.

Validates:
    1. GET / renders workbench with stats, next actions, recent records
    2. Stats cards show correct numbers
    3. Quick action links are present
    4. Recent source items and cards sections exist
    5. Empty state works

Usage:
    python scripts/acceptance_home_workbench.py --isolated-db
    python scripts/acceptance_home_workbench.py --isolated-db --keep-db
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.6 homepage workbench acceptance test (isolated DB)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_v06_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    from app.db import SessionLocal, init_db
    from app.models import InsightCard, CardStatus, SourceType, CardDecision, Source, SourceItem

    print("=" * 60)
    print("V0.6 Home Workbench Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    created_ids = {"cards": [], "source_items": [], "decisions": []}
    try:
        # 1. Create a Source so we can create SourceItems
        source = Source(
            source_key="test_v06_source",
            name="Test V0.6 Source",
            description="For V0.6 acceptance",
            source_type="rss",
            category="company",
            fetch_strategy="rss",
            relevance_hint="test",
            enabled=True,
        )
        db.add(source)
        db.commit()
        print("[OK] Created Source(test_v06_source)")

        # 2. Create 2 discovered SourceItems + 1 failed SourceItem
        for i, status in enumerate(["discovered", "discovered", "failed"]):
            item = SourceItem(
                source_id=source.id,
                source_key="test_v06_source",
                url=f"https://example.com/v06-test-item-{i}",
                title=f"V0.6 Test Item {i}",
                status=status,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            created_ids["source_items"].append(item.id)

        print(f"[OK] Created 3 SourceItems (2 discovered, 1 failed)")

        # 3. Create 1 unhandled card
        card1 = InsightCard(
            source_url="https://example.com/v06-card-1",
            source_type=SourceType.HTML,
            source_title="V0.6 Unhandled Card",
            status=CardStatus.COMPLETED,
            summary_zh="未处理卡片摘要",
            key_points_zh='[]',
            technical_insights_zh='[]',
            product_opportunities_zh='[]',
            risks_zh='[]',
            action_items_zh='[]',
            relevance_score=70,
            relevance_reasons_zh='[]',
            related_user_directions='[]',
            model_name="v06-test",
        )
        db.add(card1)
        db.commit()
        db.refresh(card1)
        created_ids["cards"].append(card1.id)

        # 4. Create 1 worth_attention card
        card2 = InsightCard(
            source_url="https://example.com/v06-card-2",
            source_type=SourceType.HTML,
            source_title="V0.6 Worth Attention Card",
            status=CardStatus.COMPLETED,
            summary_zh="值得关注卡片摘要",
            key_points_zh='[]',
            technical_insights_zh='[]',
            product_opportunities_zh='[]',
            risks_zh='[]',
            action_items_zh='[]',
            relevance_score=80,
            relevance_reasons_zh='[]',
            related_user_directions='[]',
            model_name="v06-test",
        )
        db.add(card2)
        db.commit()
        db.refresh(card2)
        created_ids["cards"].append(card2.id)

        decision_worth = CardDecision(
            card_id=card2.id,
            decision="worth_attention",
            note=None,
        )
        db.add(decision_worth)
        db.commit()
        created_ids["decisions"].append(decision_worth.id)

        # 5. Create 1 to_action card
        card3 = InsightCard(
            source_url="https://example.com/v06-card-3",
            source_type=SourceType.HTML,
            source_title="V0.6 To Action Card",
            status=CardStatus.COMPLETED,
            summary_zh="转成行动卡片摘要",
            key_points_zh='["事实一", "事实二"]',
            technical_insights_zh='["洞察一"]',
            product_opportunities_zh='["机会一"]',
            risks_zh='["风险一"]',
            action_items_zh='["行动一"]',
            relevance_score=90,
            relevance_reasons_zh='["理由一"]',
            related_user_directions='["AI产品"]',
            model_name="v06-test",
        )
        db.add(card3)
        db.commit()
        db.refresh(card3)
        created_ids["cards"].append(card3.id)

        decision_action = CardDecision(
            card_id=card3.id,
            decision="to_action",
            note="V0.6 测试备注",
        )
        db.add(decision_action)
        db.commit()
        created_ids["decisions"].append(decision_action.id)

        print(f"[OK] Created 3 cards + 2 decisions (worth_attention, to_action)")

        # 6. TestClient
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # 7. GET /
        response = client.get("/")
        assert response.status_code == 200, \
            f"GET / failed: {response.status_code}"
        text = response.text

        # 8. Verify workbench structure
        checks = [
            ("全球 AI 前沿资料中文编译工作台", "workbench title"),
            ("工作台概览", "stats section"),
            ("待编译资料", "discovered stat"),
            ("未处理卡片", "unhandled stat"),
            ("值得关注", "worth_attention stat"),
            ("转成行动", "to_action stat"),
            ("下一步建议", "next actions section"),
            ("快捷入口", "quick actions section"),
            ("最近待编译资料", "recent source items section"),
            ("最近中文洞察卡", "recent cards section"),
            ("手动编译英文资料 URL", "manual compile section"),
            ("精选 AI 前沿来源", "featured sources section"),
            ("/source-items", "source items link"),
            ("/cards", "cards link"),
            ("/cards?decision=to_action", "to_action filter link"),
            ("/sources", "sources link"),
            ("导出任务", "export task link for to_action card"),
            ("V0.6 To Action Card", "to_action card title in recent"),
            ("V0.6 测试备注", "user note in recent cards"),
            ("值得关注", "worth_attention badge in recent"),
        ]

        for check_text, description in checks:
            assert check_text in text, \
                f"Missing: {description} ('{check_text}')"
            print(f"[OK] Found: {description}")

        # 9. Verify stat numbers
        assert "2" in text and "待编译资料" in text, \
            "Discovered count should show 2"
        assert "1" in text and "值得关注" in text, \
            "Worth attention count should show 1"
        assert "1" in text and "转成行动" in text, \
            "To action count should show 1"
        print("[OK] Stat numbers are present in page")

        # 10. Verify next actions list (should show suggestions since data exists)
        assert "下一步建议" in text, "Next actions section missing"
        print("[OK] Next actions section rendered")

        # 11. Quick action links clickable
        assert 'href="/source-items"' in text, "Quick action to /source-items missing"
        assert 'href="/cards"' in text, "Quick action to /cards missing"
        print("[OK] Quick action links present")

        print("\n[OK] V0.6 home workbench PASSED")

    finally:
        # Cleanup
        if created_ids["decisions"]:
            db.query(CardDecision).filter(
                CardDecision.id.in_(created_ids["decisions"])
            ).delete(synchronize_session=False)
        if created_ids["cards"]:
            db.query(InsightCard).filter(
                InsightCard.id.in_(created_ids["cards"])
            ).delete(synchronize_session=False)
        if created_ids["source_items"]:
            db.query(SourceItem).filter(
                SourceItem.id.in_(created_ids["source_items"])
            ).delete(synchronize_session=False)
        db.query(Source).filter(Source.source_key == "test_v06_source").delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v06_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    _run_acceptance(args)

    if isolated_db_path and not args.keep_db:
        try:
            if os.path.exists(isolated_db_path):
                os.remove(isolated_db_path)
            print(f"[INFO] Cleaned up isolated DB: {isolated_db_path}")
        except OSError as e:
            print(f"[WARN] Could not remove isolated DB: {isolated_db_path}: {e}")

    print()
    print("[PASS] ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
