#!/usr/bin/env python3
"""Create demo data for V1.0-alpha.1 demonstration.

Creates a complete demo data set:
- Source (demo_ai_frontier)
- SourceItem (discovered -> compiled)
- InsightCard (completed)
- InsightCardBilingualReport
- CardDecision (to_action)

Usage:
    python scripts/create_demo_data.py
    python scripts/create_demo_data.py --reset-demo
    python scripts/create_demo_data.py --source-key custom_key
"""
import argparse
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


DEMO_SOURCE_KEY = "demo_ai_frontier"
DEMO_SOURCE_TITLE = "Demo: Agent Workflow Framework for Enterprise Document Processing"
DEMO_SOURCE_URL = "https://example.com/ai-frontier-demo/agent-workflow-framework"


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Create demo data for V1.0-alpha.1 demonstration."
    )
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="Delete existing demo data before creating new one.",
    )
    parser.add_argument(
        "--source-key",
        default=DEMO_SOURCE_KEY,
        help=f"Source key for demo data (default: {DEMO_SOURCE_KEY}).",
    )
    return parser


def _delete_demo_data(db, source_key):
    """Delete demo data associated with the given source_key."""
    from app.models import Source, SourceItem, InsightCard, CardDecision, InsightCardBilingualReport

    deleted_counts = {"sources": 0, "source_items": 0, "cards": 0, "decisions": 0, "reports": 0}

    # Get all SourceItems for this source
    source_items = db.query(SourceItem).filter(SourceItem.source_key == source_key).all()
    source_item_ids = [si.id for si in source_items]

    # Delete decisions and bilingual reports for associated cards
    if source_item_ids:
        for si_id in source_item_ids:
            card = db.query(InsightCard).filter(InsightCard.source_url == SourceItem.url).first()
            if card:
                db.query(CardDecision).filter(CardDecision.card_id == card.id).delete()
                db.query(InsightCardBilingualReport).filter(InsightCardBilingualReport.card_id == card.id).delete()
                deleted_counts["reports"] += 1
                deleted_counts["decisions"] += 1

    # Delete SourceItems
    if source_item_ids:
        db.query(SourceItem).filter(SourceItem.source_key == source_key).delete(synchronize_session=False)
        deleted_counts["source_items"] = len(source_item_ids)

    # Delete Source
    db.query(Source).filter(Source.source_key == source_key).delete(synchronize_session=False)
    deleted_counts["sources"] = 1

    db.commit()
    return deleted_counts


def create_demo_data(source_key=DEMO_SOURCE_KEY):
    """Create or verify demo data exists.

    Returns a dict with ids of created/found records.
    """
    from app.db import SessionLocal, init_db
    from app.models import Source, SourceItem, InsightCard, CardDecision, InsightCardBilingualReport, SourceType, CardStatus

    init_db()
    db = SessionLocal()

    result = {"source_id": None, "source_item_id": None, "card_id": None, "created": False}

    try:
        # Check if demo data already exists
        existing_source = db.query(Source).filter(Source.source_key == source_key).first()
        if existing_source:
            # Check if it has a compiled SourceItem and card
            source_item = db.query(SourceItem).filter(SourceItem.source_key == source_key).first()
            if source_item and source_item.insight_card_id:
                card = db.query(InsightCard).filter(InsightCard.id == source_item.insight_card_id).first()
                if card and card.status == CardStatus.COMPLETED:
                    result = {
                        "source_id": existing_source.id,
                        "source_item_id": source_item.id,
                        "card_id": card.id,
                        "created": False,
                    }
                    print("[INFO] Demo data already exists, skipping creation.")
                    return result

        # 1. Create Source
        source = Source(
            source_key=source_key,
            name="Demo AI Frontier Source",
            description="Demo source for V1.0-alpha.1 quick demonstration",
            source_type="html_index",
            category="company",
            fetch_strategy="html_index",
            homepage_url="https://example.com/ai-frontier-demo",
            relevance_hint="demo,agent,workflow,enterprise",
            enabled=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        result["source_id"] = source.id
        print(f"[OK] Created Source(id={source.id}, source_key={source_key})")

        # 2. Create SourceItem
        source_item = SourceItem(
            source_id=source.id,
            source_key=source_key,
            url=DEMO_SOURCE_URL,
            title=DEMO_SOURCE_TITLE,
            status="compiled",
            published_at=datetime_now(),
        )
        db.add(source_item)
        db.commit()
        db.refresh(source_item)
        result["source_item_id"] = source_item.id
        print(f"[OK] Created SourceItem(id={source_item.id}, status=compiled)")

        # 3. Create InsightCard
        card = InsightCard(
            source_url=DEMO_SOURCE_URL,
            source_type=SourceType.HTML,
            source_title=DEMO_SOURCE_TITLE,
            source_author="Demo Author",
            content_hash="demo-agent-workflow-hash",
            status=CardStatus.COMPLETED,
            summary_zh="本文介绍了一个面向企业文档处理的 AI Agent 工作流框架，该框架通过多智能体协作实现可靠且可解释的自动化文档分析工作流。",
            key_points_zh=json.dumps([
                "该框架提出了一种新的 Agent 工作流架构",
                "框架主要面向企业级文档处理场景",
                "多个专业 Agent 协同完成文档提取任务",
                "提供审计日志以满足合规要求",
                "高风险决策保持人工监督机制",
            ]),
            technical_insights_zh=json.dumps([
                "多 Agent 协作架构设计是关键创新点",
                "结构化输出结合自然语言推理提升准确性",
                "可解释性通过审计日志和决策链路实现",
            ]),
            product_opportunities_zh=json.dumps([
                "企业内部知识库自动化整理工具",
                "合同和发票等结构化文档处理",
                "合规审查自动化流程",
            ]),
            risks_zh=json.dumps([
                "企业文档隐私数据安全需要额外保障",
                "多 Agent 协作增加了系统复杂度",
                "对非结构化文档的处理能力有限",
            ]),
            action_items_zh=json.dumps([
                "评估企业内部文档处理场景需求",
                "测试框架在真实文档上的表现",
                "设计符合合规要求的实施方案",
            ]),
            relevance_score=88,
            relevance_reasons_zh=json.dumps([
                "直接涉及 AI Agent 工作流在企业场景的应用",
                "多智能体协作技术具有前沿性",
                "可解释性要求对 AI 产品有重要参考价值",
            ]),
            related_user_directions=json.dumps(["AI 产品开发", "企业级 AI 应用", "Agent 技术"]),
            model_name="demo-stub",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        result["card_id"] = card.id
        print(f"[OK] Created InsightCard(id={card.id}, status=completed)")

        # 4. Update SourceItem with card reference
        source_item.insight_card_id = card.id
        db.commit()

        # 5. Create InsightCardBilingualReport
        bilingual_report = InsightCardBilingualReport(
            card_id=card.id,
            english_core_summary="This article presents a new agent workflow framework for enterprise document processing. "
                                "The framework enables more reliable and interpretable automation workflows through "
                                "multi-agent collaboration, where specialized agents coordinate to handle document extraction, "
                                "analysis, and compliance review tasks.",
            english_key_claims_json=json.dumps([
                "The framework introduces a novel multi-agent architecture for document processing.",
                "It targets enterprise use cases requiring audit trails and compliance oversight.",
                "Specialized agents handle extraction, analysis, and review tasks respectively.",
                "Human oversight is maintained for high-risk decisions.",
            ]),
            english_evidence_points_json=json.dumps([
                "Audit logs are provided for compliance and accountability.",
                "Human oversight mechanisms are integrated for high-risk decision points.",
                "The system demonstrates improved accuracy over single-agent approaches.",
            ]),
            key_terms_json=json.dumps([
                {"en": "agentic workflow", "zh": "智能体工作流", "note_zh": "多步骤 AI 协作流程"},
                {"en": "document processing", "zh": "文档处理", "note_zh": "企业文档自动化处理"},
                {"en": "audit trail", "zh": "审计日志", "note_zh": "用于合规和可追溯性"},
                {"en": "human oversight", "zh": "人工监督", "note_zh": "高风险决策保持人工介入"},
            ]),
            chinese_explanation="这篇关于企业文档处理智能体框架的文章介绍了人工智能在自动化文档分析方面的新进展。 "
                               "文章提出的框架通过多智能体协作，提高了文档处理的可靠性和可解释性，"
                               "特别适合需要合规审查的企业应用场景。",
            fidelity_notes_zh="【保真提示】英文核心摘要和主张列表均来自原文所述。",
            interpretation_boundary_zh="【解读边界】产品机会和行动建议属于模型推论，不等于原文结论。",
        )
        db.add(bilingual_report)
        db.commit()
        print(f"[OK] Created InsightCardBilingualReport(card_id={card.id})")

        # 6. Create CardDecision
        decision = CardDecision(
            card_id=card.id,
            decision="to_action",
            note="用于演示完整报告导出和行动任务导出。",
        )
        db.add(decision)
        db.commit()
        print(f"[OK] Created CardDecision(card_id={card.id}, decision=to_action)")

        result["created"] = True
        return result

    finally:
        db.close()


def datetime_now():
    """Return a naive datetime for the current time."""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    print("=" * 60)
    print("Create Demo Data for V1.0-alpha.1")
    print("=" * 60)

    source_key = args.source_key

    # Reset demo if requested
    if args.reset_demo:
        from app.db import SessionLocal, init_db
        init_db()
        db = SessionLocal()
        try:
            print(f"[INFO] Resetting demo data for source_key={source_key}...")
            deleted = _delete_demo_data(db, source_key)
            print(f"[OK] Deleted demo data: {deleted}")
        finally:
            db.close()

    # Create demo data
    result = create_demo_data(source_key)

    if result["created"]:
        print()
        print("Demo data ready!")
        print()
        print("SourceItem:")
        print(f"  /source-items/{result['source_item_id']}")
        print()
        print("InsightCard:")
        print(f"  /cards/{result['card_id']}")
        print()
        print("Full report:")
        print(f"  /cards/{result['card_id']}/export-report")
        print()
        print("Action task:")
        print(f"  /cards/{result['card_id']}/export-markdown")
    else:
        print()
        print("Demo data already exists.")
        print()
        print("SourceItem:")
        print(f"  /source-items/{result['source_item_id']}")
        print()
        print("InsightCard:")
        print(f"  /cards/{result['card_id']}")
        print()
        print("Full report:")
        print(f"  /cards/{result['card_id']}/export-report")
        print()
        print("Action task:")
        print(f"  /cards/{result['card_id']}/export-markdown")

    print()
    print("[DONE] create_demo_data.py completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
