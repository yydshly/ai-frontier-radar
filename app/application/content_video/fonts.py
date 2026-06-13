"""content_video — CJK-capable font loading for scene image rendering.

Provides:
  load_cjk_font(size, bold=False) → ImageFont
  ContentVideoFontError — raised when no CJK font can be found

Priority order:
  1. CONTENT_VIDEO_BOLD_FONT_PATH / CONTENT_VIDEO_FONT_PATH env var (if bold=False/True)
  2. Platform-specific CJK system fonts
  3. Raise ContentVideoFontError (no silent fallback to load_default)

Environment variables:
  CONTENT_VIDEO_FONT_PATH       — path to regular CJK font file
  CONTENT_VIDEO_BOLD_FONT_PATH  — path to bold CJK font file
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


class ContentVideoFontError(RuntimeError):
    """Raised when no suitable CJK font can be found for video rendering."""
    pass


# ── Platform-specific CJK font candidates ────────────────────────────────────────

def _windows_cjk_fonts(*, bold: bool = False) -> list[Path]:
    """Return candidate CJK font paths on Windows."""
    fonts_base = Path("C:/Windows/Fonts")
    if bold:
        return [
            fonts_base / "msyhbd.ttc",   # Microsoft YaHei Bold
            fonts_base / "simhei.ttf",     # SimHei
            fonts_base / "Dengb.ttf",      # DengXian Bold
            fonts_base / "STHeiti Medium.ttc",
            fonts_base / "simsun.ttc",     # Note: SimSun is not bold-capable but included as last resort
        ]
    return [
        fonts_base / "msyh.ttc",          # Microsoft YaHei Regular
        fonts_base / "simhei.ttf",         # SimHei (bold-capable)
        fonts_base / "Deng.ttf",           # DengXian Regular
        fonts_base / "STHeiti Light.ttc",
        fonts_base / "simsun.ttc",         # SimSun (not bold-capable but has CJK coverage)
    ]


def _linux_cjk_fonts(*, bold: bool = False) -> list[Path]:
    """Return candidate CJK font paths on Linux."""
    candidates = []
    if bold:
        candidates += [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        ]
    candidates += [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
        Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    return candidates


def _macos_cjk_fonts(*, bold: bool = False) -> list[Path]:
    """Return candidate CJK font paths on macOS."""
    candidates = []
    if bold:
        candidates += [
            Path("/System/Library/Fonts/STHeiti Medium.ttc"),
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/Library/Fonts/Hei.ttc"),
        ]
    candidates += [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Hei.ttc"),
        Path("/Library/Fonts/Hei.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    ]
    return candidates


def _platform_cjk_fonts(*, bold: bool = False) -> list[Path]:
    """Return platform-appropriate CJK font candidates."""
    if sys.platform == "win32" or sys.platform == "cygwin":
        return _windows_cjk_fonts(bold=bold)
    elif sys.platform == "darwin":
        return _macos_cjk_fonts(bold=bold)
    else:
        return _linux_cjk_fonts(bold=bold)


@lru_cache(maxsize=64)
def load_cjk_font(size: int, *, bold: bool = False) -> ImageFont:
    """Load a CJK-capable font at the given size.

    Raises ContentVideoFontError if no suitable font can be found.
    Never falls back silently to ImageFont.load_default() (which renders boxes).
    """
    # 1. Environment variable override
    env_key = "CONTENT_VIDEO_BOLD_FONT_PATH" if bold else "CONTENT_VIDEO_FONT_PATH"
    env_path = os.getenv(env_key, "").strip()
    if env_path:
        env_font = Path(env_path)
        if env_font.exists():
            try:
                return ImageFont.truetype(str(env_font), size)
            except Exception:
                pass  # Fall through to system fonts if env var is invalid

    # 2. Platform-specific CJK system fonts
    for font_path in _platform_cjk_fonts(bold=bold):
        if not font_path.exists():
            continue
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            continue

    # 3. No font found — fail clearly
    raise ContentVideoFontError(
        f"No CJK font found for size={size}, bold={bold}. "
        "Please install a Chinese font (e.g. Microsoft YaHei on Windows, "
        "Noto Sans CJK on Linux) or set CONTENT_VIDEO_FONT_PATH / "
        "CONTENT_VIDEO_BOLD_FONT_PATH environment variables. "
        f"Platform: {sys.platform}"
    )
