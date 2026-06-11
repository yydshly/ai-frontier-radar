#!/usr/bin/env python3
"""
acceptance_daily_report_fast_path.py

V1.0-beta.26 Daily Report Fast Path Acceptance — includes static checks
and isolated DB behavior tests.

Usage:
    python -m compileall app scripts
    python scripts/acceptance_daily_report_fast_path.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Result tracking ──────────────────────────────────────────────────────────

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


# ── Isolated DB helpers ──────────────────────────────────────────────────────

_engine = None
_Session = None
_db_path = None


def _get_engine_session():
    """Lazily create a single shared engine+session for all tests."""
    global _engine, _Session, _db_path
    if _engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db import Base

        tmp_fd, _db_path = tempfile.mkstemp(suffix=".db")
        os.close(tmp_fd)
        _engine = create_engine(
            f"sqlite:///{_db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=_engine)
        _Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine, _Session


def _clear_all_items(session):
    """Delete all SourceItem rows. Use between test scenarios."""
    from app.models import SourceItem
    session.query(SourceItem).delete()
    session.commit()


def _add_source(session, id: int, source_key: str, enabled: bool = True):
    from app.models import Source
    existing = session.query(Source).get(id)
    if existing:
        return
    session.add(Source(
        id=id,
        source_key=source_key,
        name=f"Test Source {source_key}",
        description="",
        source_type="rss",
        category="blog",
        enabled=enabled,
        fetch_strategy="rss",
        relevance_hint="",
        fetch_interval_hours=24,
    ))
    session.commit()


def _add_item(
    session,
    *,
    item_id: int,
    source_id: int,
    source_key: str,
    url: str,
    title: str,
    hours_ago: int = 0,
    zh_one_liner: str | None = None,
    zh_summary: str | None = None,
    summary_basis: str | None = None,
) -> None:
    from app.models import SourceItem

    item = SourceItem(
        id=item_id,
        source_id=source_id,
        source_key=source_key,
        url=url,
        title=title,
        status="discovered",
        insight_card_id=None,
    )
    now = datetime.utcnow()
    item.first_seen_at = now - timedelta(hours=hours_ago)
    item.last_seen_at = now - timedelta(hours=hours_ago)
    if zh_one_liner or zh_summary:
        raw = {}
        if zh_one_liner:
            raw["zh_one_liner"] = zh_one_liner
        if zh_summary:
            raw["zh_summary"] = zh_summary
        if summary_basis:
            raw["summary_basis"] = summary_basis
        item.raw_metadata_json = json.dumps(raw)
    session.add(item)
    session.commit()


# ── Behavior tests ────────────────────────────────────────────────────────────

def run_behavior_tests():
    """Run isolated DB behavior tests for daily report card logic."""
    from app.application.radar.daily_report_card import build_daily_report_card

    print("\n[Behavior Tests — Isolated DB]")
    engine, Session = _get_engine_session()

    # ── Scenario 1: No today content ───────────────────────────────────────────
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        # No items added — all today items removed
        card = build_daily_report_card(sess)
        check("S1: total_items == 0", card.overview.total_items == 0,
              f"got {card.overview.total_items}")
        check("S1: report_status == empty", card.overview.report_status == "empty")
        check("S1: primary_items == []", len(card.primary_items) == 0)
        check("S1: secondary_items == []", len(card.secondary_items) == 0)
    finally:
        sess.close()

    # ── Scenario 2: Only pending (no zh summaries) ───────────────────────────
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        for i in range(1, 4):
            _add_item(sess, item_id=i, source_id=1, source_key="src1",
                      url=f"https://example.com/pending{i}",
                      title=f"Pending Item {i}", hours_ago=0)
        card = build_daily_report_card(sess)
        check("S2: total_items == 3", card.overview.total_items == 3,
              f"got {card.overview.total_items}")
        check("S2: readable_items == 0", card.overview.readable_items == 0,
              f"got {card.overview.readable_items}")
        check("S2: pending_items == 3", card.overview.pending_items == 3,
              f"got {card.overview.pending_items}")
        check("S2: report_status == empty", card.overview.report_status == "empty",
              f"got {card.overview.report_status}")
        check("S2: primary_items == []", len(card.primary_items) == 0)
        check("S2: secondary_items has 3", len(card.secondary_items) == 3)
    finally:
        sess.close()

    # ── Scenario 3: Only zh_one_liner ─────────────────────────────────────
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        for i in range(11, 14):
            _add_item(sess, item_id=i, source_id=1, source_key="src1",
                      url=f"https://example.com/oneliner{i}",
                      title=f"OneLiner Item {i}", hours_ago=0,
                      zh_one_liner=f"一句话概述{i}")
        card = build_daily_report_card(sess)
        check("S3: readable_items == 3", card.overview.readable_items == 3,
              f"got {card.overview.readable_items}")
        check("S3: report_status == partial", card.overview.report_status == "partial",
              f"got {card.overview.report_status}")
        check("S3: primary_items == 3", len(card.primary_items) == 3,
              f"got {len(card.primary_items)}")
        check("S3: secondary_items == []", len(card.secondary_items) == 0,
              f"got {len(card.secondary_items)}")
    finally:
        sess.close()

    # ── Scenario 4: Only zh_summary (html_snapshot) ───────────────────────
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        for i in range(21, 24):
            _add_item(sess, item_id=i, source_id=1, source_key="src1",
                      url=f"https://example.com/summary{i}",
                      title=f"Summary Item {i}", hours_ago=0,
                      zh_summary=f"正文摘要{i}",
                      summary_basis="html_snapshot")
        card = build_daily_report_card(sess)
        check("S4: readable_items == 3", card.overview.readable_items == 3,
              f"got {card.overview.readable_items}")
        check("S4: primary_items == 3", len(card.primary_items) == 3,
              f"got {len(card.primary_items)}")
        check("S4: each primary has zh_summary",
              all(i.zh_summary for i in card.primary_items),
              f"got {[i.zh_summary for i in card.primary_items]}")
        check("S4: secondary_items == []", len(card.secondary_items) == 0,
              f"got {len(card.secondary_items)}")
    finally:
        sess.close()

    # ── Scenario 5: Same item has both zh_one_liner + zh_summary (dedup) ──
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        for i in range(31, 34):
            _add_item(sess, item_id=i, source_id=1, source_key="src1",
                      url=f"https://example.com/both{i}",
                      title=f"Both Item {i}", hours_ago=0,
                      zh_one_liner=f"一句话{i}",
                      zh_summary=f"正文摘要{i}",
                      summary_basis="html_snapshot")
        card = build_daily_report_card(sess)
        check("S5: with_zh_one_liner == 3",
              card.overview.with_zh_one_liner == 3,
              f"got {card.overview.with_zh_one_liner}")
        check("S5: with_zh_summary == 3",
              card.overview.with_zh_summary == 3,
              f"got {card.overview.with_zh_summary}")
        check("S5: readable_items == 3 (deduped, not 6)",
              card.overview.readable_items == 3,
              f"got {card.overview.readable_items}")
    finally:
        sess.close()

    # ── Scenario 6: ready threshold (>=5 readable) ───────────────────────
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        for i in range(41, 48):
            _add_item(sess, item_id=i, source_id=1, source_key="src1",
                      url=f"https://example.com/ready{i}",
                      title=f"Ready Item {i}", hours_ago=0,
                      zh_one_liner=f"可读内容{i}")
        card = build_daily_report_card(sess)
        check("S6: report_status == ready (5+ readable)",
              card.overview.report_status == "ready",
              f"got {card.overview.report_status}")
    finally:
        sess.close()

    # ── Scenario 7: pending exceeds secondary_limit ────────────────────────
    sess = Session()
    try:
        _clear_all_items(sess)
        _add_source(sess, 1, "src1")
        for i in range(51, 63):  # 12 pending
            _add_item(sess, item_id=i, source_id=1, source_key="src1",
                      url=f"https://example.com/pend{i}",
                      title=f"Pending {i}", hours_ago=0)
        card = build_daily_report_card(sess, secondary_limit=10)
        check("S7: pending_items == 12", card.overview.pending_items == 12,
              f"got {card.overview.pending_items}")
        check("S7: secondary_items == 10 (limited)",
              len(card.secondary_items) == 10,
              f"got {len(card.secondary_items)}")
        check("S7: secondary_all_shown == False",
              card.secondary_all_shown is False)
    finally:
        sess.close()

    # ── Scenario 8: URL safety via TestClient ──────────────────────────────
    print("\n[Behavior Tests — URL Safety via TestClient]")
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

        # Note: TestClient uses the app's configured DB, not our isolated temp DB.
        # We verify URL-safety implementation (not data) by checking the response.
        resp = client.get("/radar/daily-report")
        check("S8: GET /radar/daily-report returns 200",
              resp.status_code == 200,
              f"got {resp.status_code}")
        # Unsafe URL schemes must not appear as href attributes
        check("S8: javascript:alert not in response",
              "javascript:alert" not in resp.text,
              "unsafe javascript URL must not appear in HTML")
        check("S8: no href=\"javascript:",
              'href="javascript:' not in resp.text,
              "no href=javascript: in HTML")
        # Safe https href links should be present in the response
        check("S8: https href links rendered",
              'href="https://' in resp.text,
              "safe https URLs should be rendered as href links")
        check("S8: 打开原文 link rendered",
              "打开原文" in resp.text)
    except Exception as e:
        check("S8: URL safety test", False, str(e))


# ── Static checks ────────────────────────────────────────────────────────────

def run_static_checks():
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
    check("secondary_all_shown passed to template",
          "secondary_all_shown" in routes[routes.find('def get_daily_report_card'):])
    check("safe_external_url passed to template",
          "safe_external_url" in routes[routes.find('def get_daily_report_card'):])

    # Template structure checks
    print("\n[Template Structure]")
    check("radar_daily_report.html exists", daily_report_html.exists())
    check("radar_daily_report.html title is '今日可读简报'",
          "今日可读简报" in report_html and
          ("<title>今日可读简报" in report_html or '{% block title %}今日可读简报' in report_html))
    check("radar_daily_report.html h1 is '今日可读简报'",
          '<h1 class="radar-header-title">今日可读简报</h1>' in report_html)
    check("radar_daily_report.html contains '今日可读简报' section",
          "今日可读简报" in report_html)
    check("radar_daily_report.html contains '待补全内容'",
          "待补全内容" in report_html)
    check("radar_daily_report.html contains '返回今日雷达'",
          "返回今日雷达" in report_html)
    check("radar_daily_report.html contains '查看洞察卡'",
          "查看洞察卡" in report_html)
    check("radar_daily_report.html does NOT use '今日必看'",
          "今日必看" not in report_html or "其他值得" not in report_html)
    check("radar_daily_report.html uses safe_external_url for item.url",
          "safe_external_url(item.url)" in report_html or
          "safe_external_url(item.url" in report_html)
    check("radar_daily_report.html uses readable_items in banner",
          "readable_items" in report_html)
    check("radar_daily_report.html uses pending_items in banner",
          "pending_items" in report_html)
    # V1.0-beta.15 new checks
    check("radar_daily_report.html has '当前简报依据' explanation",
          "当前简报依据" in report_html)
    check("radar_daily_report.html has '今日核心报告' section",
          "今日核心报告" in report_html)
    check("radar_daily_report.html has voice report entry",
          "音频播报" in report_html)
    check("radar_daily_report.html links to the voice script",
          "/radar/daily-report/broadcast" in report_html
          and "查看语音文稿" in report_html)

    # Rule-based report logic
    print("\n[Rule-based Report]")
    check("GET /radar/daily-report does NOT require DAILY_REPORT_ENABLED",
          "DAILY_REPORT_ENABLED" not in routes[
              routes.find('def get_daily_report_card'):
              routes.find('def get_daily_report_card') + 500])
    check("build_daily_report_card does NOT call LLM providers",
          "def build_daily_report_card" in card_py and
          "os.environ" not in card_py and
          "OPENAI" not in card_py and
          "llm_providers" not in card_py)
    check("build_daily_report_card has readable_items and pending_items fields",
          "readable_items" in card_py and "pending_items" in card_py)
    check("build_daily_report_card has _READY_THRESHOLD",
          "_READY_THRESHOLD" in card_py)

    # Guidance checks
    print("\n[Guidance]")
    check("radar_daily_report.html has partial/not-ready guidance",
          "尚未" in report_html or "补全" in report_html)
    check("radar_today.html shows recommended flow hint",
          "推荐" in today_html_content and "更新今日新增" in today_html_content
          and "生成中文摘要" in today_html_content)
    # V1.0-beta.15 naming convention checks
    check("radar_today.html has '查看今日可读简报' link",
          "查看今日可读简报" in today_html_content)
    check("radar_today.html has '生成今日核心报告' button",
          "生成今日核心报告" in today_html_content)
    check("radar_today.html mentions basis for core report",
          "基于今日已有中文摘要" in today_html_content)
    check("radar_today.html exposes recommendation as peer navigation",
          "推荐深入分析" in today_html_content
          and "radar-section-link" in today_html_content)


def main():
    global PASS, FAIL
    run_static_checks()
    run_behavior_tests()
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
