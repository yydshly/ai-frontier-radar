"""Build a full bilingual markdown report from an InsightCard.

V0.9: exports a complete Chinese-English bilingual front-end insight report
for long-term knowledge沉淀 and archival, distinct from the action-task
export in markdown_task.py.

No LLM calls, no network access, no DB writes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import InsightCard, CardDecision, InsightCardBilingualReport


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


def build_full_report_markdown(
    card: "InsightCard",
    decision: "CardDecision | None" = None,
    bilingual_report: "InsightCardBilingualReport | None" = None,
) -> str:
    """Build a full bilingual markdown report from an InsightCard.

    The report is a comprehensive document suitable for long-term knowledge
    archival, not an action-task brief (which is handled by markdown_task.py).

    Report sections:
    1. 原文信息
    2. English Core Summary
    3. Original Key Claims
    4. Key Evidence Points
    5. Key Terms EN-ZH
    6. 中文解说
    7. 中文摘要
    8. 关键事实
    9. 技术洞察
    10. 产品机会
    11. 风险与注意事项
    12. 行动建议
    13. 相关性判断
    14. 用户判断
    15. 保真提示
    16. 解读边界
    17. 后续可继续追问的问题

    Args:
        card: An InsightCard ORM object (not None).
        decision: An optional CardDecision ORM object.
        bilingual_report: An optional InsightCardBilingualReport ORM object.

    Returns:
        A Markdown string (UTF-8 safe).
    """
    # ── Parse InsightCard fields ───────────────────────────────────────────────
    key_points = _parse_json_list(card.key_points_zh)
    technical_insights = _parse_json_list(card.technical_insights_zh)
    product_opportunities = _parse_json_list(card.product_opportunities_zh)
    risks = _parse_json_list(card.risks_zh)
    action_items = _parse_json_list(card.action_items_zh)
    relevance_reasons = _parse_json_list(card.relevance_reasons_zh)
    related_directions = _parse_json_list(card.related_user_directions)

    source_title = card.source_title or "(无标题)"
    source_url = card.source_url or ""
    source_type = card.source_type.value if card.source_type else "unknown"
    source_author = card.source_author or "-"
    source_published_at = card.source_published_at or "-"
    relevance_score = card.relevance_score
    summary_zh = card.summary_zh or "暂无"
    model_name = card.model_name or "-"

    # ── Parse BilingualReport fields ───────────────────────────────────────────
    if bilingual_report:
        try:
            english_key_claims = json.loads(bilingual_report.english_key_claims_json or "[]")
        except (json.JSONDecodeError, TypeError):
            english_key_claims = []
        try:
            english_evidence_points = json.loads(bilingual_report.english_evidence_points_json or "[]")
        except (json.JSONDecodeError, TypeError):
            english_evidence_points = []
        try:
            key_terms = json.loads(bilingual_report.key_terms_json or "[]")
        except (json.JSONDecodeError, TypeError):
            key_terms = []
    else:
        english_key_claims = []
        english_evidence_points = []
        key_terms = []

    # ── Decision ─────────────────────────────────────────────────────────────
    decision_value = decision.decision if decision else None
    decision_note = decision.note if decision else None

    if decision_value:
        from app.card_decisions import get_decision_label
        decision_label = get_decision_label(decision_value)
    else:
        decision_label = "未处理"

    lines: list[str] = []

    # ── 1. Title ─────────────────────────────────────────────────────────────
    lines.append(f"# AI 前沿资料编译报告：{source_title}")
    lines.append("")

    # ── 2. 原文信息 ───────────────────────────────────────────────────────────
    lines.append("## 1. 原文信息")
    lines.append("")
    lines.append(f"- **原文链接**：[{source_url}]({source_url})" if source_url else "- **原文链接**：暂无")
    lines.append(f"- **来源类型**：{source_type}")
    lines.append(f"- **作者**：{source_author}")
    lines.append(f"- **发布时间**：{source_published_at}")
    lines.append(f"- **编译模型**：{model_name}")
    lines.append(f"- **相关性分数**：{relevance_score}/100")
    lines.append(f"- **当前处理状态**：{decision_label}")
    lines.append("")

    # ── 3. English Core Summary ───────────────────────────────────────────────
    lines.append("## 2. English Core Summary")
    lines.append("")
    if bilingual_report and bilingual_report.english_core_summary:
        lines.append(bilingual_report.english_core_summary)
    else:
        lines.append("暂无中英双语报告。")
    lines.append("")

    # ── 4. Original Key Claims ────────────────────────────────────────────────
    lines.append("## 3. Original Key Claims")
    lines.append("")
    if english_key_claims:
        for claim in english_key_claims:
            lines.append(f"  - {claim}")
    else:
        lines.append("  暂无中英双语报告。")
    lines.append("")

    # ── 5. Key Evidence Points ───────────────────────────────────────────────
    lines.append("## 4. Key Evidence Points")
    lines.append("")
    if english_evidence_points:
        for point in english_evidence_points:
            lines.append(f"  - {point}")
    else:
        lines.append("  暂无中英双语报告。")
    lines.append("")

    # ── 6. Key Terms EN-ZH ──────────────────────────────────────────────────
    lines.append("## 5. Key Terms EN-ZH")
    lines.append("")
    if key_terms:
        lines.append("| English | 中文 | 说明 |")
        lines.append("|---|---|---|")
        for term in key_terms:
            en = term.get("en", "") if isinstance(term, dict) else ""
            zh = term.get("zh", "") if isinstance(term, dict) else ""
            note_zh = term.get("note_zh", "") if isinstance(term, dict) else ""
            lines.append(f"| {en} | {zh} | {note_zh} |")
    else:
        lines.append("暂无中英双语报告。")
    lines.append("")

    # ── 7. 中文解说 ─────────────────────────────────────────────────────────
    lines.append("## 6. 中文解说")
    lines.append("")
    if bilingual_report and bilingual_report.chinese_explanation:
        lines.append(bilingual_report.chinese_explanation)
    else:
        lines.append("暂无中英双语报告。")
    lines.append("")

    # ── 8. 中文摘要 ─────────────────────────────────────────────────────────
    lines.append("## 7. 中文摘要")
    lines.append("")
    lines.append(summary_zh)
    lines.append("")

    # ── 9. 关键事实 ─────────────────────────────────────────────────────────
    lines.append(_format_list_section("8. 关键事实", key_points))

    # ── 10. 技术洞察 ─────────────────────────────────────────────────────────
    lines.append(_format_list_section("9. 技术洞察", technical_insights))

    # ── 11. 产品机会 ────────────────────────────────────────────────────────
    lines.append(_format_list_section("10. 产品机会", product_opportunities))

    # ── 12. 风险与注意事项 ─────────────────────────────────────────────────
    lines.append(_format_list_section("11. 风险与注意事项", risks))

    # ── 13. 行动建议 ────────────────────────────────────────────────────────
    lines.append(_format_list_section("12. 行动建议", action_items))

    # ── 14. 相关性判断 ─────────────────────────────────────────────────────
    lines.append("## 13. 相关性判断")
    lines.append("")
    lines.append(f"**相关性分数**：{relevance_score}/100")
    lines.append("")
    lines.append("### 匹配的关注方向")
    lines.append("")
    if related_directions:
        for direction in related_directions:
            lines.append(f"  - {direction}")
    else:
        lines.append("  暂无")
    lines.append("")
    lines.append("### 判断理由")
    lines.append("")
    if relevance_reasons:
        for reason in relevance_reasons:
            lines.append(f"  - {reason}")
    else:
        lines.append("  暂无")
    lines.append("")

    # ── 15. 用户判断 ────────────────────────────────────────────────────────
    lines.append("## 14. 用户判断")
    lines.append("")
    lines.append(f"- **当前判断**：{decision_label}")
    if decision_note:
        lines.append(f"- **用户备注**：{decision_note}")
    else:
        lines.append("- **用户备注**：暂无")
    lines.append("")

    # ── 16. 保真提示 ────────────────────────────────────────────────────────
    lines.append("## 15. 保真提示")
    lines.append("")
    if bilingual_report and bilingual_report.fidelity_notes_zh:
        lines.append(bilingual_report.fidelity_notes_zh)
    else:
        lines.append("暂无保真提示。")
    lines.append("")

    # ── 17. 解读边界 ───────────────────────────────────────────────────────
    lines.append("## 16. 解读边界")
    lines.append("")
    if bilingual_report and bilingual_report.interpretation_boundary_zh:
        lines.append(bilingual_report.interpretation_boundary_zh)
    else:
        lines.append("暂无解读边界说明。")
    lines.append("")

    # ── 18. 后续可继续追问的问题 ───────────────────────────────────────────
    lines.append("## 17. 后续可继续追问的问题")
    lines.append("")
    lines.append("1. 这篇资料和我的项目有什么关系？")
    lines.append("2. 哪些结论是原文明确说的？")
    lines.append("3. 哪些部分属于模型推论？")
    lines.append("4. 哪些方向值得继续调研？")
    lines.append("")

    return "\n".join(lines)
