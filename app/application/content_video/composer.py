"""content_video — FFmpeg-based video composer.

Composes:
  scene_XX.png + scene_XX.mp3  →  clips/scene_XX.mp4
  clips/scene_XX.mp4 [×N]      →  output.mp4

Each clip uses the audio duration with a short buffer.
V1 supports: fade-in, static image + audio.
"""
from __future__ import annotations

import re
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


def concatenate_audio(
    audio_paths: list[Path],
    output_path: Path,
) -> None:
    """Concatenate scene narration tracks into one AAC timeline."""
    if not audio_paths:
        raise RuntimeError("No audio tracks to concatenate.")

    ffmpeg = _resolve_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="share_audio_concat_") as tmpdir:
        list_file = Path(tmpdir) / "audio.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for audio_path in audio_paths:
                f.write(f"file '{audio_path.as_posix()}'\n")
        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-vn",
            "-c:a", "aac",
            "-b:a", "160k",
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
            raise RuntimeError(f"ffmpeg audio concatenation failed: {tail}")


def mux_video_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> None:
    """Mux a Remotion visual track with the concatenated narration."""
    ffmpeg = _resolve_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "160k",
        "-shortest",
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
        raise RuntimeError(f"ffmpeg audio mux failed: {tail}")


def extract_poster(video_path: Path, output_path: Path, *, at_seconds: float = 0.8) -> None:
    """Extract a representative poster frame from a generated video."""
    ffmpeg = _resolve_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-ss", str(max(0.0, at_seconds)),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0 or not output_path.exists():
        tail = (proc.stderr or b"").decode("utf-8", "replace")[-500:]
        raise RuntimeError(f"ffmpeg poster extraction failed: {tail}")


def _ass_timestamp(ms: float) -> str:
    cs = max(0, int(round(ms / 10)))  # centiseconds
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# ASS header. PlayResX/Y match the real video so Fontsize/margins are in true
# pixels (avoids libass's default-res scaling that blows the font up / breaks
# wrapping). Colours are &HAABBGGRR (AA: 00=opaque, FF=transparent).
_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,52,&H00FFFFFF,&H10000000,&H60000000,1,0,0,0,100,100,0,0,1,3,1,2,90,90,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


_CAPTION_SEPARATORS = "，,、；;：:。！？!?"
# An "atom" is either a whole alphanumeric token (kept intact — dates like
# 2026-06-12, numbers like 88.9%, words like ChatGPT) or a single other char.
_ATOM_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z\-./:%]*")


def _atomize(text: str) -> list[str]:
    atoms: list[str] = []
    i = 0
    while i < len(text):
        m = _ATOM_RE.match(text, i)
        if m:
            atoms.append(m.group())
            i = m.end()
        else:
            atoms.append(text[i])
            i += 1
    return atoms


def _chunk_caption(text: str, max_chars: int = 16) -> list[str]:
    """Break one sentence into short, readable caption chunks.

    Token-aware: never splits inside an alphanumeric token (dates/numbers/English
    stay whole). Prefers to break right after a separator; otherwise breaks once
    adding the next atom would exceed ``max_chars``.
    """
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    buf = ""
    for atom in _atomize(text):
        if buf and len(buf) + len(atom) > max_chars and len(buf) >= max_chars * 0.5:
            chunks.append(buf)
            buf = ""
        buf += atom
        if atom and atom[-1] in _CAPTION_SEPARATORS and len(buf) >= max_chars * 0.5:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    # Merge orphan tiny chunks (e.g. a trailing single char) into the previous.
    merged: list[str] = []
    for ch in chunks:
        if merged and len(ch.strip()) <= 3:
            merged[-1] += ch
        else:
            merged.append(ch)
    return [c.strip("，,、；;：: ") for c in merged if c.strip("，,、；;：: ")]


# Highlight impactful data figures (with a unit/percent) in amber; dates and
# bare counts stay white. ASS inline colour is &HBBGGRR; {\r} resets to style.
_NUM_HL_RE = re.compile(r"\d[\d.,]*(?:%|万|亿|倍)")
_NUM_HL_OPEN = "{\\c&H000BA5F5&}"
_NUM_HL_RESET = "{\\r}"


def _highlight_numbers(text: str) -> str:
    return _NUM_HL_RE.sub(lambda m: f"{_NUM_HL_OPEN}{m.group()}{_NUM_HL_RESET}", text)


def build_ass_from_scenes(scenes: list[VideoScene], *, gap_seconds: float = 0.0) -> str:
    """Build an ASS subtitle file from per-scene subtitle segments.

    Each scene's segments are timed relative to its own audio; we offset them by
    the cumulative scene placement. ``gap_seconds`` is the inter-scene padding the
    compose path adds per clip (0 for the Remotion mux, the clip buffer for PIL).
    Long sentence segments are sub-split into short caption chunks, with the
    segment's time window allocated proportionally by chunk length (approximate
    intra-sentence timing — we only have sentence-level timestamps).
    """
    events: list[str] = []
    offset_ms = 0.0
    for scene in scenes:
        dur_ms = (scene.duration_seconds or 0.0) * 1000.0
        for seg in (getattr(scene, "subtitle_segments", None) or []):
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            seg_begin = offset_ms + float(seg.get("begin_ms", 0.0))
            seg_end = min(offset_ms + float(seg.get("end_ms", 0.0)), offset_ms + dur_ms)
            if seg_end <= seg_begin:
                seg_end = seg_begin + 800
            chunks = _chunk_caption(text) or [text]
            total_chars = sum(len(c) for c in chunks) or 1
            span = seg_end - seg_begin
            t = seg_begin
            for c in chunks:
                share = span * (len(c) / total_chars)
                c_begin, c_end = t, t + share
                t = c_end
                safe = _highlight_numbers(c.replace("\n", " ").strip())
                events.append(
                    f"Dialogue: 0,{_ass_timestamp(c_begin)},{_ass_timestamp(c_end)},"
                    f"Default,,0,0,0,,{safe}"
                )
        offset_ms += dur_ms + gap_seconds * 1000.0
    return _ASS_HEADER + "\n".join(events) + "\n"


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> None:
    """Burn an SRT onto a video (libass). Raises RuntimeError on failure.

    Runs ffmpeg with cwd = the SRT's folder and references the bare filename so
    Windows drive-colon paths don't break the subtitles filter parser.
    """
    ffmpeg = _resolve_ffmpeg()
    # The subtitle file is ASS with its own [V4+ Styles] + PlayRes, so no
    # force_style is needed (and Fontsize/margins are in true pixels).
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-vf", f"subtitles={srt_path.name}",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, timeout=600, cwd=str(srt_path.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0 or not output_path.exists():
        tail = (proc.stderr or b"").decode("utf-8", "replace")[-500:]
        raise RuntimeError(f"ffmpeg subtitle burn failed: {tail}")


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
