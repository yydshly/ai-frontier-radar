"""Manually email a finalized daily report to the configured recipients.

For testing the email channel without waiting for / enabling the daily cycle.
Sends as long as SMTP config + EMAIL_TO are present (ignores EMAIL_SHARE_ENABLED,
since running this script IS an explicit opt-in).

Usage:
    python scripts/send_daily_report_email.py                 # latest final report
    python scripts/send_daily_report_email.py --date 2026-06-21
    python scripts/send_daily_report_email.py --dry-run       # build only, no send
    python scripts/send_daily_report_email.py --share-url https://example/...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on Windows GBK consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Email a finalized daily report.")
    parser.add_argument("--date", help="date label YYYY-MM-DD (default: latest final report)")
    parser.add_argument("--share-url", default=None, help="link to the online report")
    parser.add_argument("--dry-run", action="store_true", help="build the email but do not send")
    args = parser.parse_args()

    from app.application.radar.daily_report_store import (
        list_final_daily_report_dates,
        load_final_daily_report,
    )
    from app.application.radar.email_share import (
        get_email_config,
        send_report_email,
        build_report_email,
    )

    date_label = args.date
    if not date_label:
        dates = list_final_daily_report_dates()
        if not dates:
            print("没有任何正式日报，无法发送。")
            return 1
        date_label = dates[0]

    report = load_final_daily_report(date_label)
    if report is None:
        print(f"未找到 {date_label} 的正式日报。")
        return 1

    config = get_email_config()
    subject, _text, _html = build_report_email(report, share_url=args.share_url)
    print(f"日期: {date_label}")
    print(f"主题: {subject}")
    print(f"SMTP: {config.host}:{config.port} ssl={config.use_ssl} 发件={config.sender}")
    print(f"收件人: {config.recipients or '(未配置 EMAIL_TO)'}")

    outcome = send_report_email(
        report,
        share_url=args.share_url,
        config=config,
        require_enabled=False,  # explicit manual run is its own opt-in
        dry_run=args.dry_run,
    )
    print(f"结果: sent={outcome['sent']} reason={outcome['reason']} recipients={outcome['recipients']}")
    return 0 if (outcome["sent"] or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
