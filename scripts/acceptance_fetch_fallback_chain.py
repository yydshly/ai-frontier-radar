#!/usr/bin/env python3
"""
Isolated acceptance for the S3 reliability fallback chain.

Proves, against an ISOLATED database and with the probes monkeypatched (no real
network, no main-DB writes), that:

- With ``RADAR_FETCH_FALLBACK_ENABLED=true``: a source whose RSS probe fails
  falls back to html_index (the next reliable method), the FetchRun ends
  ``success``, and metadata records the attempt chain + ``fallback_used=true``.
- With the gate off (default): the same RSS failure ends ``failed`` and no
  html_index attempt is made (single effective attempt, unchanged behavior).

The real ``run_source_fetch_in_background`` control flow is exercised; only the
two probe functions are faked, so the fallback orchestration + metadata wiring
are what's under test.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SOURCE_KEY = "fallback_accept_src"


def _rss_fail(db, source, timeout_seconds=20, max_items=None):
    return {
        "items_found": 0, "items_new": 0, "items_updated": 0, "items_failed": 0,
        "error_message": "simulated RSS failure", "total_seen": 0,
        "processed_count": 0, "truncated": False, "max_items_per_run": max_items,
    }


def _html_ok(db, source, timeout_seconds=20, max_items=None):
    return {
        "items_found": 2, "items_new": 2, "items_updated": 0, "items_failed": 0,
        "error_message": None, "total_seen": 2, "processed_count": 2,
        "truncated": False, "max_items_per_run": max_items,
    }


def _seed_source():
    from app.db import init_db, SessionLocal
    from app.models import Source
    init_db()
    db = SessionLocal()
    try:
        db.add(Source(
            source_key=SOURCE_KEY,
            name="Fallback Accept Source",
            description="S3 fallback acceptance",
            source_type="rss",
            homepage_url="https://example.com/blog",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        ))
        db.commit()
    finally:
        db.close()


def _run_once() -> dict:
    """Enqueue a synchronous fetch (background_tasks=None) and return run metadata."""
    from app.db import SessionLocal
    from app.models import FetchRun
    from app.application.sources.background_fetch import SourceFetchBackgroundService

    with patch("app.sources.rss_probe.probe_rss_source", side_effect=_rss_fail), \
         patch("app.sources.html_index_probe.probe_html_index_source", side_effect=_html_ok):
        svc = SourceFetchBackgroundService()
        result = svc.enqueue_source(SOURCE_KEY)

    db = SessionLocal()
    try:
        run = db.query(FetchRun).filter(FetchRun.id == result.run_id).first()
        meta = json.loads(run.metadata_json or "{}")
        return {"status": run.status, "items_found": run.items_found, "meta": meta}
    finally:
        db.close()


def _mark_existing_runs_old():
    """Clear the duplicate-running window so a second enqueue is allowed."""
    from app.db import SessionLocal
    from app.models import FetchRun
    from datetime import datetime, timedelta
    db = SessionLocal()
    try:
        old = datetime.utcnow() - timedelta(hours=1)
        for r in db.query(FetchRun).filter(FetchRun.source_key == SOURCE_KEY).all():
            r.started_at = old
        db.commit()
    finally:
        db.close()


def main() -> int:
    print("[acceptance_fetch_fallback_chain] START")
    temp_dir = Path(tempfile.mkdtemp(prefix="fetch_fallback_accept_"))
    isolated_db = temp_dir / "fallback.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{isolated_db.as_posix()}"
    os.environ["AUTO_SUMMARY_MAX_PER_FETCH_RUN"] = "0"

    checks: list[tuple[str, bool]] = []
    try:
        _seed_source()

        # Case 1: fallback ON — RSS fails, html_index succeeds.
        os.environ["RADAR_FETCH_FALLBACK_ENABLED"] = "true"
        on = _run_once()
        fs = on["meta"].get("fetch_strategy", {})
        checks.append(("fallback_on_status_success", on["status"] == "success"))
        checks.append(("fallback_on_succeeded_html", fs.get("succeeded") == "html_index"))
        checks.append(("fallback_on_flag_true", fs.get("fallback_used") is True))
        checks.append((
            "fallback_on_attempts_chain",
            [a.get("strategy") for a in fs.get("attempts", [])] == ["rss", "html_index"],
        ))

        # Case 2: fallback OFF — RSS fails, no html attempt, run failed.
        _mark_existing_runs_old()
        os.environ["RADAR_FETCH_FALLBACK_ENABLED"] = "false"
        off = _run_once()
        fs2 = off["meta"].get("fetch_strategy", {})
        checks.append(("fallback_off_status_failed", off["status"] == "failed"))
        checks.append((
            "fallback_off_single_attempt",
            [a.get("strategy") for a in fs2.get("attempts", [])] == ["rss"],
        ))
        checks.append(("fallback_off_flag_false", fs2.get("fallback_used") is False))

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
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
