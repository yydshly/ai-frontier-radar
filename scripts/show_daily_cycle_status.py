#!/usr/bin/env python3
"""Show the most recent daily-cycle run status in a human-readable format.

Intended for local operators / future control-software to quickly check the
result of the last scheduled run without reading raw JSON or log files.

Usage:
    python scripts/show_daily_cycle_status.py

This script:
- Does NOT call any LLM
- Does NOT access the network
- Does NOT modify the database
- Is read-only
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path so the import works from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.radar.daily_cycle_runs import (
    get_daily_cycle_log_path,
    load_latest_daily_cycle_run,
)


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds} 秒"
    minutes = seconds // 60
    remaining = seconds % 60
    if minutes < 60:
        return f"{minutes} 分 {remaining} 秒"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours} 小时 {remaining_minutes} 分"


def main() -> None:
    print("Daily Cycle Status")
    print("=" * 40)

    report = load_latest_daily_cycle_run()

    if report is None:
        print()
        print("尚未执行每日任务。")
        print()
        return

    # Gracefully handle missing / extra fields (forward compatibility).
    status = report.get("status", "unknown")
    mode = report.get("mode", "unknown")
    started_at = report.get("started_at", "N/A")
    finished_at = report.get("finished_at", "N/A")
    duration = report.get("duration_seconds")

    print()
    print(f"最近一次执行：{status}")
    print(f"模式：{mode}")
    print(f"开始时间：{started_at}")
    print(f"结束时间：{finished_at}")
    print(f"耗时：{_format_duration(duration)}")
    print()

    fetch_due = report.get("fetch_due")
    fetch_started = report.get("fetch_started")
    if fetch_due is not None or fetch_started is not None:
        print(
            f"来源同步：due={fetch_due} started={fetch_started}"
        )
    else:
        print("来源同步：N/A")

    summary_targets = report.get("summary_targets")
    summary_completed = report.get("summary_completed")
    if summary_targets is not None or summary_completed is not None:
        print(
            f"中文摘要：targets={summary_targets} completed={summary_completed}"
        )
    else:
        print("中文摘要：N/A")

    report_status = report.get("report_status", "unknown")
    audio_status = report.get("audio_status", "unknown")
    print(f"日报状态：{report_status}")
    print(f"音频状态：{audio_status}")

    finalized_dates = report.get("finalized_dates", [])
    if finalized_dates:
        print(f"已结算日期：{', '.join(finalized_dates)}")
    else:
        print("已结算日期：(无)")

    print()
    errors = report.get("errors", [])
    if errors:
        print("错误：")
        for err in errors:
            print(f"  ! {err}")
    else:
        print("错误：无")

    log_path = get_daily_cycle_log_path()
    print()
    print(f"日志文件：{log_path}")
    print()


if __name__ == "__main__":
    main()
