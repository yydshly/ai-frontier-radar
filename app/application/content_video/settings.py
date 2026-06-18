"""content_video — Runtime settings for scene count and narration length.

Controls video duration and scene density via env vars.
Defaults are tuned for a ~60-second mobile briefing video.
"""
from __future__ import annotations

import os

# ── Scene count ────────────────────────────────────────────────────────────────

def get_max_scenes() -> int:
    """Maximum number of scenes to generate (excluding cover).

    V2 (full-report storyboard): default is 24 so the video can hold
    every section + every paginated overview/supporting-notes page.
    Long content is paginated by adding scenes, not by truncating."""
    raw = os.getenv("CONTENT_VIDEO_MAX_SCENES", "").strip()
    if raw:
        try:
            val = int(raw)
            if 1 <= val <= 40:
                return val
        except ValueError:
            pass
    return 24  # enough for opening + 4 overview pages + 7 sections + 3 supporting + closing


def get_max_highlights() -> int:
    """Maximum number of highlight/signal sections to include.

    Back-compat helper used by the older storyboard; the V2 storyboard
    does not enforce this.  We return a generous default so legacy
    callers still work."""
    max_scenes = get_max_scenes()
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
