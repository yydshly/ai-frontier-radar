#!/usr/bin/env python3
"""V0.9 acceptance script for InsightCard → Full Bilingual Markdown Report export.

Validates the end-to-end flow:
    1. Create a completed InsightCard in an isolated DB
    2. Optionally create a CardDecision
    3. Optionally create an InsightCardBilingualReport
    4. GET /cards/{id}/export-report — verify preview page renders
    5. GET /cards/{id}/export-report/download — verify .md file download
    6. Print ACCEPTANCE PASSED

Usage:
    python scripts/acceptance_export_full_report.py --isolated-db --with-bilingual
    python scripts/acceptance_export_full_report.py --isolated-db --without-bilingual
    python scripts/acceptance_export_full_report.py --isolated-db --with-bilingual --keep-db
"""
import argparse
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.9 Full Markdown Report export acceptance test (isolated DB)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_v09_<ts>.db).",
    )
    parser.add_argument(
        "--with-bilingual",
        action="store_true",
        default=True,
        help="Include bilingual report in test (default: True).",
    )
    parser.add_argument(
        "--without-bilingual",
        action="store_true",
        help="Test without bilingual report.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    """Run the V0.9 full report export acceptance in a clean isolated DB."""
    from app.db import SessionLocal, init_db
    from app.models import (
        InsightCard,
        CardStatus,
        SourceType,
        CardDecision,
        InsightCardBilingualReport,
    )

    print("=" * 60)
    print("V0.9 Full Markdown Report Export Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    card_id = None
    try:
        # 1. Create a completed InsightCard
        card = InsightCard(
            source_url="https://example.com/v09-acceptance-article",
            source_type=SourceType.HTML,
            source_title="V0.9 Acceptance Test Article",
            source_author="Acceptance Tester",
            content_hash="v09-acceptance-hash",
            status=CardStatus.COMPLETED,
            summary_zh="这是一张用于 V0.9 验收的中文摘要。",
            key_points_zh='["关键事实 1", "关键事实 2", "关键事实 3"]',
            technical_insights_zh='["技术洞察 1", "技术洞察 2"]',
            product_opportunities_zh='["产品机会 1"]',
            risks_zh='["风险 1"]',
            action_items_zh='["行动建议 1", "行动建议 2"]',
            relevance_score=85,
            relevance_reasons_zh='["理由 1", "理由 2"]',
            related_user_directions='["AI 产品开发", "大语言模型应用"]',
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
            note="这是一篇值得深入研究的文章",
        )
        db.add(decision_row)
        db.commit()
        print(f"[OK] Created CardDecision(card_id={card_id}, decision=to_action)")

        # 3. Optionally create bilingual report
        if not args.without_bilingual:
            import json
            bilingual_report = InsightCardBilingualReport(
                card_id=card_id,
                english_core_summary="This article discusses a breakthrough in AI agent frameworks "
                                    "for enterprise document processing, enabling more reliable "
                                    "and interpretable automation workflows.",
                english_key_claims_json=json.dumps([
                    "The article presents a new agent workflow framework.",
                    "The framework targets enterprise document processing.",
                    "Multiple specialized agents coordinate for extraction.",
                ]),
                english_evidence_points_json=json.dumps([
                    "Audit logs are provided for compliance.",
                    "Human oversight is maintained for high-risk decisions.",
                ]),
                key_terms_json=json.dumps([
                    {"en": "agentic workflow", "zh": "智能体工作流", "note_zh": "多步骤AI协作流程"},
                    {"en": "document processing", "zh": "文档处理", "note_zh": "企业文档自动化处理"},
                ]),
                chinese_explanation="这篇关于企业文档处理智能体框架的文章介绍了人工智能在自动化文档分析方面的新进展。",
                fidelity_notes_zh="【保真提示】英文核心摘要和主张列表均来自原文所述。",
                interpretation_boundary_zh="【解读边界】产品机会和行动建议属于模型推论，不等于原文结论。",
            )
            db.add(bilingual_report)
            db.commit()
            print(f"[OK] Created InsightCardBilingualReport(card_id={card_id})")

        # 4. TestClient
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # 5. GET /cards/{id}/export-report — verify preview page renders
        response = client.get(f"/cards/{card_id}/export-report")
        assert response.status_code == 200, \
            f"GET /cards/{card_id}/export-report failed: {response.status_code}"
        text = response.text
        assert "完整报告预览" in text, \
            "Preview page should contain '完整报告预览'"
        assert "英文核心摘要" in text or "English Core Summary" in text, \
            "Preview should mention English Core Summary"
        assert "中文解说" in text, \
            "Preview should mention '中文解说'"
        assert "保真提示" in text, \
            "Preview should mention '保真提示'"
        assert "解读边界" in text, \
            "Preview should mention '解读边界'"
        assert "AI 前沿资料编译报告" in text, \
            "Preview should contain report heading"
        assert "原文链接" in text, \
            "Preview should contain '原文链接'"
        print(f"[OK] GET /cards/{card_id}/export-report — preview renders correctly")

        # 6. GET /cards/{id}/export-report/download — verify file download
        response = client.get(f"/cards/{card_id}/export-report/download")
        assert response.status_code == 200, \
            f"GET /cards/{card_id}/export-report/download failed: {response.status_code}"
        assert "attachment" in response.headers.get("Content-Disposition", ""), \
            "Content-Disposition should contain 'attachment'"
        expected_filename = f"insightcard-{card_id}-report.md"
        assert expected_filename in response.headers.get("Content-Disposition", ""), \
            f"Filename should be {expected_filename}"
        download_text = response.text

        # Common sections that should appear regardless of bilingual report
        assert "AI 前沿资料编译报告" in download_text, \
            "Download should contain report heading"
        assert "原文信息" in download_text, \
            "Download should contain '原文信息'"
        assert "中文摘要" in download_text, \
            "Download should contain '中文摘要'"
        assert "关键事实" in download_text, \
            "Download should contain '关键事实'"
        assert "技术洞察" in download_text, \
            "Download should contain '技术洞察'"
        assert "产品机会" in download_text, \
            "Download should contain '产品机会'"
        assert "风险与注意事项" in download_text, \
            "Download should contain '风险与注意事项'"
        assert "行动建议" in download_text, \
            "Download should contain '行动建议'"
        assert "相关性判断" in download_text, \
            "Download should contain '相关性判断'"
        assert "用户判断" in download_text, \
            "Download should contain '用户判断'"
        assert "后续可继续追问的问题" in download_text, \
            "Download should contain '后续可继续追问的问题'"

        if args.without_bilingual:
            # Without bilingual report, should show placeholder text
            assert "暂无中英双语报告" in download_text, \
                "Download should show '暂无中英双语报告' when no bilingual report"
            # English sections should show placeholder
            assert "English Core Summary" in download_text, \
                "Download should contain English Core Summary section header"
        else:
            # With bilingual report, should contain English content
            assert "This article discusses" in download_text or "English Core Summary" in download_text, \
                "Download should contain English content from bilingual report"
            assert "Original Key Claims" in download_text, \
                "Download should contain 'Original Key Claims'"
            assert "Key Evidence Points" in download_text, \
                "Download should contain 'Key Evidence Points'"
            assert "Key Terms EN-ZH" in download_text, \
                "Download should contain 'Key Terms EN-ZH'"
            assert "【保真提示】" in download_text, \
                "Download should contain fidelity notes from bilingual report"
            assert "【解读边界】" in download_text, \
                "Download should contain interpretation boundary from bilingual report"

        print(
            f"[OK] GET /cards/{card_id}/export-report/download "
            f"— file ({expected_filename}) downloads correctly"
        )

        # 7. Test that non-existent card redirects
        response = client.get("/cards/99999/export-report", follow_redirects=False)
        assert response.status_code in (302, 303), \
            "Non-existent card should redirect"
        print("[OK] Non-existent card redirects gracefully")

    finally:
        db.close()

    return card_id


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.without_bilingual:
        args.with_bilingual = False

    # Handle --isolated-db BEFORE importing app.db
    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v09_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    mode = "with-bilingual" if args.with_bilingual else "without-bilingual"
    print(f"[INFO] Mode: {mode}")

    card_id = _run_acceptance(args)
    print(f"\n[OK] V0.9 export acceptance PASSED for InsightCard(id={card_id})")

    # Cleanup isolated DB if not --keep-db
    if isolated_db_path and not args.keep_db:
        import shutil
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
