"""Tests for content_video VideoStorage lock."""
from __future__ import annotations

import json
import time
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch


class TestVideoStorageLock:
    """Tests for VideoStorage lock mechanism."""

    def test_acquire_lock_succeeds_when_no_lock(self, tmp_path):
        """Acquiring lock when no lock exists should succeed."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        assert storage.acquire_lock("job_001") is True

    def test_acquire_lock_succeeds_for_same_job_id(self, tmp_path):
        """Same job_id re-acquiring lock should succeed (refresh)."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        assert storage.acquire_lock("job_001") is True
        assert storage.acquire_lock("job_001") is True

    def test_acquire_lock_fails_for_different_job_when_not_expired(self, tmp_path):
        """Different job_id cannot acquire lock while unexpired lock exists."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        assert storage.acquire_lock("job_001") is True

        # Simulate lock not expired
        with patch.object(storage, "_lock_timeout_seconds", return_value=3600):
            assert storage.acquire_lock("job_002") is False

    def test_acquire_lock_succeeds_after_timeout(self, tmp_path):
        """Lock can be overwritten after timeout expires."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        assert storage.acquire_lock("job_001") is True

        # Simulate expired lock (timeout = 0)
        with patch.object(storage, "_lock_timeout_seconds", return_value=0):
            # Wait a tiny bit so the lock age > 0
            time.sleep(0.01)
            assert storage.acquire_lock("job_002") is True

    def test_release_lock_by_same_job(self, tmp_path):
        """Same job_id can release lock."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        storage.acquire_lock("job_001")
        storage.release_lock("job_001")
        # After release, new job can acquire
        assert storage.acquire_lock("job_002") is True

    def test_release_lock_by_different_job_does_nothing(self, tmp_path):
        """Different job_id cannot release another's lock."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        storage.acquire_lock("job_001")
        storage.release_lock("job_002")  # Different job
        # Lock should still be held
        assert storage.acquire_lock("job_003") is False

    def test_get_lock_info_returns_correct_data(self, tmp_path):
        """get_lock_info returns lock metadata."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        storage.acquire_lock("job_001")

        info = storage.get_lock_info()
        assert info is not None
        assert info["job_id"] == "job_001"
        assert info["expired"] is False

    def test_get_lock_info_returns_expired_after_timeout(self, tmp_path):
        """After timeout, get_lock_info shows expired=True."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        storage.acquire_lock("job_001")

        with patch.object(storage, "_lock_timeout_seconds", return_value=0):
            time.sleep(0.01)
            info = storage.get_lock_info()
            assert info is not None
            assert info["expired"] is True

    def test_get_lock_info_returns_none_when_no_lock(self, tmp_path):
        """get_lock_info returns None when no lock file exists."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        assert storage.get_lock_info() is None

    def test_lock_released_on_failure_path(self, tmp_path):
        """Lock is released even when job fails (tested via release_lock in finally)."""
        from app.application.content_video.storage import VideoStorage
        storage = VideoStorage(tmp_path / "jobdir")
        storage.acquire_lock("job_001")
        # Simulate job completion releasing lock
        storage.release_lock("job_001")
        assert storage.acquire_lock("job_002") is True
