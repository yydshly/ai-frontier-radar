#!/usr/bin/env python3
"""V0.8 bilingual report acceptance script.

Validates the bilingual InsightCard report feature:
- card_detail page shows bilingual report section
- bilingual report can be generated via POST
- Markdown export includes bilingual content
- Quality inspection works

NOTE: This script validates the mock bilingual report workflow only.
For real LLM output quality validation, run:
    python scripts/acceptance_real_bilingual_report.py --isolated-db --real

Usage:
    # Mock mode (default, validates without real LLM)
    python scripts/acceptance_bilingual_report.py --isolated-db --mock

    # Keep isolated DB after run
    python scripts/acceptance_bilingual_report.py --isolated-db --mock --keep-db
"""
import argparse
import json
import os
import sys
import time

# Fix Unicode output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal, init_db
from app.models import InsightCard, CardStatus, SourceType, InsightCardBilingualReport
from app.services.insight_quality import inspect_bilingual_report_quality
from app.services.bilingual_report import build_mock_bilingual_report, upsert_bilingual_report


client = TestClient(app)


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.8 bilingual report acceptance."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after run.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock LLM (default for --isolated-db).",
    )
    return parser


def _run_acceptance(args):
    print("=" * 60)
    print("V0.8 Bilingual Report Acceptance")
    print("=" * 60)

    use_mock = args.mock or True  # Default to mock mode

    if use_mock:
        print("\n[!] Mode: MOCK (no real LLM)")
    else:
        print("\n[!] Mode: REAL LLM")

    # Set env to use isolated DB if requested
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v08_bilingual_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    results = {"passed": True, "errors": []}

    try:
        # Step 1: Create a completed InsightCard
        print("\n[1] Creating completed InsightCard...")
        card = InsightCard(
            source_url="https://example.com/test-article",
            source_type=SourceType.HTML,
            source_title="Test AI Article: Advancements in Agentic AI",
            source_author="Test Author",
            source_published_at="2025-01-15",
            content_hash="test-hash-bilingual",
            cleaned_text_preview=(
                "This article discusses the latest advancements in agentic AI systems. "
                "The research team has developed new techniques for multi-step reasoning. "
                "Key improvements include better tool use and planning capabilities. "
                "Benchmarks show 25% improvement over previous methods."
            ),
            status=CardStatus.COMPLETED,
            summary_zh="本文介绍了智能体AI系统的最新进展，研究团队开发了多步推理的新技术。",
            key_points_zh=json.dumps([
                "智能体AI系统取得重大进展",
                "多步推理能力显著提升",
                "工具使用和规划能力增强",
                "基准测试提升25%",
                "新方法具有良好的可扩展性"
            ], ensure_ascii=False),
            technical_insights_zh=json.dumps([
                "采用新型注意力机制",
                "结合外部工具调用",
                "支持多步骤任务规划"
            ], ensure_ascii=False),
            product_opportunities_zh=json.dumps([
                "开发更智能的个人助理",
                "自动化复杂工作流程",
                "提升开发工具能力"
            ], ensure_ascii=False),
            risks_zh=json.dumps([
                "技术落地需要时间验证",
                "安全性需要进一步评估"
            ], ensure_ascii=False),
            action_items_zh=json.dumps([
                "调研智能体AI最新进展",
                "评估现有产品改进空间",
                "制定技术跟进计划"
            ], ensure_ascii=False),
            relevance_score=85,
            relevance_reasons_zh=json.dumps([
                "与AI Agent发展方向高度相关",
                "有实际产品落地可能"
            ], ensure_ascii=False),
            related_user_directions=json.dumps([
                "AI Agent",
                "LLM应用",
                "智能助手"
            ], ensure_ascii=False),
            model_name="test-model",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        print(f"    Created card_id={card.id}")

        # Step 2: Generate mock bilingual report
        print("\n[2] Generating mock bilingual report...")
        if use_mock:
            report_data = build_mock_bilingual_report(card)
        else:
            # Real mode would call LLM here
            report_data = build_mock_bilingual_report(card)
            print("    [WARN] Real LLM not implemented, using mock")

        # Step 3: Upsert bilingual report
        print("\n[3] Upserting bilingual report...")
        report = upsert_bilingual_report(db, card, report_data)
        print(f"    Created report_id={report.id}, card_id={report.card_id}")

        # Step 4: GET /cards/{id} and verify page content
        print("\n[4] Verifying card_detail page content...")
        response = client.get(f"/cards/{card.id}")
        assert response.status_code == 200, f"card_detail returned {response.status_code}"

        page_text = response.text

        checks = [
            ("中英双语核心理解", "Bilingual section header"),
            ("English Core Summary", "English core summary label"),
            ("Original Key Claims", "Original key claims label"),
            ("中文解说", "Chinese explanation label"),
            ("保真提示", "Fidelity notes label"),
            ("解读边界", "Interpretation boundary label"),
            ("english-text", "English text class"),
            ("生成中英双语报告" not in page_text or "重新生成" in page_text,
             "Should show regenerate button (not generate button)"),
        ]

        for check_content, label in checks:
            if isinstance(check_content, bool):
                passed = check_content
            else:
                passed = check_content in page_text
            status = "✅" if passed else "❌"
            print(f"    {status} {label}")
            if not passed:
                results["passed"] = False
                results["errors"].append(f"Page missing: {label}")

        # Step 5: Inspect bilingual report quality
        print("\n[5] Inspecting bilingual report quality...")
        db.refresh(report)
        quality_result = inspect_bilingual_report_quality(report)
        print(f"    english_summary_present: {quality_result['english_summary_present']}")
        print(f"    english_key_claims_count: {quality_result['english_key_claims_count']}")
        print(f"    chinese_explanation_present: {quality_result['chinese_explanation_present']}")
        print(f"    fidelity_notes_present: {quality_result['fidelity_notes_present']}")
        print(f"    interpretation_boundary_present: {quality_result['interpretation_boundary_present']}")
        print(f"    passed_minimum_quality: {quality_result['passed_minimum_quality']}")

        if not quality_result["passed_minimum_quality"]:
            results["passed"] = False
            results["errors"].append(f"Quality check failed: {quality_result['warnings']}")

        # Step 6: GET /cards/{id}/export-markdown and verify content
        print("\n[6] Verifying Markdown export content...")
        response = client.get(f"/cards/{card.id}/export-markdown")
        assert response.status_code == 200, f"export-markdown returned {response.status_code}"

        markdown_text = response.text

        md_checks = [
            ("English Core Summary", "English Core Summary in Markdown"),
            ("Original Key Claims", "Original Key Claims in Markdown"),
            ("中文解说", "Chinese explanation in Markdown"),
            ("保真提示与解读边界" in markdown_text or "保真提示" in markdown_text,
             "Fidelity notes in Markdown"),
            ("暂无双语报告" not in markdown_text, "Should NOT show '暂无双语报告'"),
        ]

        for check_content, label in md_checks:
            if isinstance(check_content, bool):
                passed = check_content
            else:
                passed = check_content in markdown_text
            status = "✅" if passed else "❌"
            print(f"    {status} {label}")
            if not passed:
                results["passed"] = False
                results["errors"].append(f"Markdown missing: {label}")

        # Step 7: Verify bilingual report has no parse error
        print("\n[7] Verifying report data integrity...")
        assert report.english_core_summary, "english_core_summary should not be empty"
        assert report.chinese_explanation, "chinese_explanation should not be empty"
        assert report.fidelity_notes_zh, "fidelity_notes_zh should not be empty"
        assert report.interpretation_boundary_zh, "interpretation_boundary_zh should not be empty"
        print("    ✅ All required fields are non-empty")

        # Step 8: Test upsert behavior (re-generate updates, not insert)
        print("\n[8] Testing upsert behavior...")
        initial_report_id = report.id
        report2 = upsert_bilingual_report(db, card, report_data)
        assert report2.id == initial_report_id, "Upsert should update, not insert"
        print(f"    ✅ Upsert correctly updated existing report (id={report2.id})")

    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

    return results


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    result = _run_acceptance(args)

    print()
    if result["passed"]:
        print("[PASS] ACCEPTANCE PASSED")
        return 0
    else:
        print("[FAIL] ACCEPTANCE FAILED")
        for error in result["errors"]:
            print(f"    - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
