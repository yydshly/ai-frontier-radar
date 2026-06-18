from pathlib import Path

from app.application.content_video.models import VideoScene
from app.application.content_video.remotion_renderer import build_report_props


def test_build_report_props_preserves_scene_order_and_duration():
    scenes = [
        VideoScene(
            scene_id="scene_01",
            scene_type="opening_summary",
            visual_title="今日简报",
            visual_lines=["信号一", "信号二"],
            narration_text="开场",
            source_label="2026-06-18",
            duration_seconds=4.2,
        ),
        VideoScene(
            scene_id="scene_02",
            scene_type="signal",
            visual_title="核心洞察",
            visual_lines=["结构化调用成为评估重点"],
            narration_text="正文",
            source_label="来源文章",
            duration_seconds=6.0,
        ),
    ]

    props = build_report_props(
        scenes,
        title="AI 前沿日报",
        subtitle="今日核心判断",
        date_label="2026-06-18",
    )

    assert props["title"] == "AI 前沿日报"
    assert props["style"]["backgroundPreset"] == "tech_grid_dark"
    assert props["style"]["transitionStyle"] == "slide_fade"
    assert [scene["id"] for scene in props["scenes"]] == ["scene_01", "scene_02"]
    assert props["scenes"][0]["durationInFrames"] == 126
    assert props["scenes"][1]["sourceLabel"] == "来源文章"


def test_remotion_workspace_contains_report_composition():
    project_root = Path(__file__).resolve().parents[1]
    root_tsx = (project_root / "remotion" / "src" / "Root.tsx").read_text(
        encoding="utf-8"
    )
    report_tsx = (project_root / "remotion" / "src" / "ReportVideo.tsx").read_text(
        encoding="utf-8"
    )

    assert 'id="RadarReportVideo"' in root_tsx
    assert "tech_grid_dark" in (
        project_root / "remotion" / "src" / "types.ts"
    ).read_text(encoding="utf-8")
    assert "premountFor={30}" in report_tsx
    assert "完整报告见分享页" in report_tsx
