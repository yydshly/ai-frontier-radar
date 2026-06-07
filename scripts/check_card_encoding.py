#!/usr/bin/env python3
"""
Card encoding checker.

Reads a card from SQLite and checks for mojibake in text fields.
Does NOT call LLM, access network, or require API key.
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import sqlite3
from app.config import DATABASE_URL


def get_db_path():
    """Get path to test_smoke.db (where smoke test creates cards)."""
    # Smoke test uses data/test_smoke.db
    return Path("data/test_smoke.db")


def check_card(card_id: int):
    db_path = get_db_path()
    if not db_path:
        print(f"[ERROR] Cannot determine DB path from DATABASE_URL")
        return

    if not db_path.exists():
        print(f"[ERROR] DB file not found: {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    conn.text_factory = str
    c = conn.cursor()

    c.execute("""
        SELECT id, source_title, summary_zh, key_points_zh,
               technical_insights_zh, product_opportunities_zh,
               risks_zh, action_items_zh, relevance_reasons_zh
        FROM insight_cards WHERE id = ?
    """, (card_id,))

    row = c.fetchone()
    if not row:
        print(f"[ERROR] Card {card_id} not found")
        conn.close()
        return

    card_id, source_title, summary_zh, key_points_zh, technical_insights_zh, product_opportunities_zh, risks_zh, action_items_zh, relevance_reasons_zh = row

    print(f"Card ID: {card_id}")
    print(f"Source title: {source_title}")
    print()

    # Check summary_zh
    issues = []
    fields_to_check = [
        ("summary_zh", summary_zh),
        ("key_points_zh", key_points_zh),
        ("technical_insights_zh", technical_insights_zh),
        ("product_opportunities_zh", product_opportunities_zh),
        ("risks_zh", risks_zh),
        ("action_items_zh", action_items_zh),
        ("relevance_reasons_zh", relevance_reasons_zh),
    ]

    mojibake_patterns = ["�", "\xc3", "\xa0", "\xa4", "\x8c", "\x9c"]
    chinese_char_pattern = any(chr(0x4e00) <= c <= chr(0x9fff) for c in "中中文")

    all_ok = True
    for field_name, field_value in fields_to_check:
        if field_value is None:
            print(f"{field_name}: NULL")
            continue

        # Check for replacement char (�)
        has_replacement = "�" in field_value
        # Check for common mojibake bytes
        has_mojibake = False
        for byte_seq in [b"\xc3\xa0", b"\xc3\xa4", b"\xc3\xb6", b"\xc3\xbc"]:
            if byte_seq.decode("latin-1", errors="ignore") in field_value:
                has_mojibake = True
                break

        # Check if it looks like valid Chinese UTF-8
        try:
            field_value.encode("utf-8")
            is_valid_utf8 = True
        except UnicodeEncodeError:
            is_valid_utf8 = False

        has_chinese = False
        for char in field_value:
            if "一" <= char <= "鿿":
                has_chinese = True
                break

        if has_replacement or has_mojibake or not is_valid_utf8:
            print(f"{field_name}: MOJIBAKE")
            print(f"  repr: {repr(field_value[:100])}")
            all_ok = False
        elif has_chinese:
            print(f"{field_name}: CHINESE_OK ({len(field_value)} chars)")
            print(f"  preview: {field_value[:100]}")
        else:
            print(f"{field_name}: TEXT_OK ({len(field_value)} chars)")
            print(f"  preview: {field_value[:100]}")

    print()
    if all_ok:
        print("DB_TEXT_OK")
    else:
        print("DB_TEXT_MAYBE_MOJIBAKE")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_card_encoding.py <card_id>")
        sys.exit(1)

    card_id = int(sys.argv[1])
    check_card(card_id)
