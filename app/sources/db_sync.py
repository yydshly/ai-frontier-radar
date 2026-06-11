"""Source configuration synchronization to database.

Syncs SourceConfig from YAML into the ORM Source table.
Does NOT access network, does NOT call LLM.
"""
import json

from sqlalchemy.orm import Session

from app.models import Source
from app.sources.config_loader import load_sources_config
from app.sources.models import SourceConfig


def sync_sources_config_to_db(
    db: Session,
    force_reload: bool = False,
    dry_run: bool = False,
) -> dict:
    """Sync source configs from YAML to database.

    Args:
        db: SQLAlchemy database session.
        force_reload: If True, bypass config cache.
        dry_run: If True, only compute stats without writing to DB.

    Returns:
        dict with keys: total, created, updated, disabled
    """
    # Load all source configs (no network access)
    configs = load_sources_config(force_reload=force_reload)

    stats = {"total": len(configs), "created": 0, "updated": 0, "disabled": 0}

    for cfg in configs:
        # Check if source_key already exists in DB
        existing = db.query(Source).filter(Source.source_key == cfg.source_key).first()

        if existing is None:
            stats["created"] += 1
        else:
            stats["updated"] += 1

        if not cfg.enabled:
            stats["disabled"] += 1

    if dry_run:
        # No DB write, no commit - just return computed stats
        return stats

    # Actually apply changes
    for cfg in configs:
        existing = db.query(Source).filter(Source.source_key == cfg.source_key).first()

        if existing is None:
            source = _config_to_source(cfg)
            db.add(source)
        else:
            _update_source_from_config(existing, cfg)

    db.commit()
    return stats


def _config_to_source(cfg: SourceConfig) -> Source:
    """Convert a SourceConfig dataclass to an ORM Source model."""
    return Source(
        source_key=cfg.source_key,
        name=cfg.name,
        description=cfg.description,
        source_type=cfg.type,
        homepage_url=cfg.homepage_url,
        feed_url=cfg.feed_url,
        category=cfg.category,
        tags_json=json.dumps(cfg.tags, ensure_ascii=False),
        enabled=cfg.enabled,
        fetch_strategy=cfg.fetch_strategy,
        relevance_hint=cfg.relevance_hint,
        fetch_interval_hours=cfg.fetch_interval_hours,
    )


def _update_source_from_config(source: Source, cfg: SourceConfig) -> None:
    """Update an existing Source ORM object from a SourceConfig."""
    source.name = cfg.name
    source.description = cfg.description
    source.source_type = cfg.type
    source.homepage_url = cfg.homepage_url
    source.feed_url = cfg.feed_url
    source.category = cfg.category
    source.tags_json = json.dumps(cfg.tags, ensure_ascii=False)
    source.enabled = cfg.enabled
    source.fetch_strategy = cfg.fetch_strategy
    source.relevance_hint = cfg.relevance_hint
    source.fetch_interval_hours = cfg.fetch_interval_hours
