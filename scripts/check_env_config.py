#!/usr/bin/env python3
"""
check_env_config.py — Validate runtime environment configuration.

Reads .env.example and (optionally) .env to check that required
configuration keys are present and have reasonable values.

No LLM calls, no network access, no DB writes.

Usage:
    python scripts/check_env_config.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"

WARN_COUNT = 0
FAIL_COUNT = 0


def read_env(path: Path) -> dict[str, str]:
    """Parse a .env file into a key->value dict. Supports # comments and inline comments."""
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle inline comment after value
        if " #" in line:
            line = line.split(" #")[0]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def ok(msg: str):
    print(f"[OK] {msg}")


def warn(msg: str):
    global WARN_COUNT
    WARN_COUNT += 1
    print(f"[WARN] {msg}")


def fail(msg: str):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"[FAIL] {msg}")


def main():
    global WARN_COUNT, FAIL_COUNT
    print("Env Config Check")
    print("=" * 40)

    # 1. .env.example exists
    if not ENV_EXAMPLE.exists():
        fail(".env.example does not exist")
    else:
        ok(".env.example exists")

    example = read_env(ENV_EXAMPLE)
    env = read_env(ENV_FILE)

    # 2. .env exists (optional — just warn if missing)
    if not ENV_FILE.exists():
        warn(".env does not exist (optional — needed for real runs)")
    else:
        ok(".env exists")

    # 3. DATABASE_URL
    if "DATABASE_URL" in example:
        ok(f"DATABASE_URL configured: {example['DATABASE_URL']}")
    else:
        fail("DATABASE_URL missing from .env.example")

    # 4. LLM_PROFILE
    if "LLM_PROFILE" in example:
        profile = example["LLM_PROFILE"]
        ok(f"LLM_PROFILE={profile}")
    else:
        fail("LLM_PROFILE missing from .env.example")

    # 5. MiniMax API key check (if using minimax_* profile)
    profile = example.get("LLM_PROFILE", "")
    if profile.startswith("minimax_"):
        key = env.get("MINIMAX_API_KEY", example.get("MINIMAX_API_KEY", ""))
        if key == "replace-me" or not key:
            fail("MINIMAX_API_KEY is replace-me or missing — replace with real key")
        else:
            ok("MINIMAX_API_KEY is set (not replace-me)")

    # 6. ONE_LINER_ENABLED
    if "ONE_LINER_ENABLED" in example:
        ok(f"ONE_LINER_ENABLED={example['ONE_LINER_ENABLED']}")
    else:
        warn("ONE_LINER_ENABLED not in .env.example")

    # 7. ONE_LINER_MAX_PER_RUN
    if "ONE_LINER_MAX_PER_RUN" in example:
        val = example["ONE_LINER_MAX_PER_RUN"]
        try:
            n = int(val)
            if n == 20:
                ok(f"ONE_LINER_MAX_PER_RUN=20 (correct, matches code default)")
            elif n > 0:
                ok(f"ONE_LINER_MAX_PER_RUN={n}")
            else:
                warn(f"ONE_LINER_MAX_PER_RUN={n} is not positive")
        except ValueError:
            warn(f"ONE_LINER_MAX_PER_RUN={val} is not an integer")
    else:
        warn("ONE_LINER_MAX_PER_RUN not in .env.example")

    # 8. DAILY_REPORT_ENABLED
    if "DAILY_REPORT_ENABLED" in example:
        val = example["DAILY_REPORT_ENABLED"]
        ok(f"DAILY_REPORT_ENABLED={val}")
        if val.lower() == "false":
            warn("DAILY_REPORT_ENABLED=false, daily core report LLM generation is disabled")
        elif val.lower() == "true":
            ok("DAILY_REPORT_ENABLED=true — confirm cost before running")
        else:
            warn(f"DAILY_REPORT_ENABLED={val} — expected 'true' or 'false'")
    else:
        warn("DAILY_REPORT_ENABLED not in .env.example (recommended: false)")

    # 9. DAILY_BROADCAST_TTS_ENABLED
    if "DAILY_BROADCAST_TTS_ENABLED" in example:
        val = example["DAILY_BROADCAST_TTS_ENABLED"]
        ok(f"DAILY_BROADCAST_TTS_ENABLED={val}")
        if val.lower() == "false":
            ok("DAILY_BROADCAST_TTS_ENABLED=false (TTS not active)")
    else:
        warn("DAILY_BROADCAST_TTS_ENABLED not in .env.example (recommended: false)")

    # 10. LLM_SUMMARY_ENABLED
    if "LLM_SUMMARY_ENABLED" in example:
        val = example["LLM_SUMMARY_ENABLED"]
        ok(f"LLM_SUMMARY_ENABLED={val}")
        if val.lower() == "false":
            warn("LLM_SUMMARY_ENABLED=false, full-content summary is disabled")
        elif val.lower() == "true":
            ok("LLM_SUMMARY_ENABLED=true — confirm HTML fetch and cost before running")
    else:
        warn("LLM_SUMMARY_ENABLED not in .env.example (recommended: false)")

    # 11. DAILY_REPORT_MAX_ITEMS
    if "DAILY_REPORT_MAX_ITEMS" in example:
        val = example["DAILY_REPORT_MAX_ITEMS"]
        ok(f"DAILY_REPORT_MAX_ITEMS={val}")
    else:
        warn("DAILY_REPORT_MAX_ITEMS not in .env.example")

    print()
    print("=" * 40)
    if FAIL_COUNT > 0:
        print(f"Result: {FAIL_COUNT} FAIL, {WARN_COUNT} WARN")
        return 1
    elif WARN_COUNT > 0:
        print(f"Result: {WARN_COUNT} WARN (no critical failures)")
        return 0
    else:
        print("Result: All checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
