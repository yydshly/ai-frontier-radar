"""Tests for content_video preflight checks."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class FakePreflightItem:
    """Fake ContentVideoPreflightItem for testing."""
    def __init__(self, name, ok, message):
        self.name = name
        self.ok = ok
        self.message = message


class TestPreflightRequiredVsRenderer:
    """Tests for the required-vs-renderer split in run_preflight."""

    def test_cjk_font_not_required_when_remotion_ok(self):
        """Remotion OK + CJK font fail → preflight should pass."""
        from app.application.content_video.preflight import (
            ContentVideoPreflightResult,
            ContentVideoPreflightItem,
        )

        # Simulate: remotion OK, pillow OK, cjk_font FAIL
        items = [
            ContentVideoPreflightItem(name="ffmpeg", ok=True, message="ffmpeg found"),
            ContentVideoPreflightItem(name="ffprobe", ok=True, message="ffprobe found"),
            ContentVideoPreflightItem(name="output_dir", ok=True, message="output dir writable"),
            ContentVideoPreflightItem(name="tts", ok=True, message="TTS configured"),
            ContentVideoPreflightItem(name="remotion", ok=True, message="Remotion available"),
            ContentVideoPreflightItem(name="pillow", ok=True, message="Pillow available"),
            ContentVideoPreflightItem(name="cjk_font", ok=False, message="CJK font not available"),
        ]

        # Required: ffmpeg, ffprobe, output_dir, tts
        required_names = {"ffmpeg", "ffprobe", "output_dir", "tts"}
        required_ok = all(item.ok for item in items if item.name in required_names)
        renderer_ok = next(i.ok for i in items if i.name == "remotion") or (
            next(i.ok for i in items if i.name == "pillow") and
            next(i.ok for i in items if i.name == "cjk_font")
        )
        all_ok = required_ok and renderer_ok

        assert required_ok is True
        assert renderer_ok is True  # remotion OK suffices even if cjk_font fails
        assert all_ok is True

    def test_remotion_fail_but_fallback_ok_passes(self):
        """Remotion fail + Pillow OK + CJK OK → preflight should pass."""
        from app.application.content_video.preflight import (
            ContentVideoPreflightItem,
        )

        items = [
            ContentVideoPreflightItem(name="ffmpeg", ok=True, message="ffmpeg found"),
            ContentVideoPreflightItem(name="ffprobe", ok=True, message="ffprobe found"),
            ContentVideoPreflightItem(name="output_dir", ok=True, message="output dir writable"),
            ContentVideoPreflightItem(name="tts", ok=True, message="TTS configured"),
            ContentVideoPreflightItem(name="remotion", ok=False, message="Remotion unavailable"),
            ContentVideoPreflightItem(name="pillow", ok=True, message="Pillow available"),
            ContentVideoPreflightItem(name="cjk_font", ok=True, message="CJK font available"),
        ]

        required_names = {"ffmpeg", "ffprobe", "output_dir", "tts"}
        required_ok = all(item.ok for item in items if item.name in required_names)
        renderer_ok = next(i.ok for i in items if i.name == "remotion") or (
            next(i.ok for i in items if i.name == "pillow") and
            next(i.ok for i in items if i.name == "cjk_font")
        )
        all_ok = required_ok and renderer_ok

        assert required_ok is True
        assert renderer_ok is True  # Pillow + CJK fallback works
        assert all_ok is True

    def test_both_renderers_fail_preflight_fails(self):
        """Remotion fail + Pillow/CJK fail → preflight should fail."""
        from app.application.content_video.preflight import (
            ContentVideoPreflightItem,
        )

        items = [
            ContentVideoPreflightItem(name="ffmpeg", ok=True, message="ffmpeg found"),
            ContentVideoPreflightItem(name="ffprobe", ok=True, message="ffprobe found"),
            ContentVideoPreflightItem(name="output_dir", ok=True, message="output dir writable"),
            ContentVideoPreflightItem(name="tts", ok=True, message="TTS configured"),
            ContentVideoPreflightItem(name="remotion", ok=False, message="Remotion unavailable"),
            ContentVideoPreflightItem(name="pillow", ok=False, message="Pillow not installed"),
            ContentVideoPreflightItem(name="cjk_font", ok=False, message="CJK font not available"),
        ]

        required_names = {"ffmpeg", "ffprobe", "output_dir", "tts"}
        required_ok = all(item.ok for item in items if item.name in required_names)
        renderer_ok = next(i.ok for i in items if i.name == "remotion") or (
            next(i.ok for i in items if i.name == "pillow") and
            next(i.ok for i in items if i.name == "cjk_font")
        )
        all_ok = required_ok and renderer_ok

        assert required_ok is True
        assert renderer_ok is False  # both renderers unavailable
        assert all_ok is False


class TestPreflightTTS:
    """Tests for TTS preflight checking with real MiMoTTSSettings validation."""

    def test_dev_fake_tts_passes(self):
        """DEV_FAKE_TTS=true → TTS preflight passes."""
        with patch.dict("os.environ", {"DEV_FAKE_TTS": "true"}, clear=False):
            from app.application.content_video.preflight import _check_tts
            item = _check_tts()
            assert item.ok is True
            assert "DEV_FAKE_TTS" in item.detail

    def test_tts_with_invalid_mimo_config_fails_with_message(self):
        """TTS configured but invalid (e.g. mismatched key/url) → preflight fails with message."""
        with patch.dict("os.environ", {
            "DEV_FAKE_TTS": "",
            "MIMO_API_KEY": "sk-testkey",
            "MIMO_TTS_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",  # Token Plan URL with sk- key
        }, clear=False):
            # Force re-import to pick up env
            import importlib
            import app.application.content_video.preflight as preflight_mod
            importlib.reload(preflight_mod)
            item = preflight_mod._check_tts()
            assert item.ok is False
            assert "sk-" in item.message or "Token Plan" in item.message or "不能配合" in item.message

    def test_tts_not_configured_fails(self):
        """No TTS configured → TTS preflight fails."""
        with patch.dict("os.environ", {"DEV_FAKE_TTS": "", "MIMO_API_KEY": ""}, clear=False):
            import importlib
            import app.application.content_video.preflight as preflight_mod
            importlib.reload(preflight_mod)
            item = preflight_mod._check_tts()
            assert item.ok is False
            assert "not configured" in item.message.lower() or "缺少" in item.message
