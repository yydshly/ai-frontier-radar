"""Bilingual report generation for InsightCard.

V0.8: generates an English core content layer with Chinese explanation
to help users understand the original material while preserving fidelity.

Does NOT make network requests itself; the LLM call is done by the caller.
"""
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import InsightCard, InsightCardBilingualReport


def build_bilingual_report_prompt(card: InsightCard, source_text: str | None = None) -> str:
    """Build a prompt for generating a bilingual report from an InsightCard.

    Args:
        card: An InsightCard ORM object.
        source_text: Optional original source text (raw or cleaned). If not provided,
            cleaned_text_preview and existing card fields are used as context.

    Returns:
        A prompt string for the LLM.
    """
    source_title = card.source_title or "(无标题)"
    source_url = card.source_url or ""
    summary_zh = card.summary_zh or ""
    key_points_raw = card.key_points_zh or "[]"
    technical_insights_raw = card.technical_insights_zh or "[]"
    product_opportunities_raw = card.product_opportunities_zh or "[]"
    risks_raw = card.risks_zh or "[]"
    action_items_raw = card.action_items_zh or "[]"

    def parse_json_list(raw: str) -> list[str]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    key_points = parse_json_list(key_points_raw)
    technical_insights = parse_json_list(technical_insights_raw)
    product_opportunities = parse_json_list(product_opportunities_raw)
    risks = parse_json_list(risks_raw)
    action_items = parse_json_list(action_items_raw)

    context_parts = [
        f"# Source Information",
        f"Title: {source_title}",
        f"URL: {source_url}",
        "",
        f"# Chinese InsightCard Summary (for reference)",
        summary_zh,
        "",
    ]

    if key_points:
        context_parts.append("# Key Facts (关键事实)")
        for point in key_points:
            context_parts.append(f"- {point}")
        context_parts.append("")

    if technical_insights:
        context_parts.append("# Technical Insights (技术洞察)")
        for insight in technical_insights:
            context_parts.append(f"- {insight}")
        context_parts.append("")

    if product_opportunities:
        context_parts.append("# Product Opportunities (产品机会)")
        for opp in product_opportunities:
            context_parts.append(f"- {opp}")
        context_parts.append("")

    if risks:
        context_parts.append("# Risks (风险)")
        for risk in risks:
            context_parts.append(f"- {risk}")
        context_parts.append("")

    if action_items:
        context_parts.append("# Action Items (行动建议)")
        for item in action_items:
            context_parts.append(f"- {item}")
        context_parts.append("")

    if source_text:
        context_parts.append("# Original Source Text (excerpt)")
        context_parts.append(source_text[:3000])  # Limit to first 3000 chars
        context_parts.append("")

    context = "\n".join(context_parts)

    prompt = f"""You are generating a bilingual (English-Chinese) report for an AI Frontier Radar InsightCard.

## Goal
Help Chinese-speaking users who are not comfortable reading English understand the core content of this article while preserving fidelity to the original material.

## Language Rules (CRITICAL)
- Fields: english_core_summary, english_key_claims, english_evidence_points, key_terms.en MUST be in ENGLISH.
- Fields: chinese_explanation, fidelity_notes_zh, interpretation_boundary_zh, key_terms.zh, key_terms.note_zh MUST be in CHINESE.
- Do NOT mix languages within a single field.
- Do NOT write Chinese sentences in english_core_summary.
- Do NOT write English sentences in chinese_explanation.

## Output Format
Generate a JSON object with these fields:
- "english_core_summary": A faithful English summary of the article's main point (1-3 sentences). Written in English as if by an English speaker. NOT a translation of Chinese text.
- "english_key_claims": List of 2-8 main claims or arguments made in the article. Written in English. Max 8 items.
- "english_evidence_points": List of 2-8 evidence points, data, or specific information from the article. Written in English. Max 8 items.
- "key_terms": List of up to 10 key technical terms with Chinese translations. Each item: {{"en": "...", "zh": "...", "note_zh": "..."}}.
- "chinese_explanation": A clear Chinese explanation of what this article is about and why it matters. Written in Chinese. Do NOT simply translate english_core_summary.
- "fidelity_notes_zh": Notes in Chinese about what is faithfully from the source vs. what is interpretation.
- "interpretation_boundary_zh": A clear statement in Chinese explaining that product opportunities, action recommendations, and technical significance are model inferences, NOT the article's own conclusions.

## Fidelity Rules
1. Only include claims that appear in the source text or established InsightCard context.
2. If the source does not explicitly state something, do not claim it does.
3. Product opportunities and action items from the existing InsightCard are MODEL INTERPRETATION, not source conclusions.
4. If uncertain about a claim, write less — do not fabricate.
5. Keep each english_key_claims item to 1-2 sentences.
6. Keep each english_evidence_points item to 1-2 sentences.
7. Return ONLY the JSON object, no preamble or explanation.

## Source Context
{context}

## Output
Return ONLY the JSON object, no additional text.
"""
    return prompt


def parse_bilingual_report_response(raw: str) -> dict:
    """Parse LLM response into a structured dict.

    Args:
        raw: Raw string response from LLM.

    Returns:
        A dict with keys:
            - english_core_summary: str
            - english_key_claims: list[str]
            - english_evidence_points: list[str]
            - key_terms: list[dict]
            - chinese_explanation: str
            - fidelity_notes_zh: str
            - interpretation_boundary_zh: str
            - parse_error: str | None (present if parsing failed)

    If JSON parsing fails, returns a dict with parse_error set and other fields empty.
    """
    try:
        # Try to extract JSON from the response
        text = raw.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Find the JSON start line
            json_start = -1
            json_end = -1
            for i, line in enumerate(lines):
                if i == 0 and line.startswith("```"):
                    continue
                if i == len(lines) - 1 and line.startswith("```"):
                    continue
                if json_start == -1:
                    json_start = i
                json_end = i
            if json_start != -1 and json_end != -1:
                text = "\n".join(lines[json_start:json_end + 1])

        data = json.loads(text)

        # Validate and extract required fields
        result = {
            "english_core_summary": str(data.get("english_core_summary", "")) if data.get("english_core_summary") else "",
            "english_key_claims": [],
            "english_evidence_points": [],
            "key_terms": [],
            "chinese_explanation": str(data.get("chinese_explanation", "")) if data.get("chinese_explanation") else "",
            "fidelity_notes_zh": str(data.get("fidelity_notes_zh", "")) if data.get("fidelity_notes_zh") else "",
            "interpretation_boundary_zh": str(data.get("interpretation_boundary_zh", "")) if data.get("interpretation_boundary_zh") else "",
            "parse_error": None,
        }

        # Validate english_key_claims
        claims = data.get("english_key_claims", [])
        if isinstance(claims, list):
            result["english_key_claims"] = [str(c) for c in claims[:8]]  # Max 8

        # Validate english_evidence_points
        evidence = data.get("english_evidence_points", [])
        if isinstance(evidence, list):
            result["english_evidence_points"] = [str(e) for e in evidence[:8]]  # Max 8

        # Validate key_terms
        terms = data.get("key_terms", [])
        if isinstance(terms, list):
            validated_terms = []
            for t in terms[:10]:  # Max 10
                if isinstance(t, dict):
                    validated_terms.append({
                        "en": str(t.get("en", "")),
                        "zh": str(t.get("zh", "")),
                        "note_zh": str(t.get("note_zh", "")),
                    })
            result["key_terms"] = validated_terms

        return result

    except json.JSONDecodeError as e:
        return {
            "english_core_summary": "",
            "english_key_claims": [],
            "english_evidence_points": [],
            "key_terms": [],
            "chinese_explanation": "",
            "fidelity_notes_zh": "",
            "interpretation_boundary_zh": "",
            "parse_error": f"JSON parse error: {e}",
        }
    except Exception as e:
        return {
            "english_core_summary": "",
            "english_key_claims": [],
            "english_evidence_points": [],
            "key_terms": [],
            "chinese_explanation": "",
            "fidelity_notes_zh": "",
            "interpretation_boundary_zh": "",
            "parse_error": f"Parse error: {e}",
        }


def upsert_bilingual_report(
    db: Session,
    card: InsightCard,
    report_data: dict,
) -> InsightCardBilingualReport:
    """Insert or update a bilingual report for an InsightCard.

    If a report already exists for this card_id, updates it.
    Otherwise inserts a new report.

    Args:
        db: SQLAlchemy Session.
        card: InsightCard ORM object.
        report_data: Dict from parse_bilingual_report_response().

    Returns:
        The InsightCardBilingualReport ORM object.
    """
    # Check for existing report
    existing = (
        db.query(InsightCardBilingualReport)
        .filter(InsightCardBilingualReport.card_id == card.id)
        .first()
    )

    if existing is None:
        # Insert new
        report = InsightCardBilingualReport(
            card_id=card.id,
            english_core_summary=report_data.get("english_core_summary"),
            english_key_claims_json=json.dumps(report_data.get("english_key_claims", [])),
            english_evidence_points_json=json.dumps(report_data.get("english_evidence_points", [])),
            key_terms_json=json.dumps(report_data.get("key_terms", [])),
            chinese_explanation=report_data.get("chinese_explanation"),
            fidelity_notes_zh=report_data.get("fidelity_notes_zh"),
            interpretation_boundary_zh=report_data.get("interpretation_boundary_zh"),
        )
        db.add(report)
    else:
        # Update existing
        existing.english_core_summary = report_data.get("english_core_summary")
        existing.english_key_claims_json = json.dumps(report_data.get("english_key_claims", []))
        existing.english_evidence_points_json = json.dumps(report_data.get("english_evidence_points", []))
        existing.key_terms_json = json.dumps(report_data.get("key_terms", []))
        existing.chinese_explanation = report_data.get("chinese_explanation")
        existing.fidelity_notes_zh = report_data.get("fidelity_notes_zh")
        existing.interpretation_boundary_zh = report_data.get("interpretation_boundary_zh")
        report = existing

    db.commit()
    db.refresh(report)
    return report


def build_mock_bilingual_report(card: InsightCard) -> dict:
    """Build a mock bilingual report for testing purposes.

    This function does NOT call any LLM or make network requests.

    Args:
        card: An InsightCard ORM object.

    Returns:
        A dict matching the structure from parse_bilingual_report_response().
    """
    source_title = card.source_title or "(无标题)"

    return {
        "english_core_summary": f"[MOCK] This article discusses {source_title}. "
                               f"The key development is an advancement in AI technology "
                               f"that enables more capable and reliable AI systems.",
        "english_key_claims": [
            f"The article on {source_title} presents a significant AI development.",
            "The technology demonstrates improved performance on key benchmarks.",
            "The approach builds on previous research in the field.",
            "The authors claim practical applications are within reach.",
            "Industry experts have responded with both enthusiasm and caution.",
            "The work represents a step toward more capable AI assistants.",
        ],
        "english_evidence_points": [
            "Performance improvements of 15-30% on standard benchmarks were reported.",
            "The model architecture incorporates recent advances in transformer design.",
            "Training data includes curated sources from academic and industry labs.",
            "Safety evaluations were conducted following established red-team protocols.",
            "The research team has published related papers in top venues.",
            "Open-source components are being released to the research community.",
        ],
        "key_terms": [
            {"en": "large language model", "zh": "大型语言模型", "note_zh": "指能够理解和生成文本的深度学习模型"},
            {"en": "benchmark", "zh": "基准测试", "note_zh": "用于评估AI系统性能的标准测试"},
            {"en": "transformer", "zh": "Transformer架构", "note_zh": "一种常用的深度学习模型架构"},
            {"en": "red-team", "zh": "红队测试", "note_zh": "模拟攻击者进行的安全测试"},
            {"en": "inference", "zh": "推理", "note_zh": "使用模型进行预测的过程"},
            {"en": "fine-tuning", "zh": "微调", "note_zh": "在预训练模型基础上进行额外训练"},
        ],
        "chinese_explanation": f"这篇关于「{source_title}」的文章介绍了一个重要的人工智能技术进展。"
                               f"简单来说，这项技术让AI能够更好地理解和生成内容，"
                               f"在多个标准测试中表现有明显提升。"
                               f"文章认为这项技术有实际应用的价值，"
                               f"但也提到需要关注安全性和可靠性问题。"
                               f"对于AI从业者来说，这个进展值得关注，"
                               f"因为它可能影响未来的产品开发方向。",
        "fidelity_notes_zh": "【保真提示】以下内容来自原文："
                           "英文核心摘要部分是对原文主要论点的忠实概括；"
                           "英文关键主张列表中的每一条都有原文依据；"
                           "英文证据点列表中的数据均来自原文报告。",
        "interpretation_boundary_zh": "【解读边界说明】"
                                   "以下内容属于模型推论和个人建议，不等同于原文结论："
                                   "中文解说中对技术意义和产品机会的判断；"
                                   "行动建议部分；"
                                   "技术前景推测。",
        "parse_error": None,
    }
