#!/usr/bin/env python3
"""
Local health check script for AI Frontier Radar.

Checks:
- Python version
- Required dependencies
- Key directories
- Sources config
- Isolated DB initialization + tables
- Demo data
- Key pages (via TestClient)
- smoke_test (--full only)
- acceptance scripts (--full only)

Usage:
    python scripts/health_check.py
    python scripts/health_check.py --quick
    python scripts/health_check.py --full
    python scripts/health_check.py --skip-smoke
    python scripts/health_check.py --keep-db

Exit codes:
    0 = PASS or PASS_WITH_WARNINGS
    1 = FAIL
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


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

class CheckResult:
    def __init__(self):
        self.passed = []
        self.warnings = []
        self.failed = []
        self.section = ""

    def section_header(self, name):
        self.section = name
        print(f"\n[SECTION] {name}")

    def ok(self, msg):
        self.passed.append(msg)
        print(f"[PASS] {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"[WARN] {msg}")

    def fail(self, msg, fix=None):
        self.failed.append(msg)
        prefix = "[FAIL]"
        print(f"{prefix} {msg}")
        if fix:
            print(f"       fix: {fix}")

    def overall(self) -> tuple[str, int]:
        if self.failed:
            return "FAIL", 1
        if self.warnings:
            return "PASS_WITH_WARNINGS", 0
        return "PASS", 0


# ---------------------------------------------------------------------------
# Section 1: Python version
# ---------------------------------------------------------------------------

def check_python_version(result: CheckResult):
    result.section_header("Python")
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    if version.major >= 3 and version.minor >= 10:
        result.ok(f"Python version: {version_str}")
    else:
        result.fail(f"Python version must be >= 3.10, got {version_str}")


# ---------------------------------------------------------------------------
# Section 2: Dependencies
# ---------------------------------------------------------------------------

# name -> import name
DEPS = [
    ("fastapi", "fastapi"),
    ("sqlalchemy", "sqlalchemy"),
    ("jinja2", "jinja2"),
    ("httpx", "httpx"),
    ("pydantic", "pydantic"),
    ("yaml", "yaml"),
    ("beautifulsoup4", "bs4"),
    ("feedparser", "feedparser"),
]


def check_dependencies(result: CheckResult):
    result.section_header("Dependencies")
    for display_name, import_name in DEPS:
        try:
            __import__(import_name)
            result.ok(display_name)
        except ImportError:
            result.fail(f"{display_name} missing", fix="pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# Section 3: Key directories
# ---------------------------------------------------------------------------

KEY_DIRS = ["app", "scripts", "docs", "config", "data"]


def check_directories(result: CheckResult):
    result.section_header("Directories")
    for d in KEY_DIRS:
        p = PROJECT_ROOT / d
        if d == "data":
            p.mkdir(exist_ok=True)
            result.ok(f"{d} directory exists (created if missing)")
        elif p.exists():
            result.ok(f"{d} directory exists")
        else:
            result.fail(f"{d} directory missing")


# ---------------------------------------------------------------------------
# Section 4: Config file check
# ---------------------------------------------------------------------------

def check_config(result: CheckResult):
    result.section_header("Config")
    # Check sources.example.yaml exists
    sources_example = PROJECT_ROOT / "config" / "sources.example.yaml"
    if not sources_example.exists():
        result.fail("config/sources.example.yaml missing")
        return

    # Check if sources.yaml exists, if not suggest copying
    sources_yaml = PROJECT_ROOT / "config" / "sources.yaml"
    if not sources_yaml.exists():
        result.warn("config/sources.yaml not found (copy from sources.example.yaml if needed)")
    else:
        result.ok("config/sources.yaml present")

    # Run check_sources_config.py
    check_script = PROJECT_ROOT / "scripts" / "check_sources_config.py"
    if not check_script.exists():
        result.fail("scripts/check_sources_config.py missing")
        return

    proc = subprocess.run(
        [sys.executable, str(check_script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
    )
    if proc.returncode == 0:
        result.ok("sources config validation")
    else:
        result.fail("sources config validation failed")
        if proc.stdout:
            for line in proc.stdout.splitlines()[:5]:
                print(f"       {line}")
        if proc.stderr:
            for line in proc.stderr.splitlines()[:3]:
                print(f"       {line}")


# ---------------------------------------------------------------------------
# Section 5: Isolated DB + tables
# ---------------------------------------------------------------------------

REQUIRED_TABLES = [
    "sources",
    "source_items",
    "fetch_runs",
    "insight_cards",
    "card_decisions",
    "insight_card_bilingual_reports",
]


def check_database(result: CheckResult, isolated_db_url: str, engine_kwargs: dict):
    result.section_header("Database")

    # Import after setting isolated DB
    from sqlalchemy import create_engine, inspect
    from app.models import Base  # noqa: F401

    engine = create_engine(isolated_db_url, **engine_kwargs)

    try:
        # Create tables
        Base.metadata.create_all(bind=engine)
        result.ok("init_db()")

        # Check tables
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

        for table in REQUIRED_TABLES:
            if table in table_names:
                result.ok(f"table {table}")
            else:
                result.fail(f"table {table} missing")

        return engine
    except Exception as e:
        result.fail(f"database initialization failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Section 6: Demo data
# ---------------------------------------------------------------------------

def check_demo_data(result: CheckResult, db_session):
    result.section_header("Demo Data")

    from app.models import Source, SourceItem, InsightCard, CardDecision, InsightCardBilingualReport
    from scripts.create_demo_data import create_demo_data, DEMO_SOURCE_KEY

    # Use create_demo_data which handles existing data gracefully
    demo_result = create_demo_data(DEMO_SOURCE_KEY)

    source_item_id = demo_result.get("source_item_id")
    card_id = demo_result.get("card_id")

    if not source_item_id:
        result.fail("demo SourceItem not created")
        return None, None

    result.ok("demo Source created")

    # Verify SourceItem
    si = db_session.query(SourceItem).filter(SourceItem.id == source_item_id).first()
    if si and si.status == "compiled":
        result.ok("demo SourceItem status=compiled")
    else:
        result.fail("demo SourceItem status check failed")

    if not card_id:
        result.fail("demo InsightCard not created")
        return source_item_id, None

    result.ok("demo InsightCard created")

    # Verify InsightCard
    card = db_session.query(InsightCard).filter(InsightCard.id == card_id).first()
    if card:
        result.ok(f"demo InsightCard status={card.status.value}")
    else:
        result.fail("demo InsightCard not found in DB")

    # Verify BilingualReport
    report = db_session.query(InsightCardBilingualReport).filter(
        InsightCardBilingualReport.card_id == card_id
    ).first()
    if report:
        result.ok("demo BilingualReport created")
    else:
        result.fail("demo BilingualReport not found")

    # Verify CardDecision
    decision = db_session.query(CardDecision).filter(
        CardDecision.card_id == card_id
    ).first()
    if decision:
        result.ok(f"demo CardDecision created (decision={decision.decision})")
    else:
        result.fail("demo CardDecision not found")

    return source_item_id, card_id


# ---------------------------------------------------------------------------
# Section 7: Key pages (TestClient)
# ---------------------------------------------------------------------------

PAGE_CHECKS = [
    ("/", ["信息来源", "运行记录", "候选池", "生成队列", "InsightCard"]),  # V1.0-beta workflow
    ("/source-items", ["原始 SourceItem 列表"]),  # V1.0-beta.3: page re-labelled
    ("/candidate-pool", ["候选资料入口"]),  # V1.0-beta.3: new primary entry
    ("/fetch-runs", ["来源探测运行"]),  # V1.0-beta.4: FetchRun cockpit
    ("/cards", ["中文洞察卡工作台"]),
]


def check_pages(result: CheckResult, source_item_id, card_id):
    result.section_header("Pages")

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    for path, expected_texts in PAGE_CHECKS:
        response = client.get(path)
        if response.status_code == 200:
            result.ok(f"GET {path}")
            text = response.text
            for check_text in expected_texts:
                if check_text not in text:
                    result.warn(f"       missing expected text: {check_text}")
        else:
            result.fail(f"GET {path} returned {response.status_code}")

    # Check demo item and card pages if we have IDs
    if source_item_id:
        path = f"/source-items/{source_item_id}"
        response = client.get(path)
        if response.status_code == 200:
            result.ok(f"GET {path}")
        else:
            result.fail(f"GET {path} returned {response.status_code}")

    if card_id:
        # Card detail
        path = f"/cards/{card_id}"
        response = client.get(path)
        if response.status_code == 200:
            result.ok(f"GET {path}")
            text = response.text
            if "中英双语核心理解" not in text:
                result.warn("       missing expected text: 中英双语核心理解")
        else:
            result.fail(f"GET {path} returned {response.status_code}")

        # Export report
        path = f"/cards/{card_id}/export-report"
        response = client.get(path)
        if response.status_code == 200:
            result.ok(f"GET {path}")
            text = response.text
            if "完整报告预览" not in text:
                result.warn("       missing expected text: 完整报告预览")
        else:
            result.fail(f"GET {path} returned {response.status_code}")

        # Export markdown
        path = f"/cards/{card_id}/export-markdown"
        response = client.get(path)
        if response.status_code == 200:
            result.ok(f"GET {path}")
            text = response.text
            if "Markdown 任务" not in text:
                result.warn("       missing expected text: Markdown 任务")
        else:
            result.fail(f"GET {path} returned {response.status_code}")


# ---------------------------------------------------------------------------
# Section 8: smoke_test (--full only, unless --skip-smoke)
# ---------------------------------------------------------------------------

def check_smoke_test(result: CheckResult, skip_smoke: bool):
    if skip_smoke:
        result.section_header("Smoke Test")
        result.warn("skipped (--skip-smoke)")
        return

    result.section_header("Smoke Test")
    smoke_script = PROJECT_ROOT / "scripts" / "smoke_test.py"
    if not smoke_script.exists():
        result.fail("scripts/smoke_test.py missing")
        return

    proc = subprocess.run(
        [sys.executable, str(smoke_script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )
    if proc.returncode == 0:
        result.ok("smoke_test")
    else:
        result.fail("smoke_test failed")
        lines = (proc.stdout + proc.stderr).splitlines()
        for line in lines[-30:]:
            print(f"       {line}")


# ---------------------------------------------------------------------------
# Section 9: acceptance scripts (--full only)
# ---------------------------------------------------------------------------

def check_acceptance(result: CheckResult, run_full: bool):
    if not run_full:
        return

    # acceptance_demo_data
    result.section_header("Acceptance (Demo Data)")
    accept_script = PROJECT_ROOT / "scripts" / "acceptance_demo_data.py"
    if not accept_script.exists():
        result.fail("scripts/acceptance_demo_data.py missing")
    else:
        proc = subprocess.run(
            [sys.executable, str(accept_script), "--isolated-db"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        if proc.returncode == 0 and "PASS" in proc.stdout:
            result.ok("acceptance_demo_data")
        else:
            result.fail("acceptance_demo_data failed")
            lines = (proc.stdout + proc.stderr).splitlines()
            for line in lines[-30:]:
                print(f"       {line}")

    # acceptance_demo_flow
    result.section_header("Acceptance (Demo Flow)")
    accept_flow = PROJECT_ROOT / "scripts" / "acceptance_demo_flow.py"
    if not accept_flow.exists():
        result.fail("scripts/acceptance_demo_flow.py missing")
    else:
        proc = subprocess.run(
            [sys.executable, str(accept_flow), "--isolated-db"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        if proc.returncode == 0 and "PASS" in proc.stdout:
            result.ok("acceptance_demo_flow")
        else:
            result.fail("acceptance_demo_flow failed")
            lines = (proc.stdout + proc.stderr).splitlines()
            for line in lines[-30:]:
                print(f"       {line}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AI Frontier Radar health check.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick check: Python, deps, config, DB, demo data, pages (default).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full checks including smoke_test and acceptance scripts.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke_test (use with --full).",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep isolated health check DB after completion.",
    )
    args = parser.parse_args()

    # Default to quick if neither --quick nor --full specified
    run_full = args.full
    skip_smoke = args.skip_smoke

    print("=" * 60)
    print("AI Frontier Radar - Health Check")
    print("=" * 60)

    result = CheckResult()

    # 1. Python version
    check_python_version(result)

    # 2. Dependencies
    check_dependencies(result)

    # 3. Directories
    check_directories(result)

    # 4. Config
    check_config(result)

    # 5. Isolated DB + tables
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    db_name = f"health_check_{timestamp}.db"
    isolated_db_path = PROJECT_ROOT / "data" / db_name
    isolated_db_url = f"sqlite:///{isolated_db_path.resolve()}"

    # Set isolated DB before importing app modules that use DATABASE_URL
    original_db_url = os.environ.get("DATABASE_URL", "")
    os.environ["DATABASE_URL"] = isolated_db_url

    engine = None
    db = None
    source_item_id = None
    card_id = None

    try:
        engine_kwargs = {}
        if "sqlite" in isolated_db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        engine = check_database(result, isolated_db_url, engine_kwargs)

        if engine:
            from sqlalchemy.orm import sessionmaker
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()

            # 6. Demo data
            source_item_id, card_id = check_demo_data(result, db)

            # 7. Pages
            check_pages(result, source_item_id, card_id)

        # 8. smoke_test (only in --full mode)
        if run_full:
            check_smoke_test(result, skip_smoke=skip_smoke)
        else:
            result.section_header("Smoke Test")
            result.ok("skipped in quick mode")

        # 9. acceptance (only in --full mode)
        check_acceptance(result, run_full=run_full)

    finally:
        # Restore original DATABASE_URL
        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        if db:
            db.close()
        if engine:
            engine.dispose()

    # 10. Cleanup isolated DB
    if not args.keep_db:
        try:
            if isolated_db_path.exists():
                isolated_db_path.unlink()
        except OSError as e:
            result.warn(f"Could not delete isolated DB (Windows file lock): {e}")
    else:
        result.warn(f"Keeping isolated DB: {isolated_db_path}")

    # Summary
    overall, exit_code = result.overall()
    print("\n" + "=" * 60)
    print(f"RESULT: {overall}")
    print("=" * 60)

    # Print warnings summary
    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  - {w}")

    # Print failures summary
    if result.failed:
        print("\nFailures:")
        for f in result.failed:
            print(f"  - {f}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
