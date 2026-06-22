#!/usr/bin/env bash
# start_local.sh — Linux/macOS equivalent of start_local.ps1.
#
# Starts the uvicorn web server. Host/port overridable via env:
#   HOST (default 127.0.0.1)   PORT (default 8765)
#
# Usage:
#   scripts/start_local.sh
#   HOST=0.0.0.0 PORT=8000 scripts/start_local.sh
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

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
export PYTHONIOENCODING=utf-8

echo "AI Frontier Radar - starting on http://${HOST}:${PORT}"
exec "${PYTHON}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"
