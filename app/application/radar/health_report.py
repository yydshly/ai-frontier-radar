"""Per-run health report delivered through the email / Feishu channels.

Distinct from ``health_notify`` (a generic webhook fired only on anomalies):
this sends a per-run health *digest* — including "一切正常" — through the SAME
email + Feishu channels the user already configured for the daily report, so a
single setup covers both the 信息报告 and the 健康报告.

Config:
- ``HEALTH_REPORT_ENABLED`` (default true) — master switch.
- ``HEALTH_REPORT_MODE`` = ``always`` (default, 心跳回执) | ``on_warning``.

Delivery reuses ``email_share.send_email`` and ``feishu_notify.send_feishu_card``
and only goes out on channels that are themselves enabled (EMAIL_SHARE_ENABLED /
FEISHU_SHARE_ENABLED). Strictly best-effort: never raises, never affects the
cycle exit code.
"""
from __future__ import annotations

import os
from datetime import datetime
from html import escape


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_health_report_enabled() -> bool:
    return _env_bool("HEALTH_REPORT_ENABLED", default=True)


def get_health_report_mode() -> str:
    """``always`` (every run, heartbeat) or ``on_warning`` (only on anomalies)."""
    mode = (os.getenv("HEALTH_REPORT_MODE") or "always").strip().lower()
    return mode if mode in ("always", "on_warning") else "always"


def _is_ok(result) -> bool:
    return not getattr(result, "health_warnings", None) and not getattr(result, "errors", None)


def should_send_health(result) -> bool:
    if not is_health_report_enabled():
        return False
    if get_health_report_mode() == "on_warning":
        return not _is_ok(result)
    return True


def _summary_lines(result, *, run_id: str | None) -> tuple[bool, str, list[str]]:
    """(ok, status_emoji, body_lines) summarizing a cycle result."""
    ok = _is_ok(result)
    has_err = bool(getattr(result, "errors", None))
    emoji = "✅" if ok else ("❌" if has_err else "⚠")
    lines = [
        f"运行：{run_id or '-'}",
        f"覆盖：{getattr(result, 'coverage_status', 'unknown')} "
        f"({getattr(result, 'sources_succeeded', 0)}/{getattr(result, 'sources_total', 0)} 来源)",
        f"抓取启动：{getattr(result, 'fetch_started', 0)} · "
        f"摘要完成：{getattr(result, 'summary_completed', 0)} · "
        f"报告：{getattr(result, 'report_status', '-')}",
    ]
    finalized = list(getattr(result, "finalized_dates", []) or [])
    if finalized:
        lines.append(f"结算日报：{', '.join(finalized)}")
    delivered = list(getattr(result, "emailed_dates", []) or []) + list(getattr(result, "pushed_dates", []) or [])
    if delivered:
        lines.append(f"已分发：邮件 {len(getattr(result,'emailed_dates',[]) or [])} · 飞书 {len(getattr(result,'pushed_dates',[]) or [])}")
    if getattr(result, "stale_released", 0):
        lines.append(f"自动恢复卡死源：{result.stale_released}")
    warnings = list(getattr(result, "health_warnings", []) or [])
    for w in warnings:
        lines.append(f"⚠ {w}")
    for e in list(getattr(result, "errors", []) or []):
        lines.append(f"❌ {e}")
    if ok:
        lines.append("一切正常。")
    return ok, emoji, lines


def build_health_email(result, *, run_id: str | None = None) -> tuple[str, str, str]:
    """(subject, text_body, html_body) for the health digest email."""
    date = datetime.now().strftime("%Y-%m-%d")
    ok, emoji, lines = _summary_lines(result, run_id=run_id)
    subject = f"[AI 前沿雷达] 健康回执 {date} {emoji}"
    text_body = "\n".join([subject, "=" * 30, *lines])
    items = "".join(f"<li>{escape(l)}</li>" for l in lines)
    html_body = (
        '<div style="max-width:600px;margin:0 auto;font-family:-apple-system,'
        'Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        f'<h3 style="color:#111827;">每日周期健康回执 {emoji}</h3>'
        f'<div style="color:#6b7280;font-size:13px;">{escape(date)} · AI 前沿雷达</div>'
        f'<ul style="color:#1f2937;line-height:1.7;">{items}</ul>'
        "</div>"
    )
    return subject, text_body, html_body


def build_health_card(result, *, run_id: str | None = None) -> dict:
    """A Feishu interactive card for the health digest (green/orange/red header)."""
    date = datetime.now().strftime("%Y-%m-%d")
    ok, emoji, lines = _summary_lines(result, run_id=run_id)
    has_err = bool(getattr(result, "errors", None))
    template = "green" if ok else ("red" if has_err else "orange")
    body_md = "\n".join(lines)
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"【AI 前沿雷达】健康回执 {date} {emoji}"},
            "template": template,
        },
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body_md}}],
    }


def deliver_health_report(result, *, run_id: str | None = None, dry_run: bool = False) -> dict:
    """Send the health digest via every enabled channel. Never raises.

    Returns ``{sent, mode, channels: {email, feishu}, reason}``.
    """
    if dry_run:
        return {"sent": False, "mode": get_health_report_mode(), "reason": "dry_run", "channels": {}}
    if not should_send_health(result):
        reason = "disabled" if not is_health_report_enabled() else "ok_suppressed_on_warning_mode"
        return {"sent": False, "mode": get_health_report_mode(), "reason": reason, "channels": {}}

    channels: dict = {}
    sent_any = False

    # Email channel (reuses the report SMTP config)
    try:
        from app.application.radar.email_share import is_email_share_enabled, send_email
        if is_email_share_enabled():
            subject, text_body, html_body = build_health_email(result, run_id=run_id)
            outcome = send_email(subject, text_body, html_body, require_enabled=True)
            channels["email"] = outcome
            sent_any = sent_any or outcome.get("sent", False)
    except Exception as exc:
        channels["email"] = {"sent": False, "reason": f"error: {exc}"}

    # Feishu channel (reuses the report bot config)
    try:
        from app.application.radar.feishu_notify import is_feishu_share_enabled, send_feishu_card
        if is_feishu_share_enabled():
            card = build_health_card(result, run_id=run_id)
            outcome = send_feishu_card(card, require_enabled=True)
            channels["feishu"] = outcome
            sent_any = sent_any or outcome.get("sent", False)
    except Exception as exc:
        channels["feishu"] = {"sent": False, "reason": f"error: {exc}"}

    return {
        "sent": sent_any,
        "mode": get_health_report_mode(),
        "reason": "ok" if sent_any else "no_channel_enabled_or_failed",
        "channels": channels,
    }
