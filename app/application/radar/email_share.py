"""Opt-in email delivery of the finalized daily report (self / fixed recipients).

The lightest possible share-out channel: stdlib ``smtplib`` only, no subscriber
list, no unsubscribe flow, no external dependency. It mails the finalized daily
report to a small set of fixed recipients configured in ``.env``.

It is strictly opt-in and best-effort:
- A no-op unless ``EMAIL_SHARE_ENABLED=true`` AND SMTP host / sender / recipients
  are configured (``send_report_email`` returns a status dict, never raises).
- A send failure must never affect the daily cycle's exit code.

Designed for the "发给自己 / 少数固定收件人" use case — NOT a public newsletter.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from html import escape


@dataclass
class EmailConfig:
    host: str = ""
    port: int = 465
    user: str = ""
    password: str = ""
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    use_ssl: bool = True
    enabled: bool = False

    @property
    def is_complete(self) -> bool:
        """True when enough is configured to attempt a send."""
        return bool(self.host and self.sender and self.recipients)


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_email_config() -> EmailConfig:
    """Read SMTP + recipient config from the environment."""
    use_ssl = _env_bool("EMAIL_SMTP_SSL", default=True)
    raw_port = (os.getenv("EMAIL_SMTP_PORT") or "").strip()
    try:
        port = int(raw_port) if raw_port else (465 if use_ssl else 587)
    except ValueError:
        port = 465 if use_ssl else 587
    user = (os.getenv("EMAIL_SMTP_USER") or "").strip()
    sender = (os.getenv("EMAIL_FROM") or user).strip()
    recipients = [
        addr.strip()
        for addr in (os.getenv("EMAIL_TO") or "").replace(";", ",").split(",")
        if addr.strip()
    ]
    return EmailConfig(
        host=(os.getenv("EMAIL_SMTP_HOST") or "").strip(),
        port=port,
        user=user,
        password=os.getenv("EMAIL_SMTP_PASSWORD") or "",
        sender=sender,
        recipients=recipients,
        use_ssl=use_ssl,
        enabled=_env_bool("EMAIL_SHARE_ENABLED", default=False),
    )


def is_email_share_enabled(config: EmailConfig | None = None) -> bool:
    """True when auto email delivery is enabled AND sufficiently configured."""
    config = config or get_email_config()
    return config.enabled and config.is_complete


def build_report_email(
    report: dict,
    *,
    share_url: str | None = None,
    audio_url: str | None = None,
) -> tuple[str, str, str]:
    """Build (subject, text_body, html_body) from a finalized daily report dict.

    ``share_url`` (the public report page) and ``audio_url`` (the narration) are
    rendered as clickable links when provided.
    """
    date_label = str(report.get("date_label") or "")
    title = str(report.get("title") or "AI 前沿雷达 · 每日核心报告")
    overview = str(report.get("overview") or "")
    highlights = [str(h) for h in (report.get("highlights") or []) if str(h).strip()]
    refs = report.get("highlight_references") or []

    subject = f"[AI 前沿雷达] {date_label} · {title}".strip()

    def _first_url(idx: int) -> str | None:
        try:
            group = refs[idx]
        except (IndexError, TypeError):
            return None
        if isinstance(group, list) and group and isinstance(group[0], dict):
            url = group[0].get("url")
            return str(url) if url else None
        return None

    # ── plain-text body ──────────────────────────────────────────────────────
    text_lines = [title, "=" * 30]
    if overview:
        text_lines += [overview, ""]
    for i, h in enumerate(highlights):
        text_lines.append(f"{i + 1}. {h}")
        url = _first_url(i)
        if url:
            text_lines.append(f"   原文：{url}")
    if share_url:
        text_lines += ["", f"在线查看完整报告：{share_url}"]
    if audio_url:
        text_lines.append(f"收听语音播报：{audio_url}")
    text_body = "\n".join(text_lines)

    # ── HTML body ─────────────────────────────────────────────────────────────
    html_items = []
    for i, h in enumerate(highlights):
        url = _first_url(i)
        link = (
            f' <a href="{escape(url, quote=True)}" style="color:#2563eb;">原文 →</a>'
            if url else ""
        )
        html_items.append(f"<li style=\"margin-bottom:10px;\">{escape(h)}{link}</li>")
    overview_html = (
        f'<p style="color:#374151;line-height:1.7;">{escape(overview)}</p>'
        if overview else ""
    )
    footer_parts = []
    if share_url:
        footer_parts.append(
            f'<a href="{escape(share_url, quote=True)}" style="color:#2563eb;">在线查看完整报告 →</a>'
        )
    if audio_url:
        footer_parts.append(
            f'<a href="{escape(audio_url, quote=True)}" style="color:#2563eb;">收听语音播报 →</a>'
        )
    footer_html = (
        '<p style="margin-top:24px;">' + " &nbsp;·&nbsp; ".join(footer_parts) + "</p>"
        if footer_parts else ""
    )
    html_body = (
        '<div style="max-width:640px;margin:0 auto;font-family:-apple-system,'
        'Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        f'<h2 style="color:#111827;">{escape(title)}</h2>'
        f'<div style="color:#6b7280;font-size:13px;">{escape(date_label)} · AI 前沿雷达</div>'
        f"{overview_html}"
        f'<ol style="color:#1f2937;line-height:1.6;padding-left:20px;">{"".join(html_items)}</ol>'
        f"{footer_html}"
        "</div>"
    )
    return subject, text_body, html_body


def send_report_email(
    report: dict,
    *,
    share_url: str | None = None,
    audio_url: str | None = None,
    config: EmailConfig | None = None,
    require_enabled: bool = True,
    dry_run: bool = False,
    timeout: float = 20.0,
) -> dict:
    """Best-effort SMTP send of a finalized daily report. Never raises.

    Returns ``{sent: bool, reason: str, recipients: int}``.

    ``require_enabled=True`` (the auto path) skips when ``EMAIL_SHARE_ENABLED`` is
    off. ``require_enabled=False`` (the manual script) sends as long as SMTP
    config + recipients exist, regardless of the enabled flag.
    """
    config = config or get_email_config()
    if dry_run:
        return {"sent": False, "reason": "dry_run", "recipients": len(config.recipients)}
    if require_enabled and not config.enabled:
        return {"sent": False, "reason": "disabled", "recipients": len(config.recipients)}
    if not config.is_complete:
        return {"sent": False, "reason": "not_configured", "recipients": len(config.recipients)}

    subject, text_body, html_body = build_report_email(
        report, share_url=share_url, audio_url=audio_url
    )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.sender
    msg["To"] = ", ".join(config.recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        if config.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config.host, config.port, timeout=timeout, context=context) as smtp:
                if config.user:
                    smtp.login(config.user, config.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=timeout) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if config.user:
                    smtp.login(config.user, config.password)
                smtp.send_message(msg)
        return {"sent": True, "reason": "ok", "recipients": len(config.recipients)}
    except Exception as exc:  # network / auth / TLS — best-effort
        return {"sent": False, "reason": f"error: {exc}", "recipients": len(config.recipients)}
