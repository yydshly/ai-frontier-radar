#!/usr/bin/env python3
"""V0.4.1 acceptance script for /cards decision filter.

Validates that /cards correctly filters InsightCards by CardDecision:

  1. Create 6 InsightCards in an isolated DB (one per decision state + 1
     unhandled)
  2. GET /cards with various ?decision=... query values
  3. Assert each filter returns only the matching cards
  4. Assert invalid filter value does NOT 500 (treated as 'all')
  5. Print ACCEPTANCE PASSED

Usage:
    python scripts/acceptance_card_decision_filter.py --isolated-db
    python scripts/acceptance_card_decision_filter.py --isolated-db --keep-db
"""
import argparse
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.4.1 /cards decision filter acceptance (isolated DB)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_card_decision_filter_<ts>.db).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    return parser


# Each tuple: (unique_title_fragment, decision_value or None)
CARDS_TO_CREATE = [
    ("Card Unhandled", None),
    ("Card Worth Attention", "worth_attention"),
    ("Card Related To Me", "related_to_me"),
    ("Card Read Later", "read_later"),
    ("Card Ignore", "ignore"),
    ("Card To Action", "to_action"),
]


def _create_test_cards(db):
    """Create 6 InsightCards with distinct titles and decisions.

    Returns a dict mapping decision value (or "unhandled") -> card id.
    """
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    card_id_by_decision: dict[str, int] = {}
    for idx, (title_suffix, decision_value) in enumerate(CARDS_TO_CREATE):
        unique_title = f"V0.4.1 {title_suffix} {idx}"
        card = InsightCard(
            source_url=f"https://example.com/v041-{idx}",
            source_type=SourceType.HTML,
            source_title=unique_title,
            content_hash=f"v041-{idx}",
            status=CardStatus.COMPLETED,
            summary_zh="测试摘要",
            relevance_score=80,
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        if decision_value is not None:
            decision = CardDecision(
                card_id=card.id,
                decision=decision_value,
            )
            db.add(decision)
            db.commit()
            key = decision_value
        else:
            key = "unhandled"

        card_id_by_decision[key] = card.id
        print(f"[OK] Created card #{card.id} (decision={key}) title='{unique_title}'")

    return card_id_by_decision


def _verify_cards_page(client, decision_query: str, expected_titles: list[str], label: str):
    """GET /cards[?decision=...], assert expected titles appear / don't appear."""
    url = "/cards" if not decision_query else f"/cards?decision={decision_query}"
    response = client.get(url)
    assert response.status_code == 200, \
        f"GET {url} failed: {response.status_code} (must NOT 500)"
    text = response.text

    for expected in expected_titles:
        assert expected in text, \
            f"[{label}] Expected '{expected}' to appear on {url}"
    print(f"[OK] {label}: GET {url} returned 200 and contains expected titles")


def _verify_cards_page_excludes(client, decision_query: str, excluded_titles: list[str], label: str):
    """Assert that listed titles are NOT in the page text."""
    url = "/cards" if not decision_query else f"/cards?decision={decision_query}"
    response = client.get(url)
    assert response.status_code == 200
    text = response.text
    for excluded in excluded_titles:
        assert excluded not in text, \
            f"[{label}] '{excluded}' should NOT appear on {url}"
    print(f"[OK] {label}: excluded titles confirmed absent on {url}")


def _run_acceptance(args):
    """Run the V0.4.1 decision-filter acceptance in a clean isolated DB."""
    from app.db import SessionLocal, init_db
    from fastapi.testclient import TestClient
    from app.main import app

    print("=" * 60)
    print("V0.4.1 /cards Decision Filter Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized (incl. card_decisions table)")

    db = SessionLocal()
    try:
        # Create 6 test cards
        card_id_by_decision = _create_test_cards(db)
        total_cards = len(card_id_by_decision)
        assert total_cards == 6, f"Expected 6 test cards, got {total_cards}"

        # Use TestClient
        client = TestClient(app)

        # === 1. /cards (no filter) — should show all 6 ===
        all_titles = [f"V0.4.1 {t} " for t, _ in CARDS_TO_CREATE]
        _verify_cards_page(client, "", all_titles, "All cards")
        # No filter means no "已筛选" label
        response = client.get("/cards")
        assert "已筛选" not in response.text, \
            "No filter: page should not show '已筛选' label"
        print("[OK] No filter: no '已筛选' label")

        # === 2. /cards?decision=unhandled — only 1 card ===
        _verify_cards_page(
            client,
            "unhandled",
            ["V0.4.1 Card Unhandled"],
            "decision=unhandled",
        )
        _verify_cards_page_excludes(
            client,
            "unhandled",
            [
                "V0.4.1 Card Worth Attention",
                "V0.4.1 Card To Action",
            ],
            "decision=unhandled",
        )

        # === 3. Each valid decision filter ===
        decision_to_title_suffix = {
            "worth_attention": "Card Worth Attention",
            "related_to_me": "Card Related To Me",
            "read_later": "Card Read Later",
            "ignore": "Card Ignore",
            "to_action": "Card To Action",
        }
        for decision_value, expected_suffix in decision_to_title_suffix.items():
            _verify_cards_page(
                client,
                decision_value,
                [f"V0.4.1 {expected_suffix}"],
                f"decision={decision_value}",
            )
            # Other cards (with different decision or unhandled) should NOT appear
            other_titles = [
                f"V0.4.1 {t}"
                for t, _ in CARDS_TO_CREATE
                if t != expected_suffix
            ]
            _verify_cards_page_excludes(
                client,
                decision_value,
                other_titles,
                f"decision={decision_value}",
            )

        # === 4. Invalid decision — must NOT 500, treated as 'all' ===
        response = client.get("/cards?decision=not_real_decision")
        assert response.status_code == 200, \
            f"Invalid decision should NOT 500; got {response.status_code}"
        text = response.text
        # Should fall back to showing all 6 cards
        for title_suffix, _ in CARDS_TO_CREATE:
            assert f"V0.4.1 {title_suffix}" in text, \
                f"Invalid filter should fall back to 'all'; missing 'V0.4.1 {title_suffix}'"
        # And the result count should be 6
        assert "已筛选" not in text, \
            "Invalid filter: should NOT show '已筛选' label (treated as no filter)"
        print("[OK] decision=not_real: 200, treated as 'all' (no '已筛选' label)")

    finally:
        db.close()

    # === 5. Scenario B: 0-result filter with Chinese label ===
    # Start a fresh isolated session with a single card
    print()
    print("-" * 60)
    print("Scenario B: 0-result filter with Chinese label")
    print("-" * 60)

    db2 = SessionLocal()
    try:
        from app.models import InsightCard, CardStatus, SourceType, CardDecision

        # Create only one card with to_action
        zero_card = InsightCard(
            source_url="https://example.com/v041-zero-only",
            source_type=SourceType.HTML,
            source_title="V0.4.1 Only ToAction Card",
            content_hash="v041-zero-only",
            status=CardStatus.COMPLETED,
            summary_zh="Zero scenario test",
            relevance_score=80,
        )
        db2.add(zero_card)
        db2.commit()
        db2.refresh(zero_card)

        decision = CardDecision(card_id=zero_card.id, decision="to_action")
        db2.add(decision)
        db2.commit()

        zero_card_id = zero_card.id
        print(f"[OK] Created zero-scenario card #{zero_card_id} (decision=to_action)")

        # Wipe all worth_attention decisions so 0-result scenario is truly isolated.
        # (Scenario A created one worth_attention card which must not pollute this check.)
        db2.query(CardDecision).filter(CardDecision.decision == "worth_attention").delete(synchronize_session=False)
        db2.commit()
        print("[OK] Cleared worth_attention decisions to isolate 0-result scenario")

        # Request worth_attention filter — should return 0
        response = client.get("/cards?decision=worth_attention")
        assert response.status_code == 200, \
            f"0-result filter should return 200; got {response.status_code}"
        text = response.text

        # Should show "共找到 0 张卡片"
        assert "共找到 <strong>0</strong> 张卡片" in text, \
            "0-result filter should show '共找到 0 张卡片'"
        # Should show Chinese label
        assert "已筛选：值得关注" in text, \
            "0-result filter should show Chinese label '已筛选：值得关注'"
        # Should show empty state
        assert "当前筛选条件下没有 InsightCard" in text, \
            "0-result filter should show empty state message"
        # Should NOT show raw value
        assert "已筛选：worth_attention" not in text, \
            "Should NOT show raw value '已筛选：worth_attention'"
        # to_action card title should NOT appear
        assert "V0.4.1 Only ToAction Card" not in text, \
            "to_action card should NOT appear in worth_attention filter"
        print("[OK] 0-result filter: shows Chinese label, 0 count, and empty state")

        # Cleanup
        db2.query(CardDecision).filter(CardDecision.card_id == zero_card_id).delete(synchronize_session=False)
        db2.query(InsightCard).filter(InsightCard.id == zero_card_id).delete(synchronize_session=False)
        db2.commit()
        print(f"[OK] Cleaned up zero-scenario card #{zero_card_id}")

    finally:
        db2.close()

    return card_id_by_decision


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Handle --isolated-db BEFORE importing app.db
    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_card_decision_filter_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    card_id_by_decision = _run_acceptance(args)
    print(f"\n[OK] V0.4.1 /cards filter PASSED for {len(card_id_by_decision)} test cards")

    # Cleanup isolated DB if not --keep-db
    if isolated_db_path and not args.keep_db:
        try:
            os.remove(isolated_db_path)
            print(f"[INFO] Cleaned up isolated DB: {isolated_db_path}")
        except OSError:
            print(f"[WARN] Could not remove isolated DB: {isolated_db_path}")

    print()
    print("[PASS] ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
