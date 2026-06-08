#!/usr/bin/env python3
"""V1.0-alpha.4: Local CI acceptance script.

Runs the same checks as GitHub Actions CI locally, in the same order.
This is a local simulation of the CI pipeline, not a replacement for GitHub Actions.

Usage:
    python scripts/acceptance_ci_local.py
    python scripts/acceptance_ci_local.py --skip-smoke
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
        description="V1.0-alpha.4: Local CI acceptance script."
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke_test (e.g., if already run recently).",
    )
    return parser


def run_command(cmd: list, description: str, timeout: int = 120, env: dict | None = None) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    print(f"\n{'='*60}")
    print(f"[RUNNING] {description}")
    print(f"Command: {' '.join(str(c) for c in cmd)}")
    if env:
        print(f"Using env: DATABASE_URL={env.get('DATABASE_URL', 'not set')}")
    print("=" * 60)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    print("=" * 60)
    print("V1.0-alpha.4: Local CI Acceptance")
    print("=" * 60)
    print("\nThis script simulates GitHub Actions CI locally.")
    print("All commands are identical to what CI runs.")

    # Ensure data directory exists
    os.makedirs(PROJECT_ROOT / "data", exist_ok=True)

    # Set isolated DB env for sub-processes
    env = os.environ.copy()
    if "DATABASE_URL" not in env:
        env["DATABASE_URL"] = "sqlite:///data/ci.db"

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
            "timeout": 180,
        })

    # Step 4: acceptance_demo_data
    steps.append({
        "name": "Run demo data acceptance",
        "cmd": [sys.executable, "scripts/acceptance_demo_data.py", "--isolated-db"],
        "timeout": 120,
    })

    # Step 5: acceptance_demo_flow
    steps.append({
        "name": "Run demo flow acceptance",
        "cmd": [sys.executable, "scripts/acceptance_demo_flow.py", "--isolated-db"],
        "timeout": 120,
    })

    # Step 6: health_check
    steps.append({
        "name": "Run health check",
        "cmd": [sys.executable, "scripts/health_check.py"],
        "timeout": 120,
    })

    # Run all steps
    failed = False
    for i, step in enumerate(steps, 1):
        returncode, stdout, stderr = run_command(
            step["cmd"],
            step["name"],
            timeout=step.get("timeout", 120),
            env=env,
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
        print("[FAIL] ACCEPTANCE FAILED")
        print("=" * 60)
        return 1
    else:
        print("[PASS] ACCEPTANCE PASSED")
        print("=" * 60)
        print("\nAll CI checks passed locally.")
        print("This validates that CI would pass on GitHub Actions.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
