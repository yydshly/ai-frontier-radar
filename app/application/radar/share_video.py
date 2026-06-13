"""Compose a short, lively "video card" from the core-report poster + audio.

The client renders the core-report poster (a tall PNG) with html2canvas and uploads
it. This module muxes it against the day's narration WAV via ffmpeg into a 9:16 MP4
with motion:
  - the poster scrolls top->bottom over the narration (so the whole report plays,
    paced to the voice). Short posters are centered instead.
  - an audio-reactive waveform sits along the bottom — it moves with the speech,
    which is the "lively / 拟人化" element.
  - a gentle fade-in.

ffmpeg is optional: if unavailable the feature is disabled (the button is hidden).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

FRAME_W = 1080
FRAME_H = 1920
WAVE_H = 150
WAVE_COLOR = "0x34D399"
BG_COLOR = "0x080f18"


def _resolve(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    root = Path(__file__).resolve().parents[3]
    for fn in (name + ".exe", name):
        candidate = root / "bin" / fn
        if candidate.is_file():
            return str(candidate)
    return None


def resolve_ffmpeg() -> str | None:
    return _resolve("ffmpeg")


def video_enabled() -> bool:
    return resolve_ffmpeg() is not None


def _png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("封面不是有效 PNG")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _audio_duration(audio_path: Path) -> float:
    probe = _resolve("ffprobe")
    if probe:
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(audio_path)],
                capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return max(1.0, float(out.stdout.decode().strip()))
        except Exception:
            pass
    return 30.0  # best-effort fallback when ffprobe is unavailable


def _build_filter(scaled_h: int, duration: float) -> str:
    """Filtergraph: scroll-or-center the poster + bottom waveform + fade-in."""
    wave = (
        f"[1:a]showwaves=s={FRAME_W}x{WAVE_H}:mode=cline:rate=25:colors={WAVE_COLOR},"
        f"format=rgba,colorchannelmixer=aa=0.85[wave]"
    )
    if scaled_h > FRAME_H:
        # Pan a full-frame window from the top to the bottom over `duration`.
        span = scaled_h - FRAME_H
        base = (
            f"[0:v]scale={FRAME_W}:-1,setsar=1[card];"
            f"[card]crop={FRAME_W}:{FRAME_H}:0:"
            f"'min({span}\\,{span}*(t/{duration:.3f}))'[base]"
        )
    else:
        base = (
            f"[0:v]scale={FRAME_W}:-1,setsar=1,"
            f"pad={FRAME_W}:{FRAME_H}:0:(oh-ih)/2:color={BG_COLOR}[base]"
        )
    return (
        f"{base};{wave};"
        f"[base][wave]overlay=0:{FRAME_H - WAVE_H - 24}:shortest=1,"
        f"fade=t=in:st=0:d=0.6,format=yuv420p[v]"
    )


def compose_audiogram(
    cover_png: bytes,
    audio_path: Path,
    *,
    max_seconds: int = 600,
    timeout: int = 240,
) -> bytes:
    """Mux the poster image + audio into a 9:16 MP4 with motion. Returns mp4 bytes.

    Raises RuntimeError on any failure (no ffmpeg, bad input, ffmpeg error).
    """
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg 不可用")
    if not audio_path or not audio_path.is_file():
        raise RuntimeError("音频文件不存在")
    if not cover_png:
        raise RuntimeError("封面图为空")

    cover_w, cover_h = _png_size(cover_png)
    scaled_h = round(FRAME_W * cover_h / max(1, cover_w))
    duration = min(float(max_seconds), _audio_duration(audio_path))
    filtergraph = _build_filter(scaled_h, duration)

    tmpdir = Path(tempfile.mkdtemp(prefix="share_video_"))
    cover = tmpdir / "cover.png"
    out = tmpdir / "out.mp4"
    try:
        cover.write_bytes(cover_png)
        cmd = [
            ffmpeg, "-y",
            "-loop", "1", "-framerate", "25", "-i", str(cover),
            "-i", str(audio_path),
            "-filter_complex", filtergraph,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "25",
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
            tail = (proc.stderr or b"").decode("utf-8", "replace")[-500:]
            raise RuntimeError(f"ffmpeg 失败: {tail}")
        return out.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
