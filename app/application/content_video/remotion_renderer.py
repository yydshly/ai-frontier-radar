"""Remotion renderer for source-bound report summary videos."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from app.application.content_video.models import VideoScene


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
            "backgroundPreset": "tech_grid_dark",
            "transitionStyle": "slide_fade",
            "accentColor": "#3b82f6",
            "highlightColor": "#f59e0b",
            "motionIntensity": "medium",
        },
    }


def render_report_video(props: dict, output_path: Path, props_path: Path) -> None:
    available, message = check_remotion_available()
    if not available:
        raise RuntimeError(message)

    remotion_dir = get_remotion_dir()
    props_path.parent.mkdir(parents=True, exist_ok=True)
    props_path.write_text(
        json.dumps(props, ensure_ascii=False, indent=2),
        encoding="utf-8",
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
    timeout = int(os.getenv("CONTENT_VIDEO_REMOTION_TIMEOUT_SECONDS", "900"))
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
    if proc.returncode != 0 or not output_path.is_file():
        detail = (proc.stderr or proc.stdout or "").strip()[-1200:]
        raise RuntimeError(f"Remotion render failed: {detail}")