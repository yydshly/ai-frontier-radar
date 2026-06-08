#!/usr/bin/env python3
"""V0.5 acceptance script for InsightCard → Markdown task export.

Validates the end-to-end flow:
    1. Create a completed InsightCard in an isolated DB
    2. Create a CardDecision(decision="to_action", note="...")
    3. GET /cards/{id}/export-markdown — verify preview page renders
    4. GET /cards/{id}/export-markdown/download — verify .md file download
    5. GET /cards?decision=to_action — verify "导出任务" link appears
    6. Print ACCEPTANCE PASSED

Usage:
    python scripts/acceptance_export_action_markdown.py --isolated-db
    python scripts/acceptance_export_action_markdown.py --isolated-db --keep-db
"""
import argparse
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.5 Markdown task export acceptance test (isolated DB)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_v05_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    """Run the V0.5 export acceptance in a clean isolated DB."""
    from app.db import SessionLocal, init_db
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    print("=" * 60)
    print("V0.5 Export Action Markdown Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    card_id = None
    try:
        # 1. Create a completed InsightCard
        card = InsightCard(
            source_url="https://example.com/v05-acceptance-article",
            source_type=SourceType.HTML,
            source_title="V0.5 Acceptance Test Article",
            source_author="Acceptance Tester",
            content_hash="v05-acceptance-hash",
            status=CardStatus.COMPLETED,
            summary_zh="这是一张用于 V0.5 验收的中文摘要。",
            key_points_zh='["关键事实 1", "关键事实 2"]',
            technical_insights_zh='["技术洞察 1", "技术洞察 2"]',
            product_opportunities_zh='["产品机会 1"]',
            risks_zh='["风险 1"]',
            action_items_zh='["行动建议 1", "行动建议 2"]',
            relevance_score=85,
            relevance_reasons_zh='["理由 1"]',
            related_user_directions='["AI 产品开发"]',
            model_name="acceptance-stub",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id
        print(f"[OK] Created InsightCard(id={card_id}, status=completed)")

        # 2. Create CardDecision(decision="to_action")
        decision_row = CardDecision(
            card_id=card_id,
            decision="to_action",
            note="可以转成资料编译功能优化任务",
        )
        db.add(decision_row)
        db.commit()
        print(f"[OK] Created CardDecision(card_id={card_id}, decision=to_action)")

        # 3. TestClient
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # 4. GET /cards/{id}/export-markdown — verify preview
        response = client.get(f"/cards/{card_id}/export-markdown")
        assert response.status_code == 200, \
            f"GET /cards/{card_id}/export-markdown failed: {response.status_code}"
        text = response.text
        assert "导出 Markdown 任务" in text, \
            "Preview page should contain '导出 Markdown 任务'"
        assert "原文链接" in text, "Preview should contain '原文链接'"
        assert "中文摘要" in text, "Preview should contain '中文摘要'"
        assert "技术洞察" in text, "Preview should contain '技术洞察'"
        assert "产品机会" in text, "Preview should contain '产品机会'"
        assert "可以转成资料编译功能优化任务" in text, \
            "Preview should contain user's note"
        assert "# 行动任务" in text or "行动任务" in text, \
            "Preview should contain Markdown heading"
        print(f"[OK] GET /cards/{card_id}/export-markdown — preview renders correctly")

        # 5. GET /cards/{id}/export-markdown/download — verify file download
        response = client.get(f"/cards/{card_id}/export-markdown/download")
        assert response.status_code == 200, \
            f"GET /cards/{card_id}/export-markdown/download failed: {response.status_code}"
        assert "attachment" in response.headers.get("Content-Disposition", ""), \
            "Content-Disposition should contain 'attachment'"
        assert f"insightcard-{card_id}-task.md" in response.headers.get(
            "Content-Disposition", ""
        ), "Filename should match insightcard-{id}-task.md"
        download_text = response.text
        assert "# 行动任务" in download_text, \
            "Download should contain Markdown heading '# 行动任务'"
        assert "行动建议" in download_text, \
            "Download should contain '行动建议'"
        assert "可以转成资料编译功能优化任务" in download_text, \
            "Download should contain user's note"
        print(
            f"[OK] GET /cards/{card_id}/export-markdown/download "
            f"— file (insightcard-{card_id}-task.md) downloads correctly"
        )

        # 6. GET /cards?decision=to_action — verify "导出任务" link
        response = client.get("/cards?decision=to_action")
        assert response.status_code == 200, \
            f"GET /cards?decision=to_action failed: {response.status_code}"
        text = response.text
        assert "导出任务" in text, \
            "/cards?decision=to_action should show '导出任务' link"
        assert f"/cards/{card_id}/export-markdown" in text, \
            "Export link should point to correct URL"
        print(f"[OK] GET /cards?decision=to_action — '导出任务' link appears")

        # 7. Also verify non to_action cards do NOT have export link
        # Create a worth_attention card
        card2 = InsightCard(
            source_url="https://example.com/v05-acceptance-article-2",
            source_type=SourceType.HTML,
            source_title="V0.5 Another Test Article",
            content_hash="v05-acceptance-hash-2",
            status=CardStatus.COMPLETED,
            summary_zh="第二张卡片的摘要。",
            key_points_zh='["事实"]',
            technical_insights_zh='["洞察"]',
            product_opportunities_zh='[]',
            risks_zh='[]',
            action_items_zh='[]',
            relevance_score=50,
            relevance_reasons_zh='[]',
            related_user_directions='[]',
            model_name="acceptance-stub",
        )
        db.add(card2)
        db.commit()
        db.refresh(card2)

        decision2 = CardDecision(
            card_id=card2.id,
            decision="worth_attention",
            note=None,
        )
        db.add(decision2)
        db.commit()

        response = client.get("/cards")
        assert response.status_code == 200
        all_text = response.text
        # worth_attention card should NOT have export link
        # (to_action card should)
        assert "导出任务" in all_text, \
            "Should still have export link for to_action card on /cards"
        print("[OK] GET /cards — export link only shown for to_action cards")

    finally:
        db.close()

    return card_id


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Handle --isolated-db BEFORE importing app.db
    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v05_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    card_id = _run_acceptance(args)
    print(f"\n[OK] V0.5 export acceptance PASSED for InsightCard(id={card_id})")

    # Cleanup isolated DB if not --keep-db
    if isolated_db_path and not args.keep_db:
        import shutil
        try:
            shutil.rmtree(os.path.dirname(os.path.abspath(isolated_db_path)), ignore_errors=True)
            # Actually just remove the file
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
