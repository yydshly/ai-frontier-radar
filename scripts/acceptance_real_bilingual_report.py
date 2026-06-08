#!/usr/bin/env python3
"""V0.8.2 real LLM bilingual report acceptance script.

Validates real LLM output quality for bilingual reports:
- Calls real LLM (or uses mock) to generate a bilingual report
- Inspects language fidelity (English fields = English, Chinese fields = Chinese)
- Checks minimum quality bar

Usage:
    # Mock mode (validates workflow without real LLM)
    python scripts/acceptance_real_bilingual_report.py --isolated-db --mock

    # Real LLM mode (requires MINIMAX_API_KEY)
    python scripts/acceptance_real_bilingual_report.py --isolated-db --real

    # Use an existing card from local DB
    python scripts/acceptance_real_bilingual_report.py --card-id 1 --real

    # Keep isolated DB after run
    python scripts/acceptance_real_bilingual_report.py --isolated-db --real --keep-db
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Unicode output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.db import SessionLocal, init_db
from app.models import InsightCard, CardStatus, SourceType, InsightCardBilingualReport
from app.services.insight_quality import inspect_bilingual_report_quality
from app.services.bilingual_report import (
    build_bilingual_report_prompt,
    parse_bilingual_report_response,
    upsert_bilingual_report,
    build_mock_bilingual_report,
)
from app.llm.factory import create_llm_client


# Fixed English test text for real LLM mode (self-authored, no copyright concerns)
FIXTURE_ENGLISH_TEXT = (
    "Acme AI announced a new agent workflow framework for enterprise document processing. "
    "The framework coordinates multiple specialized agents for extraction, validation, and summarization. "
    "According to the announcement, the goal is to reduce manual review time while keeping human oversight "
    "for high-risk decisions. The release also emphasizes audit logs, evaluation datasets, "
    "and fallback procedures when agents disagree. "
    "The system is available via API starting next quarter."
)


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.8.2 real LLM bilingual report acceptance."
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
        help="Use mock LLM (validates workflow only).",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use real LLM to generate bilingual report.",
    )
    parser.add_argument(
        "--card-id",
        type=int,
        default=None,
        dest="card_id",
        help="Use an existing InsightCard from the DB.",
    )
    parser.add_argument(
        "--source-key",
        dest="source_key",
        default=None,
        help="Source key to filter existing cards by source_url (simplified).",
    )
    return parser


def _build_fixture_card() -> InsightCard:
    """Build a fixture InsightCard with English source text for real LLM testing."""
    return InsightCard(
        source_url="https://acme.ai/news/agent-workflow-framework",
        source_type=SourceType.HTML,
        source_title="Acme AI announces agent workflow framework",
        source_author="Acme AI Team",
        source_published_at="2025-01-15",
        content_hash="fixture-test-bilingual-v082",
        cleaned_text_preview=FIXTURE_ENGLISH_TEXT,
        status=CardStatus.COMPLETED,
        summary_zh="Acme AI 发布了一个面向企业文档处理的智能体工作流框架。",
        key_points_zh=json.dumps([
            "多智能体协作适合拆分抽取、校验和摘要任务",
            "审计日志和回退流程是企业场景关键要求",
        ], ensure_ascii=False),
        technical_insights_zh=json.dumps([
            "协调型多智能体工作流架构",
            "人工复核机制保留高风险决策人类把关",
        ], ensure_ascii=False),
        product_opportunities_zh=json.dumps([
            "可用于资料转换为知识产品的处理流水线",
            "可作为文档理解产品的质量控制模块",
        ], ensure_ascii=False),
        risks_zh=json.dumps([
            "多智能体协调复杂度高",
            "企业部署需要额外安全评估",
        ], ensure_ascii=False),
        action_items_zh=json.dumps([
            "整理多 Agent 文档处理流程",
            "评估现有项目是否需要审计日志和人工复核",
        ], ensure_ascii=False),
        relevance_score=80,
        relevance_reasons_zh=json.dumps([
            "与AI Agent发展方向相关",
            "有实际产品落地可能",
        ], ensure_ascii=False),
        related_user_directions=json.dumps([
            "AI Agent",
            "文档处理自动化",
        ], ensure_ascii=False),
        model_name="fixture-model",
    )


def _run_acceptance(args):
    print("=" * 60)
    print("V0.8.2 Real LLM Bilingual Report Acceptance")
    print("=" * 60)

    use_mock = args.mock or not args.real

    if use_mock:
        print("\n[!] Mode: MOCK (validates workflow only)")
    else:
        print("\n[!] Mode: REAL LLM")
        api_key = os.environ.get("MINIMAX_API_KEY", "")
        if not api_key:
            print("\n[SKIP] MINIMAX_API_KEY not set — cannot run real LLM mode.")
            print("       Set MINIMAX_API_KEY or use --mock")
            return {"passed": False, "skipped": True, "reason": "MINIMAX_API_KEY missing"}

    # Set up isolated DB if requested
    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v082_real_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    results = {"passed": True, "errors": [], "quality_result": None, "skipped": False}

    try:
        # Step 1: Get or create a card
        print("\n[1] Preparing InsightCard...")
        card = None

        if args.card_id is not None:
            # Use existing card from DB
            card = db.query(InsightCard).filter(InsightCard.id == args.card_id).first()
            if not card:
                print(f"    [FAIL] Card {args.card_id} not found in DB")
                results["passed"] = False
                results["errors"].append(f"Card {args.card_id} not found")
                return results
            print(f"    Using existing card_id={card.id}: {card.source_title}")
        elif args.source_key:
            # Find a card with matching source_url
            cards = (
                db.query(InsightCard)
                .filter(InsightCard.source_url.ilike(f"%{args.source_key}%"))
                .order_by(InsightCard.id.desc())
                .limit(1)
                .all()
            )
            if cards:
                card = cards[0]
                print(f"    Found card_id={card.id} matching source_key={args.source_key}")
            else:
                print(f"    [WARN] No card found matching source_key={args.source_key}, creating fixture")
                card = _build_fixture_card()
                db.add(card)
                db.commit()
                db.refresh(card)
                print(f"    Created fixture card_id={card.id}")
        else:
            # Create fixture card
            card = _build_fixture_card()
            db.add(card)
            db.commit()
            db.refresh(card)
            print(f"    Created fixture card_id={card.id}: {card.source_title}")

        # Step 2: Generate bilingual report
        print("\n[2] Generating bilingual report...")
        if use_mock:
            report_data = build_mock_bilingual_report(card)
            print("    Using mock report data")
        else:
            # Real LLM call
            prompt = build_bilingual_report_prompt(card, FIXTURE_ENGLISH_TEXT)
            print("    Calling real LLM...")
            try:
                client = create_llm_client()
                llm_result = client.generate_json(
                    system_prompt="You are a helpful assistant that outputs JSON.",
                    user_prompt=prompt,
                )
                # convert dict back to JSON string for parse_bilingual_report_response
                raw_response = json.dumps(llm_result)
                report_data = parse_bilingual_report_response(raw_response)

                if report_data.get("parse_error"):
                    print(f"    [FAIL] JSON parse error: {report_data['parse_error']}")
                    results["passed"] = False
                    results["errors"].append(f"JSON parse error: {report_data['parse_error']}")
                    return results

                print("    LLM response received and parsed")
            except Exception as e:
                print(f"    [FAIL] LLM call failed: {e}")
                results["passed"] = False
                results["errors"].append(f"LLM call failed: {e}")
                return results

        # Step 3: Upsert report
        print("\n[3] Upserting bilingual report...")
        report = upsert_bilingual_report(db, card, report_data)
        print(f"    Report id={report.id}, card_id={report.card_id}")

        # Step 4: Inspect quality
        print("\n[4] Inspecting bilingual report quality...")
        db.refresh(report)
        quality_result = inspect_bilingual_report_quality(report)
        results["quality_result"] = quality_result

        # Print quality details
        print(f"    english_summary_present: {quality_result['english_summary_present']}")
        print(f"    english_summary_looks_english: {quality_result['english_summary_looks_english']}")
        print(f"    english_key_claims_count: {quality_result['english_key_claims_count']}")
        print(f"    english_key_claims_look_english: {quality_result['english_key_claims_look_english']}")
        print(f"    chinese_explanation_present: {quality_result['chinese_explanation_present']}")
        print(f"    chinese_explanation_looks_chinese: {quality_result['chinese_explanation_looks_chinese']}")
        print(f"    fidelity_notes_present: {quality_result['fidelity_notes_present']}")
        print(f"    fidelity_notes_look_chinese: {quality_result['fidelity_notes_look_chinese']}")
        print(f"    interpretation_boundary_present: {quality_result['interpretation_boundary_present']}")
        print(f"    interpretation_boundary_look_chinese: {quality_result['interpretation_boundary_look_chinese']}")
        print(f"    passed_minimum_quality: {quality_result['passed_minimum_quality']}")

        if quality_result["warnings"]:
            print("    Warnings:")
            for w in quality_result["warnings"]:
                print(f"      - {w}")

        # Determine pass/fail
        if not quality_result["passed_minimum_quality"]:
            results["passed"] = False
            results["errors"].append(f"Quality check failed: {quality_result['warnings']}")

        return results

    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return results
    finally:
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    result = _run_acceptance(args)

    print()
    if result.get("skipped"):
        print(f"[SKIP] REAL LLM MODE SKIPPED: {result.get('reason', 'unknown')}")
        return 0
    elif result["passed"]:
        print("[PASS] ACCEPTANCE PASSED")
        return 0
    else:
        print("[FAIL] ACCEPTANCE FAILED")
        for error in result["errors"]:
            print(f"    - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
