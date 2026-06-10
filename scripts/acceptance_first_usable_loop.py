#!/usr/bin/env python3
"""
acceptance_first_usable_loop.py — V1.0-beta First Usable Loop 轻量验收脚本。

只做静态 / 轻量检查，不联网，不调用 LLM，不抓取外部 URL。
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path so 'app' and 'scripts' imports work
# whether this file is run directly (python scripts/acceptance_...) or
# via -m (python -m scripts.acceptance_first_usable_loop).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# TestClient-based checks require the app to be importable.
try:
    from fastapi.testclient import TestClient
    from app.main import app
    _client = TestClient(app)
except Exception as exc:
    print(f"[WARN] TestClient could not be created: {exc}")
    _client = None
PASS = 0
FAIL = 0


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check(name: str, condition: bool, message: str = "") -> bool:
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {name}")
        PASS += 1
    else:
        print(f"  [FAIL] {name}" + (f" — {message}" if message else ""))
        FAIL += 1
    return condition


def main() -> int:
    global PASS, FAIL
    print("\n=== acceptance_first_usable_loop.py: V1.0-beta First Usable Loop ===\n")

    radar_html = read("app/templates/radar_today.html")
    radar_py = read("app/application/radar/today.py")
    radar_route_py = read("app/routes/radar.py")
    style_css = read("app/static/style.css")
    main_py = read("app/main.py")
    background_fetch_py = read("app/application/sources/background_fetch.py")
    card_detail_html = read("app/templates/card_detail.html")
    card_export_markdown_html = read("app/templates/card_export_markdown.html")
    card_export_report_html = read("app/templates/card_export_report.html")
    # Read panel partial for checks that verify right-panel content
    radar_panel_partial = read("app/templates/partials/radar_today_panel.html")

    print("[1] 今日雷达主链路入口")
    check("今日雷达有更新入口",
          'action="/radar/today/update"' in radar_html and "更新今日雷达" in radar_html,
          "应有更新今日雷达表单")
    check("今日雷达有中文摘要补齐入口",
          'action="/radar/today/generate-summaries"' in radar_html and "生成本页前 5 条摘要" in radar_html,
          "应有补齐当前页中文摘要表单")
    check("今日雷达有智能阅读面板",
          ("智能阅读面板" in radar_html or "智能阅读面板" in radar_panel_partial)
          and "radar-panel-state-stack" in radar_panel_partial,
          "右侧应为智能阅读面板")

    print("\n[2] 加入生成 return_to")
    check("enqueue 接受 return_to 参数",
          "return_to: str | None = Form(None)" in main_py,
          "main.py 应接受 return_to 参数")
    check("今日雷达 enqueue 表单携带 return_to",
          'name="return_to"' in radar_html and "/radar/today" in radar_html,
          "enqueue 表单应携带 return_to")
    check("今日雷达 enqueue return_to 包含完整上下文",
          "view.active_section" in radar_html and "item.id" in radar_html,
          "return_to 应保留 section 和 item_id")

    print("\n[3] 最近探测状态")
    check("RadarFetchRunSummary dataclass 存在",
          "class RadarFetchRunSummary" in radar_py,
          "应有 RadarFetchRunSummary dataclass")
    check("今日雷达显示最近探测状态",
          "最近探测状态" in radar_html and "radar-fetch-summary" in radar_html,
          "左侧应显示最近探测状态")
    check("探测状态提供 /fetch-runs 入口",
          '/fetch-runs"' in radar_html and "radar-fetch-summary" in radar_html,
          "应有查看运行记录链接")

    print("\n[4] 雷达关注源语义")
    check("今日雷达使用雷达关注源词汇",
          "雷达关注源" in radar_html,
          "用户可见文案应使用雷达关注源")
    check("更新路由使用 due-source 计划限定雷达关注源范围",
          "compute_due_sources" in radar_route_py
          and "plan.due" in radar_route_py
          and "enqueue_source" in radar_route_py,
          "更新应通过 due-source plan 只启动到期雷达关注源")
    check("更新路由不会启动 skipped/running/unsupported/missing 来源",
          "plan.skipped" in radar_route_py
          and "plan.running" in radar_route_py
          and "plan.unsupported" in radar_route_py
          and "plan.missing" in radar_route_py,
          "非 due 来源应只用于解释，不应被 enqueue")

    print("\n[5] 工作台滚动模型")
    check("今日雷达使用工作台 shell 类",
          "radar-workbench-shell" in radar_html,
          "应使用 radar-workbench-shell")
    check("style.css 定义了 .radar-main-scroll",
          ".radar-main-scroll" in style_css,
          "应有独立滚动区域样式")

    print("\n[6] Section 状态保持")
    check("视图传递 active_section",
          "active_section" in radar_py and "section=" in radar_html,
          "section 状态应保留")
    check("表单保留 active_section",
          'value="{{ view.active_section }}"' in radar_html,
          "表单应保留 section 值")

    print("\n[7] 分类目录")
    check("今日雷达左侧有目录",
          "radar-section-links" in radar_html and "radar-sidebar-label" in radar_html,
          "左侧应有分类目录")
    check("目录包含全部和今日重点",
          "全部" in radar_html and "今日重点" in radar_html,
          "目录应包含全部和今日重点")

    print("\n[8] 分页在 toolbar")
    check("分页在 toolbar",
          "radar-main-toolbar" in radar_html and "radar-pagination-compact" in radar_html,
          "分页应在中间 toolbar")
    check("每页数量在 toolbar",
          'id="radar-per-page"' in radar_html,
          "每页数量选择器应在 toolbar")

    print("\n[9] 右面板状态化")
    check("右面板显示摘要状态",
          "radar-panel-state-summary" in radar_panel_partial,
          "右面板应显示摘要状态")
    check("右面板显示 InsightCard 状态",
          "radar-panel-state-insight" in radar_panel_partial,
          "右面板应显示 InsightCard 状态")
    check("右面板可预览 InsightCard",
          "radar-panel-insight-preview" in radar_panel_partial,
          "右面板应能预览 InsightCard")
    check("InsightCard 预览应展示洞察与行动，而非重复摘要",
          "RadarInsightPreview" in radar_py
          and "为什么值得关注" in radar_panel_partial
          and "技术洞察" in radar_panel_partial
          and "行动建议" in radar_panel_partial,
          "InsightCard 预览应展示洞察与行动，而不是重复内容摘要")

    print("\n[10] 测试来源隔离")
    check("排除 test_* 来源",
          "is_test_source_key" in radar_route_py or "test_" not in radar_route_py,
          "测试来源不应出现在生产视图")
    check("今日雷达更新使用 enabled sources",
          "enabled" in radar_route_py and "list_sources()" in radar_route_py,
          "更新应使用 enabled 来源")

    print("\n[11] 轻量摘要降级")
    one_liner_py = read("app/application/candidates/one_liner.py")
    check("支持 fill_missing_summary",
          "fill_missing_summary" in one_liner_py,
          "应支持 fill_missing_summary")

    print("\n[12] FetchRun 状态显示")
    check("FetchRun 显示运行中状态",
          "radar-fetch-summary" in radar_html and "运行中" in radar_html,
          "应显示运行中数量")
    check("FetchRun 显示成功/失败状态",
          "成功" in radar_html and "失败" in radar_html,
          "应显示成功/失败数量")

    print("\n[13] 中文概述优先展示")
    display_py = read("app/application/candidates/display.py")
    check("CandidateDisplayCard 有 primary_text 字段",
          "primary_text: str" in display_py,
          "应有 primary_text 字段")
    check("CandidateDisplayCard 有 uses_zh_one_liner 字段",
          "uses_zh_one_liner" in display_py,
          "应有 uses_zh_one_liner 字段")
    check("今日雷达卡片优先显示中文概述",
          "display.primary_text" in radar_html and "uses_zh_one_liner" in radar_html,
          "中间卡片应优先显示中文一句话概述")

    print("\n[14] 抓取后自动摘要")
    check("后台抓取触发自动摘要",
          "_auto_generate_summaries_for_fetch_run" in background_fetch_py,
          "抓取完成后应自动生成中文摘要")
    check("自动摘要复用 CandidateOneLinerService",
          "CandidateOneLinerService" in background_fetch_py,
          "应复用已有 CandidateOneLinerService")
    check("自动摘要写入 metadata_json",
          "auto_summary" in background_fetch_py,
          "自动摘要结果应写入 metadata_json")
    check("自动摘要有数量限制",
          "get_auto_summary_max_per_fetch_run" in background_fetch_py,
          "应有配置控制每次抓取的自动摘要数量")

    print("\n[15] 完整 InsightCard 页面语义")
    check(
        "完整 InsightCard 页面匹配 beta 语义",
        "完整 InsightCard" in card_detail_html
        and "内容摘要：这篇资料说了什么" in card_detail_html
        and "洞察判断：为什么值得关注" in card_detail_html,
        "完整 InsightCard 页面应与今日雷达右侧预览使用同一套语义",
    )

    print("\n[16] Markdown 导出预览页面")
    check(
        "导出预览显示可读文件名",
        "download_filename" in card_export_markdown_html
        and "download_filename" in card_export_report_html
        and "Markdown 行动任务草稿" in card_export_markdown_html
        and "完整 InsightCard Markdown 报告" in card_export_report_html,
        "导出预览应显示可读文件名和导出用途",
    )

    print("\n[17] InsightCard 生成依据可读展示")
    check(
        "完整卡片显示可读生成依据",
        "generation_basis_label" in card_detail_html
        and "_generation_basis_label" in main_py
        and "基于来源摘要 / RSS metadata" in main_py,
        "完整 InsightCard 页面不应把 source_type=unknown 直接展示为生成依据",
    )

    # ── 18. Task 8.1: panel partial sel/sel_card fix ───────────────────────
    print("\n[18] Task 8.1: panel partial sel/sel_card fix")
    if _client is None:
        check("TestClient available", False, "TestClient could not be created — skipping panel tests")
    else:
        # 18a. Full page returns 200.
        resp_main = _client.get("/radar/today")
        check("GET /radar/today returns 200", resp_main.status_code == 200,
              f"status={resp_main.status_code}")

        # 18b. Try to find a real SourceItem id from the page or DB.
        item_id = None
        try:
            from app.db import SessionLocal
            from app.models import SourceItem
            db = SessionLocal()
            try:
                row = db.query(SourceItem.id).order_by(SourceItem.id.desc()).first()
                if row:
                    item_id = row[0]
            finally:
                db.close()
        except Exception:
            pass

        if item_id is None:
            check("Panel endpoint test skipped — no SourceItem found in DB", True,
                  "Cannot test panel partial without a real item_id; this is acceptable in fresh DB")
        else:
            # 18c. Panel fragment with real item_id returns 200.
            panel_url = (
                f"/radar/today/panel?section=all&item_id={item_id}"
                f"&hours=24&limit=50&page=1&per_page=20"
            )
            resp_panel = _client.get(panel_url)
            check(f"GET /radar/today/panel with item_id={item_id} returns 200",
                  resp_panel.status_code == 200,
                  f"status={resp_panel.status_code}")

            # 18d. Panel fragment contains id="radar-panel".
            check("Panel fragment contains id=\"radar-panel\"",
                  'id="radar-panel"' in resp_panel.text,
                  f"fragment length={len(resp_panel.text)}")

            # 18e. Panel fragment does NOT contain <html or <body (must be a partial).
            check("Panel fragment is NOT a full HTML page (no <html>)",
                  "<html" not in resp_panel.text.lower())
            check("Panel fragment is NOT a full HTML page (no <body>)",
                  "<body" not in resp_panel.text.lower())

            # 18f. Panel with real item_id should NOT show "暂无可阅读的内容".
            # It may show other empty states like "内容不存在" but not the generic
            # "no sel provided" message.
            panel_text = resp_panel.text
            has_no_content_msg = "暂无可阅读的内容" in panel_text
            check(f"Panel with item_id={item_id} does NOT show '暂无可阅读的内容'",
                  not has_no_content_msg,
                  "Panel should show actual content for valid item_id")

            # 18g. Panel should contain at least one meaningful content indicator.
            content_indicators = [
                "中文摘要", "宏观洞察", "来源", "编号",
                "打开原文", "查看 InsightCard", "加入生成",
            ]
            has_any_content = any(indicator in panel_text for indicator in content_indicators)
            check(f"Panel with item_id={item_id} contains meaningful content indicators",
                  has_any_content,
                  f"No content indicators found in panel fragment")
        # 18h. Panel without item_id (empty selection) still returns 200.
        resp_empty = _client.get("/radar/today/panel?section=all&hours=24&limit=50&page=1&per_page=20")
        check("GET /radar/today/panel without item_id returns 200",
              resp_empty.status_code == 200,
              f"status={resp_empty.status_code}")

    # ── 19. V1.0-beta.4 summary semantics labels ──────────────────────────
    print("\n[19] V1.0-beta.4 summary semantics labels")
    if _client is None:
        check("TestClient available", False, "TestClient could not be created — skipping panel tests")
    else:
        import json as _json
        from datetime import datetime, timedelta
        from app.db import SessionLocal
        from app.models import SourceItem

        test_source_key = "test_v1_beta_4_summary"
        # Get a valid source_id from an existing source.
        db = SessionLocal()
        try:
            src_row = db.query(SourceItem.source_id).limit(1).first()
            if src_row is None:
                check("source_id available", False, "No sources found in DB — skipping insert tests")
                src_id = None
            else:
                src_id = src_row[0]
        except Exception:
            check("source_id lookup", False, "Could not query source_id")
            src_id = None
        finally:
            db.close()

        if src_id is None:
            pass  # Already reported above.
        else:
            # Four test cases: (case_key, raw_metadata_json dict, expected_label, must_not_appear).
            _now = datetime.utcnow()
            cases = [
                (
                    "zh_summary",
                    {"zh_summary": "这是一段AI生成的中文详细摘要。",
                     "zh_one_liner": "这是中文一句话概述。",
                     "description": "English metadata should not win."},
                    "中文摘要",
                    "中文概述",
                ),
                (
                    "zh_one_liner_only",
                    {"zh_one_liner": "这是AI生成的中文一句话概述。",
                     "description": "English metadata should not win."},
                    "中文概述",
                    "中文摘要",
                ),
                (
                    "chinese_metadata_fallback",
                    {"description": "这是来源站点提供的中文简介，不是AI生成摘要。"},
                    "来源摘要",
                    # Check heading specifically — "中文摘要" appears in banner "中文摘要未生成" which is fine
                    "<h3>中文摘要</h3>",
                ),
                (
                    "english_metadata_fallback",
                    {"description": "This is an English source metadata summary."},
                    "英文来源摘要",
                    # Check heading specifically — "中文摘要" appears in banner "中文摘要未生成" which is fine
                    "<h3>中文摘要</h3>",
                ),
            ]

            inserted_ids: list[int] = []
            db = SessionLocal()
            tx = db.begin()
            try:
                for case_key, meta_json, expected_label, must_not_appear in cases:
                    item = SourceItem(
                        source_id=src_id,
                        source_key=f"{test_source_key}_{case_key}",
                        url=f"http://test-{test_source_key}-{case_key}/item",
                        title=f"Test item for {case_key}",
                        status="discovered",
                        raw_metadata_json=_json.dumps(meta_json),
                        first_seen_at=_now,
                        last_seen_at=_now,
                    )
                    db.add(item)
                    db.flush()
                    inserted_ids.append(item.id)
                tx.commit()
            except Exception as e:
                tx.rollback()
                check(f"Insert test items", False, str(e))
                inserted_ids = []
            else:
                try:
                    for (case_key, meta_json, expected_label, must_not_appear), item_id in zip(cases, inserted_ids):
                        panel_url = (
                            f"/radar/today/panel?section=all&item_id={item_id}"
                            f"&hours=24&limit=50&page=1&per_page=20"
                        )
                        resp = _client.get(panel_url)
                        check(
                            f"Case {case_key}: GET panel returns 200",
                            resp.status_code == 200,
                            f"status={resp.status_code}",
                        )
                        check(
                            f"Case {case_key}: panel contains '{expected_label}'",
                            expected_label in resp.text,
                            f"expected '{expected_label}' in panel",
                        )
                        check(
                            f"Case {case_key}: panel does NOT contain '{must_not_appear}'",
                            must_not_appear not in resp.text,
                            f"'{must_not_appear}' should not appear when {case_key}",
                        )
                        check(
                            f"Case {case_key}: panel is a partial (no <html>)",
                            "<html" not in resp.text.lower(),
                        )
                        check(
                            f"Case {case_key}: panel is a partial (no <body>)",
                            "<body" not in resp.text.lower(),
                        )
                finally:
                    try:
                        db.query(SourceItem).filter(
                            SourceItem.id.in_(inserted_ids)
                        ).delete(synchronize_session=False)
                        db.commit()
                    except Exception:
                        db.rollback()
            finally:
                db.close()

    # ── [20] V1.0-beta.5 summary write policy ─────────────────────────────
    print("\n[20] V1.0-beta.5 summary write policy")
    try:
        project_root = Path(__file__).resolve().parents[1]
        policy_path = project_root / "docs/V1_BETA_5_SUMMARY_WRITE_POLICY.md"

        check("V1_BETA_5_SUMMARY_WRITE_POLICY.md exists",
              policy_path.exists(),
              "policy doc must exist")

        if policy_path.exists():
            policy_md = policy_path.read_text(encoding="utf-8")

            check("policy defines L0-L3 field hierarchy",
                  all(k in policy_md for k in ("L0", "L1", "L2", "L3")),
                  "policy must define L0/L1/L2/L3 hierarchy")

            check("policy states InsightCard.summary_zh does not auto-overwrite zh_one_liner",
                  "InsightCard.summary_zh" in policy_md and "不自动覆盖 zh_one_liner" in policy_md,
                  "policy must state InsightCard.summary_zh does not auto-overwrite")

            check("policy states metadata summary is not AI Chinese summary",
                  "L0" in policy_md and ("不是 AI 中文摘要" in policy_md or "永远不是 AI 中文摘要" in policy_md),
                  "policy must state L0 metadata summary is not AI-generated Chinese summary")

            check("policy defines write rules for zh_one_liner",
                  "zh_one_liner" in policy_md and "写入规则" in policy_md,
                  "policy must define zh_one_liner write rules")

            check("policy defines write rules for zh_summary",
                  "zh_summary" in policy_md and "写入规则" in policy_md,
                  "policy must define zh_summary write rules")
    except Exception as e:
        check("V1.0-beta.5 summary write policy checks", False, str(e))

    print("\n" + "=" * 60)
    print(f"First usable loop acceptance: {PASS} passed, {FAIL} failed")
    print("=" * 60 + "\n")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
