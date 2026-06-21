"""content_video — Scene audio renderer with TTS provider abstraction.

Audio is generated per-scene (one MP3 per VideoScene narration_text).
V1 uses a simple TTS provider interface — the actual TTS implementation
(e.g. MiMo) is injected by the caller (radar adapter).

Dev fallback: if DEV_FAKE_TTS=true, a silent audio file is produced so the
video pipeline can still be tested end-to-end without a real TTS key.
"""
from __future__ import annotations

import os
import struct
import subprocess
import tempfile
from pathlib import Path


def get_content_video_tts_mode() -> str:
    """Return the configured TTS mode: ``real`` or ``fake``."""
    configured = os.getenv("CONTENT_VIDEO_TTS_MODE", "").strip().lower()
    if configured in {"real", "fake"}:
        return configured
    if os.getenv("DEV_FAKE_TTS", "").strip().lower() == "true":
        return "fake"
    return "real"


def _make_silent_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate a valid silent WAV file in memory.

    Args:
        duration_seconds: length of silence (default 1.0s)
        sample_rate: samples per second (default 16000 Hz)

    Returns:
        bytes representing a valid WAV file with PCM mono 16-bit silence.
    """
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    num_samples = int(sample_rate * duration_seconds)
    data_size = num_samples * block_align

    # RIFF header
    riff = b"RIFF"
    file_size = 36 + data_size  # total file size - 8
    wave = b"WAVE"

    # fmt chunk
    fmt_chunk_id = b"fmt "
    fmt_chunk_size = 16  # PCM
    audio_format = 1  # PCM
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        fmt_chunk_id,
        fmt_chunk_size,
        audio_format,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )

    # data chunk
    data_chunk_id = b"data"
    data_chunk = struct.pack("<4sI", data_chunk_id, data_size) + b"\x00" * data_size

    return riff + struct.pack("<I", file_size) + wave + fmt_chunk + data_chunk


class TTSProviderError(RuntimeError):
    """Raised when TTS synthesis fails."""


class TTSProvider:
    """Abstract TTS provider — implemented by MiMo or fake/dev providers."""

    def synthesize(self, text: str) -> bytes:
        """Return audio bytes (WAV)."""
        raise NotImplementedError


class FakeTTSProvider(TTSProvider):
    """Development-only silent audio provider.

    Enabled via DEV_FAKE_TTS=true. NEVER use in production.
    """

    def synthesize(self, text: str) -> bytes:
        return _make_silent_wav(
            duration_seconds=estimate_fake_tts_duration(text),
            sample_rate=16000,
        )


def estimate_fake_tts_duration(
    text: str,
    *,
    chars_per_second: float = 4.5,
    minimum_seconds: float = 2.0,
    maximum_seconds: float = 10.0,
) -> float:
    """Estimate readable silent-audio duration for local visual acceptance."""
    meaningful_chars = sum(1 for char in (text or "") if not char.isspace())
    estimated = meaningful_chars / max(1.0, chars_per_second)
    return round(min(maximum_seconds, max(minimum_seconds, estimated)), 2)


def _find_ffmpeg() -> str | None:
    """Find ffmpeg binary."""
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    root = Path(__file__).resolve().parents[3]
    for fn in ("ffmpeg.exe", "ffmpeg"):
        candidate = root / "bin" / fn
        if candidate.is_file():
            return str(candidate)
    return None


def _wav_to_mp3(wav_bytes: bytes, output_path: Path) -> None:
    """Convert WAV bytes to MP3 using ffmpeg.

    Raises TTSProviderError if ffmpeg is unavailable or conversion fails.
    """
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise TTSProviderError(
            "ffmpeg not available — cannot convert audio. "
            "Please install ffmpeg to enable video generation."
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        tmp_wav.write(wav_bytes)
        tmp_wav.flush()
        tmp_wav_path = Path(tmp_wav.name)

    try:
        cmd = [
            ffmpeg, "-y",
            "-i", str(tmp_wav_path),
            "-codec:a", "libmp3lame", "-q:a", "5",
            str(output_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", "replace")[-300:]
            raise TTSProviderError(
                f"ffmpeg WAV-to-MP3 conversion failed (return code {proc.returncode}): {stderr}"
            )
    finally:
        tmp_wav_path.unlink(missing_ok=True)


def _audio_duration_from_path(path: Path) -> float:
    """Get audio duration using ffprobe or fallback to file-based estimate."""
    import shutil as _sh
    ffprobe = _sh.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return max(1.0, float(out.stdout.decode().strip()))
        except Exception:
            pass
    try:
        return max(1.0, path.stat().st_size / 32000)
    except Exception:
        return 5.0


def make_dev_tts_provider() -> TTSProvider:
    """Create a dev TTS provider based on environment.

    Returns FakeTTSProvider if DEV_FAKE_TTS=true, otherwise raises
    TTSProviderError indicating no TTS is configured.
    """
    if get_content_video_tts_mode() == "fake":
        return FakeTTSProvider()
    raise TTSProviderError(
        "TTS provider is not configured. "
        "Set DEV_FAKE_TTS=true for development or configure MIMO_API_KEY for production."
    )


def render_scene_audio(
    scene,
    output_path: Path,
    provider: TTSProvider | None = None,
) -> float:
    """Render a scene's narration to an MP3 file.

    Args:
        scene: VideoScene with narration_text
        output_path: destination .mp3 path
        provider: TTSProvider instance. If None, uses make_dev_tts_provider().

    Returns the audio duration in seconds.
    Raises TTSProviderError on failure.
    """
    if not scene.narration_text.strip():
        raise TTSProviderError(f"Scene {scene.scene_id} has empty narration text.")

    prov = provider or make_dev_tts_provider()

    try:
        wav_bytes = prov.synthesize(scene.narration_text)
    except Exception as exc:
        raise TTSProviderError(
            f"TTS failed for scene {scene.scene_id}: {exc}"
        ) from exc

    # Capture per-scene subtitle segments if the provider supplies them
    # (e.g. MiniMaxT2AProvider). Best-effort: absence just means no subtitles.
    segments = getattr(prov, "last_subtitles", None)
    if isinstance(segments, list):
        scene.subtitle_segments = list(segments)

    _wav_to_mp3(wav_bytes, output_path)
    duration = _audio_duration_from_path(output_path)
    return duration
