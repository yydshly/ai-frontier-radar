#!/usr/bin/env python3
"""
Source Registry configuration diagnostic script.

Checks that config/sources.yaml (or sources.example.yaml) is valid
and prints a summary of all configured sources. Does NOT access the network.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sources import list_sources, get_enabled_sources, load_sources_config


def main():
    print("=" * 50)
    print("Source Registry Config Check")
    print("=" * 50)

    # Determine which file is active
    from app.sources.config_loader import _find_config_file, SOURCES_YAML, SOURCES_EXAMPLE_YAML

    try:
        config_file = _find_config_file()
        if config_file == SOURCES_YAML:
            print(f"[OK] loaded sources config: {SOURCES_YAML}")
        else:
            print(f"[OK] loaded sources config: {SOURCES_EXAMPLE_YAML} (sources.yaml not found)")
    except FileNotFoundError as e:
        print(f"[FAIL] {e}")
        return 1

    # Load config (may raise)
    try:
        all_sources = load_sources_config()
    except Exception as e:
        print(f"[FAIL] config validation error: {e}")
        return 1

    print(f"[OK] total sources: {len(all_sources)}")

    enabled = get_enabled_sources()
    print(f"[OK] enabled sources: {len(enabled)}")

    # Category stats
    category_counts: dict[str, int] = {}
    for s in all_sources:
        category_counts[s.category] = category_counts.get(s.category, 0) + 1

    cat_str = ", ".join(f"{k}={v}" for k, v in sorted(category_counts.items()))
    print(f"[OK] categories: {cat_str}")

    # Strategy stats
    strategy_counts: dict[str, int] = {}
    for s in all_sources:
        strategy_counts[s.fetch_strategy] = strategy_counts.get(s.fetch_strategy, 0) + 1

    strat_str = ", ".join(f"{k}={v}" for k, v in sorted(strategy_counts.items()))
    print(f"[OK] strategies: {strat_str}")

    print()
    print("-" * 60)

    # List each source
    for s in all_sources:
        status = "enabled" if s.enabled else "disabled"
        print(
            f"  {s.source_key:<30} {s.name:<30} "
            f"{s.category:<12} {s.fetch_strategy:<12} {status}"
        )

    print("-" * 60)
    print(f"[OK] config validation passed")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
