"""Remotion renderer for source-bound report summary videos."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from app.application.content_video.models import VideoScene

logger = logging.getLogger(__name__)


COMPOSITION_ID = "RadarReportVideo"
FPS = 30


def get_remotion_dir() -> Path:
    configured = os.getenv("CONTENT_VIDEO_REMOTION_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "remotion"


def _npx_command() -> list[str]:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found; install Node.js to enable Remotion.")
    return [npx]


def _remotion_timeout_seconds() -> int:
    """Return Remotion render timeout in seconds from env var, default 360.

    Validates the value: must be at least 30 seconds to avoid accidental 0/negative.
    Falls back to 360 on invalid or empty values.
    """
    raw = os.getenv("CONTENT_VIDEO_REMOTION_TIMEOUT_SECONDS", "").strip()
    try:
        value = int(raw) if raw else 360
    except ValueError:
        value = 360
    return max(30, value)


def check_remotion_available() -> tuple[bool, str]:
    remotion_dir = get_remotion_dir()
    if not shutil.which("node"):
        return False, "Node.js not found"
    if not (remotion_dir / "package.json").is_file():
        return False, f"Remotion workspace missing: {remotion_dir}"
    if not (remotion_dir / "node_modules" / "remotion").is_dir():
        return False, f"Remotion dependencies missing; run npm install in {remotion_dir}"
    try:
        _npx_command()
    except RuntimeError as exc:
        return False, str(exc)
    return True, f"Remotion available: {remotion_dir}"


def _scene_kicker(scene: VideoScene) -> str:
    """Pick a kicker label for a scene, honoring the metadata-set value."""
    md = scene.metadata or {}
    if isinstance(md, dict) and md.get("kicker"):
        return str(md["kicker"])
    if scene.scene_type == "opening":
        return "AI FRONTIER RADAR"
    if scene.scene_type == "overview_paged":
        page = md.get("page") if isinstance(md, dict) else None
        total = md.get("total_pages") if isinstance(md, dict) else None
        if page and total and total > 1:
            return f"TODAY'S OVERVIEW · {page}/{total}"
        return "TODAY'S OVERVIEW"
    if scene.scene_type == "core_insight":
        return "CORE INSIGHT"
    if scene.scene_type == "core_insight_continuation":
        idx = md.get("section_index") if isinstance(md, dict) else None
        part = md.get("part") if isinstance(md, dict) else None
        if idx is not None and part is not None:
            return f"CORE INSIGHT {idx:02d} · PART {part}"
        return "CORE INSIGHT · CONTINUED"
    if scene.scene_type == "supporting_notes":
        page = md.get("page") if isinstance(md, dict) else None
        total = md.get("total_pages") if isinstance(md, dict) else None
        if page and total and total > 1:
            return f"MORE SIGNALS · {page}/{total}"
        return "MORE SIGNALS"
    if scene.scene_type == "closing":
        return "READ THE FULL REPORT"
    return "DAILY INTELLIGENCE"


def build_report_props(
    scenes: list[VideoScene],
    *,
    title: str,
    subtitle: str | None,
    date_label: str | None,
    share_url: str | None = None,
    qr_code_data_url: str | None = None,
) -> dict:
    """Build the props dict consumed by the Remotion composition.

    The ``scenes`` array preserves the original order and per-scene
    duration.  Each scene carries its kicker, lines, and any QR/shareUrl
    metadata needed by the closing scene.
    """
    scene_props = []
    for index, scene in enumerate(scenes):
        duration = max(1.0, float(scene.duration_seconds or 1.0))
        md = scene.metadata or {}
        kicker = _scene_kicker(scene)
        scene_props.append({
            "id": scene.scene_id,
            "type": scene.scene_type,
            "title": scene.visual_title,
            "lines": list(scene.visual_lines),
            "sourceLabel": (scene.source_label or "")[:60] or None,
            "durationInFrames": max(30, round(duration * FPS)),
            "index": index,
            "kicker": kicker,
            "shareUrl": (
                md.get("share_url") if isinstance(md, dict) else None
            ) or share_url,
            "qrCodeDataUrl": (
                md.get("qr_code_data_url") if isinstance(md, dict) else None
            ) or qr_code_data_url,
            "metadata": md,
        })

    return {
        "title": title,
        "subtitle": subtitle or "",
        "dateLabel": date_label or "",
        "shareUrl": share_url,
        "qrCodeDataUrl": qr_code_data_url,
        "scenes": scene_props,
        "style": {
            # Background + motion are configurable (calmer = better reading):
            #   CONTENT_VIDEO_BG_PRESET  calm | grid | plain   (default calm)
            #   CONTENT_VIDEO_MOTION     low | medium          (default low)
            "backgroundPreset": (os.getenv("CONTENT_VIDEO_BG_PRESET") or "calm").strip().lower(),
            "transitionStyle": "slide_fade",
            "accentColor": (os.getenv("CONTENT_VIDEO_ACCENT") or "#3b82f6").strip(),
            "highlightColor": (os.getenv("CONTENT_VIDEO_HIGHLIGHT") or "#f59e0b").strip(),
            "motionIntensity": (os.getenv("CONTENT_VIDEO_MOTION") or "low").strip().lower(),
        },
    }


def render_report_video(props: dict, output_path: Path, props_path: Path) -> None:
    available, message = check_remotion_available()
    if not available:
        raise RuntimeError(message)

    remotion_dir = get_remotion_dir()

    # [DEBUG-1] 开始写 props
    logger.info(
        "[DEBUG-1] Starting render: remotion_dir=%s, remotion_dir_exists=%s, cwd=%s",
        remotion_dir, remotion_dir.exists(), os.getcwd(),
    )

    props_path.parent.mkdir(parents=True, exist_ok=True)
    props_path.write_text(
        json.dumps(props, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # [DEBUG-2] props 写完后
    logger.info(
        "[DEBUG-2] Props written: props_path=%s, props_size=%d bytes, output_path=%s",
        props_path, props_path.stat().st_size, output_path,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *_npx_command(),
        "remotion",
        "render",
        "./src/Root.tsx",
        COMPOSITION_ID,
        output_path.resolve().as_posix(),
        "--props",
        props_path.resolve().as_posix(),
        "--codec",
        "h264",
        "--x264-preset",
        "veryfast",
        "--crf",
        "24",
        "--concurrency",
        os.getenv("CONTENT_VIDEO_REMOTION_CONCURRENCY", "50%"),
    ]
    run_command = command
    if os.name == "nt":
        run_command = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            subprocess.list2cmdline(command),
        ]

    timeout = _remotion_timeout_seconds()

    # [DEBUG-3] subprocess 启动前（关键）
    logger.info(
        "[DEBUG-3] About to call subprocess.run: "
        "cwd=%s, cwd_exists=%s, timeout=%d, "
        "run_command[0]=%s, run_command_type=%s, creationflags=%s, "
        "COMSPEC=%s, PATH_snippet=%s",
        str(remotion_dir), os.path.exists(str(remotion_dir)),
        timeout,
        run_command[0], type(run_command[0]).__name__,
        getattr(subprocess, "CREATE_NO_WINDOW", 0),
        os.environ.get("COMSPEC", ""),
        os.environ.get("PATH", "")[:150],
    )

    try:
        proc = subprocess.run(
            run_command,
            cwd=str(remotion_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # [DEBUG-4] subprocess 返回了
        logger.info(
            "[DEBUG-4] subprocess returned: returncode=%s, stdout_len=%d, stderr_len=%d",
            proc.returncode, len(proc.stdout), len(proc.stderr),
        )

    except subprocess.TimeoutExpired as exc:
        # [DEBUG-5] 超时发生
        logger.warning(
            "[DEBUG-5] TimeoutExpired: timeout=%ds, "
            "remotion_dir=%s, remotion_dir_exists=%s, output_exists=%s, cwd=%s",
            timeout, remotion_dir, remotion_dir.exists(), output_path.exists(), os.getcwd(),
        )
        raise RuntimeError(
            f"Remotion render timed out after {timeout}s; "
            f"remotion_dir={remotion_dir}; output_path={output_path}; props_path={props_path}"
        ) from exc

    if proc.returncode != 0 or not output_path.is_file():
        detail = (proc.stderr or proc.stdout or "").strip()[-1200:]
        logger.warning("Remotion render failed: %s", detail)
        raise RuntimeError(f"Remotion render failed: {detail}")

    # [DEBUG-6] 成功完成
    logger.info(
        "[DEBUG-6] Remotion render finished: output_path=%s, size=%s",
        output_path,
        output_path.stat().st_size if output_path.is_file() else "N/A",
    )