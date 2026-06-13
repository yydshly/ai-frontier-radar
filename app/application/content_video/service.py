"""content_video — Unified video generation service.

Orchestrates the full pipeline:
  1. Compute input_hash
  2. Check existing success (reuse)
  3. Save input_snapshot.json
  4. Build storyboard
  5. Render scene images
  6. Generate scene audio
  7. Compose scene clips
  8. Concatenate output.mp4
  9. Generate poster.png
  10. Write status.json

Provides:
  generate_video(request) → VideoGenerationResult
  get_existing_video_status(source_key, input_hash) → VideoGenerationResult | None
  get_video_paths(source_key, input_hash) → dict | None
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.application.content_video.models import (
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoScene,
)
from app.application.content_video.hashing import compute_input_hash
from app.application.content_video.storage import (
    VideoStorage,
    video_storage_for,
    ensure_video_dirs,
)
from app.application.content_video.storyboard import build_storyboard
from app.application.content_video.image_renderer import render_scene_image
from app.application.content_video.audio_renderer import (
    render_scene_audio,
    TTSProviderError,
    TTSProvider,
)
from app.application.content_video import composer

logger = logging.getLogger(__name__)

# Valid status values
_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_SUCCESS = "success"
_STATUS_FAILED = "failed"
_STATUS_EXISTING = "existing"

# Valid current_step values (in order)
STEPS = [
    "queued",
    "checking_existing_video",
    "building_storyboard",
    "rendering_scene_images",
    "generating_scene_audio",
    "composing_scene_videos",
    "concatenating_video",
    "saving_artifacts",
    "done",
    "failed",
]


def _job_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _update_step(step: str) -> str:
    if step not in STEPS:
        return step
    return step


def generate_video(
    request: VideoGenerationRequest,
    *,
    tts_provider: TTSProvider | None = None,
    job_id: str | None = None,
) -> VideoGenerationResult:
    """Generate a video from a VideoSourceSnapshot.

    Args:
        request: video generation request
        tts_provider: TTS provider instance (required; raise if not provided)
        job_id: optional external job_id; if None, one is generated internally

    On success: saves output.mp4, poster.png, and status.json.
    On "existing": returns the existing result without regenerating.
    On failure: writes status.json with error.
    """
    snapshot = request.source_snapshot
    source_key = snapshot.source_key
    job_id = job_id or _job_id()

    # Step: calculating_input_hash
    input_hash = compute_input_hash(request)

    storage = video_storage_for(source_key, input_hash)
    ensure_video_dirs(storage.base_dir)

    # Save hash + snapshot for traceability
    storage.save_input_hash(input_hash)
    storage.save_input_snapshot(snapshot)

    # Step: checking_existing_video
    existing = storage.check_existing_success()
    if existing is not None and not request.force:
        logger.info(
            "Video already exists for source_key=%s input_hash=%s — reusing",
            source_key, input_hash,
        )
        return existing

    # Begin or continue generation
    storage.write_status(
        job_id=job_id,
        input_hash=input_hash,
        status=_STATUS_RUNNING,
        current_step="building_storyboard",
    )

    try:
        # Step: building_storyboard
        scenes = build_storyboard(snapshot)
        storage.save_storyboard(scenes)

        # Step: rendering_scene_images
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_RUNNING,
            current_step="rendering_scene_images",
        )
        for scene in scenes:
            img_path = storage.scene_image_path(scene.scene_id)
            render_scene_image(scene, img_path, size=request.output_size)
            scene.image_path = str(img_path)

        # Step: generating_scene_audio
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_RUNNING,
            current_step="generating_scene_audio",
        )
        # TTS provider must be injected by the caller; raise if not provided
        if tts_provider is None:
            raise TTSProviderError(
                "No TTS provider configured. "
                "Set DEV_FAKE_TTS=true or inject a TTS provider."
            )

        for scene in scenes:
            audio_path = storage.scene_audio_path(scene.scene_id)
            duration = render_scene_audio(scene, audio_path, provider=tts_provider)
            scene.audio_path = str(audio_path)
            scene.duration_seconds = duration

        # Step: composing_scene_videos
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_RUNNING,
            current_step="composing_scene_videos",
        )
        for scene in scenes:
            img = Path(scene.image_path)
            aud = Path(scene.audio_path)
            clip = storage.scene_clip_path(scene.scene_id)
            composer.compose_clip(img, aud, clip)
            scene.image_path = str(img)
            scene.audio_path = str(aud)

        # Step: concatenating_video
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_RUNNING,
            current_step="concatenating_video",
        )
        output_mp4 = composer.compose_video(scenes, storage)

        # Step: saving_artifacts
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_RUNNING,
            current_step="saving_artifacts",
        )

        # Generate a simple poster: copy scene 1 image
        poster_path = storage.poster_path
        scene1_img = Path(scenes[0].image_path) if scenes else None
        if scene1_img and scene1_img.exists():
            import shutil
            shutil.copy(scene1_img, poster_path)

        # Step: done
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_SUCCESS,
            current_step="done",
            video_path=str(output_mp4),
            poster_path=str(poster_path) if poster_path.exists() else None,
        )

        return VideoGenerationResult(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_SUCCESS,
            video_path=str(output_mp4),
            poster_path=str(poster_path) if poster_path.exists() else None,
            current_step="done",
        )

    except TTSProviderError as exc:
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_FAILED,
            current_step="generating_scene_audio",
            error=str(exc),
        )
        logger.error("TTS provider error during video generation: %s", exc)
        return VideoGenerationResult(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_FAILED,
            error=str(exc),
            current_step="generating_scene_audio",
        )

    except Exception as exc:
        tb = traceback.format_exc()
        storage.write_status(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_FAILED,
            current_step="failed",
            error=f"{exc}\n{tb}",
        )
        logger.exception("Video generation failed for source_key=%s", source_key)
        return VideoGenerationResult(
            job_id=job_id,
            input_hash=input_hash,
            status=_STATUS_FAILED,
            error=str(exc),
            current_step="failed",
        )


def get_existing_video_status(source_key: str, input_hash: str) -> VideoGenerationResult | None:
    """Check if a video already exists for the given source_key + input_hash."""
    storage = video_storage_for(source_key, input_hash)
    return storage.check_existing_success()


def get_video_paths(source_key: str, input_hash: str) -> dict | None:
    """Return a dict with video_path, poster_path, status for the given video."""
    storage = video_storage_for(source_key, input_hash)
    status = storage.read_status()
    if status is None:
        return None
    return {
        "status": status.get("status"),
        "current_step": status.get("current_step"),
        "video_path": status.get("video_path"),
        "poster_path": status.get("poster_path"),
        "error": status.get("error"),
        "input_hash": status.get("input_hash"),
        "job_id": status.get("job_id"),
    }
