"""FastAPI main application."""
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import InsightCard, CardStatus, Source, SourceItem, CardDecision, InsightCardBilingualReport
from app.schemas import HealthResponse
from app.sources import sync_sources_config_to_db, get_featured_sources
from app.services.insight_compiler import compile_url
from app.card_decisions import ALLOWED_CARD_DECISIONS, is_valid_decision, get_decision_label
from app.logging_config import setup_logging, get_logger
from app.exports.markdown_task import build_action_markdown
from app.exports.markdown_report import build_full_report_markdown
from app.version import APP_VERSION

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
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Static files - mount before any routes
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# --- Routes ---

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok")


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

        # ── InsightCard statistics ──────────────────────────────────────────
        cards_total_count = db.query(InsightCard).count()

        # Unhandled = cards without any CardDecision
        all_card_ids = [r[0] for r in db.query(InsightCard.id).all()]
        if all_card_ids:
            handled_card_ids = {
                r[0] for r in db.query(CardDecision.card_id).distinct().all()
            }
            cards_unhandled_count = len(set(all_card_ids) - handled_card_ids)
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
            decision_value = decision_row.decision if decision_row else None
            decision_note = decision_row.note if decision_row else None
            recent_cards_data.append({
                "id": card.id,
                "source_title": card.source_title or "无标题",
                "source_url": card.source_url,
                "status": card.status.value if card.status else "unknown",
                "decision_value": decision_value,
                "decision_label": get_decision_label(decision_value),
                "decision_note": decision_note or "",
                "relevance_score": card.relevance_score,
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
        }

        return templates.TemplateResponse("index.html", {
            "request": request,
            "featured_sources": featured_sources,
            "dashboard_stats": dashboard_stats,
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
    2. Fetch, extract, clean content
    3. Check for duplicates
    4. Call LLM to generate InsightCard
    5. Save to database
    6. Redirect to detail page (always, including failed cards)
    """
    logger.info(f"Received compile request for URL: {url}")

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        return RedirectResponse(url="/", status_code=303)

    db = next(get_db())
    try:
        # compile_url now always returns a card (never raises)
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
            decision_value = decision_row.decision if decision_row else None

            # Apply filter
            if filter_decision == "unhandled" and decision_value is not None:
                continue
            if filter_decision and filter_decision != "unhandled":
                if decision_value != filter_decision:
                    continue

            cards_data.append({
                "id": card.id,
                "source_title": card.source_title,
                "source_url": card.source_url,
                "status": card.status.value if card.status else "unknown",
                "status_value": card.status.value if card.status else "unknown",
                "relevance_score": card.relevance_score,
                "created_at": card.created_at,
                "decision_value": decision_value,
                "decision_label": get_decision_label(decision_value),
            })

        # Determine filter label for template display
        filter_decision_label = ""
        if filter_decision == "unhandled":
            filter_decision_label = "未处理"
        elif filter_decision and is_valid_decision(filter_decision):
            filter_decision_label = get_decision_label(filter_decision)

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
            "source_type_value": card.source_type.value if card.source_type else "unknown",
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

        return templates.TemplateResponse("card_export_markdown.html", {
            "request": request,
            "card": card,
            "decision": decision_row,
            "markdown_text": markdown_text,
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

        filename = f"insightcard-{card_id}-task.md"
        return PlainTextResponse(
            content=markdown_text,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    finally:
        db.close()


@app.get("/cards/{card_id}/export-report", response_class=HTMLResponse)
def card_export_report_preview(request: Request, card_id: int):
    """Preview the full bilingual markdown report for an InsightCard.

    V0.9: renders a full-page preview of the complete bilingual report.
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

        markdown_text = build_full_report_markdown(card, decision_row, bilingual_report)

        return templates.TemplateResponse("card_export_report.html", {
            "request": request,
            "card": card,
            "markdown_text": markdown_text,
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

        filename = f"insightcard-{card_id}-report.md"
        return PlainTextResponse(
            content=markdown_text,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    finally:
        db.close()


@app.get("/sources", response_class=HTMLResponse)
def list_sources_page(request: Request):
    """List all configured sources from database."""
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

        # Convert to plain dicts for template
        sources_data = []
        for s in sources_orm:
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
            })

        return templates.TemplateResponse(
            "sources.html",
            {"request": request, "sources": sources_data, "sync_result": sync_result},
        )
    finally:
        db.close()


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

        context = {
            "request": request,
            "items": items_data,
            "sources": [{"source_key": s.source_key} for s in all_sources],
            "status_options": status_options,
            "filter_source_key": source_key,
            "filter_status": status,
            "filter_q": q,
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

        context = {
            "request": request,
            "item": item,
            "source": source,
            "card": card,
        }
        return templates.TemplateResponse("source_item_detail.html", context)
    finally:
        db.close()


@app.post("/source-items/{item_id}/compile")
def compile_source_item(item_id: int):
    """Manually compile a SourceItem into an InsightCard.

    Idempotent: if the item is already compiled with a valid insight_card_id,
    redirects back without re-calling compile_url.
    """
    from datetime import datetime

    db = next(get_db())
    try:
        item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
        if not item:
            return RedirectResponse(url="/source-items", status_code=303)

        # Case A: already compiled — skip re-compilation (idempotent)
        if item.status == "compiled" and item.insight_card_id is not None:
            return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)

        # Case D: empty URL guard
        if not item.url:
            item.status = "failed"
            item.error_message = "SourceItem url is empty"
            item.updated_at = datetime.utcnow()
            db.commit()
            return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)

        try:
            card = compile_url(db, item.url)
        except Exception as e:
            item.status = "failed"
            item.error_message = f"Unexpected compile error: {e}"
            item.updated_at = datetime.utcnow()
            db.commit()
            return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)

        # Link card regardless of success/failure
        item.insight_card_id = card.id
        item.updated_at = datetime.utcnow()

        if card.status.value == "completed":
            item.status = "compiled"
            item.error_message = None  # Clear old error on success
        else:
            item.status = "failed"
            item.error_message = card.error_message or "InsightCard compilation failed"

        db.commit()
        return RedirectResponse(url=f"/source-items/{item_id}", status_code=303)
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
