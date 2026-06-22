"""Opt-in external notification for daily-cycle health warnings (P2).

The daily cycle already derives ``health_warnings`` (stuck runs, partial/failed
coverage, truncated sources, abnormal report status) and writes them to the log
+ run record. But an *unattended* scheduled run means nobody reads those — a bad
day stays silent until someone opens the dashboard. This module pushes the
warnings to a generic JSON webhook so the operator is actually alerted.

It is strictly opt-in: a no-op unless ``HEALTH_ALERT_WEBHOOK_URL`` is set, and
always best-effort (a notification failure must never affect the cycle's exit
code). Uses only the stdlib so it adds no dependency and is safe to call from
the scheduled entrypoint.

The payload is intentionally generic — a top-level ``text`` summary (consumed by
most chat webhooks) plus structured fields. Vendor-specific envelopes
(Slack blocks, Feishu msg_type, etc.) can be layered on later if needed.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# Coverage states that warrant an alert even with no explicit warning text.
_ALERT_COVERAGE = {"failed", "partial", "no_content"}


def get_health_alert_webhook_url() -> str | None:
    """Return the configured webhook URL, or None when alerting is disabled."""
    url = (os.getenv("HEALTH_ALERT_WEBHOOK_URL") or "").strip()
    return url or None


def should_notify(result) -> bool:
    """True when the cycle result is worth alerting on (warnings or bad coverage)."""
    if getattr(result, "health_warnings", None):
        return True
    return getattr(result, "coverage_status", None) in _ALERT_COVERAGE


def build_payload(result, *, run_id: str | None = None) -> dict:
    """Assemble the generic webhook JSON payload from a cycle result."""
    warnings = list(getattr(result, "health_warnings", []) or [])
    coverage = getattr(result, "coverage_status", "unknown")
    succeeded = getattr(result, "sources_succeeded", 0)
    total = getattr(result, "sources_total", 0)
    header = f"⚠ AI Frontier Radar 日报周期异常 (coverage={coverage}, {succeeded}/{total} 来源)"
    lines = [header]
    if run_id:
        lines.append(f"run_id: {run_id}")
    for w in warnings:
        lines.append(f"• {w}")
    return {
        "text": "\n".join(lines),
        "run_id": run_id,
        "coverage_status": coverage,
        "sources_succeeded": succeeded,
        "sources_total": total,
        "report_status": getattr(result, "report_status", None),
        "warnings": warnings,
        "truncated_sources": list(getattr(result, "truncated_sources", []) or []),
    }


def notify_health_warnings(
    result,
    *,
    run_id: str | None = None,
    dry_run: bool = False,
    timeout: float = 10.0,
) -> dict:
    """Best-effort POST of health warnings to the configured webhook.

    Returns a small status dict ``{notified, reason}`` describing what happened
    (for logging). Never raises.
    """
    if dry_run:
        return {"notified": False, "reason": "dry_run"}
    url = get_health_alert_webhook_url()
    if not url:
        return {"notified": False, "reason": "no_webhook_configured"}
    if not should_notify(result):
        return {"notified": False, "reason": "no_warnings"}

    payload = build_payload(result, run_id=run_id)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
        return {"notified": True, "reason": f"http_{status}"}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"notified": False, "reason": f"error: {exc}"}
