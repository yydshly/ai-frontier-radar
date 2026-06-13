"""content_video — Scene audio renderer with TTS provider abstraction.

Audio is generated per-scene (one MP3 per VideoScene narration_text).
V1 uses a simple TTS provider interface — the actual TTS implementation
(e.g. MiMo) is injected by the caller (radar adapter).

Dev fallback: if DEV_FAKE_TTS=true, a silent audio file is produced so the
video pipeline can still be tested end-to-end without a real TTS key.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

# Minimal WAV header for a silent audio file (1 second, 16-bit mono 16kHz)
_SILENT_WAV = (
    b"RIFF"
    b"\x24\x00\x00\x00"  # file size - 8
    b"WAVE"
    b"fmt "
    b"\x10\x00\x00\x00"  # chunk size
    b"\x01\x00"          # PCM
    b"\x01\x00"          # mono
    b"\x80\x3e\x00\x00"  # 16000 Hz
    b"\x00\x7d\x00\x00"  # byte rate
    b"\x02\x00"          # block align
    b"\x10\x00"          # 16-bit
    b"data"
    b"\x00\x00\x00\x00"  # data size
)


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
        return _SILENT_WAV


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
    """Convert WAV bytes to MP3 using ffmpeg. Falls back to saving WAV as .mp3."""
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        output_path.write_bytes(wav_bytes)
        return

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
            output_path.write_bytes(wav_bytes)
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
    if os.getenv("DEV_FAKE_TTS", "").strip().lower() == "true":
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

    _wav_to_mp3(wav_bytes, output_path)
    duration = _audio_duration_from_path(output_path)
    return duration
