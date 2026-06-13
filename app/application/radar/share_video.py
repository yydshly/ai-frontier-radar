"""Compose a short "video card" from a still cover image + the day's audio.

The client renders a 9:16 cover (the share page's video card) with html2canvas and
uploads it; this module muxes it against the day's narration WAV via ffmpeg into a
single MP4 (a still-image audiogram). ffmpeg is optional: if it is not available the
feature is simply disabled (the share page hides the button).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def resolve_ffmpeg() -> str | None:
    """Return a usable ffmpeg path: PATH first, then a bundled bin\\ffmpeg(.exe)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    # Bundled fallback for portable installs that ship ffmpeg under bin/.
    root = Path(__file__).resolve().parents[3]
    for name in ("ffmpeg.exe", "ffmpeg"):
        candidate = root / "bin" / name
        if candidate.is_file():
            return str(candidate)
    return None


def video_enabled() -> bool:
    return resolve_ffmpeg() is not None


def compose_audiogram(
    cover_png: bytes,
    audio_path: Path,
    *,
    max_seconds: int = 600,
    timeout: int = 180,
) -> bytes:
    """Mux a still cover image + audio into an MP4 and return its bytes.

    Raises RuntimeError on any failure (no ffmpeg, bad input, ffmpeg error).
    """
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg 不可用")
    if not audio_path or not audio_path.is_file():
        raise RuntimeError("音频文件不存在")
    if not cover_png:
        raise RuntimeError("封面图为空")

    tmpdir = Path(tempfile.mkdtemp(prefix="share_video_"))
    cover = tmpdir / "cover.png"
    out = tmpdir / "out.mp4"
    try:
        cover.write_bytes(cover_png)
        cmd = [
            ffmpeg, "-y",
            "-loop", "1", "-i", str(cover),
            "-i", str(audio_path),
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "2",
            # force even dimensions (yuv420p requirement)
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-t", str(max_seconds),
            "-movflags", "+faststart",
            str(out),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not out.is_file():
            tail = (proc.stderr or b"").decode("utf-8", "replace")[-400:]
            raise RuntimeError(f"ffmpeg 失败: {tail}")
        return out.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
