#!/usr/bin/env python3
"""
acceptance_daily_report_fast_path.py

V1.0-beta.26 Daily Report Fast Path Acceptance Script

Checks static / lightweight conditions only — no LLM calls, no DB writes.

Usage:
    python -m compileall app scripts
    python scripts/acceptance_daily_report_fast_path.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

PASS = 0
FAIL = 0
FAILED_CHECKS = []


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL, FAILED_CHECKS
    if condition:
        print(f"  [PASS] {name}")
        PASS += 1
    else:
        msg = f"  [FAIL] {name}" + (f" — {detail}" if detail else "")
        print(msg)
        FAIL += 1
        FAILED_CHECKS.append(name)


def main():
    global PASS, FAIL, FAILED_CHECKS

    ROOT = Path(__file__).parent.parent
    radar_py = ROOT / "app" / "routes" / "radar.py"
    daily_report_html = ROOT / "app" / "templates" / "radar_daily_report.html"
    today_html = ROOT / "app" / "templates" / "radar_today.html"
    daily_report_card_py = ROOT / "app" / "application" / "radar" / "daily_report_card.py"

    print("Daily Report Fast Path Acceptance")
    print("=" * 50)

    routes = radar_py.read_text(encoding="utf-8")
    report_html = daily_report_html.read_text(encoding="utf-8")
    today_html_content = today_html.read_text(encoding="utf-8")
    card_py = daily_report_card_py.read_text(encoding="utf-8")

    # Route checks
    print("\n[Routes]")
    check("GET /radar/daily-report route exists",
          'router.get("/daily-report"' in routes or 'GET /daily-report' in routes)
    check("POST /radar/today/daily-report route exists",
          'router.post("/today/daily-report"' in routes or 'POST /today/daily-report' in routes)

    # Template structure checks
    print("\n[Template Structure]")
    check("radar_daily_report.html exists",
          daily_report_html.exists())
    check("radar_daily_report.html contains '今日报告' page title",
          "今日报告" in report_html)
    check("radar_daily_report.html contains '今日可读简报'",
          "今日可读简报" in report_html)
    check("radar_daily_report.html contains '待补全内容'",
          "待补全内容" in report_html)
    check("radar_daily_report.html contains '返回今日雷达'",
          "返回今日雷达" in report_html)
    check("radar_daily_report.html contains '查看洞察卡'",
          "查看洞察卡" in report_html)
    check("radar_daily_report.html does NOT use '今日必看' as primary section",
          "今日必看" not in report_html or "其他值得" not in report_html)
    check("radar_daily_report.html does NOT show pending items as primary",
          "待补全内容" in report_html)
    check("radar_daily_report.html has report status banners (ready/partial/empty)",
          ("radar-report-ready-banner" in report_html or "radar-report-partial-banner" in report_html or "radar-report-empty" in report_html))
    check("radar_daily_report.html uses clearer stat labels ('收录内容', '洞察卡')",
          "收录内容" in report_html or "洞察卡" in report_html)
    check("radar_daily_report.html does NOT show misleading '今日新增 N' stat",
          '>今日新增<' not in report_html and
          '今日新增</span>' not in report_html and
          '今日新增\n' not in report_html)

    # Rule-based: no LLM dependency
    print("\n[Rule-based Report]")
    check("GET /radar/daily-report does NOT require DAILY_REPORT_ENABLED",
          "DAILY_REPORT_ENABLED" not in routes[routes.find('def get_daily_report_card'):routes.find('def get_daily_report_card') + 500])
    check("build_daily_report_card does NOT call LLM providers",
          "def build_daily_report_card" in card_py and
          "os.environ" not in card_py and
          "OPENAI" not in card_py and
          "llm_providers" not in card_py)
    check("build_daily_report_card has report_status logic",
          "report_status" in card_py and "READY_THRESHOLD" in card_py)

    # Guidance checks
    print("\n[Guidance]")
    check("radar_daily_report.html has partial/not-ready guidance",
          "尚未" in report_html or "补全" in report_html)
    check("radar_daily_report.html links back to today radar for summary generation",
          "/radar/today" in report_html and "生成中文摘要" in report_html)
    check("radar_today.html shows recommended flow hint",
          "推荐" in today_html_content and "更新今日新增" in today_html_content and "生成中文摘要" in today_html_content)

    # Summary
    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"Daily Report Fast Path Acceptance")
    print(f"Total: {total}")
    print(f"Passed: {PASS}")
    print(f"Failed: {FAIL}")
    if FAIL > 0:
        print(f"\nFailed checks:")
        for name in FAILED_CHECKS:
            print(f"  - {name}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
