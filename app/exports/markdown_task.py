"""Build a Markdown task draft from an InsightCard + optional CardDecision.

V0.5: converts a "转成行动" InsightCard into a readable Markdown task
that can be copied, saved, or passed to an AI execution model.
No LLM call, no network access, no DB writes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import InsightCard, CardDecision


def _parse_json_list(value: str | None) -> list[str]:
    """Parse a JSON list string into a Python list.

    Returns an empty list on failure (malformed JSON, None, etc.).
    Does not raise.
    """
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _format_list_section(title: str, items: list[str], indent: str = "  ") -> str:
    """Render a Markdown section containing a bullet list.

    If items is empty, renders "暂无" instead.
    """
    lines = [f"### {title}", ""]
    if items:
        for item in items:
            lines.append(f"{indent}- {item}")
    else:
        lines.append(f"{indent}暂无")
    lines.append("")
    return "\n".join(lines)


def build_action_markdown(
    card: "InsightCard",
    decision: "CardDecision | None" = None,
) -> str:
    """Build a Markdown task draft from an InsightCard.

    The output is a structured Markdown document containing:
    - 原文信息 (original source info)
    - 中文摘要
    - 为什么值得行动
    - 关键事实 / 技术洞察 / 产品机会 / 风险与注意事项 / 行动建议
    - 用户备注
    - 可交给 AI 执行模型的任务草稿

    Args:
        card: An InsightCard ORM object (not None).
        decision: An optional CardDecision ORM object.

    Returns:
        A Markdown string (UTF-8 safe).
    """
    # Parse JSON fields
    key_points = _parse_json_list(card.key_points_zh)
    technical_insights = _parse_json_list(card.technical_insights_zh)
    product_opportunities = _parse_json_list(card.product_opportunities_zh)
    risks = _parse_json_list(card.risks_zh)
    action_items = _parse_json_list(card.action_items_zh)
    relevance_reasons = _parse_json_list(card.relevance_reasons_zh)
    related_directions = _parse_json_list(card.related_user_directions)

    # Card fields
    source_title = card.source_title or "(无标题)"
    source_url = card.source_url or ""
    source_type = card.source_type.value if card.source_type else "unknown"
    source_author = card.source_author or "-"
    source_published_at = card.source_published_at or "-"
    relevance_score = card.relevance_score
    summary_zh = card.summary_zh or "暂无"

    # Decision fields
    decision_value = decision.decision if decision else None
    decision_note = decision.note if decision else None

    # Relevance label
    if decision_value:
        from app.card_decisions import get_decision_label
        decision_label = get_decision_label(decision_value)
    else:
        decision_label = "未处理"

    lines: list[str] = []

    # ── Title ────────────────────────────────────────────────────────────────
    lines.append(f"# 行动任务：{source_title}")
    lines.append("")

    # ── 原文信息 ──────────────────────────────────────────────────────────────
    lines.append("## 原文信息")
    lines.append("")
    lines.append(f"- **原文链接**：[{source_url}]({source_url})" if source_url else "- **原文链接**：暂无")
    lines.append(f"- **来源类型**：{source_type}")
    lines.append(f"- **作者**：{source_author}")
    lines.append(f"- **发布时间**：{source_published_at}")
    lines.append(f"- **相关性分数**：{relevance_score}/100")
    lines.append(f"- **当前处理状态**：{decision_label}")
    if decision_note:
        lines.append(f"- **用户备注**：{decision_note}")
    else:
        lines.append("- **用户备注**：暂无")
    lines.append("")

    # ── 中文摘要 ─────────────────────────────────────────────────────────────
    lines.append("## 中文摘要")
    lines.append("")
    lines.append(summary_zh)
    lines.append("")

    # ── 为什么值得行动 ───────────────────────────────────────────────────────
    lines.append("## 为什么值得行动")
    lines.append("")
    if relevance_reasons:
        for reason in relevance_reasons:
            lines.append(f"  - {reason}")
    else:
        lines.append("  暂无")
    lines.append("")

    # ── 关键事实 ─────────────────────────────────────────────────────────────
    lines.append(_format_list_section("关键事实", key_points))

    # ── 技术洞察 ────────────────────────────────────────────────────────────
    lines.append(_format_list_section("技术洞察", technical_insights))

    # ── 产品机会 ────────────────────────────────────────────────────────────
    lines.append(_format_list_section("产品机会", product_opportunities))

    # ── 风险与注意事项 ──────────────────────────────────────────────────────
    lines.append(_format_list_section("风险与注意事项", risks))

    # ── 行动建议 ────────────────────────────────────────────────────────────
    lines.append(_format_list_section("行动建议", action_items))

    # ── 匹配的关注方向 ─────────────────────────────────────────────────────
    lines.append("### 匹配的关注方向")
    lines.append("")
    if related_directions:
        for direction in related_directions:
            lines.append(f"  - {direction}")
    else:
        lines.append("  暂无")
    lines.append("")

    # ── 可交给 AI 执行模型的任务草稿 ───────────────────────────────────────
    lines.append("## 可交给 AI 执行模型的任务草稿")
    lines.append("")
    lines.append("请基于以上资料，帮助我进一步拆解：")
    lines.append("")
    lines.append("1. 这篇资料对我的项目有什么启发？")
    lines.append("2. 哪些点可以转化为产品功能？")
    lines.append("3. 哪些点需要继续调研？")
    lines.append("4. 下一步最小可执行动作是什么？")
    lines.append("")

    return "\n".join(lines)
