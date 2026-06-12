"""FastAPI main application."""
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import InsightCard, CardStatus, Source, SourceItem, FetchRun, CardDecision, InsightCardBilingualReport
from app.schemas import HealthResponse
from app.sources import sync_sources_config_to_db, get_featured_sources
from app.services.insight_compiler import compile_url
from app.intake import classify_url_by_pattern
from app.application.source_items.compile_service import SourceItemCompileService
from app.application.source_items.background_compile import (
    BackgroundCompileService,
    run_source_item_compile_in_background,
)
from app.card_decisions import ALLOWED_CARD_DECISIONS, is_valid_decision, get_decision_label
from app.logging_config import setup_logging, get_logger
from app.exports.markdown_task import build_action_markdown
from app.exports.markdown_report import build_full_report_markdown
from app.version import APP_VERSION
from app.url_safety import is_safe_external_url
from app.routes.project_docs import router as project_docs_router
from app.routes.candidate_pool import router as candidate_pool_router
from app.routes.fetch_runs import router as fetch_runs_router, is_test_source_key
from app.routes.radar import router as radar_router


# ── Shared card display helper (V1.0-alpha.8.6) ─────────────────────────────
def _build_card_display_data(card: InsightCard, decision_row: CardDecision | None = None) -> dict:
    """Build display-friendly fields for an InsightCard.

    Handles blocked/failed cards with friendly title fallback, status display,
    and relevance score display. Used by both index and /cards list.
    """
    from urllib.parse import urlparse

    decision_value = decision_row.decision if decision_row else None

    # Determine if this is an intake-blocked card
    is_intake_blocked = (
        card.status == CardStatus.FAILED
        and card.error_message
        and "[intake:blocked]" in card.error_message
    )
    is_failed = card.status == CardStatus.FAILED

    # Compute display title
    if card.source_title:
        display_title = card.source_title
    elif is_intake_blocked:
        parsed = urlparse(card.source_url)
        path = parsed.path if parsed.path else ""
        host_or_path = (parsed.netloc + path) if parsed.netloc else card.source_url
        if len(host_or_path) > 60:
            host_or_path = host_or_path[:57] + "..."
        display_title = f"已拦截：{host_or_path}"
    elif is_failed:
        parsed = urlparse(card.source_url)
        path = parsed.path if parsed.path else ""
        host_or_path = (parsed.netloc + path) if parsed.netloc else card.source_url
        if len(host_or_path) > 60:
            host_or_path = host_or_path[:57] + "..."
        display_title = f"处理失败：{host_or_path}"
    else:
        display_title = card.source_title or "无标题"

    # Compute status display
    if is_intake_blocked:
        status_display = "已拦截"
    elif is_failed:
        status_display = "处理失败"
    else:
        status_display = card.status.value if card.status else "unknown"

    # Relevance score display: "-" for failed/blocked
    relevance_score_display = "-" if (is_intake_blocked or is_failed) else card.relevance_score

    return {
        "display_title": display_title,
        "status_display": status_display,
        "is_intake_blocked": is_intake_blocked,
        "is_failed": is_failed,
        "relevance_score_display": relevance_score_display,
        "decision_value": decision_value,
    }


# ── Markdown export filename helpers ─────────────────────────────────────────

import re
from urllib.parse import quote


def _sanitize_filename_part(value: str | None, *, max_len: int = 48) -> str:
    """Sanitize a string to be safe inside a filename.

    Removes Windows/macOS unsafe characters, collapses whitespace,
    and truncates to max_len.
    """
    if not value:
        return "untitled"

    text = " ".join(str(value).strip().split())
    if not text:
        return "untitled"

    # Remove Windows/macOS unsafe filename characters.
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)

    # Replace whitespace with underscore.
    text = re.sub(r"\s+", "_", text)

    # Avoid too many separators.
    text = re.sub(r"_+", "_", text).strip("._- ")

    if not text:
        return "untitled"

    if len(text) > max_len:
        text = text[:max_len].rstrip("._- ")

    return text or "untitled"


def _build_markdown_download_filename(
    card: InsightCard,
    *,
    export_kind: str,
) -> str:
    """Build a readable, safe download filename for InsightCard Markdown exports.

    Format: YYYY-MM-DD_AI前沿雷达_{id}_{title}_{suffix}.md
    """
    date_part = (
        card.created_at.strftime("%Y-%m-%d")
        if card.created_at
        else datetime.utcnow().strftime("%Y-%m-%d")
    )

    title_part = _sanitize_filename_part(card.source_title or "untitled", max_len=56)

    suffix_map = {
        "task": "行动任务",
        "report": "完整报告",
    }
    suffix = suffix_map.get(export_kind, "导出")

    return f"{date_part}_AI前沿雷达_{card.id}_{title_part}_{suffix}.md"


def _markdown_download_headers(filename: str) -> dict[str, str]:
    """Build Content-Disposition headers for Markdown file download.

    Provides UTF-8 filename* encoding with ASCII fallback for browser compatibility.
    """
    ascii_fallback = "ai-frontier-radar-export.md"
    encoded = quote(filename)
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_fallback}"; '
            f"filename*=UTF-8''{encoded}"
        )
    }


# ── InsightCard display helpers ────────────────────────────────────────────────

def _source_type_label(card: InsightCard) -> str:
    """Return a human-readable content type label for display purposes."""
    if not card.source_type:
        return "未标注"

    value = card.source_type.value if hasattr(card.source_type, "value") else str(card.source_type)

    if value == "html":
        return "网页正文"
    if value == "pdf":
        return "PDF 文本"
    if value == "unknown":
        return "未标注"

    return value


def _generation_basis_label(card: InsightCard, source_item: SourceItem | None = None) -> str:
    """Return a human-readable generation basis label for display purposes.

    This is a display-only derived field. It does not persist anything.
    RSS/metadata snapshot cards are identified by checking the linked SourceItem.
    """
    # RSS / metadata snapshot cards: linked SourceItem exists with raw_metadata_json
    if source_item is not None and source_item.raw_metadata_json:
        return "基于来源摘要 / RSS metadata"

    # Full-text parsing based on raw_text_path
    if card.raw_text_path:
        if card.source_type and card.source_type.value == "pdf":
            return "基于 PDF 文本解析"
        if card.source_type and card.source_type.value == "html":
            return "基于网页正文解析"
        return "基于全文解析"

    # Fallback: source_type-based label
    if card.source_type:
        value = card.source_type.value if hasattr(card.source_type, "value") else str(card.source_type)
        if value == "pdf":
            return "基于 PDF 文本解析"
        if value == "html":
            return "基于网页正文解析"

    return "生成依据未标注"


# Setup
setup_logging()
logger = get_logger(__name__)

# Initialize database on startup
init_db()

# FastAPI app
app = FastAPI(title="AI Frontier Radar", version=APP_VERSION)

# Base directory for templates and static
BASE_DIR = Path(__file__).resolve().parent

# Jinja2 templates
from app.context_processors import inject_sources_nav, _format_dt
templates = Jinja2Templates(directory=BASE_DIR / "templates", context_processors=[inject_sources_nav])
templates.env.filters["format_dt"] = _format_dt

# Static files - mount before any routes
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# --- Routes ---

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    """System design and technical explanation page.

    V1.0-alpha.8.4: explains the complete processing pipeline, source control,
    URL type classification, failure handling, and LLM analysis boundaries.
    """
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """V0.6: Home page upgraded to personal AI frontier workbench.

    Aggregates dashboard statistics, recent records, and action suggestions
    without calling LLM or network access.
    """
    db = next(get_db())
    try:
        featured_sources = get_featured_sources()

        # ── SourceItem statistics ────────────────────────────────────────────
        source_items_discovered_count = (
            db.query(SourceItem).filter(SourceItem.status == "discovered").count()
        )
        source_items_failed_count = (
            db.query(SourceItem).filter(SourceItem.status == "failed").count()
        )

        # ── Candidate Pool statistics (V1.0-beta.2) ─────────────────────────
        # Candidate pool uses the same SourceItem model with various statuses
        candidate_pool_total_count = db.query(SourceItem).count()
        candidate_pool_discovered_count = (
            db.query(SourceItem).filter(SourceItem.status == "discovered").count()
        )
        candidate_pool_compiling_count = (
            db.query(SourceItem).filter(SourceItem.status == "compiling").count()
        )
        candidate_pool_failed_count = (
            db.query(SourceItem).filter(SourceItem.status == "failed").count()
        )

        # ── InsightCard statistics ──────────────────────────────────────────
        cards_total_count = db.query(InsightCard).count()

        # V1.0-alpha.8.6: unhandled = COMPLETED cards without any CardDecision
        # (excludes failed / blocked cards from unhandled count)
        completed_card_ids = [
            r[0] for r in
            db.query(InsightCard.id).filter(InsightCard.status == CardStatus.COMPLETED).all()
        ]
        if completed_card_ids:
            handled_card_ids = {
                r[0] for r in
                db.query(CardDecision.card_id)
                .filter(CardDecision.card_id.in_(completed_card_ids))
                .distinct()
                .all()
            }
            cards_unhandled_count = len(set(completed_card_ids) - handled_card_ids)
        else:
            cards_unhandled_count = 0

        # Count by decision value
        decision_counts: dict[str, int] = {}
        for decision_value in ALLOWED_CARD_DECISIONS.keys():
            count = (
                db.query(CardDecision)
                .filter(CardDecision.decision == decision_value)
                .count()
            )
            decision_counts[decision_value] = count

        cards_worth_attention_count = decision_counts.get("worth_attention", 0)
        cards_related_to_me_count = decision_counts.get("related_to_me", 0)
        cards_read_later_count = decision_counts.get("read_later", 0)
        cards_ignore_count = decision_counts.get("ignore", 0)
        cards_to_action_count = decision_counts.get("to_action", 0)

        # ── Recent SourceItems (last 5, discovered first) ──────────────────
        recent_source_items = (
            db.query(SourceItem)
            .order_by(SourceItem.last_seen_at.desc())
            .limit(5)
            .all()
        )
        recent_source_items_data = []
        for item in recent_source_items:
            recent_source_items_data.append({
                "id": item.id,
                "source_key": item.source_key,
                "title": item.title or "无标题",
                "url": item.url,
                "status": item.status,
                "insight_card_id": item.insight_card_id,
                "last_seen_at": item.last_seen_at,
            })

        recent_fetch_runs = (
            db.query(FetchRun)
            .order_by(FetchRun.created_at.desc())
            .limit(5)
            .all()
        )
        recent_fetch_runs_data = []
        for run in recent_fetch_runs:
            recent_fetch_runs_data.append({
                "id": run.id,
                "source_key": run.source_key,
                "status": run.status,
                "items_new": run.items_new or 0,
                "items_found": run.items_found or 0,
                "items_updated": run.items_updated or 0,
                "items_failed": run.items_failed or 0,
                "started_at": run.started_at,
                "created_at": run.created_at,
            })

        # ── Recent InsightCards (last 5) ───────────────────────────────────
        recent_cards = (
            db.query(InsightCard)
            .order_by(InsightCard.created_at.desc())
            .limit(5)
            .all()
        )
        recent_card_ids = [c.id for c in recent_cards]
        recent_decisions: dict[int, CardDecision] = {}
        if recent_card_ids:
            decision_rows = (
                db.query(CardDecision)
                .filter(CardDecision.card_id.in_(recent_card_ids))
                .all()
            )
            recent_decisions = {row.card_id: row for row in decision_rows}

        recent_cards_data = []
        for card in recent_cards:
            decision_row = recent_decisions.get(card.id)
            display = _build_card_display_data(card, decision_row)
            decision_value = display["decision_value"]
            decision_note = decision_row.note if decision_row else None

            recent_cards_data.append({
                "id": card.id,
                "source_title": display["display_title"],
                "source_url": card.source_url,
                "status": card.status.value if card.status else "unknown",
                "status_display": display["status_display"],
                "is_intake_blocked": display["is_intake_blocked"],
                "is_failed": display["is_failed"],
                "decision_value": decision_value,
                "decision_label": get_decision_label(decision_value),
                "decision_note": decision_note or "",
                "relevance_score": display["relevance_score_display"],
                "created_at": card.created_at,
            })

        # ── Demo data entry (V1.0-alpha.1) ────────────────────────────────
        demo_source_item = None
        demo_card = None
        demo_source_item_row = (
            db.query(SourceItem)
            .filter(SourceItem.source_key == "demo_ai_frontier")
            .first()
        )
        if demo_source_item_row and demo_source_item_row.insight_card_id:
            demo_card = (
                db.query(InsightCard)
                .filter(InsightCard.id == demo_source_item_row.insight_card_id)
                .first()
            )
            if demo_card and demo_card.status == CardStatus.COMPLETED:
                demo_source_item = demo_source_item_row

        # ── Build context ──────────────────────────────────────────────────
        dashboard_stats = {
            "source_items_discovered": source_items_discovered_count,
            "source_items_failed": source_items_failed_count,
            "cards_total": cards_total_count,
            "cards_unhandled": cards_unhandled_count,
            "cards_worth_attention": cards_worth_attention_count,
            "cards_related_to_me": cards_related_to_me_count,
            "cards_read_later": cards_read_later_count,
            "cards_ignore": cards_ignore_count,
            "cards_to_action": cards_to_action_count,
            # V1.0-beta.2: Candidate Pool statistics
            "candidate_pool_total": candidate_pool_total_count,
            "candidate_pool_discovered": candidate_pool_discovered_count,
            "candidate_pool_compiling": candidate_pool_compiling_count,
            "candidate_pool_failed": candidate_pool_failed_count,
        }

        return templates.TemplateResponse("index.html", {
            "request": request,
            "show_url_compile_bar": True,
            "featured_sources": featured_sources,
            "dashboard_stats": dashboard_stats,
            "recent_fetch_runs": recent_fetch_runs_data,
            "recent_source_items": recent_source_items_data,
            "recent_cards": recent_cards_data,
            "demo_source_item": {
                "id": demo_source_item.id,
                "title": demo_source_item.title or "无标题",
                "url": demo_source_item.url,
                "status": demo_source_item.status,
            } if demo_source_item else None,
            "demo_card": {
                "id": demo_card.id,
                "source_title": demo_card.source_title or "无标题",
                "source_url": demo_card.source_url,
            } if demo_card else None,
        })
    finally:
        db.close()


@app.post("/compile")
def compile_source(url: str = Form(...)):
    """
    Submit a URL for InsightCard compilation.

    Flow:
    1. Validate URL
    2. Classify URL type via intake classifier
    3a. If blocked by strategy: create failed card with reason, redirect to it
    3b. If allowed: proceed with compile_url pipeline
    4. Redirect to card detail page (always, including failed cards)
    """
    logger.info(f"Received compile request for URL: {url}")

    # Basic URL validation
    if not is_safe_external_url(url):
        return RedirectResponse(url="/", status_code=303)

    # ── Intake classification gate ─────────────────────────────────
    decision = classify_url_by_pattern(url)
    logger.info(f"Intake classification: {decision.page_type.value} | "
                f"strategy={decision.strategy.value} | compile={decision.can_compile_directly}")

    db = next(get_db())
    try:
        # ── Blocked by strategy: create failed card without calling LLM ──
        if not decision.can_compile_directly:
            from app.models import SourceType
            card = InsightCard(
                source_url=url,
                source_type=SourceType.UNKNOWN,
                status=CardStatus.FAILED,
                error_message=f"[intake:blocked] {decision.reason}",
                relevance_score=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(card)
            db.commit()
            db.refresh(card)
            logger.info(f"Intake blocked URL {url}: created failed card {card.id}")
            return RedirectResponse(url=f"/cards/{card.id}", status_code=303)

        # ── Allowed: proceed with normal compile pipeline ──
        card = compile_url(db, url)
        return RedirectResponse(url=f"/cards/{card.id}", status_code=303)
    except Exception as e:
        logger.error(f"Unexpected error during compilation: {e}")
        return RedirectResponse(url="/", status_code=303)
    finally:
        db.close()


@app.get("/cards", response_class=HTMLResponse)
def list_cards(request: Request, decision: str | None = None):
    """List InsightCards with optional decision filter.

    V0.4.1: supports ?decision=unhandled | worth_attention | related_to_me |
    read_later | ignore | to_action. Invalid values are treated as "all".
    """
    db = next(get_db())
    try:
        # Normalize filter: 'unhandled' or a known decision value, else empty
        filter_decision = ""
        if decision == "unhandled":
            filter_decision = "unhandled"
        elif decision and is_valid_decision(decision):
            filter_decision = decision
        # else: invalid / empty -> show all (filter_decision stays "")

        cards = (
            db.query(InsightCard)
            .order_by(InsightCard.created_at.desc())
            .all()
        )

        # V0.4.1: load all decisions in one query (avoid N+1)
        card_ids = [card.id for card in cards]
        decision_by_card_id: dict[int, CardDecision] = {}
        if card_ids:
            decision_rows = (
                db.query(CardDecision)
                .filter(CardDecision.card_id.in_(card_ids))
                .all()
            )
            decision_by_card_id = {row.card_id: row for row in decision_rows}

        # Build cards_data and apply Python-level filter
        cards_data = []
        for card in cards:
            decision_row = decision_by_card_id.get(card.id)
            display = _build_card_display_data(card, decision_row)
            decision_value = display["decision_value"]

            # Apply filter
            if filter_decision == "unhandled":
                # V1.0-alpha.8.6.1: only show completed cards without decisions
                if card.status != CardStatus.COMPLETED:
                    continue
                if decision_value is not None:
                    continue
            elif filter_decision and filter_decision != "unhandled":
                if decision_value != filter_decision:
                    continue

            cards_data.append({
                "id": card.id,
                "source_title": display["display_title"],
                "source_url": card.source_url,
                "status": display["status_display"],
                "status_value": card.status.value if card.status else "unknown",
                "relevance_score": display["relevance_score_display"],
                "created_at": card.created_at,
                "decision_value": decision_value,
                "decision_label": get_decision_label(decision_value),
                "is_intake_blocked": display["is_intake_blocked"],
                "is_failed": display["is_failed"],
            })

        # Determine filter label for template display
        filter_decision_label = ""
        if filter_decision == "unhandled":
            filter_decision_label = "未处理"
        elif filter_decision and is_valid_decision(filter_decision):
            filter_decision_label = get_decision_label(filter_decision)

        from app.routes.fetch_runs import safe_external_url

        context = {
            "request": request,
            "cards": cards_data,
            "filter_decision": filter_decision,
            "filter_decision_label": filter_decision_label,
            "decision_options": ALLOWED_CARD_DECISIONS,
            "decision_filter_options": [
                ("unhandled", "未处理"),
                *ALLOWED_CARD_DECISIONS.items(),
            ],
            "total_cards": len(cards),
            "filtered_cards": len(cards_data),
            "safe_external_url": safe_external_url,
        }
        return templates.TemplateResponse("cards.html", context)
    finally:
        db.close()


@app.get("/cards/{card_id}", response_class=HTMLResponse)
def card_detail(request: Request, card_id: int):
    """Show InsightCard detail."""
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        # V0.4: load user's current decision
        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )
        current_decision = decision_row.decision if decision_row else None
        current_note = decision_row.note if decision_row else None

        # V0.8: load bilingual report if exists
        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        # Load linked SourceItem (for RSS/metadata snapshot cards)
        source_item = (
            db.query(SourceItem)
            .filter(SourceItem.insight_card_id == card.id)
            .first()
        )

        # Parse JSON fields for template
        def parse_json_field(value):
            if not value:
                return []
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []

        # Parse bilingual report JSON fields
        english_key_claims = []
        english_evidence_points = []
        key_terms = []
        if bilingual_report:
            try:
                if bilingual_report.english_key_claims_json:
                    english_key_claims = json.loads(bilingual_report.english_key_claims_json)
            except (json.JSONDecodeError, TypeError):
                english_key_claims = []
            try:
                if bilingual_report.english_evidence_points_json:
                    english_evidence_points = json.loads(bilingual_report.english_evidence_points_json)
            except (json.JSONDecodeError, TypeError):
                english_evidence_points = []
            try:
                if bilingual_report.key_terms_json:
                    key_terms = json.loads(bilingual_report.key_terms_json)
            except (json.JSONDecodeError, TypeError):
                key_terms = []

        # Pass stable string values for template comparisons
        context = {
            "request": request,
            "card": card,
            "status_value": card.status.value if card.status else "unknown",
            "source_type_value": _source_type_label(card),
            "generation_basis_label": _generation_basis_label(card, source_item),
            "key_points": parse_json_field(card.key_points_zh),
            "technical_insights": parse_json_field(card.technical_insights_zh),
            "product_opportunities": parse_json_field(card.product_opportunities_zh),
            "risks": parse_json_field(card.risks_zh),
            "action_items": parse_json_field(card.action_items_zh),
            "related_directions": parse_json_field(card.related_user_directions),
            "relevance_reasons": parse_json_field(card.relevance_reasons_zh),
            # V0.4 decision context
            "current_decision": current_decision,
            "current_note": current_note or "",
            "current_decision_label": get_decision_label(current_decision),
            "decision_options": ALLOWED_CARD_DECISIONS,
            # V0.8 bilingual report context
            "bilingual_report": bilingual_report,
            "english_key_claims": english_key_claims,
            "english_evidence_points": english_evidence_points,
            "key_terms": key_terms,
        }
        return templates.TemplateResponse("card_detail.html", context)
    finally:
        db.close()


@app.post("/cards/{card_id}/bilingual-report")
def generate_bilingual_report(card_id: int):
    """Generate or regenerate a bilingual report for an InsightCard.

    V0.8: creates an English core content layer with Chinese explanation
    to help users understand the original material while preserving fidelity.

    If a report already exists, updates it (upsert behavior).
    On failure, does NOT cause 500 - failure info is stored in fidelity_notes_zh.
    """
    from app.services.bilingual_report import (
        build_bilingual_report_prompt,
        upsert_bilingual_report,
        build_mock_bilingual_report,
    )

    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        # Try to read raw text from raw_text_path if available
        source_text = None
        if card.raw_text_path:
            raw_path = Path(card.raw_text_path)
            if raw_path.exists() and raw_path.is_file():
                try:
                    source_text = raw_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fall back to cleaned_text_preview if no raw text
        if not source_text:
            source_text = card.cleaned_text_preview

        # Build prompt
        prompt = build_bilingual_report_prompt(card, source_text)

        # Check if we should use mock mode (no API key or explicit flag)
        use_mock = os.environ.get("MINIMAX_API_KEY") in ("", None)

        if use_mock:
            # Use mock report for testing/development
            report_data = build_mock_bilingual_report(card)
        else:
            # Call LLM for real report
            try:
                from app.llm.factory import create_llm_client

                client = create_llm_client()
                llm_result = client.generate_json(
                    system_prompt="You are a helpful assistant that outputs JSON.",
                    user_prompt=prompt,
                )
                # generate_json returns a dict directly; parse_bilingual_report_response
                # is for raw string responses from call_llm, not needed here.
                report_data = llm_result
            except Exception as e:
                logger.error(f"LLM call failed for bilingual report: {e}")
                # Store error info rather than failing
                report_data = {
                    "english_core_summary": "",
                    "english_key_claims": [],
                    "english_evidence_points": [],
                    "key_terms": [],
                    "chinese_explanation": "",
                    "fidelity_notes_zh": f"[错误] 生成双语报告时发生问题：{e}",
                    "interpretation_boundary_zh": "生成失败，内容仅供参考。",
                    "parse_error": str(e),
                }

        # Upsert the report
        try:
            upsert_bilingual_report(db, card, report_data)
        except Exception as e:
            logger.error(f"Failed to upsert bilingual report: {e}")

        return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
    finally:
        db.close()


@app.post("/cards/{card_id}/decision")
def update_card_decision(card_id: int, decision: str = Form(...), note: str = Form("")):
    """Update (or create) the user's decision for a card.

    One CardDecision per card. Re-submitting updates the existing row.
    Invalid decision values are rejected and redirect back to the detail page
    without writing to the database.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        if not is_valid_decision(decision):
            # Invalid decision: don't write, just redirect back to detail
            return RedirectResponse(url=f"/cards/{card_id}", status_code=303)

        # Normalize note: strip whitespace, treat empty as None
        note_clean = (note or "").strip()
        note_value: str | None = note_clean if note_clean else None

        existing = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card_id)
            .first()
        )

        if existing is None:
            new_decision = CardDecision(
                card_id=card_id,
                decision=decision,
                note=note_value,
            )
            db.add(new_decision)
        else:
            existing.decision = decision
            existing.note = note_value
            # updated_at is auto-updated by onupdate=datetime.utcnow

        db.commit()
        return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
    finally:
        db.close()


@app.post("/cards/{card_id}/delete")
def delete_failed_card(card_id: int):
    """Delete a failed InsightCard and its associated data.

    Only allows deletion of cards with status=FAILED to prevent accidental
    deletion of completed cards. Cleans up CardDecision and
    InsightCardBilingualReport before deleting the InsightCard.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        # Only allow deletion of failed cards
        if card.status != CardStatus.FAILED:
            logger.warning(f"Attempted to delete non-failed card {card_id} (status={card.status})")
            return RedirectResponse(url=f"/cards/{card_id}", status_code=303)

        # V1.0-alpha.8.6: clear SourceItem references before deleting card
        # to avoid dangling insight_card_id foreign keys
        db.query(SourceItem).filter(SourceItem.insight_card_id == card_id).update({
            "insight_card_id": None,
            "status": "failed",
            "error_message": "关联的失败记录已删除，可重新处理或忽略",
            "updated_at": datetime.utcnow(),
        })

        # Delete in correct order to handle foreign key constraints
        # 1. CardDecision
        db.query(CardDecision).filter(CardDecision.card_id == card_id).delete()
        # 2. InsightCardBilingualReport
        db.query(InsightCardBilingualReport).filter(InsightCardBilingualReport.card_id == card_id).delete()
        # 3. InsightCard itself
        db.query(InsightCard).filter(InsightCard.id == card_id).delete()

        db.commit()
        logger.info(f"Deleted failed card {card_id}")
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"Error deleting card {card_id}: {e}")
        db.rollback()
        return RedirectResponse(url=f"/cards/{card_id}", status_code=303)
    finally:
        db.close()


@app.get("/cards/{card_id}/export-markdown", response_class=HTMLResponse)
def card_export_markdown(request: Request, card_id: int):
    """Preview the Markdown task draft for an InsightCard.

    V0.5: renders a full-page preview of the generated Markdown.
    V0.8: includes bilingual report if available.
    Does not modify the database or call LLM.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_action_markdown(card, decision_row, bilingual_report)

        download_filename = _build_markdown_download_filename(card, export_kind="task")

        return templates.TemplateResponse("card_export_markdown.html", {
            "request": request,
            "card": card,
            "decision": decision_row,
            "markdown_text": markdown_text,
            "download_filename": download_filename,
        })
    finally:
        db.close()


@app.get("/cards/{card_id}/export-markdown/download")
def card_export_markdown_download(card_id: int):
    """Download the Markdown task draft for an InsightCard as a .md file.

    V0.5: streams the file content directly without writing to disk.
    V0.8: includes bilingual report if available.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_action_markdown(card, decision_row, bilingual_report)

        filename = _build_markdown_download_filename(card, export_kind="task")
        return PlainTextResponse(
            content=markdown_text,
            headers=_markdown_download_headers(filename),
        )
    finally:
        db.close()


@app.get("/cards/{card_id}/export-report", response_class=HTMLResponse)
def card_export_report_preview(request: Request, card_id: int):
    """Preview the full bilingual markdown report for an InsightCard.

    V0.9: renders a full-page preview of the complete bilingual report.
    V1.0-alpha.8.5: changed to structured HTML reading mode.
    Does not modify the database or call LLM.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        # Load linked SourceItem (for RSS/metadata snapshot cards)
        source_item = (
            db.query(SourceItem)
            .filter(SourceItem.insight_card_id == card.id)
            .first()
        )

        markdown_text = build_full_report_markdown(card, decision_row, bilingual_report)

        # ── Build structured view data for HTML preview ───────────────────────
        import json as _json

        def _safe_json_list(value):
            if not value:
                return []
            try:
                parsed = _json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except (_json.JSONDecodeError, TypeError):
                return []

        def _safe_json_dict(value):
            if not value:
                return {}
            try:
                parsed = _json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (_json.JSONDecodeError, TypeError):
                return {}

        # Decision label
        if decision_row:
            from app.card_decisions import get_decision_label
            decision_label = get_decision_label(decision_row.decision)
            decision_note = decision_row.note or ""
        else:
            decision_label = "未处理"
            decision_note = ""

        # Parse bilingual report
        if bilingual_report:
            english_key_claims = _safe_json_list(bilingual_report.english_key_claims_json)
            english_evidence_points = _safe_json_list(bilingual_report.english_evidence_points_json)
            key_terms = _safe_json_list(bilingual_report.key_terms_json)
            fidelity_notes = bilingual_report.fidelity_notes_zh or ""
            interpretation_boundary = bilingual_report.interpretation_boundary_zh or ""
        else:
            english_key_claims = []
            english_evidence_points = []
            key_terms = []
            fidelity_notes = ""
            interpretation_boundary = ""

        # Parse card JSON fields
        key_points = _safe_json_list(card.key_points_zh)
        technical_insights = _safe_json_list(card.technical_insights_zh)
        product_opportunities = _safe_json_list(card.product_opportunities_zh)
        risks = _safe_json_list(card.risks_zh)
        action_items = _safe_json_list(card.action_items_zh)
        relevance_reasons = _safe_json_list(card.relevance_reasons_zh)
        related_directions = _safe_json_list(card.related_user_directions)

        # Source fields
        source_title = card.source_title or "(无标题)"
        source_url = card.source_url or ""
        source_type = _source_type_label(card)
        generation_basis_label = _generation_basis_label(card, source_item)
        source_author = card.source_author or "-"
        source_published_at = card.source_published_at or "-"
        relevance_score = card.relevance_score
        summary_zh = card.summary_zh or "暂无"
        model_name = card.model_name or "-"

        # Has bilingual report flag
        has_bilingual_report = bool(bilingual_report and bilingual_report.english_core_summary)

        return templates.TemplateResponse("card_export_report.html", {
            "request": request,
            "card": card,
            "markdown_text": markdown_text,
            # Structured view data
            "source_title": source_title,
            "source_url": source_url,
            "source_type": source_type,
            "generation_basis_label": generation_basis_label,
            "source_author": source_author,
            "source_published_at": source_published_at,
            "relevance_score": relevance_score,
            "model_name": model_name,
            "summary_zh": summary_zh,
            "decision_label": decision_label,
            "decision_note": decision_note,
            # Lists
            "key_points": key_points,
            "technical_insights": technical_insights,
            "product_opportunities": product_opportunities,
            "risks": risks,
            "action_items": action_items,
            "relevance_reasons": relevance_reasons,
            "related_directions": related_directions,
            # Bilingual report
            "has_bilingual_report": has_bilingual_report,
            "english_core_summary": bilingual_report.english_core_summary if bilingual_report else "",
            "english_key_claims": english_key_claims,
            "english_evidence_points": english_evidence_points,
            "key_terms": key_terms,
            "chinese_explanation": bilingual_report.chinese_explanation if bilingual_report else "",
            "fidelity_notes": fidelity_notes,
            "interpretation_boundary": interpretation_boundary,
            # Download filename
            "download_filename": _build_markdown_download_filename(card, export_kind="report"),
        })
    finally:
        db.close()


@app.get("/cards/{card_id}/export-report/download")
def card_export_report_download(card_id: int):
    """Download the full bilingual markdown report for an InsightCard as a .md file.

    V0.9: streams the file content directly without writing to disk.
    """
    db = next(get_db())
    try:
        card = db.query(InsightCard).filter(InsightCard.id == card_id).first()
        if not card:
            return RedirectResponse(url="/cards", status_code=303)

        decision_row = (
            db.query(CardDecision)
            .filter(CardDecision.card_id == card.id)
            .first()
        )

        bilingual_report = (
            db.query(InsightCardBilingualReport)
            .filter(InsightCardBilingualReport.card_id == card.id)
            .first()
        )

        markdown_text = build_full_report_markdown(card, decision_row, bilingual_report)

        filename = _build_markdown_download_filename(card, export_kind="report")
        return PlainTextResponse(
            content=markdown_text,
            headers=_markdown_download_headers(filename),
        )
    finally:
        db.close()


@app.get("/sources", response_class=HTMLResponse)
def list_sources_page(request: Request, include_test: int = Query(0, ge=0, le=1)):
    """List all configured sources from database."""
    return _render_sources_page(request, include_test=include_test)


# V1.0-beta.13: Human-readable error messages for fetch failures
_FETCH_ERROR_KEYWORDS: tuple[tuple[list[str], str], ...] = (
    (["timeout", "timed out"], "请求超时"),
    (["connection", "connect"], "连接失败"),
    (["404", "not found", "不存在"], "页面不存在（404）"),
    (["403", "forbidden", "拒绝访问"], "页面拒绝访问（403）"),
    (["500", "server error", "服务器错误"], "服务器错误"),
    (["no candidates", "未发现候选", "没有发现链接"], "未发现任何候选链接"),
    (["empty", "no content", "内容为空"], "页面内容为空"),
    (["parse", "解析失败", "structure"], "页面结构解析失败"),
    (["selector", "css", "xpath"], "页面选择器匹配失败"),
    (["rss", "feed"], "RSS/Feed 获取失败"),
    (["encoding", "编码"], "页面编码解析失败"),
    (["ssl", "certificate", "证书"], "SSL 证书错误"),
    (["redirect", "重定向"], "页面重定向次数过多"),
    (["size", "too large", "太大"], "页面体积过大已截断"),
    (["content-type", "content type", "类型不支持"], "页面内容类型不支持"),
)


def _humanize_fetch_error(error: str | None, strategy: str) -> str | None:
    """Convert a raw fetch error message to a short Chinese description."""
    if not error:
        return None
    error_lower = error.lower()
    for keywords, label in _FETCH_ERROR_KEYWORDS:
        if any(kw.lower() in error_lower for kw in keywords):
            return f"{label}：{error[:60]}"
    # No keyword match — return truncated original
    return error[:80] if len(error) > 80 else error


def _render_sources_page(
    request: Request,
    *,
    include_test: int = 0,
    custom_preview: dict | None = None,
    custom_form: dict | None = None,
):
    db = next(get_db())
    try:
        # Sync config to DB first (no network access)
        sync_result = sync_sources_config_to_db(db)

        # Query sources from DB, sorted by category then source_key
        sources_orm = (
            db.query(Source)
            .order_by(Source.category, Source.source_key)
            .all()
        )
        show_test_sources = bool(include_test)
        if not show_test_sources:
            sources_orm = [s for s in sources_orm if not is_test_source_key(s.source_key)]

        # Build FetchRun health map for all source keys
        source_keys = [s.source_key for s in sources_orm]
        from app.application.fetch_runs.services import FetchRunService
        service = FetchRunService(db)
        health_map = service.get_source_health_map(source_keys)

        # Convert to plain dicts for template
        from app.application.sources.strategy_labels import describe_fetch_strategy
        from app.application.sources.effective_strategy import compute_effective_strategy
        from app.sources.config_loader import get_source as get_config_source
        sources_data = []
        for s in sources_orm:
            health = health_map.get(s.source_key)
            # Effective strategy (RSS when feed_url exists) — centralized helper.
            effective_strategy = compute_effective_strategy(s.feed_url, s.fetch_strategy)
            effective_label = describe_fetch_strategy(effective_strategy)
            # V1.0-beta.13: recommended strategy (RSS if feed works, HTML index otherwise)
            recommended_strategy = effective_strategy
            # V1.0-beta.13: needs_review when HTML index is used (no RSS feed)
            needs_review = (effective_strategy == "html_index")
            # V1.0-beta.14: RSS status label (three-tier, replaces "需补充 RSS")
            # Look up config for strategy_notes to determine if manually verified.
            cfg = get_config_source(s.source_key)
            rss_status_label = None
            rss_status_class = ""
            if effective_strategy == "rss":
                rss_status_label = "RSS 已验证"
                rss_status_class = "rss-ok"
            elif effective_strategy == "html_index":
                notes = (cfg.strategy_notes or "") if cfg else ""
                if any(kw in notes for kw in ("No public RSS", "No reliable RSS", "HTML index fallback", "fallback")):
                    rss_status_label = "未发现可靠 RSS"
                    rss_status_class = "rss-warn"
                elif not notes and needs_review:
                    rss_status_label = "待核查 RSS"
                    rss_status_class = "rss-pending"
            # V1.0-beta.13: readable error message
            raw_error = (health.latest_error_message if health else None) or s.last_error_message
            # A stale-timeout recovery is not a real fetch failure — the source
            # had a stuck run cleaned up. Surface it neutrally, not as red 失败.
            is_stale_recovered = bool(raw_error and "[stale-timeout]" in raw_error)
            readable_error = _humanize_fetch_error(raw_error, effective_strategy)
            sources_data.append({
                "source_key": s.source_key,
                "name": s.name,
                "category": s.category,
                "source_type": s.source_type,
                "fetch_strategy": s.fetch_strategy,
                "enabled": s.enabled,
                "homepage_url": s.homepage_url,
                "feed_url": s.feed_url,
                "fetch_interval_hours": s.fetch_interval_hours,
                "last_checked_at": s.last_checked_at,
                "last_success_at": s.last_success_at,
                "last_error_message": s.last_error_message,
                # V1.0-beta.4: FetchRun health overlay
                "fetch_run_status": health.latest_status if health else None,
                "fetch_run_started_at": health.latest_started_at if health else None,
                "fetch_run_finished_at": health.latest_finished_at if health else None,
                "fetch_run_items_found": health.latest_items_found if health else 0,
                "fetch_run_items_new": health.latest_items_new if health else 0,
                "fetch_run_error_message": health.latest_error_message if health else None,
                # V1.0-beta.13: effective strategy label
                "effective_strategy": effective_strategy,
                "effective_strategy_label": effective_label,
                # V1.0-beta.13: recommended strategy and needs_review
                "recommended_strategy": recommended_strategy,
                "needs_review": needs_review,
                # V1.0-beta.14: RSS status (three-tier, replaces "需补充 RSS")
                "rss_status_label": rss_status_label,
                "rss_status_class": rss_status_class,
                # V1.0-beta.13: readable error
                "readable_error": readable_error,
                # Stale-timeout recovery is not a real failure (show neutrally).
                "is_stale_recovered": is_stale_recovered,
            })

        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request,
                "sources": sources_data,
                "sync_result": sync_result,
                "include_test": show_test_sources,
                "include_test_url": "/sources" if show_test_sources else "/sources?include_test=1",
                "custom_preview": custom_preview,
                "custom_form": custom_form or {},
            },
        )
    finally:
        db.close()


@app.post("/sources/custom/preview", response_class=HTMLResponse)
def preview_custom_source_page(
    request: Request,
    include_test: int = Form(0),
    name: str = Form(""),
    fetch_strategy: str = Form("rss"),
    homepage_url: str = Form(""),
    feed_url: str = Form(""),
    category: str = Form("other"),
    relevance_hint: str = Form(""),
    fetch_interval_hours: int = Form(24),
    source_key: str = Form(""),
):
    """Preview a custom source draft. Dry-run only: no writes, no network."""
    from app.application.sources.custom_intake import CustomSourceDraft, preview_custom_source

    form_data = {
        "name": name,
        "fetch_strategy": fetch_strategy,
        "homepage_url": homepage_url,
        "feed_url": feed_url,
        "category": category,
        "relevance_hint": relevance_hint,
        "fetch_interval_hours": fetch_interval_hours,
        "source_key": source_key,
    }
    db = next(get_db())
    try:
        preview = preview_custom_source(
            db,
            CustomSourceDraft(
                name=name,
                fetch_strategy=fetch_strategy,
                homepage_url=homepage_url or None,
                feed_url=feed_url or None,
                category=category or "other",
                relevance_hint=relevance_hint or "",
                fetch_interval_hours=fetch_interval_hours,
                source_key=source_key or None,
            ),
        )
    finally:
        db.close()

    return _render_sources_page(
        request,
        include_test=include_test,
        custom_preview=preview,
        custom_form=form_data,
    )


@app.get("/sources/{source_key}", response_class=HTMLResponse)
def source_workspace_page(request: Request, source_key: str):
    """Single source workspace (read-only).

    Shows:
    - Basic info
    - Radar-source / due-source decision
    - Recent FetchRuns
    - Recent SourceItems
    - Coverage stats

    This page is read-only — does NOT trigger fetches, summaries, or
    InsightCard generation.
    """
    db: Session = next(get_db())
    try:
        # 1. Find the DB Source row.
        source: Source | None = (
            db.query(Source)
            .filter(Source.source_key == source_key)
            .order_by(Source.id.desc())
            .first()
        )
        if source is None:
            return templates.TemplateResponse(
                "source_detail.html",
                {
                    "request": request,
                    "source_key": source_key,
                    "source": None,
                    "not_found": True,
                },
                status_code=404,
            )

        # 2. Find the corresponding config (for radar-scope and interval info).
        from app.sources.config_loader import get_enabled_sources, list_sources
        from app.application.sources.due_sources import (
            SUPPORTED_FETCH_STRATEGIES,
            compute_due_sources,
        )
        from app.application.sources.strategy_labels import describe_fetch_strategy
        from app.application.sources.effective_strategy import compute_effective_strategy

        all_configured = list_sources(include_disabled=True)
        config_by_key = {s.source_key: s for s in all_configured}
        config_enabled_keys = {s.source_key for s in get_enabled_sources()}
        config_source = config_by_key.get(source_key)
        is_radar_source = config_source is not None and source_key in config_enabled_keys
        strategy_supported = (source.fetch_strategy or "") in SUPPORTED_FETCH_STRATEGIES

        # 3. Get this source's due-source decision (if any).
        decision = None
        if is_radar_source:
            plan = compute_due_sources(db)
            for bucket in (plan.due, plan.skipped, plan.running, plan.unsupported, plan.missing):
                for d in bucket:
                    if d.source_key == source_key:
                        decision = d
                        break
                if decision is not None:
                    break

        # 4. Recent FetchRuns.
        recent_runs = (
            db.query(FetchRun)
            .filter(FetchRun.source_key == source_key)
            .order_by(FetchRun.started_at.desc().nullslast(), FetchRun.id.desc())
            .limit(10)
            .all()
        )

        latest_success_run = next((r for r in recent_runs if r.status == "success"), None)
        latest_failed_run = next((r for r in recent_runs if r.status == "failed"), None)

        # Effective strategy for this source — centralized helper.
        effective_strategy = compute_effective_strategy(source.feed_url, source.fetch_strategy)
        # V1.0-beta.13: recommended strategy and needs_review flag
        recommended_strategy = effective_strategy
        needs_review = (effective_strategy == "html_index")
        # V1.0-beta.14: RSS status label (three-tier, replaces "需补充 RSS")
        rss_status_label = None
        rss_status_class = ""
        if effective_strategy == "rss":
            rss_status_label = "RSS 已验证"
            rss_status_class = "rss-ok"
        elif effective_strategy == "html_index":
            notes = (config_source.strategy_notes or "") if config_source else ""
            if any(kw in notes for kw in ("No public RSS", "No reliable RSS", "HTML index fallback", "fallback")):
                rss_status_label = "未发现可靠 RSS"
                rss_status_class = "rss-warn"
            elif not notes and needs_review:
                rss_status_label = "待核查 RSS"
                rss_status_class = "rss-pending"
        # S2: configured-vs-effective consistency for a sensible "获取方式" display.
        from app.application.sources.effective_strategy import check_strategy_consistency
        strategy_consistency = check_strategy_consistency(source.feed_url, source.fetch_strategy)

        # 4b. Stale running FetchRun diagnostics (read-only) for this source.
        from app.application.sources.stale_runs import build_stale_fetch_run_report

        stale_report = build_stale_fetch_run_report(db)
        source_stale_runs = [
            r for r in stale_report.stale_runs if r.source_key == source_key
        ]

        # 5. Recent SourceItems and coverage stats.
        recent_items = (
            db.query(SourceItem)
            .filter(SourceItem.source_key == source_key)
            .order_by(SourceItem.last_seen_at.desc(), SourceItem.id.desc())
            .limit(20)
            .all()
        )

        total_items = (
            db.query(SourceItem).filter(SourceItem.source_key == source_key).count()
        )

        # Summarized items: SourceItem.raw_metadata_json contains a summary marker.
        # Counted in SQL (no full-table load into Python). Uses the canonical
        # marker set (daily_scope.SUMMARY_MARKERS) — the local copy here was
        # missing "zh_summary" and undercounted (same bug class as C4).
        from sqlalchemy import or_
        from app.application.radar.daily_scope import SUMMARY_MARKERS

        summarized_items = (
            db.query(SourceItem)
            .filter(SourceItem.source_key == source_key)
            .filter(
                or_(*[SourceItem.raw_metadata_json.like(f"%{m}%") for m in SUMMARY_MARKERS])
            )
            .count()
        )

        # InsightCard linkage: insight_card_id is set.
        insightcard_items = (
            db.query(SourceItem)
            .filter(SourceItem.source_key == source_key)
            .filter(SourceItem.insight_card_id.isnot(None))
            .count()
        )

        def _has_summary(item: SourceItem) -> bool:
            raw = item.raw_metadata_json or ""
            return any(m in raw for m in SUMMARY_MARKERS)

        # P-002: reuse the canonical candidate display helper for the Chinese
        # one-liner preview — never re-parse summaries here. Only the 20 recent
        # items are processed (no full-table scan).
        from app.application.candidates.display import build_candidate_display_card

        def _summary_state(item: SourceItem, uses_zh_one_liner: bool) -> str:
            if uses_zh_one_liner:
                return "已生成中文摘要"
            if _has_summary(item):
                return "仅元数据摘要"
            return "未生成"

        recent_items_view = []
        for it in recent_items:
            card = build_candidate_display_card(it)
            recent_items_view.append({
                "id": it.id,
                "title": it.title,
                "url": it.url,
                "status": it.status,
                "first_seen_at": it.first_seen_at,
                "last_seen_at": it.last_seen_at,
                "published_at": it.published_at,
                "insight_card_id": it.insight_card_id,
                "has_summary": _has_summary(it),
                "zh_preview": card.primary_text if card.uses_zh_one_liner else None,
                "summary_state": _summary_state(it, card.uses_zh_one_liner),
            })

        recent_runs_view = [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "items_found": r.items_found,
                "items_new": r.items_new,
                "items_updated": r.items_updated,
                "items_failed": r.items_failed,
                "error_message": r.error_message,
                # V1.0-beta.13: readable error
                "readable_error": _humanize_fetch_error(r.error_message, effective_strategy),
            }
            for r in recent_runs
        ]

        summary_coverage = (
            f"{summarized_items}/{total_items}"
            if total_items > 0
            else "暂无数据"
        )
        insightcard_coverage = (
            f"{insightcard_items}/{total_items}"
            if total_items > 0
            else "暂无数据"
        )

        return templates.TemplateResponse(
            "source_detail.html",
            {
                "request": request,
                "source_key": source_key,
                "source": source,
                "config_source": config_source,
                "is_radar_source": is_radar_source,
                "strategy_supported": strategy_supported,
                "fetch_strategy_label": describe_fetch_strategy(source.fetch_strategy),
                "effective_strategy": effective_strategy,
                "effective_strategy_label": describe_fetch_strategy(effective_strategy),
                "strategy_consistent": strategy_consistency.consistent,
                "strategy_consistency_message": strategy_consistency.message,
                "recommended_strategy": recommended_strategy,
                "needs_review": needs_review,
                "rss_status_label": rss_status_label,
                "rss_status_class": rss_status_class,
                "stale_runs": source_stale_runs,
                "stale_threshold_minutes": stale_report.threshold_minutes,
                "decision": decision,
                "recent_runs": recent_runs_view,
                "recent_items": recent_items_view,
                "total_items": total_items,
                "summarized_items": summarized_items,
                "insightcard_items": insightcard_items,
                "summary_coverage": summary_coverage,
                "insightcard_coverage": insightcard_coverage,
                "latest_success_run": latest_success_run,
                "latest_failed_run": latest_failed_run,
                "not_found": False,
            },
        )
    finally:
        db.close()


@app.post("/sources/{source_key}/fetch")
def trigger_source_fetch(source_key: str, background_tasks: BackgroundTasks):
    """Manually trigger a background fetch for the specified source.

    POST only — no GET allowed.

    Creates a FetchRun(status=running) immediately and redirects to its
    detail page. The actual probe runs in the background.
    Returns 404 if source_key does not exist.
    """
    from app.application.sources.background_fetch import SourceFetchBackgroundService

    service = SourceFetchBackgroundService()
    result = service.enqueue_source(source_key, background_tasks=background_tasks)

    if result.status == "not_found":
        return JSONResponse(status_code=404, content={"detail": result.message})

    # Redirect to the FetchRun detail page (either new or already-running)
    return RedirectResponse(url=f"/fetch-runs/{result.run_id}", status_code=303)


@app.get("/source-items", response_class=HTMLResponse)
def list_source_items_page(
    request: Request,
    source_key: str | None = None,
    status: str | None = None,
    q: str | None = None,
):
    """List discovered SourceItem entries with optional filters."""
    db = next(get_db())
    try:
        # Build query
        query = db.query(SourceItem)

        if source_key:
            query = query.filter(SourceItem.source_key == source_key)

        if status:
            query = query.filter(SourceItem.status == status)

        if q:
            pattern = f"%{q}%"
            query = query.filter(
                (SourceItem.title.ilike(pattern)) | (SourceItem.url.ilike(pattern))
            )

        items_orm = (
            query
            .order_by(SourceItem.last_seen_at.desc(), SourceItem.id.desc())
            .limit(200)
            .all()
        )

        # Get all sources for filter dropdown
        all_sources = db.query(Source).order_by(Source.source_key.asc()).all()

        # Convert to plain dicts
        items_data = []
        for item in items_orm:
            items_data.append({
                "id": item.id,
                "source_key": item.source_key,
                "title": item.title,
                "url": item.url,
                "status": item.status,
                "published_at": item.published_at,
                "first_seen_at": item.first_seen_at,
                "last_seen_at": item.last_seen_at,
                "insight_card_id": item.insight_card_id,
            })

        # Fixed status options
        # Current active states: discovered / compiled / failed.
        # Reserved for future pipeline stages: fetched / skipped_duplicate.
        status_options = [
            "discovered",
            "fetched",
            "compiled",
            "skipped_duplicate",
            "failed",
        ]

        from app.routes.fetch_runs import safe_external_url

        context = {
            "request": request,
            "items": items_data,
            "sources": [{"source_key": s.source_key} for s in all_sources],
            "status_options": status_options,
            "filter_source_key": source_key,
            "filter_status": status,
            "filter_q": q,
            "safe_external_url": safe_external_url,
        }
        return templates.TemplateResponse("source_items.html", context)
    finally:
        db.close()


@app.get("/source-items/{item_id}", response_class=HTMLResponse)
def source_item_detail(request: Request, item_id: int):
    """Show SourceItem detail with optional compile action."""
    db = next(get_db())
    try:
        item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
        if not item:
            return RedirectResponse(url="/source-items", status_code=303)

        # Get associated Source
        source = db.query(Source).filter(Source.id == item.source_id).first()

        # Get associated InsightCard if any
        card = None
        if item.insight_card_id:
            card = db.query(InsightCard).filter(InsightCard.id == item.insight_card_id).first()

        # V1.0-beta.5: compute candidate quality
        from app.application.candidate_quality.services import CandidateQualityService
        quality_service = CandidateQualityService()
        quality = quality_service.evaluate(item)

        # Import safe_external_url helper
        from app.routes.fetch_runs import safe_external_url

        context = {
            "request": request,
            "item": item,
            "source": source,
            "card": card,
            "quality": quality,
            "safe_external_url": safe_external_url,
        }
        return templates.TemplateResponse("source_item_detail.html", context)
    finally:
        db.close()


@app.post("/source-items/{item_id}/compile")
def compile_source_item(item_id: int):
    """Manually compile a SourceItem into an InsightCard (synchronous).

    Idempotent: if the item is already compiled with a valid insight_card_id,
    redirects back without re-calling compile_url.
    """
    db = next(get_db())
    try:
        service = SourceItemCompileService(db)
        result = service.compile_item(item_id)
        return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)
    finally:
        db.close()


def _safe_return_to(return_to: str | None) -> str | None:
    """Return a safe same-site relative redirect target, or None.

    This prevents open redirects while allowing page-local workflow returns
    such as /radar/today?section=...
    """
    if not return_to:
        return None

    value = return_to.strip()
    if not value:
        return None

    # Only allow site-relative paths.
    if not value.startswith("/"):
        return None

    # Reject protocol-relative URLs.
    if value.startswith("//"):
        return None

    lowered = value.lower()

    # Reject obvious slash/backslash encoded bypasses.
    if lowered.startswith(("/\\", "/%5c", "/%2f")):
        return None

    # Reject CRLF injection.
    if "\r" in value or "\n" in value:
        return None

    return value


@app.post("/source-items/{item_id}/enqueue-compile")
def enqueue_source_item_compile(
    item_id: int,
    background_tasks: BackgroundTasks,
    return_to: str | None = Form(None),
):
    """Enqueue a SourceItem for background InsightCard generation.

    Sets status to 'compiling' immediately, then dispatches a background task
    that calls SourceItemCompileService. Returns immediately (does not wait).

    Idempotent: compiled/composing items are not re-enqueued.
    """
    service = BackgroundCompileService()
    result = service.enqueue_item(item_id)

    if result.accepted:
        background_tasks.add_task(run_source_item_compile_in_background, item_id)

    redirect_url = _safe_return_to(return_to) or f"/source-items/{item_id}"
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/generation-queue", response_class=HTMLResponse)
def generation_queue_page(request: Request):
    """Display the InsightCard generation queue with items in compiling/compiled/failed states."""
    db = next(get_db())
    try:
        from app.models import SourceItem
        from sqlalchemy import desc
        from app.application.candidates.display import build_candidate_display_card

        # Show items with status in compiling/compiled/failed, ordered by updated_at desc
        items = (
            db.query(SourceItem)
            .filter(SourceItem.status.in_(["compiling", "compiled", "failed", "discovered"]))
            .order_by(desc(SourceItem.updated_at))
            .limit(50)
            .all()
        )

        display_map = {
            item.id: build_candidate_display_card(item)
            for item in items
        }

        from app.routes.fetch_runs import safe_external_url

        return templates.TemplateResponse(
            "generation_queue.html",
            {
                "request": request,
                "items": items,
                "display_map": display_map,
                "safe_external_url": safe_external_url,
            },
        )
    finally:
        db.close()


# ── Mount project docs routes ────────────────────────────────────────────────
app.include_router(project_docs_router)

# ── Mount candidate pool routes ───────────────────────────────────────────────
app.include_router(candidate_pool_router)

# ── Mount fetch runs routes ───────────────────────────────────────────────────
app.include_router(fetch_runs_router)

# ── Mount radar routes ────────────────────────────────────────────────────────
app.include_router(radar_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
