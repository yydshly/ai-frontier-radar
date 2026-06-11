#!/usr/bin/env python3
"""Audit the 15 curated sources in config/sources.example.yaml for onboarding quality.

Checks:
- source_key, name, category, source_type presence
- homepage_url reachability
- feed_url reachability
- feed_url is parseable as RSS/Atom
- feed item count
- recommended_strategy (RSS if feed_url works, else HTML index)
- needs_review flag for HTML-index sources

Usage (dry-run, default):
    python scripts/audit_sources_onboarding.py

With actual config (sources.yaml):
    python scripts/audit_sources_onboarding.py --use-config-sources-yaml

Timeout per request:
    python scripts/audit_sources_onboarding.py --timeout 15

Exit code:
    0 = all checks passed
    1 = at least one source has a hard config error
    2 = network errors occurred (but all sources were still checked)
"""
import argparse
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import feedparser

from app.sources.config_loader import _find_config_file, SOURCES_YAML, SOURCES_EXAMPLE_YAML
from app.sources import load_sources_config


# ----------------------------------------------------------------------
# Probe helpers (same logic as probe_feed_url.py but scoped here)
# ----------------------------------------------------------------------
def probe_homepage(url: str, timeout: int = 10) -> dict:
    """Check if homepage URL is reachable."""
    result = {
        "reachable": False,
        "status_code": None,
        "error_code": None,
        "error_detail": None,
    }
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        result["reachable"] = True
        result["status_code"] = response.status_code
    except httpx.TimeoutException:
        result["error_code"] = "timeout"
        result["error_detail"] = f"Homepage timed out after {timeout}s"
    except httpx.HTTPStatusError as e:
        result["error_code"] = "http_error"
        result["error_detail"] = f"HTTP {e.response.status_code}"
        result["reachable"] = True  # Still reachable, just error status
        result["status_code"] = e.response.status_code
    except httpx.RequestError as e:
        result["error_code"] = "network_error"
        result["error_detail"] = str(e)
    except Exception as e:
        result["error_code"] = "unknown"
        result["error_detail"] = str(e)
    return result


def probe_feed(url: str, timeout: int = 15) -> dict:
    """Probe a feed URL. Returns (success, feed_type, item_count, error_code, error_detail)."""
    result = {
        "reachable": False,
        "feed_type": None,
        "item_count": 0,
        "sample_titles": [],
        "error_code": None,
        "error_detail": None,
    }
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        result["content_type"] = response.headers.get("content-type", "")
        result["reachable"] = True
    except httpx.TimeoutException:
        result["error_code"] = "timeout"
        result["error_detail"] = f"Feed timed out after {timeout}s"
        return result
    except httpx.HTTPStatusError as e:
        result["error_code"] = "http_error"
        result["error_detail"] = f"HTTP {e.response.status_code}"
        return result
    except httpx.RequestError as e:
        result["error_code"] = "network_error"
        result["error_detail"] = str(e)
        return result
    except Exception as e:
        result["error_code"] = "unknown"
        result["error_detail"] = str(e)
        return result

    # Parse feed
    try:
        feed = feedparser.parse(response.text)
    except Exception as e:
        result["error_code"] = "parse_error"
        result["error_detail"] = f"Failed to parse: {e}"
        return result

    version = feed.feed.get("version", "")
    if version.startswith("rss"):
        result["feed_type"] = "rss"
    elif version.startswith("atom"):
        result["feed_type"] = "atom"
    elif feed.entries:
        result["feed_type"] = "unknown"
    else:
        result["error_code"] = "empty_feed"
        result["error_detail"] = "No entries found and unrecognised format"
        return result

    entries = list(feed.entries or [])
    result["item_count"] = len(entries)
    result["sample_titles"] = [
        (getattr(e, "title", None) or "")[:80]
        for e in entries[:3]
    ]
    return result


def compute_recommended_strategy(source) -> tuple[str, str]:
    """Compute recommended strategy and whether it needs review.

    Returns (recommended_strategy, needs_review_reason_or_none)
    """
    if source.feed_url:
        return ("rss", None)
    # No feed_url — needs HTML index, which is less stable
    return (source.fetch_strategy, "no_feed_url")


# ----------------------------------------------------------------------
# Main audit logic
# ----------------------------------------------------------------------
def audit_source(source, homepage_timeout: int = 10, feed_timeout: int = 15) -> dict:
    """Audit a single source. Returns a dict with all findings."""
    findings = {
        "source_key": source.source_key,
        "name": source.name,
        "category": source.category,
        "source_type": getattr(source, "type", None) or getattr(source, "source_type", None),
        "homepage_url": source.homepage_url,
        "feed_url": source.feed_url,
        "fetch_strategy": source.fetch_strategy,
        # Homepage check
        "homepage_reachable": None,
        "homepage_status_code": None,
        "homepage_error_code": None,
        # Feed check
        "feed_reachable": None,
        "feed_type": None,
        "feed_item_count": None,
        "feed_sample_titles": [],
        "feed_error_code": None,
        "feed_error_detail": None,
        # Computed
        "recommended_strategy": None,
        "needs_review": False,
        "needs_review_reasons": [],
        "action": None,
        "overall_status": "unknown",
    }

    # Compute recommended strategy
    rec_strategy, review_reason = compute_recommended_strategy(source)
    findings["recommended_strategy"] = rec_strategy

    # Homepage probe
    if source.homepage_url:
        hp = probe_homepage(source.homepage_url, timeout=homepage_timeout)
        findings["homepage_reachable"] = hp["reachable"]
        findings["homepage_status_code"] = hp["status_code"]
        findings["homepage_error_code"] = hp["error_code"]
        if hp["error_code"]:
            findings["needs_review"] = True
            findings["needs_review_reasons"].append(f"homepage:{hp['error_code']}")
    else:
        findings["homepage_reachable"] = None
        findings["needs_review"] = True
        findings["needs_review_reasons"].append("homepage:missing")

    # Feed probe
    if source.feed_url:
        fp = probe_feed(source.feed_url, timeout=feed_timeout)
        findings["feed_reachable"] = fp["reachable"]
        findings["feed_type"] = fp["feed_type"]
        findings["feed_item_count"] = fp["item_count"]
        findings["feed_sample_titles"] = fp["sample_titles"]
        findings["feed_error_code"] = fp["error_code"]
        findings["feed_error_detail"] = fp["error_detail"]

        if fp["error_code"]:
            findings["needs_review"] = True
            findings["needs_review_reasons"].append(f"feed:{fp['error_code']}")
            findings["action"] = f"fix feed_url ({fp['error_code']})"
        elif not fp["reachable"]:
            findings["needs_review"] = True
            findings["needs_review_reasons"].append("feed:unreachable")
            findings["action"] = "check feed_url reachability"
        elif rec_strategy == "rss" and fp["feed_type"] not in ("rss", "atom", "unknown"):
            # We expected RSS but got something else
            findings["needs_review"] = True
            findings["needs_review_reasons"].append(f"feed:unexpected_type:{fp['feed_type']}")
            findings["action"] = "verify feed type matches expectation"
        else:
            # Feed works fine
            findings["action"] = None
    else:
        # No feed_url
        findings["feed_reachable"] = None
        if review_reason == "no_feed_url":
            findings["needs_review"] = True
            findings["needs_review_reasons"].append("no_feed_url")
            findings["action"] = "add feed_url (RSS/Atom recommended)"

    # Determine overall status
    if not findings["homepage_reachable"] and source.homepage_url:
        findings["overall_status"] = "fail"
    elif source.feed_url and not findings["feed_reachable"]:
        findings["overall_status"] = "fail"
    elif source.feed_url and findings["feed_reachable"] and not findings["feed_error_code"]:
        findings["overall_status"] = "ok"
    elif not source.feed_url:
        findings["overall_status"] = "warn"  # HTML index, needs review
    else:
        findings["overall_status"] = "warn"

    return findings


def format_source_report(f: dict) -> str:
    """Format a single source audit finding as a human-readable report block."""
    status_icon = {
        "ok": "[OK]",
        "warn": "[WARN]",
        "fail": "[FAIL]",
    }.get(f["overall_status"], "[??]")

    lines = []
    lines.append(f"{status_icon} {f['source_key']}")
    lines.append(f"       name: {f['name']}")
    lines.append(f"       category: {f['category']}")
    lines.append(f"       homepage: {format_homepage(f)}")
    lines.append(f"       feed_url: {format_feed(f)}")
    lines.append(f"       recommended_strategy: {f['recommended_strategy']}")

    if f["needs_review"]:
        lines.append(f"       needs_review: {'; '.join(f['needs_review_reasons']) or 'yes'}")

    if f["action"]:
        lines.append(f"       action: {f['action']}")

    return "\n".join(lines)


def format_homepage(f: dict) -> str:
    if f["homepage_url"] is None:
        return "missing"
    if f["homepage_reachable"] is True:
        return f"reachable ({f['homepage_status_code']})"
    elif f["homepage_reachable"] is False:
        return f"failed ({f['homepage_error_code'] or 'unreachable'})"
    return "unchecked"


def format_feed(f: dict) -> str:
    if f["feed_url"] is None:
        return "none"
    if f["feed_reachable"] is True:
        items = f["feed_item_count"] if f["feed_item_count"] is not None else "?"
        return f"reachable ({f['feed_type']}, {items} items)"
    elif f["feed_reachable"] is False:
        return f"failed ({f['feed_error_code'] or 'unreachable'})"
    return "unchecked"


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Audit the 15 curated sources in config/sources.example.yaml "
                    "for onboarding quality (dry-run by default)."
    )
    parser.add_argument(
        "--use-config-sources-yaml",
        action="store_true",
        help="Use config/sources.yaml instead of sources.example.yaml. "
             "Useful when you have a real config to validate."
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=10,
        help="Homepage probe timeout in seconds (default: 10)."
    )
    parser.add_argument(
        "--feed-timeout", type=int, default=15,
        help="Feed probe timeout in seconds (default: 15)."
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true", default=True,
        help="Dry-run mode (default: True). This script always runs read-only."
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Source Onboarding Audit (V1.0-beta.13)")
    print("=" * 70)

    # Find config file
    if args.use_config_sources_yaml:
        config_path = SOURCES_YAML
    else:
        config_path = SOURCES_EXAMPLE_YAML

    if not Path(config_path).exists():
        print(f"[FAIL] Config file not found: {config_path}")
        print("       Use --use-config-sources-yaml if you have a real sources.yaml.")
        return 1

    print(f"[OK] Loading config: {config_path}")

    # Load sources
    try:
        all_sources = load_sources_config()
    except Exception as e:
        print(f"[FAIL] Failed to load sources config: {e}")
        return 1

    print(f"[OK] Total sources in config: {len(all_sources)}")
    print()

    # Audit each source
    ok_count = 0
    warn_count = 0
    fail_count = 0
    network_errors = 0
    findings_by_key: dict[str, dict] = {}

    for source in all_sources:
        try:
            f = audit_source(source, homepage_timeout=args.timeout, feed_timeout=args.feed_timeout)
        except Exception as e:
            # Single source failure does NOT interrupt global check
            f = {
                "source_key": source.source_key,
                "name": source.name,
                "overall_status": "fail",
                "needs_review": True,
                "needs_review_reasons": [f"audit_error:{e}"],
                "homepage_reachable": None,
                "feed_reachable": None,
                "feed_error_code": "audit_script_error",
                "error_detail": str(e),
            }
            network_errors += 1

        findings_by_key[source.source_key] = f

        if f["overall_status"] == "ok":
            ok_count += 1
        elif f["overall_status"] == "warn":
            warn_count += 1
        else:
            fail_count += 1

        if f.get("feed_error_code") in ("timeout", "network_error", "http_error", "parse_error"):
            network_errors += 1

        # Print immediately so we see progress
        print(format_source_report(f))
        print()

    # Summary
    print("-" * 70)
    print("Summary")
    print("-" * 70)
    print(f"  Total audited:  {len(all_sources)}")
    print(f"  OK:             {ok_count}")
    print(f"  WARN:           {warn_count}")
    print(f"  FAIL:           {fail_count}")
    print(f"  Network errors: {network_errors} (not hard failures for this script)")

    # List sources needing RSS
    html_sources = [
        f for f in findings_by_key.values()
        if f["recommended_strategy"] != "rss" and f["feed_url"] is None
    ]
    if html_sources:
        print()
        print("  Sources without RSS (consider adding feed_url):")
        for f in html_sources:
            print(f"    - {f['source_key']}: {f['name']}")

    # List sources needing review
    review_sources = [
        f for f in findings_by_key.values()
        if f["needs_review"]
    ]
    if review_sources:
        print()
        print(f"  Sources needing review ({len(review_sources)}):")
        for f in review_sources:
            reasons = "; ".join(f["needs_review_reasons"])
            print(f"    - {f['source_key']}: {reasons}")

    print()
    print("=" * 70)

    if fail_count > 0:
        print(f"[FAIL] {fail_count} source(s) failed")
        return 1
    elif network_errors > 0:
        print(f"[WARN] Audit complete with {network_errors} network error(s)")
        return 2
    else:
        print("[OK] Audit complete — all sources passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
