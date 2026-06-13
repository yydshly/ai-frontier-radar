"""content_video — Core data models.

These models are source-key agnostic and carry no radar-specific fields.
They are designed to be reusable across any structured content that can be
converted into a voice-narrated mobile video.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VideoSourceSection:
    """One section / highlight within a VideoSourceSnapshot."""
    title: str
    summary: str
    key_points: list[str] = field(default_factory=list)
    why_it_matters: str | None = None
    source_name: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class VideoSourceSnapshot:
    """A content snapshot that can be turned into a video.

    This is a pure data carrier — it carries no radar-specific fields.
    The ``metadata`` dict allows business adapters to stash extra info
    without polluting the core schema.
    """
    source_key: str
    title: str
    subtitle: str | None
    date_label: str | None
    summary: str
    sections: list[VideoSourceSection]
    takeaways: list[str] = field(default_factory=list)
    source_url: str | None = None
    version_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_key": self.source_key,
            "title": self.title,
            "subtitle": self.subtitle,
            "date_label": self.date_label,
            "summary": self.summary,
            "sections": [
                {
                    "title": s.title,
                    "summary": s.summary,
                    "key_points": s.key_points,
                    "why_it_matters": s.why_it_matters,
                    "source_name": s.source_name,
                    "source_url": s.source_url,
                }
                for s in self.sections
            ],
            "takeaways": self.takeaways,
            "source_url": self.source_url,
            "version_id": self.version_id,
            "metadata": self.metadata,
        }


@dataclass
class VideoScene:
    """One scene within the video storyboard.

    Each scene has its own image, narration audio, and duration.
    scene_id is unique within a single generation job.
    scene_type drives which visual template is used.
    """
    scene_id: str
    scene_type: str          # e.g. "cover" | "summary" | "highlight" | "takeaways" | "ending"
    visual_title: str
    visual_lines: list[str]
    narration_text: str
    source_label: str | None = None
    image_path: str | None = None
    audio_path: str | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True)
class VideoGenerationRequest:
    """Request to generate a video from a source snapshot."""
    source_snapshot: VideoSourceSnapshot
    template_id: str = "mobile_briefing_v1"
    voice_id: str | None = None
    bgm_id: str | None = None
    output_size: str = "1080x1920"
    force: bool = False


@dataclass(frozen=True)
class VideoGenerationResult:
    """Result of a video generation request."""
    job_id: str
    input_hash: str
    status: str            # "pending" | "running" | "success" | "failed" | "existing"
    video_path: str | None = None
    poster_path: str | None = None
    error: str | None = None
    current_step: str | None = None
