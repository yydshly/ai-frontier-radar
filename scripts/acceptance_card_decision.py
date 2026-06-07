#!/usr/bin/env python3
"""V0.4 acceptance script for InsightCard user decision loop.

Validates the end-to-end flow:
    1. Create a completed InsightCard in an isolated DB
    2. Open /cards/{id} via TestClient
    3. POST decision=worth_attention
    4. Verify CardDecision is created in DB
    5. POST again with decision=to_action + a note
    6. Verify the same card_id still has only one CardDecision, updated
    7. Open /cards and confirm 处理状态 column shows "转成行动"
    8. Print ACCEPTANCE PASSED

Usage:
    python scripts/acceptance_card_decision.py --isolated-db
    python scripts/acceptance_card_decision.py --isolated-db --keep-db
"""
import argparse
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.4 card decision acceptance test (isolated DB)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_card_decision_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


def _run_acceptance(args):
    """Run the V0.4 decision loop acceptance in a clean isolated DB."""
    # Imports inside function so env / DB is loaded by caller context
    from app.db import SessionLocal, init_db
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    # Reset env so the FastAPI app picks up our isolated DB too
    print("=" * 60)
    print("V0.4 Card Decision Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized (incl. card_decisions table)")

    db = SessionLocal()
    card_id = None
    try:
        # 1. Create a completed InsightCard directly
        card = InsightCard(
            source_url="https://example.com/v04-acceptance-article",
            source_type=SourceType.HTML,
            source_title="V0.4 Acceptance Test Article",
            source_author="Acceptance Tester",
            content_hash="v04-acceptance-hash",
            status=CardStatus.COMPLETED,
            summary_zh="这是一张用于 V0.4 验收的中文摘要。",
            key_points_zh='["关键事实 1", "关键事实 2"]',
            technical_insights_zh='["技术洞察 1"]',
            product_opportunities_zh='["产品机会 1"]',
            risks_zh='["风险 1"]',
            action_items_zh='["行动建议 1"]',
            relevance_score=82,
            relevance_reasons_zh='["理由 1"]',
            related_user_directions='["方向 1"]',
            model_name="acceptance-stub",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id
        print(f"[OK] Created InsightCard(id={card_id}, status=completed)")

        # 2. TestClient — use FastAPI app directly (isolated env already set)
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # 3. Open /cards/{id} and verify decision section is rendered
        response = client.get(f"/cards/{card_id}")
        assert response.status_code == 200, f"GET /cards/{card_id} failed: {response.status_code}"
        text = response.text
        assert "看完后的判断" in text, "Decision section header missing on /cards/{id}"
        assert "值得" in text or "worth_attention" in text, "worth_attention option missing"
        assert "to_action" in text or "转成行动" in text, "to_action option missing"
        assert "未处理" in text, "Current decision should default to '未处理' for new card"
        print("[OK] GET /cards/{id} renders decision section (current=未处理)")

        # 4. POST first decision: worth_attention (no note)
        response = client.post(
            f"/cards/{card_id}/decision",
            data={"decision": "worth_attention", "note": ""},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303), \
            f"Expected redirect, got {response.status_code}"
        print(f"[OK] POST decision=worth_attention -> redirect ({response.status_code})")

        # 5. Verify DB: exactly one CardDecision with right value
        db.expire_all()
        decisions = db.query(CardDecision).filter(CardDecision.card_id == card_id).all()
        assert len(decisions) == 1, f"Expected 1 decision, got {len(decisions)}"
        assert decisions[0].decision == "worth_attention", \
            f"Expected worth_attention, got {decisions[0].decision}"
        assert decisions[0].note is None, f"Expected None note, got {decisions[0].note!r}"
        print(f"[OK] DB: CardDecision(card_id={card_id}, decision=worth_attention, note=None)")

        # 6. POST second decision: to_action + note
        response = client.post(
            f"/cards/{card_id}/decision",
            data={"decision": "to_action", "note": "可以转成资料编译功能优化任务"},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303), \
            f"Expected redirect, got {response.status_code}"
        print(f"[OK] POST decision=to_action + note -> redirect ({response.status_code})")

        # 7. Verify still exactly one CardDecision, with updated values
        db.expire_all()
        decisions = db.query(CardDecision).filter(CardDecision.card_id == card_id).all()
        assert len(decisions) == 1, \
            f"Expected 1 decision after re-submit, got {len(decisions)} (should update, not insert)"
        assert decisions[0].decision == "to_action", \
            f"Expected to_action, got {decisions[0].decision}"
        assert decisions[0].note == "可以转成资料编译功能优化任务", \
            f"Expected updated note, got {decisions[0].note!r}"
        print(f"[OK] DB: same row updated (decision=to_action, note set)")

        # 8. Open /cards and confirm 处理状态 column shows "转成行动"
        response = client.get("/cards")
        assert response.status_code == 200, f"GET /cards failed: {response.status_code}"
        text = response.text
        assert "处理状态" in text, "/cards should have '处理状态' column"
        assert "转成行动" in text, "/cards should show '转成行动' for the updated card"
        # And the card title should be present too
        assert "V0.4 Acceptance Test Article" in text, \
            "Test card title should appear in /cards"
        print("[OK] GET /cards shows 处理状态=转成行动 for updated card")

        # 9. Verify detail page shows current decision and note
        response = client.get(f"/cards/{card_id}")
        text = response.text
        assert "转成行动" in text, "Detail page should show '转成行动' as current decision"
        assert "可以转成资料编译功能优化任务" in text, \
            "Detail page should show the saved note"
        # The to_action radio should be checked
        import re
        to_action_match = re.search(
            r'<input[^>]*value="to_action"[^>]*>',
            text,
        )
        assert to_action_match is not None, \
            "to_action radio input not found in detail page"
        assert "checked" in to_action_match.group(0), \
            f"to_action radio should be checked; got: {to_action_match.group(0)}"
        print("[OK] GET /cards/{id} shows current decision=转成行动 and saved note")

        # 10. Invalid decision should be rejected
        response = client.post(
            f"/cards/{card_id}/decision",
            data={"decision": "not_a_real_decision", "note": ""},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303), \
            f"Invalid decision should still redirect, got {response.status_code}"
        db.expire_all()
        decisions = db.query(CardDecision).filter(CardDecision.card_id == card_id).all()
        assert len(decisions) == 1
        assert decisions[0].decision == "to_action", \
            f"Invalid decision should NOT overwrite existing; got {decisions[0].decision}"
        print("[OK] Invalid decision is rejected (does not overwrite)")

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
        db_name = f"acceptance_card_decision_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    card_id = _run_acceptance(args)
    print(f"\n[OK] V0.4 decision loop PASSED for InsightCard(id={card_id})")

    # Cleanup isolated DB if not --keep-db
    if isolated_db_path and not args.keep_db:
        import os as _os
        try:
            _os.remove(isolated_db_path)
            print(f"[INFO] Cleaned up isolated DB: {isolated_db_path}")
        except OSError:
            print(f"[WARN] Could not remove isolated DB: {isolated_db_path}")

    print()
    print("[PASS] ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
