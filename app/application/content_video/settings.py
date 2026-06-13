"""content_video — Runtime settings for scene count and narration length.

Controls video duration and scene density via env vars.
Defaults are tuned for a ~60-second mobile briefing video.
"""
from __future__ import annotations

import os

# ── Scene count ────────────────────────────────────────────────────────────────

def get_max_scenes() -> int:
    """Maximum number of scenes to generate (excluding cover)."""
    raw = os.getenv("CONTENT_VIDEO_MAX_SCENES", "").strip()
    if raw:
        try:
            val = int(raw)
            if 1 <= val <= 20:
                return val
        except ValueError:
            pass
    return 8  # cover + summary + 3 signals + takeaways + ending ≈ 7 scenes


def get_max_highlights() -> int:
    """Maximum number of highlight/signal sections to include."""
    max_scenes = get_max_scenes()
    # Reserve: 1 cover + 1 summary + 1 takeaways + 1 ending = 4
    # Remaining slots are for signals
    return max(1, max_scenes - 4)


# ── Narration length ────────────────────────────────────────────────────────

def get_max_narration_chars() -> int:
    """Maximum characters in a single scene's narration_text (for TTS pacing)."""
    raw = os.getenv("CONTENT_VIDEO_MAX_NARRATION_CHARS", "").strip()
    if raw:
        try:
            val = int(raw)
            if 30 <= val <= 300:
                return val
        except ValueError:
            pass
    return 90  # ~10-12s of TTS per scene


def get_target_duration_seconds() -> int:
    """Target total video duration in seconds (informational; not enforced)."""
    raw = os.getenv("CONTENT_VIDEO_MAX_DURATION_SECONDS", "").strip()
    if raw:
        try:
            val = int(raw)
            if 20 <= val <= 300:
                return val
        except ValueError:
            pass
    return 75  # ~60-75s target
