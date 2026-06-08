#!/usr/bin/env python3
"""V0.7.2 cross-source compile acceptance script.

Validates that expected_content SourceItems from Anthropic/Mistral/DeepMind
can be compiled into Chinese InsightCards.

This script accesses external websites and optionally calls LLM.
It is NOT run as part of smoke_test (except --mock-llm mode).

Usage:
    # Mock mode (no real LLM, validates SourceItem -> card -> SourceItem update)
    python scripts/acceptance_cross_source_compile.py --isolated-db --mock-llm

    # Real mode (validates full end-to-end including LLM)
    python scripts/acceptance_cross_source_compile.py --isolated-db --source-key anthropic_news
    python scripts/acceptance_cross_source_compile.py --isolated-db --source-key mistral_ai_news
"""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, SourceItem, InsightCard, CardStatus, SourceType
from app.sources import sync_sources_config_to_db
from app.sources.html_index_probe import run_html_index_probe_for_source
from app.sources.quality import classify_source_item_url
from app.services.insight_quality import inspect_insight_card_quality


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.7.2 cross-source compile acceptance."
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
        "--timeout",
        type=int,
        default=20,
        help="HTTP request timeout in seconds (default: 20).",
    )
    parser.add_argument(
        "--source-key",
        action="append",
        dest="source_keys",
        default=[],
        help="Source key to probe and compile (can be repeated). "
             "Defaults to anthropic_news + mistral_ai_news.",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM instead of real API call.",
    )
    return parser


def _get_default_source_keys():
    return ["anthropic_news", "mistral_ai_news"]


def _select_expected_source_item(db, source: Source) -> SourceItem | None:
    """Select one expected_content SourceItem for a source.

    Prefers items with status='discovered' that don't have an existing card.
    """
    items = (
        db.query(SourceItem)
        .filter(SourceItem.source_id == source.id)
        .filter(SourceItem.status.in_(["discovered", "failed"]))
        .all()
    )

    for item in items:
        classification = classify_source_item_url(
            source.source_key, item.url, source.homepage_url or None
        )
        if classification["suspected_listing"]:
            continue
        if classification["suspected_off_topic"]:
            continue
        if classification["expected_content"]:
            return item

    # Fallback: any non-suspected-listing, non-off-topic item
    for item in items:
        classification = classify_source_item_url(
            source.source_key, item.url, source.homepage_url or None
        )
        if classification["suspected_listing"]:
            continue
        if classification["suspected_off_topic"]:
            continue
        return item

    return None


def _build_mock_llm_result(url: str) -> dict:
    """Build a mock LLM result for --mock-llm mode."""
    return {
        "source_title": f"Mock Article for {url}",
        "source_author": "Mock Author",
        "source_published_at": "2025-01-01",
        "summary_zh": "这是一个模拟编译的中文摘要，用于验证从发现条目到编译卡片的完整链路。",
        "key_points_zh": ["关键点1：验证了编译链路完整性", "关键点2：确认了SourceItem到InsightCard的回写机制"],
        "technical_insights_zh": ["技术洞察：测试环境可以模拟真实编译流程"],
        "product_opportunities_zh": ["产品机会：验证了端到端编译能力"],
        "risks_zh": ["风险：Mock模式不验证真实LLM输出质量"],
        "action_items_zh": ["行动项1：使用真实API Key进行端到端验证", "行动项2：检查生成的InsightCard字段完整性"],
        "relevance_score": 85,
        "relevance_reasons_zh": ["Mock编译", "用于验证完整链路"],
        "related_user_directions": ["AI Agent", "LLM应用"],
        "model_name": "mock-model",
    }


def _run_compile_with_mock(db, item: SourceItem):
    """Compile a SourceItem with mock LLM (does not call real API)."""
    import app.services.insight_compiler as compiler

    # Save original
    original_compile_url = compiler.compile_url

    def mock_compile_url(db_session, url):
        # Return a completed mock card
        mock_result = _build_mock_llm_result(url)
        content_hash = f"mock-hash-{uuid.uuid4().hex[:8]}"
        card = InsightCard(
            source_url=url,
            source_type=SourceType.HTML,
            source_title=mock_result["source_title"],
            source_author=mock_result["source_author"],
            source_published_at=mock_result["source_published_at"],
            content_hash=content_hash,
            cleaned_text_preview="Mock cleaned text preview for testing.",
            status=CardStatus.COMPLETED,
            error_message=None,
            summary_zh=mock_result["summary_zh"],
            key_points_zh=json.dumps(mock_result["key_points_zh"], ensure_ascii=False),
            technical_insights_zh=json.dumps(mock_result["technical_insights_zh"], ensure_ascii=False),
            product_opportunities_zh=json.dumps(mock_result["product_opportunities_zh"], ensure_ascii=False),
            risks_zh=json.dumps(mock_result["risks_zh"], ensure_ascii=False),
            action_items_zh=json.dumps(mock_result["action_items_zh"], ensure_ascii=False),
            relevance_score=mock_result["relevance_score"],
            relevance_reasons_zh=json.dumps(mock_result["relevance_reasons_zh"], ensure_ascii=False),
            related_user_directions=json.dumps(mock_result["related_user_directions"], ensure_ascii=False),
            model_name=mock_result["model_name"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(card)
        db_session.commit()
        db_session.refresh(card)
        return card

    compiler.compile_url = mock_compile_url
    try:
        card = compiler.compile_url(db, item.url)
    finally:
        compiler.compile_url = original_compile_url

    # Update SourceItem
    item.insight_card_id = card.id
    item.updated_at = datetime.utcnow()
    if card.status == CardStatus.COMPLETED:
        item.status = "compiled"
        item.error_message = None
    else:
        item.status = "failed"
        item.error_message = card.error_message or "Mock compilation failed"
    db.commit()
    db.refresh(item)
    db.refresh(card)

    return card


def _print_source_result(
    source_key: str,
    selected_url: str | None,
    compile_status: str,
    insight_card_id: int | None,
    error_message: str | None,
    quality_result: dict | None,
):
    """Print result for one source."""
    print(f"\n{'─' * 55}")
    print(f"  {source_key}")
    print(f"  selected_url: {selected_url or '(none)'}")
    print(f"  compile_status: {compile_status}")
    print(f"  insight_card_id: {insight_card_id or 'N/A'}")
    if error_message:
        print(f"  error: {error_message[:80]}")
    if quality_result:
        print(f"  quality:")
        print(f"    summary_present: {quality_result['summary_present']}")
        print(f"    key_points_count: {quality_result['key_points_count']}")
        print(f"    technical_insights_count: {quality_result['technical_insights_count']}")
        print(f"    product_opportunities_count: {quality_result['product_opportunities_count']}")
        print(f"    action_items_count: {quality_result['action_items_count']}")
        print(f"    relevance_score_present: {quality_result['relevance_score_present']}")
        print(f"    passed_minimum_quality: {quality_result['passed_minimum_quality']}")
        if quality_result["warnings"]:
            for w in quality_result["warnings"]:
                print(f"    warning: {w}")


def _run_acceptance(args):
    print("=" * 60)
    print("V0.7.2 Cross-Source Compile Acceptance")
    print("=" * 60)

    if args.mock_llm:
        print("\n[!] Mode: MOCK LLM (validates SourceItem -> card -> update)")
    else:
        print("\n[!] Mode: REAL LLM (validates full end-to-end)")

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    try:
        # Sync sources config
        print("\n[1] Syncing source config to database...")
        sync_result = sync_sources_config_to_db(db, force_reload=True)
        print(f"    total={sync_result['total']}, created={sync_result['created']}, "
              f"updated={sync_result['updated']}")

        # Determine source keys
        source_keys = args.source_keys if args.source_keys else _get_default_source_keys()
        print(f"\n[2] Target sources: {source_keys}")

        # Load sources
        sources = []
        for key in source_keys:
            src = db.query(Source).filter(Source.source_key == key).first()
            if not src:
                print(f"\n[WARN] Source '{key}' not found in registry — skipping")
                continue
            if not src.enabled:
                print(f"\n[WARN] Source '{key}' is disabled — skipping")
                continue
            sources.append(src)

        if not sources:
            print("\n[FAIL] No valid sources to test.")
            return False

        # Run probe + compile for each source
        all_results = []

        for source in sources:
            print(f"\n{'═' * 55}")
            print(f"  {source.source_key}")
            print(f"{'═' * 55}")

            result = {
                "source_key": source.source_key,
                "selected_url": None,
                "compile_status": "not_run",
                "insight_card_id": None,
                "error_message": None,
                "quality_result": None,
            }

            # Step 1: Probe to generate SourceItems
            print(f"\n  [1] Probing {source.source_key}...")
            try:
                fetch_run = run_html_index_probe_for_source(
                    db, source, timeout_seconds=args.timeout
                )
                print(f"      probe status={fetch_run.status}, "
                      f"items_found={fetch_run.items_found}")
            except Exception as e:
                print(f"      probe ERROR: {e}")
                result["error_message"] = f"Probe failed: {e}"
                all_results.append(result)
                continue

            # Step 2: Select expected_content SourceItem
            print(f"\n  [2] Selecting expected_content SourceItem...")
            selected_item = _select_expected_source_item(db, source)

            if not selected_item:
                print(f"      No expected_content SourceItem found")
                result["error_message"] = "No expected_content SourceItem found"
                result["compile_status"] = "no_item"
                all_results.append(result)
                continue

            result["selected_url"] = selected_item.url
            print(f"      selected: {selected_item.url[:80]}")
            print(f"      item_id={selected_item.id}, status={selected_item.status}")

            # Step 3: Compile
            print(f"\n  [3] Compiling SourceItem...")
            try:
                if args.mock_llm:
                    print(f"      (using mock LLM)")
                    card = _run_compile_with_mock(db, selected_item)
                else:
                    # Use real compile_url
                    import app.services.insight_compiler as compiler
                    card = compiler.compile_url(db, selected_item.url)

                    # Update SourceItem
                    selected_item.insight_card_id = card.id
                    selected_item.updated_at = datetime.utcnow()
                    if card.status == CardStatus.COMPLETED:
                        selected_item.status = "compiled"
                        selected_item.error_message = None
                    else:
                        selected_item.status = "failed"
                        selected_item.error_message = card.error_message or "Compilation failed"
                    db.commit()
                    db.refresh(selected_item)
                    db.refresh(card)

                result["compile_status"] = card.status.value if card.status else "unknown"
                result["insight_card_id"] = card.id

                if card.status == CardStatus.FAILED:
                    result["error_message"] = card.error_message

                # Step 4: Inspect quality
                quality_result = inspect_insight_card_quality(card)
                result["quality_result"] = quality_result

                print(f"      compile_status={result['compile_status']}, "
                      f"card_id={card.id}")
                print(f"      passed_minimum_quality={quality_result['passed_minimum_quality']}")

            except Exception as e:
                print(f"      compile ERROR: {e}")
                result["error_message"] = f"Compile exception: {e}"
                result["compile_status"] = "exception"

            all_results.append(result)

        # Summary
        print(f"\n{'═' * 60}")
        print("  Acceptance Summary")
        print(f"{'═' * 60}")

        success_count = 0
        quality_pass_count = 0

        for r in all_results:
            _print_source_result(
                r["source_key"],
                r["selected_url"],
                r["compile_status"],
                r["insight_card_id"],
                r["error_message"],
                r["quality_result"],
            )
            if r["compile_status"] == "completed":
                success_count += 1
            if r["quality_result"] and r["quality_result"]["passed_minimum_quality"]:
                quality_pass_count += 1

        print(f"\n{'─' * 55}")
        print(f"  Sources tested: {len(all_results)}")
        print(f"  Compile success: {success_count}")
        print(f"  Quality passed: {quality_pass_count}")

        # Determine pass/fail
        passed = True
        reasons = []

        if len(all_results) == 0:
            passed = False
            reasons.append("No sources were tested")

        if success_count < 1:
            passed = False
            reasons.append("No source produced a completed InsightCard")

        # mock mode must pass quality
        if args.mock_llm and quality_pass_count < len(all_results):
            passed = False
            reasons.append(f"Mock mode: {quality_pass_count}/{len(all_results)} passed quality check")

        print(f"\n  -> Overall: {'PASS' if passed else 'FAIL'}")
        for reason in reasons:
            print(f"     {reason}")

        return passed

    finally:
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v072_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    try:
        result = _run_acceptance(args)
    finally:
        if isolated_db_path and not args.keep_db:
            try:
                if os.path.exists(isolated_db_path):
                    os.remove(isolated_db_path)
                print(f"\n[INFO] Cleaned up isolated DB: {isolated_db_path}")
            except OSError as e:
                print(f"\n[WARN] Could not remove isolated DB: {isolated_db_path}: {e}")

    print()
    if result:
        print("[PASS] ACCEPTANCE PASSED")
        return 0
    else:
        print("[FAIL] ACCEPTANCE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
