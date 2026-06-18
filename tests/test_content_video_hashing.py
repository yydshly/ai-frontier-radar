from unittest.mock import patch

from app.application.content_video.hashing import compute_input_hash
from app.application.content_video.models import (
    VideoGenerationRequest,
    VideoSourceSnapshot,
)


def _request() -> VideoGenerationRequest:
    return VideoGenerationRequest(
        source_snapshot=VideoSourceSnapshot(
            source_key="radar_2026-06-17",
            title="日报",
            subtitle=None,
            date_label="2026-06-17",
            summary="完整概述。",
            sections=[],
        ),
        template_id="remotion_report_v1",
    )


def test_hash_changes_with_storyboard_version():
    request = _request()
    original = compute_input_hash(request)
    with patch(
        "app.application.content_video.hashing.STORYBOARD_VERSION",
        "full_report_storyboard_future",
    ):
        changed = compute_input_hash(request)
    assert changed != original


def test_hash_changes_with_video_engine_version():
    request = _request()
    original = compute_input_hash(request)
    with patch(
        "app.application.content_video.hashing.VIDEO_ENGINE_VERSION",
        "content_video_future",
    ):
        changed = compute_input_hash(request)
    assert changed != original


def test_hash_changes_between_fake_and_real_tts(monkeypatch):
    request = _request()
    monkeypatch.setenv("CONTENT_VIDEO_TTS_MODE", "fake")
    fake_hash = compute_input_hash(request)
    monkeypatch.setenv("CONTENT_VIDEO_TTS_MODE", "real")
    monkeypatch.setenv("MIMO_TTS_MODEL", "mimo-v2.5-tts")
    monkeypatch.setenv("MIMO_TTS_VOICE", "冰糖")
    real_hash = compute_input_hash(request)
    assert real_hash != fake_hash
