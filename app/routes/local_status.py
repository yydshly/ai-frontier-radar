"""Local run status page — read-only, no LLM calls."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["local-status"])
_templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
)


def _project_root() -> Path:
    """Return the project root directory.

    This file lives at app/routes/local_status.py, so:
      parents[0] = app/routes/
      parents[1] = app/
      parents[2] = <project root>/
    """
    return Path(__file__).resolve().parents[2]


def _load_latest_report() -> dict | None:
    """Load runtime/daily_cycle_runs/latest.json safely. Returns None if absent or corrupt."""
    latest_path = _project_root() / "runtime" / "daily_cycle_runs" / "latest.json"
    try:
        return json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


@router.get("/local-status", response_class=HTMLResponse)
def local_status(request: Request):
    """Render the local run status page.

    Shows:
    - Web service address
    - Key directory paths
    - Latest daily-cycle run result (from latest.json)
    - NO API keys, no LLM calls, no network access.
    """
    report = _load_latest_report()

    project_root = _project_root()
    logs_dir = project_root / "logs"
    runtime_dir = project_root / "runtime"

    key_dirs = {
        "配置文件 (.env)": str(project_root / ".env"),
        "来源配置": str(project_root / "config" / "sources.yaml"),
        "数据目录": str(project_root / "data"),
        "运行产物目录": str(runtime_dir),
        "日志目录": str(logs_dir),
        "Web 日志": str(logs_dir / "app.log"),
        "每日任务日志": str(logs_dir / "daily_cycle.log"),
        "最近执行报告": str(runtime_dir / "daily_cycle_runs" / "latest.json"),
        "日报存储": str(runtime_dir / "daily_reports"),
        "音频存储": str(runtime_dir / "daily_audio"),
    }

    return _templates.TemplateResponse(
        "local_status.html",
        {
            "request": request,
            "report": report,
            "key_dirs": key_dirs,
            "project_root": str(project_root),
            "web_address": "http://127.0.0.1:8765",
        },
    )
