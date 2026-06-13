"""content_video — Reusable structured-content → video generation module.

Architecture
─────────────
This module is intentionally isolated from radar/business logic.

  radar adapter → content_video (this module)
  content_video → radar  ← FORBIDDEN

The module takes a VideoSourceSnapshot and produces a 9:16 MP4 with
scene images + corresponding audio narration.

Future re-use cases:
  - AI Frontier Radar today / history report videos
  - Material → knowledge-product讲解视频
  - Poetry explanation videos
  - Emotional copy explanation videos
  - Course knowledge-card videos
  - Product report videos

Lazy-loading note
─────────────────
Only lightweight, dependency-free modules are imported here:
  - models
  - hashing
  - storage

Heavy modules (service, image_renderer, audio_renderer, composer) are NOT
imported at package level to avoid pulling in Pillow and other heavy
dependencies when only status queries are needed.
"""

from app.application.content_video.models import (
    VideoSourceSnapshot,
    VideoSourceSection,
    VideoScene,
    VideoGenerationRequest,
    VideoGenerationResult,
)

__all__ = [
    "VideoSourceSnapshot",
    "VideoSourceSection",
    "VideoScene",
    "VideoGenerationRequest",
    "VideoGenerationResult",
]
