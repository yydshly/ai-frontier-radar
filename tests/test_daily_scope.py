#!/usr/bin/env python3
"""
Unit tests for daily_scope helpers: daily_anchor, daily_window, daily_date_label.

Tests cover:
- daily_anchor with various UTC times and anchor_hour=8, tz_offset=+8
- daily_window returns correct [start, end) tuple
- daily_date_label returns correct local date string
- UTC 00:30 belongs to previous day's anchor period
- UTC 08:30 belongs to current day's anchor period

Run:
    python -m pytest tests/test_daily_scope.py -v
    # or without pytest:
    python tests/test_daily_scope.py
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure test environment
os.environ.setdefault("RADAR_DAILY_ANCHOR_HOUR", "8")
os.environ.setdefault("RADAR_DAILY_ANCHOR_TZ_OFFSET", "8")
os.environ.setdefault("RADAR_INCREMENT_CEILING", "2000")

import pytest
from app.application.radar.daily_scope import (
    daily_anchor,
    daily_window,
    daily_date_label,
)


# ── Test fixtures ────────────────────────────────────────────────────────────

class TestDailyAnchor:
    """Tests for daily_anchor()."""

    def test_anchor_before_threshold(self):
        """UTC 23:30 Jun 12 = Beijing 07:30 Jun 13, before 08:00 threshold."""
        # Beijing 2026-06-13 07:30 = UTC 2026-06-12 23:30
        # Since Beijing 07:30 < 08:00, anchor is previous day Jun 12 00:00 UTC
        utc = datetime(2026, 6, 12, 23, 30, 0)
        result = daily_anchor(utc)
        assert result == datetime(2026, 6, 12, 0, 0, 0)

    def test_anchor_at_exact_threshold(self):
        """UTC 00:00 Jun 13 = Beijing 08:00 Jun 13, so anchor is Jun 13 00:00 UTC."""
        utc = datetime(2026, 6, 13, 0, 0, 0)
        result = daily_anchor(utc)
        # UTC 00:00 Jun 13 = Beijing 08:00 Jun 13 (exactly at threshold)
        assert result == datetime(2026, 6, 13, 0, 0, 0)

    def test_anchor_after_threshold(self):
        """UTC 08:00 Jun 13 = Beijing 16:00 Jun 13, well after 08:00 threshold."""
        utc = datetime(2026, 6, 13, 8, 0, 0)
        result = daily_anchor(utc)
        # Beijing 16:00 > 08:00, so anchor is today Jun 13 00:00 UTC
        assert result == datetime(2026, 6, 13, 0, 0, 0)

    def test_anchor_just_before_threshold(self):
        """UTC 2026-06-13 23:30 = Beijing 2026-06-14 07:30, still before 08:00."""
        utc = datetime(2026, 6, 13, 23, 30, 0)
        result = daily_anchor(utc)
        # Beijing 07:30 < 08:00, so anchor is Jun 13 00:00 UTC
        assert result == datetime(2026, 6, 13, 0, 0, 0)

    def test_anchor_at_midnight_utc(self):
        """UTC midnight Jun 13 = Beijing 08:00 Jun 13 (exact threshold)."""
        utc = datetime(2026, 6, 13, 0, 0, 0)
        result = daily_anchor(utc)
        # Beijing 08:00 exactly, anchor is today
        assert result == datetime(2026, 6, 13, 0, 0, 0)

    def test_anchor_30_minutes_before_threshold(self):
        """UTC 23:30 Jun 12 = Beijing 07:30 Jun 13, still in previous period."""
        utc = datetime(2026, 6, 12, 23, 30, 0)
        result = daily_anchor(utc)
        # Beijing 07:30 < 08:00, anchor is Jun 12 00:00 UTC
        assert result == datetime(2026, 6, 12, 0, 0, 0)

    def test_anchor_30_minutes_after_threshold(self):
        """UTC 00:30 Jun 13 = Beijing 08:30 Jun 13, in current period."""
        utc = datetime(2026, 6, 13, 0, 30, 0)
        result = daily_anchor(utc)
        # Beijing 08:30 > 08:00, anchor is Jun 13 00:00 UTC
        assert result == datetime(2026, 6, 13, 0, 0, 0)


class TestDailyWindow:
    """Tests for daily_window()."""

    def test_window_start_equals_anchor(self):
        """daily_window()[0] should equal daily_anchor()."""
        utc = datetime(2026, 6, 13, 10, 0, 0)
        start, end = daily_window(utc)
        assert start == daily_anchor(utc)

    def test_window_end_is_24_hours_after_start(self):
        """daily_window()[1] should be 24 hours after [0]."""
        utc = datetime(2026, 6, 13, 10, 0, 0)
        start, end = daily_window(utc)
        assert end == start + timedelta(hours=24)

    def test_window_before_threshold(self):
        """Window before threshold should be previous day's period."""
        # UTC 23:30 Jun 12 = Beijing 07:30 Jun 13 (< 08:00)
        utc = datetime(2026, 6, 12, 23, 30, 0)
        start, end = daily_window(utc)
        assert start == datetime(2026, 6, 12, 0, 0, 0)
        assert end == datetime(2026, 6, 13, 0, 0, 0)

    def test_window_after_threshold(self):
        """Window after threshold should be current day's period."""
        utc = datetime(2026, 6, 13, 10, 0, 0)
        start, end = daily_window(utc)
        assert start == datetime(2026, 6, 13, 0, 0, 0)
        assert end == datetime(2026, 6, 14, 0, 0, 0)


class TestDailyDateLabel:
    """Tests for daily_date_label()."""

    def test_local_morning_belongs_to_previous_day(self):
        """Local 2026-06-13 07:30 (Beijing) should return 2026-06-12.

        Beijing 07:30 = UTC 2026-06-12 23:30.
        Since local 07:30 < 08:00 threshold, it belongs to previous day's period.
        """
        # UTC 2026-06-12 23:30 = Beijing 2026-06-13 07:30
        utc = datetime(2026, 6, 12, 23, 30, 0)
        result = daily_date_label(utc)
        assert result == "2026-06-12"

    def test_local_after_threshold_belongs_to_current_day(self):
        """Local 2026-06-13 08:30 (Beijing) should return 2026-06-13.

        Beijing 08:30 = UTC 2026-06-13 00:30.
        Since local 08:30 >= 08:00 threshold, it belongs to current day's period.
        """
        # UTC 2026-06-13 00:30 = Beijing 2026-06-13 08:30
        utc = datetime(2026, 6, 13, 0, 30, 0)
        result = daily_date_label(utc)
        assert result == "2026-06-13"

    def test_exact_threshold(self):
        """Local 2026-06-13 08:00 exactly should return 2026-06-13."""
        # UTC 2026-06-13 00:00 = Beijing 2026-06-13 08:00
        utc = datetime(2026, 6, 13, 0, 0, 0)
        result = daily_date_label(utc)
        assert result == "2026-06-13"

    def test_just_before_threshold(self):
        """Local 2026-06-13 07:59:59 (Beijing) should return 2026-06-12."""
        # UTC 2026-06-12 23:59:59 = Beijing 2026-06-13 07:59:59
        utc = datetime(2026, 6, 12, 23, 59, 59)
        result = daily_date_label(utc)
        assert result == "2026-06-12"

    def test_jun_14_morning(self):
        """Local 2026-06-14 07:30 (Beijing) should return 2026-06-13.

        Beijing 07:30 = UTC 2026-06-13 23:30.
        Since local 07:30 < 08:00, it belongs to Jun 13's period.
        """
        # UTC 2026-06-13 23:30 = Beijing 2026-06-14 07:30
        utc = datetime(2026, 6, 13, 23, 30, 0)
        result = daily_date_label(utc)
        assert result == "2026-06-13"

    def test_jun_14_after_threshold(self):
        """Local 2026-06-14 09:00 (Beijing) should return 2026-06-14."""
        # UTC 2026-06-14 01:00 = Beijing 2026-06-14 09:00
        utc = datetime(2026, 6, 14, 1, 0, 0)
        result = daily_date_label(utc)
        assert result == "2026-06-14"


def run_as_script():
    """Run all tests and print results (for non-pytest execution)."""
    print("\n=== test_daily_scope.py ===\n")

    test_classes = [TestDailyAnchor, TestDailyWindow, TestDailyDateLabel]
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
elif "pytest" in sys.modules or __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v"])
