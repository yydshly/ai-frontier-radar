"""Tests for the daily-cycle run-report persistence layer.

Scope:
- save_daily_cycle_run_report writes <run_id>.json and latest.json
- load_latest_daily_cycle_run reads the latest report
- Chinese content round-trips correctly
- latest.json is overwritten on subsequent saves
- Corrupt latest.json is handled gracefully (returns None)
- scripts/show_daily_cycle_status.py is a proper read-only status script
- scripts/run_daily_cycle.py integrates the report functions

These tests do NOT:
- Call any LLM
- Access the network
- Modify the real runtime directory
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# Import the module under test.
from app.application.radar.daily_cycle_runs import (
    get_daily_cycle_latest_path,
    get_daily_cycle_run_path,
    get_daily_cycle_runs_dir,
    get_daily_cycle_log_path,
    load_latest_daily_cycle_run,
    save_daily_cycle_run_report,
    append_daily_cycle_log,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_root(tmp_path: Path) -> Path:
    """Return an isolated temp root so tests never touch the real runtime."""
    return tmp_path


def _make_report(run_id: str, **overrides) -> dict:
    """Return a minimal valid report dict for testing."""
    base = {
        "run_id": run_id,
        "mode": "apply",
        "status": "success",
        "exit_code": 0,
        "started_at": "2026-06-13T08:05:00",
        "finished_at": "2026-06-13T08:07:31",
        "duration_seconds": 151,
        "fetch_due": 12,
        "fetch_started": 8,
        "summary_targets": 24,
        "summary_completed": 24,
        "report_status": "finalized",
        "audio_status": "generated",
        "finalized_dates": ["2026-06-12"],
        "steps": [
            "report: finalization 2026-06-12=finalized",
            "fetch: due=12 started=8",
            "summary: targets=24 covered=24",
        ],
        "errors": [],
        "log_path": "logs/daily_cycle.log",
        "command": "python scripts/run_daily_cycle.py --apply",
    }
    base.update(overrides)
    return base


# ─── Directory / path helpers ────────────────────────────────────────────────

class TestGetPaths:
    def test_get_daily_cycle_runs_dir_creates_if_absent(self, isolated_root: Path):
        root = get_daily_cycle_runs_dir(root_dir=isolated_root)
        assert root.exists()
        assert root.is_dir()

    def test_get_daily_cycle_latest_path(self, isolated_root: Path):
        path = get_daily_cycle_latest_path(root_dir=isolated_root)
        assert path.name == "latest.json"
        # The project-root structure is:
        #   isolated_root / runtime / daily_cycle_runs / latest.json
        assert path.parent.name == "daily_cycle_runs"
        assert path.parent.parent.name == "runtime"
        assert path.parent.parent.parent == isolated_root

    def test_get_daily_cycle_run_path_valid_id(self, isolated_root: Path):
        path = get_daily_cycle_run_path("20260613_080500", root_dir=isolated_root)
        assert path.name == "20260613_080500.json"

    def test_get_daily_cycle_run_path_invalid_id_raises(self, isolated_root: Path):
        with pytest.raises(ValueError, match="YYYYMMDD_HHMMSS"):
            get_daily_cycle_run_path("invalid", root_dir=isolated_root)

    def test_get_daily_cycle_log_path(self, isolated_root: Path):
        path = get_daily_cycle_log_path(root_dir=isolated_root)
        assert path.name == "daily_cycle.log"
        assert "logs" in path.parts


# ─── save / load ─────────────────────────────────────────────────────────────

class TestSaveAndLoad:
    def test_save_writes_run_id_json_and_latest_json(self, isolated_root: Path):
        report = _make_report("20260613_080500")
        result = save_daily_cycle_run_report(report, root_dir=isolated_root)

        # <run_id>.json should exist.
        run_path = get_daily_cycle_run_path("20260613_080500", root_dir=isolated_root)
        assert run_path.exists()

        # latest.json should exist.
        latest_path = get_daily_cycle_latest_path(root_dir=isolated_root)
        assert latest_path.exists()

        # Both should contain the same data.
        run_data = json.loads(run_path.read_text(encoding="utf-8"))
        latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
        assert run_data == latest_data == report

    def test_save_returns_report_unchanged(self, isolated_root: Path):
        report = _make_report("20260613_080500")
        result = save_daily_cycle_run_report(report, root_dir=isolated_root)
        assert result == report

    def test_save_with_chinese_content_round_trips(self, isolated_root: Path):
        report = _make_report(
            "20260613_080500",
            steps=[
                "报告：finalization 2026-06-12=finalized",
                "抓取：due=5 started=3",
                "摘要：targets=10 covered=8",
            ],
            errors=["错误：网络超时"],
        )
        save_daily_cycle_run_report(report, root_dir=isolated_root)

        loaded = load_latest_daily_cycle_run(root_dir=isolated_root)
        assert loaded is not None
        assert loaded["steps"][0] == "报告：finalization 2026-06-12=finalized"
        assert loaded["errors"][0] == "错误：网络超时"

    def test_load_latest_returns_none_when_no_file(self, isolated_root: Path):
        result = load_latest_daily_cycle_run(root_dir=isolated_root)
        assert result is None

    def test_load_latest_returns_none_for_corrupt_json(self, isolated_root: Path):
        latest_path = get_daily_cycle_latest_path(root_dir=isolated_root)
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text("not valid json{", encoding="utf-8")

        result = load_latest_daily_cycle_run(root_dir=isolated_root)
        assert result is None

    def test_load_latest_returns_none_for_empty_file(self, isolated_root: Path):
        latest_path = get_daily_cycle_latest_path(root_dir=isolated_root)
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text("", encoding="utf-8")

        result = load_latest_daily_cycle_run(root_dir=isolated_root)
        assert result is None


class TestLatestOverride:
    def test_second_save_overwrites_latest(self, isolated_root: Path):
        report1 = _make_report("20260613_080500", status="success")
        report2 = _make_report("20260613_090000", status="success")

        save_daily_cycle_run_report(report1, root_dir=isolated_root)
        save_daily_cycle_run_report(report2, root_dir=isolated_root)

        latest = load_latest_daily_cycle_run(root_dir=isolated_root)
        assert latest is not None
        assert latest["run_id"] == "20260613_090000"

        # The first run's file should still exist.
        run1_path = get_daily_cycle_run_path("20260613_080500", root_dir=isolated_root)
        assert run1_path.exists()


class TestAppendLog:
    def test_append_creates_log_file(self, isolated_root: Path):
        log_path = get_daily_cycle_log_path(root_dir=isolated_root)
        assert not log_path.exists()

        append_daily_cycle_log(
            run_id="20260613_080500",
            mode="apply",
            command="python scripts/run_daily_cycle.py --apply",
            started_at="2026-06-13T08:05:00",
            finished_at="2026-06-13T08:07:31",
            duration_seconds=151,
            exit_code=0,
            status="success",
            report_status="finalized",
            audio_status="generated",
            steps=["step one", "step two"],
            errors=[],
            root_dir=isolated_root,
        )

        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "Daily cycle APPLY 2026-06-13T08:05:00" in content
        assert "run_id:           20260613_080500" in content
        assert "duration_seconds: 151" in content
        assert "step one" in content
        assert "errors:        (none)" in content

    def test_append_preserves_previous_content(self, isolated_root: Path):
        log_path = get_daily_cycle_log_path(root_dir=isolated_root)

        append_daily_cycle_log(
            run_id="20260613_080500",
            mode="apply",
            command="python scripts/run_daily_cycle.py --apply",
            started_at="2026-06-13T08:05:00",
            finished_at="2026-06-13T08:07:31",
            duration_seconds=151,
            exit_code=0,
            status="success",
            report_status="finalized",
            audio_status="generated",
            steps=["step one"],
            errors=[],
            root_dir=isolated_root,
        )

        append_daily_cycle_log(
            run_id="20260613_090000",
            mode="dry-run",
            command="python scripts/run_daily_cycle.py",
            started_at="2026-06-13T09:00:00",
            finished_at="2026-06-13T09:01:00",
            duration_seconds=60,
            exit_code=0,
            status="success",
            report_status="skipped",
            audio_status="skipped",
            steps=["step a"],
            errors=["警告：缺少配置"],
            root_dir=isolated_root,
        )

        content = log_path.read_text(encoding="utf-8")
        assert "20260613_080500" in content
        assert "20260613_090000" in content
        assert "警告：缺少配置" in content


# ─── Script static checks ────────────────────────────────────────────────────

class TestRunDailyCycleIntegration:
    """Smoke-test that run_daily_cycle.py wires up the report functions."""

    def test_run_daily_cycle_script_uses_save_function(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_daily_cycle.py"
        content = script_path.read_text(encoding="utf-8")
        assert "save_daily_cycle_run_report" in content

    def test_run_daily_cycle_script_uses_append_log_function(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_daily_cycle.py"
        content = script_path.read_text(encoding="utf-8")
        assert "append_daily_cycle_log" in content

    def test_run_daily_cycle_script_has_started_at_and_finished_at(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_daily_cycle.py"
        content = script_path.read_text(encoding="utf-8")
        assert "started_at" in content
        assert "finished_at" in content
        assert "duration_seconds" in content


class TestShowStatusScript:
    """Smoke-test that show_daily_cycle_status.py is a well-behaved read-only script."""

    def test_script_exists(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "show_daily_cycle_status.py"
        assert script_path.exists()

    def test_script_imports_load_latest_function(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "show_daily_cycle_status.py"
        content = script_path.read_text(encoding="utf-8")
        assert "load_latest_daily_cycle_run" in content

    def test_script_does_not_import_run_daily_cycle(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "show_daily_cycle_status.py"
        content = script_path.read_text(encoding="utf-8")
        # The status script must not trigger a new daily cycle.
        assert "run_daily_cycle" not in content

    def test_script_does_not_import_llm_modules(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "show_daily_cycle_status.py"
        content = script_path.read_text(encoding="utf-8")
        # Must not import any LLM-related modules that could trigger API calls.
        llm_indicators = [
            "openai", "anthropic", "llm", "generate", "chatCompletion",
            "Completion", "Message", "minimax", "zhipu",
        ]
        for indicator in llm_indicators:
            assert indicator not in content, f"Script should not contain '{indicator}'"

    def test_script_does_not_import_fetch_or_audio_modules(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "show_daily_cycle_status.py"
        content = script_path.read_text(encoding="utf-8")
        forbidden = [
            "run_source_discovery", "fetch_service", "SourceFetchService",
            "generate_audio", "daily_broadcast", "text_to_speech",
            "mimo_tts",
        ]
        for name in forbidden:
            assert name not in content, f"Script should not contain '{name}'"
