#!/usr/bin/env bash
# run_fetch_once.sh — Linux/macOS FETCH-ONLY runner (companion to the daily cycle).
#
# Fetches due sources only (no finalize, no report, no LLM). Run it frequently
# (cron / systemd timer, every few hours) so the current daily window accumulates
# fresh content before run_daily_cycle finalizes it. See README
# "信息及时性：抓取节奏与报告窗口".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# The two explicit safety gates required by run_due_sources_once.py --apply.
export RADAR_SCHEDULER_ENABLED=true
export AUTO_SUMMARY_MAX_PER_FETCH_RUN=0   # fetch only — never trigger LLM summaries
export PYTHONIOENCODING=utf-8

exec "${PYTHON}" -u scripts/run_due_sources_once.py --apply
