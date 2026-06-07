#!/usr/bin/env python3
"""
Card page HTML checker.

Uses TestClient to fetch card detail page and check for encoding issues.
Does NOT require real API key or network access.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

# Set test database
os.environ["DATABASE_URL"] = "sqlite:///./data/test_smoke.db"
os.environ["LLM_PROFILE"] = "minimax_m27_highspeed_anthropic"

from app.main import app

client = TestClient(app)


def check_card_page(card_id: int):
    print(f"Checking card page /cards/{card_id}...")

    response = client.get(f"/cards/{card_id}")
    print(f"Status: {response.status_code}")

    if response.status_code != 200:
        print("[ERROR] Page did not return 200")
        return

    html = response.text

    # Check UTF-8 charset
    if 'charset="UTF-8"' in html or "charset='UTF-8'" in html or "charset=utf-8" in html.lower():
        print("[OK] Page declares UTF-8 charset")
    else:
        print("[WARN] Page may not declare UTF-8 charset")

    # Check for replacement characters
    if "�" in html:
        print("[WARN] Page contains replacement character '�'")
        has_mojibake = True
    else:
        has_mojibake = False

    # Look for summary section content
    if "中文摘要" in html:
        print("[OK] Page contains '中文摘要' section")
    else:
        print("[WARN] Page missing '中文摘要' section")

    if "关键事实" in html:
        print("[OK] Page contains '关键事实' section")
    else:
        print("[WARN] Page missing '关键事实' section")

    if "技术洞察" in html:
        print("[OK] Page contains '技术洞察' section")
    else:
        print("[WARN] Page missing '技术洞察' section")

    # Check for meaningful Chinese characters in content
    chinese_count = 0
    for char in html:
        if "一" <= char <= "鿿":
            chinese_count += 1

    print(f"[INFO] Chinese character count in HTML: {chinese_count}")

    if chinese_count > 100:
        print("[OK] Page contains substantial Chinese text")
    elif chinese_count > 10:
        print("[OK] Page contains some Chinese text")
    else:
        print("[WARN] Page contains very little Chinese text")

    # Check for model name
    if "MiniMax" in html:
        print("[OK] Page shows MiniMax model")
    else:
        print("[WARN] Page does not show MiniMax model")

    print()
    if has_mojibake:
        print("PAGE_TEXT_MAYBE_MOJIBAKE")
    else:
        print("PAGE_UTF8_OK")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_card_page.py <card_id>")
        sys.exit(1)

    card_id = int(sys.argv[1])
    check_card_page(card_id)
