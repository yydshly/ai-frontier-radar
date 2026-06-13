"""content_video — Input-hash computation.

The input hash deterministically captures:
  - the stable serialization of VideoSourceSnapshot
  - template_id / voice_id / bgm_id / output_size
  - video_engine_version

Hash is SHA256 → first 16 hex chars (64 bits), directory-name safe.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.application.content_video.models import VideoSourceSnapshot, VideoGenerationRequest

# Bump this whenever the rendering / scene / audio algorithm changes meaningfully.
# Old hashes will still resolve to their existing output; new inputs get a new hash.
VIDEO_ENGINE_VERSION = "content_video_v1"


def _stable_dict(obj: Any) -> Any:
    """Recursively convert an object to a sorted, JSON-serializable form."""
    if isinstance(obj, dict):
        return sorted((k, _stable_dict(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_stable_dict(item) for item in obj]
    if isinstance(obj, str):
        return obj
    if obj is None:
        return None
    return str(obj)


def compute_input_hash(request: VideoGenerationRequest) -> str:
    """Compute a deterministic input hash for a video generation request.

    The hash covers:
    - The stable serialization of the source snapshot
    - template_id, voice_id, bgm_id, output_size
    - VIDEO_ENGINE_VERSION
    """
    snapshot = request.source_snapshot

    payload: dict[str, Any] = {
        "snapshot": snapshot.to_dict(),
        "template_id": request.template_id,
        "voice_id": request.voice_id,
        "bgm_id": request.bgm_id,
        "output_size": request.output_size,
        "video_engine_version": VIDEO_ENGINE_VERSION,
    }

    normalized = _stable_dict(payload)
    serialized = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return digest[:16]
