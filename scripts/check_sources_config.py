#!/usr/bin/env python3
"""
Source Registry configuration diagnostic script.

Checks that config/sources.yaml (or sources.example.yaml) is valid
and prints a summary of all configured sources. Does NOT access the network.

V1.0-beta.9 additions:
- Effective strategy computation (feed_url overrides fetch_strategy)
- Warnings for feed_url without rss strategy
- needs_review flag for company sources using html_index
- Strategy distribution summary
- Sources needing RSS verification
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sources import list_sources, get_enabled_sources, load_sources_config


def compute_effective_strategy(source) -> str:
    """Compute effective fetch strategy based on feed_url presence.

    Rule: if feed_url exists, effective strategy is always 'rss'
    regardless of the fetch_strategy field value.
    """
    if source.feed_url:
        return "rss"
    return source.fetch_strategy


def main():
    print("=" * 60)
    print("Source Registry Config Check (v1.0-beta.9)")
    print("=" * 60)

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

    # Strategy stats (declared fetch_strategy)
    strategy_counts: dict[str, int] = {}
    for s in all_sources:
        strategy_counts[s.fetch_strategy] = strategy_counts.get(s.fetch_strategy, 0) + 1

    strat_str = ", ".join(f"{k}={v}" for k, v in sorted(strategy_counts.items()))
    print(f"[OK] declared strategies: {strat_str}")

    # Effective strategy stats (feed_url overrides)
    effective_strategy_counts: dict[str, int] = {}
    for s in all_sources:
        eff = compute_effective_strategy(s)
        effective_strategy_counts[eff] = effective_strategy_counts.get(eff, 0) + 1

    eff_str = ", ".join(f"{k}={v}" for k, v in sorted(effective_strategy_counts.items()))
    print(f"[OK] effective strategies: {eff_str}")

    # Warnings and needs_review tracking
    warnings: list[str] = []
    needs_review: list[tuple[str, str, str]] = []  # (source_key, reason, detail)

    for s in all_sources:
        eff = compute_effective_strategy(s)

        # Warning: feed_url exists but fetch_strategy != rss
        if s.feed_url and s.fetch_strategy != "rss":
            warnings.append(
                f"  [WARN] {s.source_key}: has feed_url but fetch_strategy='{s.fetch_strategy}'. "
                f"Effective strategy is 'rss'. Consider setting fetch_strategy='rss' explicitly."
            )

        # needs_review: company source using html_index without feed_url
        if s.category == "company" and eff == "html_index" and not s.feed_url:
            needs_review.append((
                s.source_key,
                "company+html_index without feed_url",
                f"Consider verifying if RSS/Atom feed exists for {s.name}"
            ))

        # needs_review: research source using html_index without feed_url
        if s.category == "research" and eff == "html_index" and not s.feed_url:
            needs_review.append((
                s.source_key,
                "research+html_index without feed_url",
                f"Consider verifying if RSS/Atom feed exists for {s.name}"
            ))

    # Output warnings
    if warnings:
        print()
        print("-" * 60)
        print("Warnings (feed_url without rss strategy):")
        for w in warnings:
            print(w)

    # Output needs_review list
    if needs_review:
        print()
        print("-" * 60)
        print(f"needs_review ({len(needs_review)} sources - RSS verification suggested):")
        for sk, reason, detail in needs_review:
            print(f"  [REVIEW] {sk}: {reason}")
            print(f"           {detail}")

    print()
    print("-" * 60)
    print("Strategy distribution:")
    print(f"  Declared strategies: {strat_str}")
    print(f"  Effective strategies: {eff_str}")
    print("  (Effective = rss when feed_url exists, otherwise = fetch_strategy)")

    print()
    print("-" * 60)

    # List each source with effective strategy
    print(f"{'source_key':<30} {'name':<28} {'category':<12} {'declared':<12} {'effective':<12} {'status'}")
    print("-" * 120)
    for s in all_sources:
        status = "enabled" if s.enabled else "disabled"
        eff = compute_effective_strategy(s)
        print(
            f"{s.source_key:<30} {s.name:<28} {s.category:<12} "
            f"{s.fetch_strategy:<12} {eff:<12} {status}"
        )

    print("-" * 60)

    # Summary
    print(f"[OK] config validation passed")

    if warnings:
        print(f"[WARN] {len(warnings)} warnings issued (see above)")
    if needs_review:
        print(f"[REVIEW] {len(needs_review)} sources need RSS verification")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
