#!/usr/bin/env python3
"""Probe a single RSS/Atom feed URL and report its status.

Usage:
    python scripts/probe_feed_url.py --url "https://example.com/feed.xml"
    python scripts/probe_feed_url.py --url "https://example.com/feed.xml" --timeout 15

Output fields:
    reachable: true|false
    content_type: MIME type observed
    feed_type: rss|atom|unknown
    item_count: number of entries found
    sample_titles: first 3 entry titles
    error_code: network_timeout|http_error|parse_error|moved_permanently|none
    error_detail: human-readable error description
"""
import argparse
import sys
import feedparser
import httpx


def probe_feed_url(url: str, timeout: int = 15) -> dict:
    """Probe a single feed URL and return structured result.

    Args:
        url: The feed URL to probe.
        timeout: Request timeout in seconds.

    Returns:
        dict with keys: reachable, content_type, feed_type, item_count,
                        sample_titles, error_code, error_detail
    """
    result = {
        "reachable": False,
        "content_type": None,
        "feed_type": "unknown",
        "item_count": 0,
        "sample_titles": [],
        "error_code": None,
        "error_detail": None,
    }

    # Step 1: Fetch the URL
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        result["content_type"] = response.headers.get("content-type", "")
        response.raise_for_status()
        result["reachable"] = True
    except httpx.TimeoutException:
        result["error_code"] = "network_timeout"
        result["error_detail"] = f"Connection timed out after {timeout}s"
        return result
    except httpx.HTTPStatusError as e:
        result["error_code"] = "http_error"
        result["error_detail"] = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return result
    except httpx.RequestError as e:
        result["error_code"] = "network_error"
        result["error_detail"] = f"Request error: {e}"
        return result
    except Exception as e:
        result["error_code"] = "unknown_error"
        result["error_detail"] = str(e)
        return result

    # Step 2: Check for permanent redirect (feed moved)
    if response.status_code in (301, 308):
        result["error_code"] = "moved_permanently"
        result["error_detail"] = f"Permanent redirect to {response.headers.get('location', 'unknown')}"
        return result

    # Step 3: Parse the feed
    try:
        feed = feedparser.parse(response.text)
    except Exception as e:
        result["error_code"] = "parse_error"
        result["error_detail"] = f"Failed to parse feed content: {e}"
        return result

    # Step 4: Determine feed type
    if feed.feed.get("version", "").startswith("rss"):
        result["feed_type"] = "rss"
    elif feed.feed.get("version", "").startswith("atom"):
        result["feed_type"] = "atom"
    elif feed.entries:
        # feedparser can detect some feeds even without version
        result["feed_type"] = "unknown"
    else:
        result["feed_type"] = "unknown"

    # Step 5: Count entries
    entries = list(feed.entries or [])
    result["item_count"] = len(entries)
    result["sample_titles"] = [
        (getattr(e, "title", None) or "")[:100]
        for e in entries[:3]
    ]

    return result


def format_result(result: dict, url: str) -> str:
    """Format probe result for console output."""
    lines = []
    lines.append(f"URL: {url}")
    lines.append(f"reachable: {result['reachable']}")

    if result["reachable"]:
        lines.append(f"content_type: {result['content_type']}")
        lines.append(f"feed_type: {result['feed_type']}")
        lines.append(f"item_count: {result['item_count']}")
        if result["sample_titles"]:
            lines.append("sample_titles:")
            for title in result["sample_titles"]:
                lines.append(f"  - {title}")
    else:
        if result["error_code"]:
            lines.append(f"error_code: {result['error_code']}")
        if result["error_detail"]:
            lines.append(f"error_detail: {result['error_detail']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Probe a single RSS/Atom feed URL and report its status."
    )
    parser.add_argument(
        "--url", "-u", type=str, required=True,
        help="The feed URL to probe."
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=15,
        help="Request timeout in seconds (default: 15)."
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="Output raw JSON instead of human-readable format."
    )
    args = parser.parse_args()

    result = probe_feed_url(args.url, timeout=args.timeout)

    if args.json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_result(result, args.url))

    # Exit code: 0 if reachable, 1 otherwise
    sys.exit(0 if result["reachable"] else 1)


if __name__ == "__main__":
    main()
