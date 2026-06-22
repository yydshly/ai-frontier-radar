"""Opt-in push of the finalized daily report to a Feishu (Lark) custom bot.

Companion to ``email_share`` for the "推送到通信软件" use case. Uses a Feishu
群机器人 custom webhook (https://open.feishu.cn/...). Stdlib only.

Strictly opt-in + best-effort:
- A no-op unless ``FEISHU_SHARE_ENABLED=true`` and ``FEISHU_WEBHOOK_URL`` is set.
- Optional signing via ``FEISHU_WEBHOOK_SECRET`` (when the bot has 签名校验 on).
- A send failure never affects the daily cycle.

Sends a ``msg_type=text`` message (the most robust shape — URLs are clickable in
the Feishu client). Title + overview + top highlights + report/audio links.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# How many highlights to include in the pushed message (keep it scannable).
_MAX_HIGHLIGHTS = 5


@dataclass
class FeishuConfig:
    webhook_url: str = ""
    secret: str = ""
    enabled: bool = False

    @property
    def is_complete(self) -> bool:
        return bool(self.webhook_url)


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_feishu_config() -> FeishuConfig:
    return FeishuConfig(
        webhook_url=(os.getenv("FEISHU_WEBHOOK_URL") or "").strip(),
        secret=(os.getenv("FEISHU_WEBHOOK_SECRET") or "").strip(),
        enabled=_env_bool("FEISHU_SHARE_ENABLED", default=False),
    )


def is_feishu_share_enabled(config: FeishuConfig | None = None) -> bool:
    config = config or get_feishu_config()
    return config.enabled and config.is_complete


def build_feishu_text(
    report: dict,
    *,
    share_url: str | None = None,
    audio_url: str | None = None,
) -> str:
    """Build the plain-text body for a Feishu text message from a report dict."""
    date_label = str(report.get("date_label") or "")
    title = str(report.get("title") or "AI 前沿雷达 · 每日核心报告")
    overview = str(report.get("overview") or "").strip()
    highlights = [str(h) for h in (report.get("highlights") or []) if str(h).strip()]

    lines = [f"【AI 前沿雷达】{date_label}", title]
    if overview:
        lines += ["", overview]
    if highlights:
        lines.append("")
        for i, h in enumerate(highlights[:_MAX_HIGHLIGHTS]):
            lines.append(f"{i + 1}. {h}")
        extra = len(highlights) - _MAX_HIGHLIGHTS
        if extra > 0:
            lines.append(f"…… 其余 {extra} 条见完整报告")
    if share_url:
        lines += ["", f"完整报告：{share_url}"]
    if audio_url:
        lines.append(f"语音播报：{audio_url}")
    return "\n".join(lines)


def build_feishu_card(
    report: dict,
    *,
    share_url: str | None = None,
    audio_url: str | None = None,
) -> dict:
    """Build a Feishu interactive card (the ``card`` object) from a report dict.

    Header = date + title; body = overview + top highlights (lark_md); an action
    row with 「查看完整报告」/「收听语音播报」buttons when the links exist.
    """
    date_label = str(report.get("date_label") or "")
    title = str(report.get("title") or "AI 前沿雷达 · 每日核心报告")
    overview = str(report.get("overview") or "").strip()
    highlights = [str(h) for h in (report.get("highlights") or []) if str(h).strip()]

    body_lines: list[str] = []
    if overview:
        body_lines.append(overview)
    if highlights:
        if body_lines:
            body_lines.append("")
        for i, h in enumerate(highlights[:_MAX_HIGHLIGHTS]):
            body_lines.append(f"**{i + 1}.** {h}")
        extra = len(highlights) - _MAX_HIGHLIGHTS
        if extra > 0:
            body_lines.append(f"_…… 其余 {extra} 条见完整报告_")
    body_md = "\n".join(body_lines) or title

    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": body_md}},
    ]
    buttons: list[dict] = []
    if share_url:
        buttons.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看完整报告"},
            "url": share_url,
            "type": "primary",
        })
    if audio_url:
        buttons.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "收听语音播报"},
            "url": audio_url,
            "type": "default",
        })
    if buttons:
        elements.append({"tag": "hr"})
        elements.append({"tag": "action", "actions": buttons})

    header_title = f"【AI 前沿雷达】{date_label} · {title}" if date_label else title
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": "blue",
        },
        "elements": elements,
    }


def _gen_sign(secret: str, timestamp: int) -> str:
    """Feishu custom-bot signature: base64(hmac_sha256(key='ts\\nsecret', msg=''))."""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_report_to_feishu(
    report: dict,
    *,
    share_url: str | None = None,
    audio_url: str | None = None,
    config: FeishuConfig | None = None,
    require_enabled: bool = True,
    dry_run: bool = False,
    timeout: float = 10.0,
) -> dict:
    """Best-effort push of a report to a Feishu custom bot. Never raises.

    Returns ``{sent: bool, reason: str}``. ``require_enabled=False`` (manual
    script) sends as long as a webhook URL is configured.
    """
    config = config or get_feishu_config()
    if dry_run:
        return {"sent": False, "reason": "dry_run"}
    if require_enabled and not config.enabled:
        return {"sent": False, "reason": "disabled"}
    if not config.is_complete:
        return {"sent": False, "reason": "not_configured"}

    card = build_feishu_card(report, share_url=share_url, audio_url=audio_url)
    return send_feishu_card(card, config=config, require_enabled=False, timeout=timeout)


def send_feishu_card(
    card: dict,
    *,
    config: FeishuConfig | None = None,
    require_enabled: bool = True,
    dry_run: bool = False,
    timeout: float = 10.0,
) -> dict:
    """Best-effort POST of an interactive card to the Feishu bot. Never raises.

    Shared by the report push and the health-report push. Returns
    ``{sent, reason}``.
    """
    config = config or get_feishu_config()
    if dry_run:
        return {"sent": False, "reason": "dry_run"}
    if require_enabled and not config.enabled:
        return {"sent": False, "reason": "disabled"}
    if not config.is_complete:
        return {"sent": False, "reason": "not_configured"}

    payload: dict = {"msg_type": "interactive", "card": card}
    if config.secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = _gen_sign(config.secret, ts)

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        config.webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        # Feishu returns {"code":0,...} (or StatusCode 0) on success.
        try:
            parsed = json.loads(body)
            code = parsed.get("code", parsed.get("StatusCode", 0))
        except (json.JSONDecodeError, AttributeError):
            code = 0
        if code in (0, "0"):
            return {"sent": True, "reason": "ok"}
        return {"sent": False, "reason": f"feishu_code_{code}: {body[:200]}"}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"sent": False, "reason": f"error: {exc}"}
