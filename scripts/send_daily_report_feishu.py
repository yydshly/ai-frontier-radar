"""Manually push a finalized daily report to the Feishu custom bot.

For testing the Feishu channel without enabling the daily cycle. Sends as long
as FEISHU_WEBHOOK_URL is set (ignores FEISHU_SHARE_ENABLED — running this is the
opt-in).

Usage:
    python scripts/send_daily_report_feishu.py                 # latest final report
    python scripts/send_daily_report_feishu.py --date 2026-06-21
    python scripts/send_daily_report_feishu.py --dry-run       # build text only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Push a finalized daily report to Feishu.")
    parser.add_argument("--date", help="date label YYYY-MM-DD (default: latest final report)")
    parser.add_argument("--dry-run", action="store_true", help="build the message but do not send")
    args = parser.parse_args()

    from app.application.radar.daily_report_store import (
        list_final_daily_report_dates,
        load_final_daily_report,
    )
    from app.application.radar.daily_cycle import _share_urls_for
    from app.application.radar.feishu_notify import (
        get_feishu_config,
        build_feishu_text,
        send_report_to_feishu,
    )

    date_label = args.date
    if not date_label:
        dates = list_final_daily_report_dates()
        if not dates:
            print("没有任何正式日报，无法推送。")
            return 1
        date_label = dates[0]

    report = load_final_daily_report(date_label)
    if report is None:
        print(f"未找到 {date_label} 的正式日报。")
        return 1

    share_url, audio_url = _share_urls_for(date_label, report)
    config = get_feishu_config()
    print(f"日期: {date_label}")
    print(f"Webhook: {config.webhook_url or '(未配置 FEISHU_WEBHOOK_URL)'} 签名={'有' if config.secret else '无'}")
    print("---- 消息预览 ----")
    print(build_feishu_text(report, share_url=share_url, audio_url=audio_url))
    print("------------------")

    outcome = send_report_to_feishu(
        report,
        share_url=share_url,
        audio_url=audio_url,
        config=config,
        require_enabled=False,
        dry_run=args.dry_run,
    )
    print(f"结果: sent={outcome['sent']} reason={outcome['reason']}")
    return 0 if (outcome["sent"] or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
