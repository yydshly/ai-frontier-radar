#!/usr/bin/env python3
"""V1.0-alpha.3 acceptance script for health_check.py.

Validates:
    1. health_check.py --quick runs successfully
    2. health_check.py --full --skip-smoke runs successfully
    3. Output contains expected content markers

Usage:
    python scripts/acceptance_health_check.py
    python scripts/acceptance_health_check.py --keep-db
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V1.0-alpha.3 health_check.py acceptance test."
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep isolated DB after acceptance (default: delete after).",
    )
    return parser


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    print("=" * 60)
    print("V1.0-alpha.3 Health Check Acceptance")
    print("=" * 60)

    health_check_script = PROJECT_ROOT / "scripts" / "health_check.py"
    if not health_check_script.exists():
        print("[FAIL] scripts/health_check.py not found")
        return 1

    # Step 1: Run --quick
    print("\n--- Step 1: python scripts/health_check.py --quick ---")
    keep_db_flag = ["--keep-db"] if args.keep_db else []
    proc = subprocess.run(
        [sys.executable, str(health_check_script), "--quick"] + keep_db_flag,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )

    print(f"Exit code: {proc.returncode}")
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)

    # Verify exit code
    if proc.returncode != 0:
        print("\n[FAIL] health_check.py --quick failed (non-zero exit code)")
        return 1

    # Verify output content
    combined_output = proc.stdout + proc.stderr
    required_in_quick = [
        "AI Frontier Radar - Health Check",
        "RESULT:",
    ]
    for marker in required_in_quick:
        if marker not in combined_output:
            print(f"\n[FAIL] Expected '{marker}' in output")
            return 1

    # Check for PASS or PASS_WITH_WARNINGS
    if "RESULT: PASS" not in combined_output and "RESULT: PASS_WITH_WARNINGS" not in combined_output:
        print("\n[FAIL] Expected RESULT: PASS or RESULT: PASS_WITH_WARNINGS in output")
        return 1

    print("[OK] Step 1 passed: health_check.py --quick succeeded")

    # Step 2: Run --full --skip-smoke
    print("\n--- Step 2: python scripts/health_check.py --full --skip-smoke ---")
    proc2 = subprocess.run(
        [sys.executable, str(health_check_script), "--full", "--skip-smoke"] + keep_db_flag,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,  # 5 min for full check
    )

    print(f"Exit code: {proc2.returncode}")
    if proc2.stdout:
        print(proc2.stdout)
    if proc2.stderr:
        print(proc2.stderr)

    # Verify exit code
    if proc2.returncode != 0:
        print("\n[FAIL] health_check.py --full --skip-smoke failed (non-zero exit code)")
        return 1

    # Verify output content
    combined_output2 = proc2.stdout + proc2.stderr
    required_in_full = [
        "Demo Data",
        "Pages",
        "RESULT:",
    ]
    for marker in required_in_full:
        if marker not in combined_output2:
            print(f"\n[FAIL] Expected '{marker}' in --full output")
            return 1

    if "RESULT: PASS" not in combined_output2 and "RESULT: PASS_WITH_WARNINGS" not in combined_output2:
        print("\n[FAIL] Expected RESULT: PASS or RESULT: PASS_WITH_WARNINGS in --full output")
        return 1

    print("[OK] Step 2 passed: health_check.py --full --skip-smoke succeeded")

    print("\n" + "=" * 60)
    print("[PASS] ACCEPTANCE PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
