"""Tests for content_video audio renderer."""
from __future__ import annotations

import struct
import pytest
from app.application.content_video.audio_renderer import (
    _make_silent_wav,
    FakeTTSProvider,
    TTSProviderError,
)


class TestMakeSilentWav:
    """Tests for _make_silent_wav function."""

    def test_returns_valid_wav_bytes(self):
        """Returns bytes that start with RIFF and contain WAVE."""
        wav = _make_silent_wav(duration_seconds=1.0, sample_rate=16000)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"

    def test_data_chunk_size_nonzero(self):
        """data chunk size should be non-zero for 1 second of PCM audio."""
        wav = _make_silent_wav(duration_seconds=1.0, sample_rate=16000)
        # Find 'data' chunk
        data_start = wav.find(b"data")
        assert data_start != -1, "data chunk not found"
        # data size is 4 bytes after 'data' header
        data_size = struct.unpack("<I", wav[data_start + 4:data_start + 8])[0]
        assert data_size > 0, "data chunk size is zero"

    def test_approx_duration(self):
        """1 second at 16kHz should produce ~16000 samples."""
        wav = _make_silent_wav(duration_seconds=1.0, sample_rate=16000)
        data_start = wav.find(b"data")
        data_size = struct.unpack("<I", wav[data_start + 4:data_start + 8])[0]
        # 16-bit mono = 2 bytes per sample
        assert data_size == 16000 * 2  # 32000 bytes = 1 second

    def test_stereo_params_rejected_or_adjusted(self):
        """The function uses mono 16-bit PCM."""
        wav = _make_silent_wav(duration_seconds=0.5, sample_rate=16000)
        # Check fmt chunk
        fmt_start = wav.find(b"fmt ")
        assert fmt_start != -1
        # Audio format (PCM = 1)
        audio_format = struct.unpack("<H", wav[fmt_start + 8:fmt_start + 10])[0]
        assert audio_format == 1
        # Number of channels (mono = 1)
        channels = struct.unpack("<H", wav[fmt_start + 10:fmt_start + 12])[0]
        assert channels == 1
        # Bits per sample (16)
        bits = struct.unpack("<H", wav[fmt_start + 22:fmt_start + 24])[0]
        assert bits == 16


class TestFakeTTSProvider:
    """Tests for FakeTTSProvider."""

    def test_synthesize_returns_valid_wav(self):
        """synthesize() returns a valid WAV with non-zero data."""
        provider = FakeTTSProvider()
        result = provider.synthesize("任何文本")
        assert result[:4] == b"RIFF"
        assert result[8:12] == b"WAVE"
        assert len(result) > 44  # Header + some data

    def test_synthesize_data_size_nonzero(self):
        """synthesize() returns WAV with actual PCM data (not just header)."""
        provider = FakeTTSProvider()
        result = provider.synthesize("测试文本")
        data_start = result.find(b"data")
        assert data_start != -1
        data_size = struct.unpack("<I", result[data_start + 4:data_start + 8])[0]
        assert data_size > 0

    def test_synthesize_empty_text_still_produces_audio(self):
        """Even empty-ish text produces valid WAV (caller should filter empty)."""
        provider = FakeTTSProvider()
        # Empty text after strip would normally be rejected by render_scene_audio
        # but synthesize itself doesn't validate
        result = provider.synthesize("  ")
        assert result[:4] == b"RIFF"


class TestWavToMp3Error:
    """Tests for _wav_to_mp3 error handling."""

    def test_ffmpeg_missing_raises_error(self, tmp_path):
        """If ffmpeg is not available, _wav_to_mp3 raises TTSProviderError."""
        from app.application.content_video.audio_renderer import _wav_to_mp3

        # Patch _find_ffmpeg to return None
        from unittest.mock import patch
        with patch("app.application.content_video.audio_renderer._find_ffmpeg", return_value=None):
            with pytest.raises(TTSProviderError) as exc_info:
                _wav_to_mp3(b"RIFF...WAVE...data...", tmp_path / "out.mp3")
            assert "ffmpeg" in str(exc_info.value).lower()
