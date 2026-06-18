"""Tests for final daily report requirement in video generation."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestFinalReportRequired:
    """Tests for final report enforcement in share video generation."""

    def test_start_video_generation_requires_final_report(self):
        """_start_video_generation returns failed when no final daily report exists."""
        from app.routes.radar import _start_video_generation

        # Mock db and other dependencies to isolate the final report check
        mock_db = MagicMock()

        # load_final_daily_report is imported locally inside _start_video_generation
        # so we must patch it at its real definition
        with patch("app.application.radar.daily_report_store.load_final_daily_report", return_value=None):
            with patch("app.routes.radar._build_video_source_from_share") as mock_build:
                job_id, input_hash, response = _start_video_generation(
                    mock_db, "2026-06-18", force=False, background_tasks=MagicMock()
                )

        assert response["status"] == "failed"
        assert response["current_step"] == "finalization_check"
        assert "尚未生成最终日报" in response["error"]
        # Verify _build_video_source_from_share was NOT called
        mock_build.assert_not_called()

    def test_start_video_generation_proceeds_with_final_report(self):
        """_start_video_generation proceeds when final daily report exists."""
        from app.routes.radar import _start_video_generation
        from app.application.radar.share_snapshot import ShareReportSnapshot
        from app.application.content_video.models import VideoSourceSnapshot

        mock_db = MagicMock()
        mock_snapshot = ShareReportSnapshot(
            share_key="radar_2026-06-18",
            date_label="2026-06-18",
            report_version_id="v1",
            title="AI 前沿雷达",
            headline="今日要闻",
            overview="概述",
            highlights=[],
            takeaways=[],
        )
        mock_video_snapshot = VideoSourceSnapshot(
            source_key="radar_2026-06-18",
            title="AI 前沿雷达",
            subtitle="今日要闻",
            date_label="2026-06-18",
            summary="概述",
            sections=[],
        )

        # load_final_daily_report is imported locally inside _start_video_generation
        with patch("app.application.radar.daily_report_store.load_final_daily_report", return_value={"title": "Report"}):
            with patch("app.routes.radar._build_video_source_from_share", return_value=mock_video_snapshot):
                with patch("app.application.content_video.storage.ensure_video_dirs"):
                    with patch("app.application.content_video.service.get_existing_video_status", return_value=None):
                        with patch("app.application.content_video.storage.video_storage_for") as mock_storage:
                            mock_storage_instance = MagicMock()
                            mock_storage_instance.acquire_lock.return_value = True
                            mock_storage.return_value = mock_storage_instance

                            # Mock preflight to fail so we don't need full dependencies
                            with patch("app.application.content_video.preflight.run_preflight") as mock_preflight:
                                mock_preflight.return_value.ok = False
                                mock_preflight.return_value.items = []

                                job_id, input_hash, response = _start_video_generation(
                                    mock_db, "2026-06-18", force=False, background_tasks=MagicMock()
                                )

        # Should get to preflight step (not the finalization check)
        assert response["current_step"] == "preflight"
