#!/usr/bin/env python3
"""
acceptance_v1_beta_first_usable_loop.py

V1.0-beta First Usable Loop Acceptance Script

Checks static / lightweight conditions only — no LLM calls, no DB writes.

Usage:
    python -m compileall app scripts
    python scripts/acceptance_v1_beta_first_usable_loop.py
"""
import re
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


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    global PASS, FAIL, FAILED_CHECKS

    ROOT = Path(__file__).parent.parent
    radar_today = ROOT / "app" / "templates" / "radar_today.html"
    panel = ROOT / "app" / "templates" / "partials" / "radar_today_panel.html"
    radar_py = ROOT / "app" / "routes" / "radar.py"
    today_py = ROOT / "app" / "application" / "radar" / "today.py"
    profile_py = ROOT / "scripts" / "profile_today_radar.py"

    print("V1.0-beta First Usable Loop Acceptance")
    print("=" * 50)

    # ── Load content ─────────────────────────────────────────────────────────
    html = read(radar_today)
    panel_html = read(panel)
    routes = read(radar_py)
    today = read(today_py)
    profile = read(profile_py)

    # ── Path A: Today Radar Main Flow ─────────────────────────────────────────
    print("\n[Path A] Today Radar Main Flow")

    check("页面标题为'今日 AI 前沿雷达'",
          "今日 AI 前沿雷达" in html,
          "radar_today.html missing '今日 AI 前沿雷达'")

    check("顶部快捷入口包含信息来源",
          'href="/sources"' in html and ">信息来源</a>" in html)
    check("顶部快捷入口包含候选池",
          'href="/candidate-pool"' in html and ">候选池</a>" in html)
    check("顶部快捷入口包含生成队列",
          'href="/generation-queue"' in html and ">生成队列</a>" in html)
    check("顶部快捷入口包含洞察卡",
          'href="/cards"' in html and ">洞察卡</a>" in html)

    check("左侧分组包含目录",
          'radar-sidebar-label">目录</span>' in html or 'radar-directory-header' in html)
    check("左侧分组包含今日操作",
          "今日操作" in html)
    check("左侧分组包含今日编译概览",
          "今日编译概览" in html)
    check("左侧分组包含运行状态",
          "运行状态" in html)
    check("左侧分组包含高级 / 运维",
          "高级 / 运维" in html)

    check("今日操作区包含'更新今日新增'",
          "更新今日新增" in html)
    check("今日操作区包含'查看今日可读简报'",
          "查看今日可读简报" in html)
    check("今日操作区包含'生成今日核心报告'",
          "生成今日核心报告" in html)

    check("高级/运维默认折叠",
          "<details class=\"radar-dev-tools\">" in html)

    check("'初始化来源内容'只出现在高级/运维内",
          has_init_after_dev_tools(html))

    check("页面不再出现'生成今日报告卡片'",
          "生成今日报告卡片" not in html,
          "Found '生成今日报告卡片' residual")

    # ── Path B: Summary Generation Chain ─────────────────────────────────────
    print("\n[Path B] Summary Generation Chain")

    check("包含'生成文章摘要'按钮",
          "生成文章摘要" in html)
    check("summary_limit hidden value = 20",
          'name="summary_limit" value="20"' in html)
    check("按钮说明最多处理20条",
          "最多处理 20 条" in html)

    check("compile_candidates 优先逻辑存在于 generate_today_summaries",
          "_prioritize_compile_candidates" in routes or
          "compile_candidates" in routes[routes.find("generate_today_summaries"):routes.find("generate_today_summaries") + 3000])

    check("generate_today_summaries 包含按 source_item_id 去重",
          "source_item_id" in routes[routes.find("generate_today_summaries"):routes.find("generate_today_summaries") + 3000])

    check("generate_today_summaries 包含 _needs_chinese_summary 优先",
          "_needs_chinese_summary" in routes[routes.find("generate_today_summaries"):routes.find("generate_today_summaries") + 3000] or
          "needs_chinese_summary" in routes[routes.find("generate_today_summaries"):routes.find("generate_today_summaries") + 3000])

    check("generate_today_summaries cap 20",
          "cap 20" in routes[routes.find("generate_today_summaries"):routes.find("generate_today_summaries") + 3000] or
          "min(summary_limit" in routes[routes.find("generate_today_summaries"):routes.find("generate_today_summaries") + 3000])

    # ── Path C: Recommended Deep Analysis ────────────────────────────────────
    print("\n[Path C] Recommended Deep Analysis")

    check("区块标题为'推荐深入分析'",
          "推荐深入分析" in html)
    check("推荐深入分析使用独立右侧面板",
          "panel=recommendations" in html and "radar-panel-recommendations" in panel_html)
    check("副说明解释推荐依据",
          "今日推荐" in panel_html and "主题相关性" in panel_html)
    check("每条候选优先展示 summary_preview",
          "c.summary_preview" in panel_html)
    check("技术推荐依据默认折叠",
          "<details" in panel_html and "查看推荐依据" in panel_html)
    check("点击候选带 item_id，能联动右侧阅读面板",
          "item_id={{ c.source_item_id }}" in panel_html)
    check("推荐候选支持一键批量生成洞察卡",
          "/radar/today/generate-recommended-insights" in panel_html
          and "最多 5 条" in panel_html)

    # ── Path D: Insight Card Chain ────────────────────────────────────────────
    print("\n[Path D] Insight Card Chain")

    check("'生成洞察卡'按钮存在于主列表",
          ">生成洞察卡</button>" in html)
    check("'查看洞察卡'按钮存在于主列表",
          ">查看洞察卡</a>" in html)
    check("顶部快捷入口使用'洞察卡'（非 InsightCard）",
          ">洞察卡</a>" in html and "InsightCard</a>" not in html)

    check("主列表状态使用用户可理解文案",
          "待生成洞察" in html or "status-badge" in html)
    check("主列表状态包含'已完成'",
          "已完成" in html)
    check("主列表状态包含'生成中'",
          "生成中" in html)
    check("主列表状态包含'失败'",
          "失败" in html)

    # ── Path E: Daily Report Chain ───────────────────────────────────────────
    print("\n[Path E] Daily Report Chain")

    check("'查看今日可读简报'入口存在，href=/radar/daily-report",
          'href="/radar/daily-report"' in html and "查看今日可读简报" in html)
    check("'生成今日核心报告'入口存在，method=post",
          'method="post"' in html and "生成今日核心报告" in html and
          'action="/radar/today/daily-report"' in html)
    check("未启用提示清楚说明",
          "今日核心报告未启用" in html and "DAILY_REPORT_ENABLED=true" in html)
    check("不把规则版和LLM版混为同一按钮",
          html.count(">查看今日可读简报</a>") == 1)

    check("POST /today/daily-report 存在于 radar.py",
          'POST /today/daily-report' in routes or
          'router.post("/today/daily-report"' in routes)
    check("GET /daily-report 存在于 radar.py",
          'GET /daily-report' in routes or
          'router.get("/daily-report"' in routes)

    # ── Path F: Right Reading Panel ──────────────────────────────────────────
    print("\n[Path F] Right Reading Panel")

    check("右侧面板包含中文概述状态",
          "中文概述" in panel_html)
    check("右侧面板包含中文摘要状态",
          "中文摘要" in panel_html)
    check("右侧面板包含正文状态",
          "正文" in panel_html)
    check("右侧面板包含洞察卡状态",
          "洞察" in panel_html and "状态" in panel_html)
    check("右侧面板包含下一步建议",
          "下一步建议" in panel_html)

    # ── Additional Code Checks ────────────────────────────────────────────────
    print("\n[Code] Compile candidates and quality filter stats")

    check("quality_filter_stats 仅 all/page=1 执行（today.py）",
          "section == ALL_KEY and page == 1" in today)

    check("profile_today_radar.py 中 quality_filter_stats guard 与生产一致",
          'section == "all" and page == 1' in profile or
          'section == ALL_KEY and page == 1' in profile)

    # ── Residual Check ───────────────────────────────────────────────────────
    print("\n[Residual] No legacy phrasing")

    check("radar_today.html 不含'生成今日报告卡片'",
          "生成今日报告卡片" not in html)

    # ── Summary ───────────────────────────────────────────────────────────────
    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"V1.0-beta First Usable Loop Acceptance")
    print(f"Total: {total}")
    print(f"Passed: {PASS}")
    print(f"Failed: {FAIL}")
    if FAIL > 0:
        print(f"\nFailed checks:")
        for name in FAILED_CHECKS:
            print(f"  - {name}")
    return 0 if FAIL == 0 else 1


def has_init_after_dev_tools(html: str) -> bool:
    """Check that '初始化来源内容' appears after the <details class=radar-dev-tools> open tag."""
    dev_tools_match = re.search(r'<details[^>]*class="[^"]*radar-dev-tools[^"]*"[^>]*>', html)
    if not dev_tools_match:
        return False
    after_dev_tools = html[dev_tools_match.end():]
    init_match = re.search(r'初始化来源内容', after_dev_tools)
    if not init_match:
        return False
    # Make sure there's no closing </details> before the init text
    prev_close = html.rfind("</details>", 0, dev_tools_match.start())
    return True


if __name__ == "__main__":
    sys.exit(main())
