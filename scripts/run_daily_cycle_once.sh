#!/usr/bin/env bash
# run_daily_cycle_once.sh — Linux/macOS equivalent of run_daily_cycle_once.ps1.
#
# Runs ONE daily cycle (fetch → summarize → report → opt-in audio/share-out).
# Intended for manual runs and for cron / systemd timers.
#
# Usage:
#   scripts/run_daily_cycle_once.sh            # --apply
#   scripts/run_daily_cycle_once.sh --no-audio
set -euo pipefail

# Resolve the project root (parent of this script's dir), regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Python selection: project venv > python3 > python.
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

export PYTHONIOENCODING=utf-8

echo "============================================================"
echo "AI Frontier Radar - Run Daily Cycle Once"
echo "============================================================"
echo "Project root: ${PROJECT_ROOT}"
echo "Python:       ${PYTHON}"
echo "Live log:     logs/daily_cycle.live.log"
echo

# Default to --apply when no args are given; otherwise pass args through.
if [ "$#" -eq 0 ]; then
    exec "${PYTHON}" -u scripts/run_daily_cycle.py --apply
else
    exec "${PYTHON}" -u scripts/run_daily_cycle.py "$@"
fi
