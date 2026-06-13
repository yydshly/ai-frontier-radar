"""content_video — Storage management for generated video artifacts.

Storage layout
──────────────
runtime/generated_videos/<source_key>/<input_hash>/
  input_snapshot.json    ← frozen VideoSourceSnapshot
  input_hash.txt         ← the input_hash itself
  storyboard.json        ← list of VideoScene dicts
  status.json            ← job status (pending/running/success/failed)
  output.mp4             ← final video (success only)
  poster.png             ← video poster frame
  scenes/
    scene_01.png
    scene_02.png
    ...
  audio/
    scene_01.mp3
    scene_02.mp3
    ...
  clips/
    scene_01.mp4
    scene_02.mp4
    ...
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from app.application.content_video.models import VideoSourceSnapshot, VideoSourceSection, VideoScene, VideoGenerationResult

# Root directory for all generated videos
_GENERATED_VIDEOS_ROOT = "runtime/generated_videos"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_video_base_dir(source_key: str, input_hash: str) -> Path:
    base = _project_root() / _GENERATED_VIDEOS_ROOT / source_key / input_hash
    return base


def ensure_video_dirs(base_dir: Path) -> None:
    """Create all required sub-directories under base_dir."""
    (base_dir / "scenes").mkdir(parents=True, exist_ok=True)
    (base_dir / "audio").mkdir(parents=True, exist_ok=True)
    (base_dir / "clips").mkdir(parents=True, exist_ok=True)


def video_storage_for(source_key: str, input_hash: str) -> "VideoStorage":
    return VideoStorage(get_video_base_dir(source_key, input_hash))


@dataclass
class VideoStorage:
    """Manages read/write access to a single video generation job's artifacts."""
    base_dir: Path

    @property
    def input_snapshot_path(self) -> Path:
        return self.base_dir / "input_snapshot.json"

    @property
    def input_hash_path(self) -> Path:
        return self.base_dir / "input_hash.txt"

    @property
    def storyboard_path(self) -> Path:
        return self.base_dir / "storyboard.json"

    @property
    def status_path(self) -> Path:
        return self.base_dir / "status.json"

    @property
    def output_mp4_path(self) -> Path:
        return self.base_dir / "output.mp4"

    @property
    def poster_path(self) -> Path:
        return self.base_dir / "poster.png"

    @property
    def scenes_dir(self) -> Path:
        return self.base_dir / "scenes"

    @property
    def audio_dir(self) -> Path:
        return self.base_dir / "audio"

    @property
    def clips_dir(self) -> Path:
        return self.base_dir / "clips"

    @property
    def metadata_path(self) -> Path:
        return self.base_dir / "metadata.json"

    def scene_image_path(self, scene_id: str) -> Path:
        return self.scenes_dir / f"{scene_id}.png"

    def scene_audio_path(self, scene_id: str) -> Path:
        return self.audio_dir / f"{scene_id}.mp3"

    def scene_clip_path(self, scene_id: str) -> Path:
        return self.clips_dir / f"{scene_id}.mp4"

    def save_input_snapshot(self, snapshot: VideoSourceSnapshot) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        ensure_video_dirs(self.base_dir)
        self.input_snapshot_path.write_text(
            json.dumps(snapshot.to_dict(), sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_input_hash(self, input_hash: str) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.input_hash_path.write_text(input_hash, encoding="utf-8")

    def save_storyboard(self, scenes: list[VideoScene]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        data = [asdict(s) for s in scenes]
        self.storyboard_path.write_text(
            json.dumps(data, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_storyboard(self) -> list[VideoScene]:
        if not self.storyboard_path.exists():
            return []
        with open(self.storyboard_path, encoding="utf-8") as f:
            raw = json.load(f)
        return [VideoScene(**item) for item in raw]

    def load_input_snapshot(self) -> VideoSourceSnapshot | None:
        if not self.input_snapshot_path.exists():
            return None
        with open(self.input_snapshot_path, encoding="utf-8") as f:
            data = json.load(f)
        sections = [
            VideoSourceSection(
                title=s.get("title", ""),
                summary=s.get("summary", ""),
                key_points=s.get("key_points", []),
                why_it_matters=s.get("why_it_matters"),
                source_name=s.get("source_name"),
                source_url=s.get("source_url"),
            )
            for s in data.get("sections", [])
        ]
        return VideoSourceSnapshot(
            source_key=data["source_key"],
            title=data["title"],
            subtitle=data.get("subtitle"),
            date_label=data.get("date_label"),
            summary=data["summary"],
            sections=sections,
            takeaways=data.get("takeaways", []),
            source_url=data.get("source_url"),
            version_id=data.get("version_id"),
            metadata=data.get("metadata", {}),
        )

    def read_status(self) -> dict | None:
        if not self.status_path.exists():
            return None
        with open(self.status_path, encoding="utf-8") as f:
            return json.load(f)

    def write_status(
        self,
        job_id: str,
        input_hash: str,
        status: str,
        current_step: str | None = None,
        video_path: str | None = None,
        poster_path: str | None = None,
        error: str | None = None,
    ) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        existing = self.read_status()
        payload = {
            "job_id": job_id,
            "input_hash": input_hash,
            "status": status,
            "current_step": current_step,
            "video_path": video_path,
            "poster_path": poster_path,
            "error": error,
            "created_at": existing.get("created_at") if existing else now,
            "updated_at": now,
        }
        self.status_path.write_text(
            json.dumps(payload, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_metadata(self, metadata: dict) -> None:
        """Write metadata.json for the generated video."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read_metadata(self) -> dict | None:
        """Read metadata.json if it exists."""
        if not self.metadata_path.exists():
            return None
        with open(self.metadata_path, encoding="utf-8") as f:
            return json.load(f)

    def update_status_extra(
        self,
        scene_count: int | None = None,
        duration_seconds: float | None = None,
        file_size_bytes: int | None = None,
        tts_mode: str | None = None,
        intermediate_kept: bool | None = None,
    ) -> None:
        """Append extra fields to an existing status.json without overwriting."""
        status = self.read_status()
        if status is None:
            return
        if scene_count is not None:
            status["scene_count"] = scene_count
        if duration_seconds is not None:
            status["duration_seconds"] = round(duration_seconds, 1)
        if file_size_bytes is not None:
            status["file_size_bytes"] = file_size_bytes
        if tts_mode is not None:
            status["tts_mode"] = tts_mode
        if intermediate_kept is not None:
            status["intermediate_kept"] = intermediate_kept
        self.status_path.write_text(
            json.dumps(status, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def check_existing_success(self) -> VideoGenerationResult | None:
        """Return a success result if output.mp4 already exists, else None."""
        status = self.read_status()
        if status is None:
            return None
        if status.get("status") == "success" and self.output_mp4_path.exists():
            return VideoGenerationResult(
                job_id=status.get("job_id", ""),
                input_hash=status.get("input_hash", ""),
                status="existing",
                video_path=str(self.output_mp4_path),
                poster_path=status.get("poster_path"),
                current_step="done",
            )
        return None


def should_keep_intermediate() -> bool:
    """Return True if intermediate artifacts (scenes/audio/clips) should be kept.

    Controlled by CONTENT_VIDEO_KEEP_INTERMEDIATE env var.
    Default: False (clean up intermediates after successful generation).
    """
    val = os.getenv("CONTENT_VIDEO_KEEP_INTERMEDIATE", "").strip().lower()
    return val in ("true", "1", "yes")


def cleanup_intermediate_artifacts(storage: "VideoStorage") -> None:
    """Remove scenes/, audio/, clips/ directories if they exist.

    Called after successful video generation unless CONTENT_VIDEO_KEEP_INTERMEDIATE=true.
    Does NOT raise if directories don't exist.
    """
    for subdir in (storage.scenes_dir, storage.audio_dir, storage.clips_dir):
        if subdir.exists() and subdir.is_dir():
            shutil.rmtree(subdir)
