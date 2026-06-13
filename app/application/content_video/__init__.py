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
"""
from app.application.content_video.models import (
    VideoSourceSnapshot,
    VideoSourceSection,
    VideoScene,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from app.application.content_video.service import generate_video, get_existing_video_status

__all__ = [
    "VideoSourceSnapshot",
    "VideoSourceSection",
    "VideoScene",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "generate_video",
    "get_existing_video_status",
]
