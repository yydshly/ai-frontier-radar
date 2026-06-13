"""content_video — Runtime preflight checks for video generation dependencies.

Provides a structured way to verify that all required dependencies and
configurations are available before attempting video generation.

Exports:
    ContentVideoPreflightItem
    ContentVideoPreflightResult
    run_preflight()
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── Data models ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContentVideoPreflightItem:
    """Result of a single preflight check."""
    name: str
    ok: bool
    message: str
    detail: str | None = None


@dataclass(frozen=True)
class ContentVideoPreflightResult:
    """Aggregated result of all preflight checks."""
    ok: bool
    items: list[ContentVideoPreflightItem] = field(default_factory=list)

    def by_name(self, name: str) -> ContentVideoPreflightItem | None:
        for item in self.items:
            if item.name == name:
                return item
        return None


# ── Individual check functions ────────────────────────────────────────────────


def _check_ffmpeg() -> ContentVideoPreflightItem:
    """Check if ffmpeg is available."""
    import shutil as _sh
    ff = _sh.which("ffmpeg")
    if ff:
        return ContentVideoPreflightItem(
            name="ffmpeg",
            ok=True,
            message=f"ffmpeg found: {ff}",
            detail=ff,
        )
    # Fallback: check project bin/ dir
    root = Path(__file__).resolve().parents[2]
    for fn in ("ffmpeg.exe", "ffmpeg"):
        candidate = root / "bin" / fn
        if candidate.is_file():
            return ContentVideoPreflightItem(
                name="ffmpeg",
                ok=True,
                message=f"ffmpeg found: {candidate}",
                detail=str(candidate),
            )
    return ContentVideoPreflightItem(
        name="ffmpeg",
        ok=False,
        message="ffmpeg not found in PATH",
        detail=None,
    )


def _check_ffprobe() -> ContentVideoPreflightItem:
    """Check if ffprobe is available."""
    import shutil as _sh
    fp = _sh.which("ffprobe")
    if fp:
        return ContentVideoPreflightItem(
            name="ffprobe",
            ok=True,
            message=f"ffprobe found: {fp}",
            detail=fp,
        )
    root = Path(__file__).resolve().parents[2]
    for fn in ("ffprobe.exe", "ffprobe"):
        candidate = root / "bin" / fn
        if candidate.is_file():
            return ContentVideoPreflightItem(
                name="ffprobe",
                ok=True,
                message=f"ffprobe found: {candidate}",
                detail=str(candidate),
            )
    return ContentVideoPreflightItem(
        name="ffprobe",
        ok=False,
        message="ffprobe not found in PATH",
        detail=None,
    )


def _check_pillow() -> ContentVideoPreflightItem:
    """Check if Pillow is importable."""
    try:
        from PIL import Image
        import PIL
        return ContentVideoPreflightItem(
            name="pillow",
            ok=True,
            message=f"Pillow available: {PIL.__version__}",
            detail=PIL.__version__,
        )
    except ImportError:
        return ContentVideoPreflightItem(
            name="pillow",
            ok=False,
            message="Pillow is not installed",
            detail=None,
        )


def _check_cjk_font() -> ContentVideoPreflightItem:
    """Check if a CJK font is available via fonts.py."""
    try:
        from app.application.content_video.fonts import load_cjk_font
        font = load_cjk_font(16, bold=False)
        font_path = font.path if hasattr(font, "path") else None
        return ContentVideoPreflightItem(
            name="cjk_font",
            ok=True,
            message=f"CJK font loaded: {font_path or 'unknown path'}",
            detail=font_path,
        )
    except Exception as exc:
        return ContentVideoPreflightItem(
            name="cjk_font",
            ok=False,
            message=f"CJK font not available: {exc}",
            detail=None,
        )


def _check_tts() -> ContentVideoPreflightItem:
    """Check TTS configuration (DEV_FAKE_TTS or real provider)."""
    dev_fake = os.getenv("DEV_FAKE_TTS", "").strip().lower() == "true"
    if dev_fake:
        return ContentVideoPreflightItem(
            name="tts",
            ok=True,
            message="Using DEV_FAKE_TTS for local testing",
            detail="DEV_FAKE_TTS=true",
        )
    # Check for real TTS provider
    mimo_key = os.getenv("MIMO_API_KEY", "").strip()
    if mimo_key:
        return ContentVideoPreflightItem(
            name="tts",
            ok=True,
            message="TTS provider configured (MIMO_API_KEY set)",
            detail="MIMO_API_KEY=***",
        )
    return ContentVideoPreflightItem(
        name="tts",
        ok=False,
        message="TTS provider is not configured",
        detail=None,
    )


def _check_output_dir() -> ContentVideoPreflightItem:
    """Check if the output directory is writable."""
    root = Path(__file__).resolve().parents[2]
    out_dir = root / "runtime" / "generated_videos"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        test_file = out_dir / ".write_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        return ContentVideoPreflightItem(
            name="output_dir",
            ok=True,
            message=f"Output directory writable: {out_dir}",
            detail=str(out_dir),
        )
    except Exception as exc:
        return ContentVideoPreflightItem(
            name="output_dir",
            ok=False,
            message=f"Output directory not writable: {exc}",
            detail=None,
        )


# ── Main preflight runner ─────────────────────────────────────────────────────


def run_preflight(*, require_tts: bool = True) -> ContentVideoPreflightResult:
    """Run all preflight checks.

    Args:
        require_tts: If True, TTS must be available (or DEV_FAKE_TTS=true).
                     If False, TTS check is skipped.

    Returns:
        ContentVideoPreflightResult with all item results.
        result.ok is True only when all required checks pass.
    """
    items: list[ContentVideoPreflightItem] = []

    # Always-checked items
    items.append(_check_ffmpeg())
    items.append(_check_ffprobe())
    items.append(_check_pillow())
    items.append(_check_cjk_font())
    items.append(_check_output_dir())

    # Conditional TTS check
    if require_tts:
        items.append(_check_tts())

    all_ok = all(item.ok for item in items)
    return ContentVideoPreflightResult(ok=all_ok, items=items)


def preflight_summary(result: ContentVideoPreflightResult) -> str:
    """Build a human-readable summary string from a preflight result."""
    lines = []
    for item in result.items:
        icon = "✅" if item.ok else "❌"
        lines.append(f"{icon} {item.message}")
    return "\n".join(lines)
