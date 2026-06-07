"""FastAPI main application."""
import json
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import InsightCard, CardStatus, Source, SourceItem, CardDecision
from app.schemas import HealthResponse
from app.sources import sync_sources_config_to_db, get_featured_sources
from app.services.insight_compiler import compile_url
from app.card_decisions import ALLOWED_CARD_DECISIONS, is_valid_decision, get_decision_label
from app.logging_config import setup_logging, get_logger

# Setup
setup_logging()
logger = get_logger(__name__)

# Initialize database on startup
init_db()

# FastAPI app
app = FastAPI(title="AI Frontier Radar", version="0.1.0")

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
    """Home page with URL submission form and featured AI sources."""
    featured_sources = get_featured_sources()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "featured_sources": featured_sources,
    })


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
def list_cards(request: Request):
    """List all InsightCards."""
    db = next(get_db())
    try:
        cards = (
            db.query(InsightCard)
            .order_by(InsightCard.created_at.desc())
            .all()
        )
        # Pass stable string values for template comparisons
        cards_data = []
        for card in cards:
            # Load user's decision (V0.4) — small per-row query is fine for MVP
            decision_row = (
                db.query(CardDecision)
                .filter(CardDecision.card_id == card.id)
                .first()
            )
            decision_value = decision_row.decision if decision_row else None
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
        return templates.TemplateResponse("cards.html", {"request": request, "cards": cards_data})
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

        # Parse JSON fields for template
        def parse_json_field(value):
            if not value:
                return []
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []

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
        }
        return templates.TemplateResponse("card_detail.html", context)
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
