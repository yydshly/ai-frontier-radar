#!/usr/bin/env python3
"""V1.0-alpha acceptance script for demo flow page guidance.

Validates:
    1. GET / renders "推荐主流程" section
    2. GET /source-items renders "主流程第 2 步" notice
    3. GET /source-items/{id} renders next-step hint based on status
    4. GET /cards renders workbench description
    5. GET /cards/{id} renders main flow guidance, bilingual notice, decision notice
    6. GET /cards/{id}/export-report renders full report preview
    7. GET /cards/{id}/export-markdown renders markdown task

Usage:
    python scripts/acceptance_demo_flow.py --isolated-db
    python scripts/acceptance_demo_flow.py --isolated-db --keep-db
"""
import argparse
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V1.0-alpha demo flow acceptance test (isolated DB)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_v10_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    """Run the V1.0-alpha demo flow acceptance in a clean isolated DB."""
    from app.db import SessionLocal, init_db
    from app.models import (
        InsightCard,
        CardStatus,
        SourceType,
        CardDecision,
        InsightCardBilingualReport,
        Source,
        SourceItem,
    )

    print("=" * 60)
    print("V1.0-alpha Demo Flow Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    created_ids = {"cards": [], "source_items": [], "decisions": [], "sources": []}
    try:
        # 1. Create a Source
        source = Source(
            source_key="test_v10_demo",
            name="Test V1.0 Demo Source",
            description="For V1.0-alpha demo flow acceptance",
            source_type="rss",
            category="company",
            fetch_strategy="rss",
            relevance_hint="test",
            enabled=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        created_ids["sources"].append(source.id)
        print(f"[OK] Created Source(id={source.id}, source_key=test_v10_demo)")

        # 2. Create a discovered SourceItem
        source_item = SourceItem(
            source_id=source.id,
            source_key="test_v10_demo",
            url="https://example.com/v10-demo-article",
            title="V1.0 Demo Test Article",
            status="discovered",
        )
        db.add(source_item)
        db.commit()
        db.refresh(source_item)
        source_item_id = source_item.id
        created_ids["source_items"].append(source_item_id)
        print(f"[OK] Created SourceItem(id={source_item_id}, status=discovered)")

        # 3. Create a completed InsightCard
        card = InsightCard(
            source_url="https://example.com/v10-demo-article",
            source_type=SourceType.HTML,
            source_title="V1.0 Demo Test Article",
            source_author="Demo Author",
            content_hash="v10-demo-hash",
            status=CardStatus.COMPLETED,
            summary_zh="这是 V1.0-alpha 演示流程测试卡片的中文摘要。",
            key_points_zh='["关键事实 1", "关键事实 2"]',
            technical_insights_zh='["技术洞察 1"]',
            product_opportunities_zh='["产品机会 1"]',
            risks_zh='["风险 1"]',
            action_items_zh='["行动建议 1"]',
            relevance_score=85,
            relevance_reasons_zh='["理由 1"]',
            related_user_directions='["AI 产品"]',
            model_name="acceptance-stub",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id
        created_ids["cards"].append(card_id)
        print(f"[OK] Created InsightCard(id={card_id}, status=completed)")

        # 4. Link SourceItem to the card
        source_item.insight_card_id = card_id
        source_item.status = "compiled"
        db.commit()
        print(f"[OK] Linked SourceItem(id={source_item_id}) to InsightCard(id={card_id})")

        # 5. Create a CardDecision(decision="to_action")
        decision = CardDecision(
            card_id=card_id,
            decision="to_action",
            note="V1.0-alpha 测试备注",
        )
        db.add(decision)
        db.commit()
        decision_id = decision.id
        created_ids["decisions"].append(decision_id)
        print(f"[OK] Created CardDecision(id={decision_id}, decision=to_action)")

        # 6. Create an InsightCardBilingualReport
        bilingual_report = InsightCardBilingualReport(
            card_id=card_id,
            english_core_summary="This is a test article for V1.0-alpha demo flow validation.",
            english_key_claims_json=json.dumps([
                "This is a key claim from the test article.",
            ]),
            english_evidence_points_json=json.dumps([
                "Evidence point from the test article.",
            ]),
            key_terms_json=json.dumps([
                {"en": "demo", "zh": "演示", "note_zh": "测试用术语"},
            ]),
            chinese_explanation="这是 V1.0-alpha 演示流程的中文解说。",
            fidelity_notes_zh="【保真提示】本文档用于验收测试。",
            interpretation_boundary_zh="【解读边界】本报告为测试数据。",
        )
        db.add(bilingual_report)
        db.commit()
        print(f"[OK] Created InsightCardBilingualReport(card_id={card_id})")

        # 7. TestClient
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # ── 8. GET / ────────────────────────────────────────────
        print("\n--- Step 1: GET / ---")
        response = client.get("/")
        assert response.status_code == 200, \
            f"GET / failed: {response.status_code}"
        text = response.text

        checks_index = [
            ("推荐主流程", "推荐主流程 section"),
            ("待编译资料", "待编译资料 link in flow"),
            ("中文 InsightCard", "中文 InsightCard text in flow"),
            ("中英双语核心理解", "bilingual report text in flow"),
            ("转成行动", "转成行动 text in flow"),
            ("导出完整 Markdown 报告", "export full report text in flow"),
            ("工作台概览", "工作台概览 section"),
            ("下一步建议", "下一步建议 section"),
        ]

        for check_text, description in checks_index:
            assert check_text in text, \
                f"Missing on index: {description} ('{check_text}')"
            print(f"[OK] Found on index: {description}")

        # ── 9. GET /source-items ────────────────────────────────
        print("\n--- Step 2: GET /source-items ---")
        response = client.get("/source-items")
        assert response.status_code == 200, \
            f"GET /source-items failed: {response.status_code}"
        text = response.text

        checks_si = [
            ("主流程第 2 步", "主流程第 2 步 notice"),
            ("编译为中文 InsightCard", "compile to InsightCard text"),
            ("编译为 InsightCard", "compile to InsightCard text variant"),
        ]

        for check_text, description in checks_si:
            assert check_text in text, \
                f"Missing on /source-items: {description} ('{check_text}')"
            print(f"[OK] Found on /source-items: {description}")

        # ── 10. GET /source-items/{id} ─────────────────────────
        print(f"\n--- Step 3: GET /source-items/{source_item_id} ---")
        response = client.get(f"/source-items/{source_item_id}")
        assert response.status_code == 200, \
            f"GET /source-items/{source_item_id} failed: {response.status_code}"
        text = response.text

        # Since the item is now 'compiled', should show "compiled" next-step
        checks_sid = [
            ("下一步", "下一步 hint"),
            ("关联 InsightCard", "关联 InsightCard text"),
        ]

        for check_text, description in checks_sid:
            assert check_text in text, \
                f"Missing on /source-items/{source_item_id}: {description} ('{check_text}')"
            print(f"[OK] Found on /source-items/{source_item_id}: {description}")

        # ── 11. GET /cards ─────────────────────────────────────
        print("\n--- Step 4: GET /cards ---")
        response = client.get("/cards")
        assert response.status_code == 200, \
            f"GET /cards failed: {response.status_code}"
        text = response.text

        checks_cards = [
            ("中文洞察卡工作台", "中文洞察卡工作台 heading"),
            ("完整报告", "完整报告 link"),
        ]

        for check_text, description in checks_cards:
            assert check_text in text, \
                f"Missing on /cards: {description} ('{check_text}')"
            print(f"[OK] Found on /cards: {description}")

        # ── 12. GET /cards/{id} ────────────────────────────────
        print(f"\n--- Step 5: GET /cards/{card_id} ---")
        response = client.get(f"/cards/{card_id}")
        assert response.status_code == 200, \
            f"GET /cards/{card_id} failed: {response.status_code}"
        text = response.text

        checks_card_detail = [
            ("中英双语核心理解", "中英双语核心理解 section"),
            ("看完后的判断", "看完后的判断 section"),
            ("导出完整 Markdown 报告", "export full report button"),
            ("导出为 Markdown 任务", "export markdown task button (to_action case)"),
            ("预览 Markdown 任务草稿", "preview markdown task draft button (non to_action case)"),
            ("判断不是模型做的", "decision guidance notice"),
        ]

        # Verify at least one of the export markdown variants is present
        has_export_markdown = "导出为 Markdown 任务" in text or "预览 Markdown 任务草稿" in text
        assert has_export_markdown, \
            f"Missing export markdown button on /cards/{card_id}"
        print(f"[OK] Found export markdown button on /cards/{card_id}")

        for check_text, description in checks_card_detail:
            # Skip the conditional export markdown checks (handled separately above)
            if "button (to_action case)" in description or "button (non to_action case)" in description:
                continue
            assert check_text in text, \
                f"Missing on /cards/{card_id}: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{card_id}: {description}")

        # ── 13. GET /cards/{id}/export-report ──────────────────
        print(f"\n--- Step 6: GET /cards/{card_id}/export-report ---")
        response = client.get(f"/cards/{card_id}/export-report")
        assert response.status_code == 200, \
            f"GET /cards/{card_id}/export-report failed: {response.status_code}"
        text = response.text

        checks_export_report = [
            ("完整 Markdown 报告预览", "完整 Markdown 报告预览 heading"),
        ]

        for check_text, description in checks_export_report:
            assert check_text in text, \
                f"Missing on /cards/{card_id}/export-report: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{card_id}/export-report: {description}")

        # ── 14. GET /cards/{id}/export-markdown ────────────────
        print(f"\n--- Step 7: GET /cards/{card_id}/export-markdown ---")
        response = client.get(f"/cards/{card_id}/export-markdown")
        assert response.status_code == 200, \
            f"GET /cards/{card_id}/export-markdown failed: {response.status_code}"
        text = response.text

        checks_export_md = [
            ("Markdown 任务", "Markdown 任务 heading"),
        ]

        for check_text, description in checks_export_md:
            assert check_text in text, \
                f"Missing on /cards/{card_id}/export-markdown: {description} ('{check_text}')"
            print(f"[OK] Found on /cards/{card_id}/export-markdown: {description}")

        print("\n" + "=" * 60)
        print("[PASS] ACCEPTANCE PASSED")
        print("=" * 60)

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
        if created_ids["sources"]:
            db.query(Source).filter(
                Source.id.in_(created_ids["sources"])
            ).delete(synchronize_session=False)
        db.commit()
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v10_{timestamp}.db"
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
            pass  # Engine may not be imported in this context

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
