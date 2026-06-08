#!/usr/bin/env python3
"""V1.0-alpha Release Candidate acceptance script.

Aggregates all no-external-dependency checks for V1.0-alpha RC verification.
This script does NOT call real LLM, does NOT access real network.

Usage:
    python scripts/acceptance_release_candidate.py
    python scripts/acceptance_release_candidate.py --skip-smoke
"""
import argparse
import subprocess
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V1.0-alpha Release Candidate acceptance script."
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke_test (if already run recently).",
    )
    return parser


def run_command(cmd: list, description: str, timeout: int = 180) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    print(f"\n{'='*60}")
    print(f"[RUNNING] {description}")
    print(f"Command: {' '.join(str(c) for c in cmd)}")
    print("=" * 60)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    print("=" * 60)
    print("V1.0-alpha Release Candidate Acceptance")
    print("=" * 60)

    steps = []

    # Step 1: compileall
    steps.append({
        "name": "Compile Python files",
        "cmd": [sys.executable, "-m", "compileall", "app", "scripts"],
        "timeout": 60,
    })

    # Step 2: check_sources_config
    steps.append({
        "name": "Validate sources config",
        "cmd": [sys.executable, "scripts/check_sources_config.py"],
        "timeout": 30,
    })

    # Step 3: smoke_test (unless --skip-smoke)
    if not args.skip_smoke:
        steps.append({
            "name": "Run smoke test",
            "cmd": [sys.executable, "scripts/smoke_test.py"],
            "timeout": 300,
        })

    # Step 4: health_check (quick mode)
    steps.append({
        "name": "Run health check (quick)",
        "cmd": [sys.executable, "scripts/health_check.py"],
        "timeout": 120,
    })

    # Step 5: acceptance_ui_links
    steps.append({
        "name": "Run UI links acceptance",
        "cmd": [sys.executable, "scripts/acceptance_ui_links.py", "--isolated-db"],
        "timeout": 120,
    })

    # Step 6: acceptance_ci_local (always uses --skip-smoke internally)
    steps.append({
        "name": "Run local CI acceptance",
        "cmd": [sys.executable, "scripts/acceptance_ci_local.py", "--skip-smoke"],
        "timeout": 300,
    })

    # Run all steps
    failed = False
    for i, step in enumerate(steps, 1):
        returncode, stdout, stderr = run_command(
            step["cmd"],
            step["name"],
            timeout=step.get("timeout", 120),
        )

        combined = stdout + stderr

        if returncode == 0:
            print(f"\n[OK] Step {i}/{len(steps)} passed: {step['name']}")
        else:
            print(f"\n[FAIL] Step {i}/{len(steps)} failed: {step['name']}")
            print(f"Exit code: {returncode}")
            print("\n--- Last 40 lines of output ---")
            lines = combined.splitlines()
            for line in lines[-40:]:
                print(f"  {line}")
            failed = True
            break

    # Summary
    print("\n" + "=" * 60)
    if failed:
        print("[FAIL] RELEASE CANDIDATE CHECK FAILED")
        print("=" * 60)
        return 1
    else:
        print("[PASS] RELEASE CANDIDATE CHECK PASSED")
        print("=" * 60)
        print("\nAll V1.0-alpha RC checks passed.")
        print("Ready for docs/RELEASE_CHECKLIST.md final review.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
