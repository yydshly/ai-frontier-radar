#!/usr/bin/env python3
"""
acceptance_first_usable_loop.py — V1.0-beta First Usable Loop 轻量验收脚本。

只做静态 / 轻量检查，不联网，不调用 LLM，不抓取外部 URL。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

    print("[1] 今日雷达主链路入口")
    check("今日雷达有更新入口",
          'action="/radar/today/update"' in radar_html and "更新今日雷达" in radar_html,
          "应有更新今日雷达表单")
    check("今日雷达有中文摘要补齐入口",
          'action="/radar/today/generate-summaries"' in radar_html and "补齐当前页中文摘要" in radar_html,
          "应有补齐当前页中文摘要表单")
    check("今日雷达有智能阅读面板",
          "智能阅读面板" in radar_html and "radar-panel-state-stack" in radar_html,
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
    check("更新路由限定雷达关注源范围",
          "configured_keys" in radar_route_py and "Source.source_key.in_(configured_keys)" in radar_route_py,
          "更新应限定在 configured_keys 范围内")

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
          "radar-panel-state-summary" in radar_html,
          "右面板应显示摘要状态")
    check("右面板显示 InsightCard 状态",
          "radar-panel-state-insight" in radar_html,
          "右面板应显示 InsightCard 状态")
    check("右面板可预览 InsightCard",
          "radar-panel-insight-preview" in radar_html,
          "右面板应能预览 InsightCard")
    check("InsightCard 预览应展示洞察与行动，而非重复摘要",
          "RadarInsightPreview" in radar_py
          and "为什么值得关注" in radar_html
          and "技术洞察" in radar_html
          and "行动建议" in radar_html,
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

    print("\n" + "=" * 60)
    print(f"First usable loop acceptance: {PASS} passed, {FAIL} failed")
    print("=" * 60 + "\n")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
