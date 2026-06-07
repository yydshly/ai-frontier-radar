"""Source Registry configuration loader.

Loads sources from config/sources.yaml (user config) with fallback to
config/sources.example.yaml (bundled defaults). Does NOT access the network.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.sources.models import (
    SourceConfig,
    SourceType,
    SourceCategory,
    FetchStrategy,
)

# Absolute path to project root (parent of app/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

SOURCES_YAML = CONFIG_DIR / "sources.yaml"
SOURCES_EXAMPLE_YAML = CONFIG_DIR / "sources.example.yaml"

_allowed_types: set[str] = {"rss", "html_index", "manual_pdf", "report_page"}
_allowed_categories: set[str] = {
    "company", "research", "paper", "policy",
    "blog", "benchmark", "funding", "open_source",
}
_allowed_strategies: set[str] = {"rss", "html_index", "manual"}

# Cache for loaded config to avoid repeated file I/O
_cached_sources: list[SourceConfig] | None = None
_cached_path: Path | None = None


def _find_config_file() -> Path:
    """Return the active config file path, preferring sources.yaml over example."""
    if SOURCES_YAML.exists():
        return SOURCES_YAML
    if SOURCES_EXAMPLE_YAML.exists():
        return SOURCES_EXAMPLE_YAML
    raise FileNotFoundError(
        f"Neither {SOURCES_YAML} nor {SOURCES_EXAMPLE_YAML} found. "
        "Please copy sources.example.yaml to sources.yaml."
    )


def _parse_bool(value: Any, field: str, source_key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"source '{source_key}': field '{field}' must be a bool, got {type(value).__name__}"
        )
    return value


def _parse_int(value: Any, field: str, source_key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            f"source '{source_key}': field '{field}' must be an int, got {type(value).__name__}"
        )
    return value


def _parse_str(value: Any, field: str, source_key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"source '{source_key}': field '{field}' must be a string, got {type(value).__name__}"
        )
    return value


def _parse_str_or_null(value: Any, field: str, source_key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"source '{source_key}': field '{field}' must be a string or null, "
            f"got {type(value).__name__}"
        )
    return value


def _parse_tags(value: Any, source_key: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(
            f"source '{source_key}': field 'tags' must be a list, got {type(value).__name__}"
        )
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"source '{source_key}': tags[{i}] must be a string, got {type(item).__name__}"
            )
    return value


def validate_source_config(source_key: str, raw: dict) -> SourceConfig:
    """Validate and coerce a raw source dict into a SourceConfig.

    Raises ValueError with a clear message on any validation failure.
    """
    # Required string fields
    name = _parse_str(raw.get("name"), "name", source_key)
    if not name:
        raise ValueError(f"source '{source_key}': 'name' must not be empty")

    description = _parse_str(raw.get("description"), "description", source_key)
    if not description:
        raise ValueError(f"source '{source_key}': 'description' must not be empty")

    # type
    type_val = raw.get("type")
    if not isinstance(type_val, str) or type_val not in _allowed_types:
        raise ValueError(
            f"source '{source_key}': 'type' must be one of {sorted(_allowed_types)}, "
            f"got '{type_val}'"
        )
    type_: SourceType = type_val  # type: ignore

    # category
    cat_val = raw.get("category")
    if not isinstance(cat_val, str) or cat_val not in _allowed_categories:
        raise ValueError(
            f"source '{source_key}': 'category' must be one of {sorted(_allowed_categories)}, "
            f"got '{cat_val}'"
        )
    category: SourceCategory = cat_val  # type: ignore

    # fetch_strategy
    strategy_val = raw.get("fetch_strategy")
    if not isinstance(strategy_val, str) or strategy_val not in _allowed_strategies:
        raise ValueError(
            f"source '{source_key}': 'fetch_strategy' must be one of {sorted(_allowed_strategies)}, "
            f"got '{strategy_val}'"
        )
    fetch_strategy: FetchStrategy = strategy_val  # type: ignore

    # homepage_url / feed_url
    homepage_url = _parse_str_or_null(raw.get("homepage_url"), "homepage_url", source_key)
    feed_url = _parse_str_or_null(raw.get("feed_url"), "feed_url", source_key)

    # Strategy-specific URL requirements
    if fetch_strategy == "rss":
        if not feed_url:
            raise ValueError(
                f"source '{source_key}': fetch_strategy='rss' requires a non-null 'feed_url'"
            )
    if fetch_strategy == "html_index":
        if not homepage_url:
            raise ValueError(
                f"source '{source_key}': fetch_strategy='html_index' requires a non-null 'homepage_url'"
            )
    if fetch_strategy == "manual":
        if not homepage_url and not description:
            raise ValueError(
                f"source '{source_key}': fetch_strategy='manual' requires at least one of "
                "'homepage_url' or 'description'"
            )

    # tags
    tags = _parse_tags(raw.get("tags", []), source_key)

    # enabled
    enabled = _parse_bool(raw.get("enabled", True), "enabled", source_key)

    # relevance_hint
    relevance_hint = _parse_str(raw.get("relevance_hint", ""), "relevance_hint", source_key)

    # fetch_interval_hours
    interval_raw = raw.get("fetch_interval_hours")
    if interval_raw is None:
        raise ValueError(f"source '{source_key}': 'fetch_interval_hours' is required")
    fetch_interval_hours = _parse_int(interval_raw, "fetch_interval_hours", source_key)
    if fetch_interval_hours <= 0:
        raise ValueError(
            f"source '{source_key}': 'fetch_interval_hours' must be a positive integer, "
            f"got {fetch_interval_hours}"
        )

    return SourceConfig(
        source_key=source_key,
        name=name,
        description=description,
        type=type_,
        homepage_url=homepage_url,
        feed_url=feed_url,
        category=category,
        tags=tags,
        enabled=enabled,
        fetch_strategy=fetch_strategy,
        relevance_hint=relevance_hint,
        fetch_interval_hours=fetch_interval_hours,
    )


def load_sources_config() -> list[SourceConfig]:
    """Load and validate all sources from the active YAML config file.

    Caches results after first load; pass force_reload=True to bypass cache.
    """
    global _cached_sources, _cached_path

    config_file = _find_config_file()

    # Return cache if valid
    if _cached_sources is not None and _cached_path == config_file:
        return _cached_sources

    with open(config_file, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    if not raw_data:
        raise ValueError(f"{config_file} is empty")

    sources_node = raw_data.get("sources")
    if not sources_node:
        raise ValueError(f"{config_file}: root must have a 'sources' key")

    if not isinstance(sources_node, dict):
        raise ValueError(f"{config_file}: 'sources' must be a mapping")

    validated: list[SourceConfig] = []
    seen_keys: set[str] = set()

    for source_key, raw_source in sources_node.items():
        # Validate source_key format
        if not re.fullmatch(r"[a-z][a-z0-9_]*", source_key):
            raise ValueError(
                f"source_key '{source_key}' must start with lowercase letter and contain only "
                "lowercase letters, digits, and underscores"
            )
        if source_key in seen_keys:
            raise ValueError(f"duplicate source_key: '{source_key}'")
        seen_keys.add(source_key)

        if not isinstance(raw_source, dict):
            raise ValueError(
                f"source '{source_key}': value must be a mapping, "
                f"got {type(raw_source).__name__}"
            )

        validated.append(validate_source_config(source_key, raw_source))

    _cached_sources = validated
    _cached_path = config_file
    return validated


def list_sources(include_disabled: bool = True) -> list[SourceConfig]:
    """Return all sources, optionally filtering out disabled ones."""
    sources = load_sources_config()
    if include_disabled:
        return list(sources)
    return [s for s in sources if s.enabled]


def get_source(source_key: str) -> SourceConfig | None:
    """Return the SourceConfig for source_key, or None if not found."""
    for source in load_sources_config():
        if source.source_key == source_key:
            return source
    return None


def get_enabled_sources() -> list[SourceConfig]:
    """Return only enabled sources."""
    return [s for s in load_sources_config() if s.enabled]
