#!/usr/bin/env python3
"""
V1.0-beta.2 Task 3B — isolated acceptance for run_due_sources_once.py --apply.

Proves that the CLI single-shot scheduler's --apply path can really create a
FetchRun and ingest SourceItems, WITHOUT touching the production database,
WITHOUT accessing the external network, and WITHOUT calling any LLM.

How isolation works:
- A temp directory holds an isolated SQLite DB. ``DATABASE_URL`` is pointed at
  it BEFORE any ``app.*`` import, so neither this script nor the spawned
  ``run_due_sources_once.py --apply`` subprocess can see the production DB.
- A local ThreadingHTTPServer on 127.0.0.1 serves a static mock RSS feed, so the
  RSS probe fetches from localhost only (no external network).
- A single config-enabled source (``openai_news``) is seeded into the isolated
  DB with ``feed_url`` pointing at the local mock feed and no FetchRun, so it is
  ``never_fetched`` → due.
- ``AUTO_SUMMARY_MAX_PER_FETCH_RUN=0`` disables auto summary, so the synchronous
  fetch records ``auto_summary.enabled=false`` and never calls an LLM.

Usage:
    python scripts/acceptance_run_due_sources_once_apply.py
    python scripts/acceptance_run_due_sources_once_apply.py --keep-temp
    python scripts/acceptance_run_due_sources_once_apply.py --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SEED_SOURCE_KEY = "openai_news"

MOCK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>AI Frontier Radar Mock Feed</title>
    <link>http://127.0.0.1/</link>
    <description>Mock RSS feed for scheduler apply acceptance</description>
    <item>
      <title>Mock AI Article 1</title>
      <link>http://127.0.0.1/mock/article-1</link>
      <description>Mock summary 1</description>
      <pubDate>Wed, 10 Jun 2026 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Mock AI Article 2</title>
      <link>http://127.0.0.1/mock/article-2</link>
      <description>Mock summary 2</description>
      <pubDate>Wed, 10 Jun 2026 00:01:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Isolated acceptance for run_due_sources_once.py --apply"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temp dir / isolated DB for inspection.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra diagnostic output.",
    )
    return parser.parse_args()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # noqa: D401 - silence default logging
        pass


def _start_mock_feed_server(feed_dir: Path) -> tuple[ThreadingHTTPServer, str]:
    """Serve feed_dir on 127.0.0.1:<random port>. Return (server, feed_url)."""
    handler = lambda *a, **k: _QuietHandler(*a, directory=str(feed_dir), **k)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    feed_url = f"http://127.0.0.1:{port}/mock-feed.xml"
    return server, feed_url


def _seed_source(feed_url: str) -> None:
    """Seed a single never-fetched Source into the isolated DB."""
    from app.db import init_db, SessionLocal
    from app.models import Source

    init_db()
    db = SessionLocal()
    try:
        source = Source(
            source_key=SEED_SOURCE_KEY,
            name="OpenAI News Mock",
            description="Mock source for scheduler apply acceptance",
            source_type="rss",
            homepage_url="http://127.0.0.1/",
            feed_url=feed_url,
            category="company",
            tags_json="[]",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="mock scheduler acceptance",
            fetch_interval_hours=24,
        )
        db.add(source)
        db.commit()
    finally:
        db.close()


def _run_scheduler_apply(isolated_url: str, verbose: bool) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATABASE_URL": isolated_url,
        "RADAR_SCHEDULER_ENABLED": "true",
        "AUTO_SUMMARY_MAX_PER_FETCH_RUN": "0",
        "SOURCE_FETCH_MAX_ITEMS_PER_RUN": "5",
    }
    return subprocess.run(
        [
            sys.executable,
            "scripts/run_due_sources_once.py",
            "--apply",
            "--max-sources",
            "1",
            "--show-missing",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def main() -> int:
    args = parse_args()

    print("[acceptance_run_due_sources_once_apply] START")

    temp_dir = Path(tempfile.mkdtemp(prefix="scheduler_apply_acceptance_"))
    isolated_db = temp_dir / "scheduler_apply_acceptance.db"
    isolated_url = f"sqlite:///{isolated_db.as_posix()}"

    # CRITICAL: point DATABASE_URL at the isolated DB BEFORE importing app.*.
    os.environ["DATABASE_URL"] = isolated_url
    os.environ["AUTO_SUMMARY_MAX_PER_FETCH_RUN"] = "0"

    feed_dir = temp_dir / "feed"
    feed_dir.mkdir(parents=True, exist_ok=True)
    (feed_dir / "mock-feed.xml").write_text(MOCK_RSS, encoding="utf-8")

    server = None
    checks: list[tuple[str, bool]] = []
    try:
        server, feed_url = _start_mock_feed_server(feed_dir)
        print(f"isolated_db={isolated_db}")
        print(f"mock_feed_url={feed_url}")
        print()

        _seed_source(feed_url)

        proc = _run_scheduler_apply(isolated_url, args.verbose)

        print("scheduler_stdout:")
        for line in proc.stdout.splitlines():
            print(f"  {line}")
        if args.verbose and proc.stderr:
            print("scheduler_stderr:")
            for line in proc.stderr.splitlines():
                print(f"  {line}")
        print()

        # ── Verify against the isolated DB ────────────────────────────────
        from app.db import SessionLocal
        from app.models import FetchRun, SourceItem, InsightCard

        db = SessionLocal()
        try:
            scheduler_ok = (
                proc.returncode == 0
                and "APPLY" in proc.stdout
                and "started=1" in proc.stdout
                and SEED_SOURCE_KEY in proc.stdout
                and "run_id=" in proc.stdout
            )
            checks.append(("scheduler_apply_started", scheduler_ok))

            runs = db.query(FetchRun).all()
            fetch_run = runs[0] if len(runs) == 1 else None
            checks.append(("fetch_run_created", len(runs) == 1))

            if fetch_run is not None:
                checks.append((
                    "fetch_run_success",
                    fetch_run.source_key == SEED_SOURCE_KEY
                    and fetch_run.status == "success"
                    and fetch_run.finished_at is not None
                    and fetch_run.error_message is None,
                ))
                checks.append((
                    "fetch_run_item_counts",
                    fetch_run.items_found == 2
                    and fetch_run.items_new == 2
                    and fetch_run.items_updated == 0
                    and fetch_run.items_failed == 0,
                ))

                meta = json.loads(fetch_run.metadata_json or "{}")
                auto = meta.get("auto_summary", {})
                checks.append((
                    "auto_summary_disabled",
                    auto.get("enabled") is False
                    and auto.get("reason") == "AUTO_SUMMARY_MAX_PER_FETCH_RUN=0"
                    and auto.get("processed_count") == 0,
                ))
            else:
                checks.append(("fetch_run_success", False))
                checks.append(("fetch_run_item_counts", False))
                checks.append(("auto_summary_disabled", False))

            items = db.query(SourceItem).filter(SourceItem.source_key == SEED_SOURCE_KEY).all()
            titles = {it.title for it in items}
            checks.append(("source_items_created", len(items) == 2))
            checks.append((
                "source_items_titles",
                "Mock AI Article 1" in titles and "Mock AI Article 2" in titles,
            ))
            checks.append((
                "source_items_discovered",
                all(it.status == "discovered" for it in items),
            ))

            checks.append(("no_insight_cards", db.query(InsightCard).count() == 0))

            running = db.query(FetchRun).filter(FetchRun.status == "running").count()
            checks.append(("no_running_fetch_runs", running == 0))

            from app.application.sources.stale_runs import build_stale_fetch_run_report
            report = build_stale_fetch_run_report(db)
            checks.append(("stale_count_zero", report.stale_count == 0))
        finally:
            db.close()

        print("checks:")
        all_ok = True
        for name, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'} {name}")
            all_ok = all_ok and ok
        print()

        if all_ok:
            print("ACCEPTANCE_OK")
            return 0
        print("ACCEPTANCE_FAILED")
        return 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if args.keep_temp:
            print(f"[keep-temp] isolated dir retained: {temp_dir}")
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
