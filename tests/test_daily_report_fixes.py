#!/usr/bin/env python3
"""
Unit tests for daily report fixes — verifying correct behavior through
direct assertions on settings and code inspection.

Run:
    python tests/test_daily_report_fixes.py
    python -m pytest tests/test_daily_report_fixes.py -v
"""
from __future__ import annotations

import sys
import os
import inspect
import re
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RADAR_DAILY_ANCHOR_HOUR", "8")
os.environ.setdefault("RADAR_DAILY_ANCHOR_TZ_OFFSET", "8")
os.environ.setdefault("RADAR_INCREMENT_CEILING", "2000")
os.environ.setdefault("RADAR_DAILY_ITEM_LIMIT", "50")
os.environ.setdefault("DAILY_REPORT_MAX_ITEMS", "50")


class TestBuildDailyReportInputSourceCode:
    """Verify build_daily_report_input source code doesn't use item_limit in query."""

    def test_source_code_no_longer_uses_min_item_limit(self):
        """Source should use limit(max_items) directly, not min(item_limit, max_items)."""
        import app.application.radar.daily_report as dr_module
        source = inspect.getsource(dr_module.build_daily_report_input)

        # The OLD buggy code had: .limit(min(scope_settings.item_limit, max_items))
        # The FIX removes min(item_limit, ...) wrapper
        assert "min(scope_settings.item_limit, max_items)" not in source, \
            "Source still contains 'min(scope_settings.item_limit, max_items)' — bug not fixed"

        # Should have: .limit(max_items)
        assert ".limit(max_items)" in source, \
            "Source should contain '.limit(max_items)'"

    def test_source_uses_daily_date_label(self):
        """Source should use daily_date_label, not day_start.strftime."""
        import app.application.radar.daily_report as dr_module
        source = inspect.getsource(dr_module.build_daily_report_input)

        # Should NOT have the old UTC midnight pattern
        assert "now.replace(hour=0, minute=0, second=0, microsecond=0)" not in source, \
            "Source still uses UTC midnight 'now.replace(hour=0...)' — should use daily_date_label"
        assert "day_start.strftime" not in source, \
            "Source still uses day_start.strftime — should use daily_date_label"

    def test_date_label_from_daily_date_label(self):
        """date_label assignment should come from daily_date_label function."""
        import app.application.radar.daily_report as dr_module
        source = inspect.getsource(dr_module.build_daily_report_input)

        # The fix: date_label = daily_date_label(now)
        assert "daily_date_label" in source, \
            "Source should call daily_date_label for date_label"


class TestBuildDailyReportCardSourceCode:
    """Verify DailyReportCard source uses count() for total_items."""

    def test_source_uses_count_for_total_items(self):
        """Source should call base.count() to get total_items."""
        import app.application.radar.daily_report_card as drc_module
        source = inspect.getsource(drc_module.build_daily_report_card)

        # Should have: total_items = base.count()
        assert "total_items = base.count()" in source or "total_items=base.count()" in source, \
            "Source should set total_items from base.count()"

    def test_source_no_longer_uses_item_limit_for_total(self):
        """Source should NOT compute total_items from len(limit(50).all())."""
        import app.application.radar.daily_report_card as drc_module
        source = inspect.getsource(drc_module.build_daily_report_card)

        # The OLD bug: rows = base.order_by(...).limit(settings.item_limit).all()
        #              total_items = len(rows)
        # The FIX: total_items = base.count() first
        assert "total_items=len(rows)" not in source and "total_items = len(rows)" not in source, \
            "Source still computes total_items from len(rows) — should use base.count()"

    def test_source_uses_daily_date_label(self):
        """Source should use daily_date_label for date_label."""
        import app.application.radar.daily_report_card as drc_module
        source = inspect.getsource(drc_module.build_daily_report_card)

        assert "now.replace(hour=0, minute=0, second=0, microsecond=0)" not in source, \
            "Source still uses UTC midnight pattern for date_label"
        assert "daily_date_label" in source, \
            "Source should use daily_date_label for date_label"


class TestBuildDailyDigestSourceCode:
    """Verify daily_digest.py uses daily_date_label and removed _start_of_utc_day."""

    def test_removed_start_of_utc_day(self):
        """_start_of_utc_day function should be removed."""
        import app.application.radar.daily_digest as dd_module
        source = inspect.getsource(dd_module)

        assert "_start_of_utc_day" not in source, \
            "_start_of_utc_day should be removed from daily_digest.py"

    def test_uses_daily_date_label(self):
        """Should use daily_date_label instead of _start_of_utc_day."""
        import app.application.radar.daily_digest as dd_module
        source = inspect.getsource(dd_module)

        assert "daily_date_label" in source, \
            "daily_digest.py should use daily_date_label"

    def test_no_utc_midnight_pattern(self):
        """Should not use now.replace(hour=0) for date_label."""
        import app.application.radar.daily_digest as dd_module
        source = inspect.getsource(dd_module)

        # The old code: day_start.strftime("%Y-%m-%d")
        # Should be replaced by daily_date_label(now)
        assert "day_start.strftime" not in source, \
            "daily_digest.py should not use day_start.strftime"


class TestSettingsDAILYREPORTMAXITEMS:
    """Verify DAILY_REPORT_MAX_ITEMS maximum has been raised to 200."""

    def test_daily_report_max_items_can_be_set_to_100(self):
        """DAILY_REPORT_MAX_ITEMS should accept 100 (was capped at 50)."""
        from app.application.radar.settings import get_daily_report_max_items
        from unittest.mock import patch

        with patch.dict(os.environ, {"DAILY_REPORT_MAX_ITEMS": "100"}):
            import importlib
            import app.application.radar.settings as settings_module
            importlib.reload(settings_module)

            result = settings_module.get_daily_report_max_items()
            assert result == 100, f"Expected 100, got {result}"

    def test_daily_report_max_items_can_be_set_to_200(self):
        """DAILY_REPORT_MAX_ITEMS should accept 200 (new maximum)."""
        from app.application.radar.settings import get_daily_report_max_items
        from unittest.mock import patch

        with patch.dict(os.environ, {"DAILY_REPORT_MAX_ITEMS": "200"}):
            import importlib
            import app.application.radar.settings as settings_module
            importlib.reload(settings_module)

            result = settings_module.get_daily_report_max_items()
            assert result == 200, f"Expected 200, got {result}"

    def test_daily_report_max_items_still_rejects_over_200(self):
        """DAILY_REPORT_MAX_ITEMS > 200 should fall back to default."""
        from app.application.radar.settings import get_daily_report_max_items
        from unittest.mock import patch

        with patch.dict(os.environ, {"DAILY_REPORT_MAX_ITEMS": "500"}):
            import importlib
            import app.application.radar.settings as settings_module
            importlib.reload(settings_module)

            result = settings_module.get_daily_report_max_items()
            # Should fall back to default (50) because 500 > 200
            assert result == 50, f"Expected fallback to 50, got {result}"

    def test_maximum_in_source_code_is_200(self):
        """The function's _env_int call should specify maximum=200."""
        import app.application.radar.settings as settings_module
        source = inspect.getsource(settings_module.get_daily_report_max_items)

        # Should have maximum=200, not maximum=50
        assert "maximum=200" in source, \
            "get_daily_report_max_items should specify maximum=200 in _env_int call"


class TestTodaySummaryPanelUsesDailyDateLabel:
    """Verify today_summary_panel uses daily_date_label instead of UTC midnight."""

    def test_today_summary_panel_uses_daily_date_label(self):
        """today_summary_panel._today_date_label should use daily_date_label."""
        import app.application.radar.today_summary_panel as tsp_module
        source = inspect.getsource(tsp_module._today_date_label)

        assert "daily_date_label" in source, \
            "_today_date_label should use daily_date_label()"
        assert "datetime.utcnow().strftime" not in source, \
            "_today_date_label should not use datetime.utcnow().strftime"


def run_as_script():
    """Run all tests and print results."""
    print("\n=== test_daily_report_fixes.py ===\n")

    test_classes = [
        TestBuildDailyReportInputSourceCode,
        TestBuildDailyReportCardSourceCode,
        TestBuildDailyDigestSourceCode,
        TestSettingsDAILYREPORTMAXITEMS,
        TestTodaySummaryPanelUsesDailyDateLabel,
    ]
    total = passed = failed = 0

    for cls in test_classes:
        print(f"[{cls.__name__}]")
        for name in dir(cls):
            if name.startswith("test_"):
                total += 1
                try:
                    instance = cls()
                    getattr(instance, name)()
                    print(f"  [PASS] {name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  [FAIL] {name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  [ERROR] {name}: {e}")
                    failed += 1
        print()

    print(f"Results: {passed}/{total} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_as_script())
else:
    import pytest
    pytest.main([__file__, "-v"])
