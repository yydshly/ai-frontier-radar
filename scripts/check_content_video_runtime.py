#!/usr/bin/env python
"""Check content_video runtime dependencies and configuration.

Exit codes:
  0 — all checks passed
  1 — one or more checks failed

Usage:
    python scripts/check_content_video_runtime.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from app.application.content_video.preflight import run_preflight, ContentVideoPreflightItem

    print("=== Content Video Runtime Check ===\n")

    result = run_preflight(require_tts=True)

    all_passed = True
    for item in result.items:
        icon = "[OK]" if item.ok else "[FAIL]"
        print(f"{icon} {item.name}: {item.message}")
        if item.detail:
            print(f"      detail: {item.detail}")
        if not item.ok:
            all_passed = False

    print()
    if all_passed:
        print("Content video runtime is ready.")
        print()
        # Offer next steps
        import os
        if os.getenv("DEV_FAKE_TTS", "").strip().lower() == "true":
            print("Note: DEV_FAKE_TTS=true — using local test audio (not real TTS).")
            print("      This is fine for local development/testing.")
        else:
            print("Warning: DEV_FAKE_TTS is not set and no real TTS is configured.")
            print("         Set DEV_FAKE_TTS=true for local testing.")
        print()
        print("Next steps:")
        print("  1. Start the app: .\\scripts\\start_local.ps1")
        print("  2. Open: http://127.0.0.1:8000/radar/share/today")
        print("  3. Click: 分享 → 生成核心报告视频")
        return 0
    else:
        print("Content video runtime has issues — fix them before generating video.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
