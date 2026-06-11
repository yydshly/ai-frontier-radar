#!/usr/bin/env python3
"""
Read-only feed auto-discovery for html_index sources (S5).

For each html_index source (which by convention has no feed_url), fetches its
homepage and looks for advertised RSS/Atom/JSON feeds. If a feed is found, it
SUGGESTS upgrading the source to the more reliable ``rss`` strategy.

Strictly read-only and suggest-only:
- It does NOT modify config/sources.yaml.
- It does NOT write the database.
- It does NOT change fetch behavior.
Network access happens only when you run this explicitly. It is never run in
quick_test/CI (which stay offline).

Usage:
    python scripts/discover_source_feeds.py
    python scripts/discover_source_feeds.py --source-key stanford_hai
    python scripts/discover_source_feeds.py --all          # include rss sources too
    python scripts/discover_source_feeds.py --timeout 15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suggest RSS upgrades by discovering feeds on html_index sources (read-only)"
    )
    parser.add_argument("--source-key", type=str, default=None, help="Only check this source.")
    parser.add_argument("--all", action="store_true", help="Also check rss sources (verify feed).")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds (default 15).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        import httpx
        from app.sources.config_loader import list_sources
        from app.application.sources.feed_discovery import discover_feed_links
    except Exception as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        return 1

    sources = list(list_sources(include_disabled=True))
    if args.source_key:
        sources = [s for s in sources if s.source_key == args.source_key]
    if not args.all:
        sources = [s for s in sources if s.fetch_strategy == "html_index"]

    print("Feed discovery (read-only, suggest-only)")
    print(f"sources_to_check: {len(sources)}")
    print()

    suggested = 0
    for s in sources:
        target = s.homepage_url or s.feed_url
        if not target:
            print(f"- {s.source_key}: no homepage_url to inspect, skipped")
            continue
        try:
            resp = httpx.get(target, timeout=args.timeout, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            print(f"- {s.source_key}: fetch failed ({e})")
            continue

        feeds = discover_feed_links(resp.text, base_url=str(resp.url))
        if feeds:
            suggested += 1
            print(f"- {s.source_key}: FOUND {len(feeds)} feed(s) — consider upgrading to RSS:")
            for f in feeds:
                print(f"    feed_url: {f.url}  (type={f.type or 'n/a'})")
        else:
            print(f"- {s.source_key}: no advertised feed found")

    print()
    print(f"summary: {suggested} source(s) have a discoverable feed worth reviewing.")
    print("This script only suggests; update config/sources.yaml manually after verifying.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
