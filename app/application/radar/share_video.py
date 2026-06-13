"""Compose a static-but-lively "video card" from the core-report poster + audio.

The client renders the core-report poster (a single full PNG showing the whole
report — no scrolling) with html2canvas and uploads it together with the pixel
boxes of each readable block (overview + each highlight). This module muxes the
poster against the day's narration WAV via ffmpeg into a portrait MP4 where:
  - the poster stays static and fully readable;
  - a read-along highlight steps through the blocks, paced by playback progress
    (audio duration / block count) — an approximate "跟读" marker, NOT word-level
    sync (we have no transcript timing);
  - an audio-reactive waveform sits in a strip below the poster — it moves with
    the actual voice (the genuinely voice-synced element);
  - a gentle fade-in.

ffmpeg is optional: if unavailable the feature is disabled (the button is hidden).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

WAVE_H = 140          # waveform render height
WAVE_STRIP = 168      # bottom strip added under the poster to hold the waveform
HILITE_COLOR = "0x34D399"
HILITE_ALPHA = 0.16
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


def _sanitize_lines(lines, cover_w: int, cover_h: int) -> list[dict]:
    """Keep only well-formed, in-bounds boxes."""
    clean: list[dict] = []
    for ln in lines or []:
        try:
            x, y, w, h = int(ln["x"]), int(ln["y"]), int(ln["w"]), int(ln["h"])
        except (TypeError, KeyError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        x = max(0, min(x, cover_w - 1))
        y = max(0, min(y, cover_h - 1))
        w = min(w, cover_w - x)
        h = min(h, cover_h - y)
        if w > 0 and h > 0:
            clean.append({"x": x, "y": y, "w": w, "h": h})
    return clean


def _build_filter(cover_w: int, duration: float, lines: list[dict]) -> str:
    parts = [
        f"[0:v]scale={cover_w}:-2,setsar=1,"
        f"pad=iw:ih+{WAVE_STRIP}:0:0:color={BG_COLOR}[base0]"
    ]
    label = "base0"
    if lines:
        seg = duration / len(lines)
        for i, ln in enumerate(lines):
            s, e = i * seg, (i + 1) * seg
            out = f"hl{i}"
            parts.append(
                f"[{label}]drawbox=x={ln['x']}:y={ln['y']}:w={ln['w']}:h={ln['h']}:"
                f"color={HILITE_COLOR}@{HILITE_ALPHA}:t=fill:"
                f"enable='between(t,{s:.2f},{e:.2f})'[{out}]"
            )
            label = out
    parts.append(
        f"[1:a]showwaves=s={cover_w}x{WAVE_H}:mode=cline:rate=25:colors={HILITE_COLOR},"
        f"format=rgba,colorchannelmixer=aa=0.85[wave]"
    )
    parts.append(
        f"[{label}][wave]overlay=0:H-{WAVE_H + 14}:shortest=1,"
        f"fade=t=in:st=0:d=0.6,format=yuv420p[v]"
    )
    return ";".join(parts)


def compose_audiogram(
    cover_png: bytes,
    audio_path: Path,
    *,
    lines=None,
    max_seconds: int = 600,
    timeout: int = 240,
) -> bytes:
    """Mux the static poster + audio into a portrait MP4 with a read-along
    highlight and a voice-reactive waveform. Returns mp4 bytes.

    `lines` is an optional list of {x,y,w,h} pixel boxes (in cover coordinates)
    for each readable block, used to drive the read-along highlight.

    Raises RuntimeError on any failure.
    """
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg 不可用")
    if not audio_path or not audio_path.is_file():
        raise RuntimeError("音频文件不存在")
    if not cover_png:
        raise RuntimeError("封面图为空")

    cover_w, cover_h = _png_size(cover_png)
    even_w = cover_w - (cover_w % 2)
    duration = min(float(max_seconds), _audio_duration(audio_path))
    clean_lines = _sanitize_lines(lines, cover_w, cover_h)
    filtergraph = _build_filter(even_w, duration, clean_lines)

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
