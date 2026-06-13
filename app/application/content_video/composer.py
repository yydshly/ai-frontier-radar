"""content_video — FFmpeg-based video composer.

Composes:
  scene_XX.png + scene_XX.mp3  →  clips/scene_XX.mp4
  clips/scene_XX.mp4 [×N]      →  output.mp4

Each clip uses the audio duration with a short buffer.
V1 supports: fade-in, static image + audio.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.application.content_video.models import VideoScene


def _find_binary(name: str) -> str | None:
    import shutil as _sh
    found = _sh.which(name)
    if found:
        return found
    root = Path(__file__).resolve().parents[3]
    for fn in (name + ".exe", name):
        candidate = root / "bin" / fn
        if candidate.is_file():
            return str(candidate)
    return None


def get_video_duration(path: Path) -> float | None:
    """Get video duration in seconds using ffprobe.

    Returns None if ffprobe is unavailable or fails.
    """
    ffprobe = _find_binary("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode == 0:
            return max(0.1, float(out.stdout.decode().strip()))
    except Exception:
        pass
    return None


def _resolve_ffmpeg() -> str:
    ffmpeg = _find_binary("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found — install ffmpeg to enable video composition.")
    return ffmpeg


def _audio_duration(path: Path) -> float:
    """Get audio duration via ffprobe."""
    ffprobe = _find_binary("ffprobe")
    if not ffprobe:
        return 5.0
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return max(1.0, float(out.stdout.decode().strip()))
    except Exception:
        return 5.0


def compose_clip(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    *,
    fade_in: float = 0.5,
    buffer: float = 0.5,
) -> float:
    """Compose one scene: static PNG + MP3 → MP4 clip.

    Returns the clip duration in seconds.
    Raises RuntimeError on ffmpeg failure.
    """
    ffmpeg = _resolve_ffmpeg()
    duration = _audio_duration(audio_path)
    total_dur = duration + buffer

    cmd = [
        ffmpeg, "-y",
        "-loop", "1",
        "-framerate", "25",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x080f18,"
        f"fade=t=in:st=0:d={fade_in}:alpha=1,"
        f"format=yuv420p[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-r", "25",
        "-t", str(total_dur),
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        timeout=max(60, int(total_dur * 2)),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0 or not output_path.exists():
        tail = (proc.stderr or b"").decode("utf-8", "replace")[-500:]
        raise RuntimeError(f"ffmpeg clip composition failed: {tail}")
    return total_dur


def concatenate_clips(
    clip_paths: list[Path],
    output_path: Path,
) -> None:
    """Concatenate multiple MP4 clips into a single output MP4.

    Raises RuntimeError if ffmpeg is unavailable or concatenation fails.
    """
    if not clip_paths:
        raise RuntimeError("No clips to concatenate.")

    ffmpeg = _resolve_ffmpeg()

    with tempfile.TemporaryDirectory(prefix="share_video_concat_") as tmpdir:
        list_file = Path(tmpdir) / "clips.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                f.write(f"file '{clip.as_posix()}'\n")

        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not output_path.exists():
            tail = (proc.stderr or b"").decode("utf-8", "replace")[-500:]
            raise RuntimeError(f"ffmpeg concatenation failed: {tail}")


def compose_video(
    scenes: list[VideoScene],
    storage,
    output_path: Path | None = None,
) -> Path:
    """Compose all scenes into a final MP4.

    Args:
        scenes: ordered list of VideoScene (must have image_path + audio_path set)
        storage: VideoStorage instance for clip_dir access
        output_path: explicit output path; defaults to storage.output_mp4_path

    Returns the path to the final MP4.
    """
    if output_path is None:
        output_path = storage.output_mp4_path

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Compose each scene clip
    clip_paths: list[Path] = []
    for scene in scenes:
        img = Path(scene.image_path) if scene.image_path else storage.scene_image_path(scene.scene_id)
        aud = Path(scene.audio_path) if scene.audio_path else storage.scene_audio_path(scene.scene_id)
        clip = storage.scene_clip_path(scene.scene_id)

        if not img.exists():
            raise RuntimeError(f"Scene image missing: {img}")
        if not aud.exists():
            raise RuntimeError(f"Scene audio missing: {aud}")

        compose_clip(img, aud, clip)
        clip_paths.append(clip)

    # Concatenate all clips
    concatenate_clips(clip_paths, output_path)
    return output_path
