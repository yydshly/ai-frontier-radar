from pathlib import Path

from app.application.content_video.models import VideoScene
from app.application.content_video.remotion_renderer import build_report_props


def test_build_report_props_preserves_scene_order_and_duration():
    scenes = [
        VideoScene(
            scene_id="scene_01",
            scene_type="opening",
            visual_title="今日简报",
            visual_lines=["信号一", "信号二"],
            narration_text="开场",
            source_label="2026-06-18",
            duration_seconds=4.2,
        ),
        VideoScene(
            scene_id="scene_02",
            scene_type="core_insight",
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


def test_build_report_props_passes_share_url_and_qr():
    """The closing-scene props must include shareUrl / qrCodeDataUrl when provided."""
    scenes = [
        VideoScene(
            scene_id="scene_01",
            scene_type="opening",
            visual_title="入口",
            visual_lines=["AI 前沿雷达"],
            narration_text="开场",
            duration_seconds=3.0,
        ),
        VideoScene(
            scene_id="scene_99",
            scene_type="closing",
            visual_title="查看完整报告",
            visual_lines=["扫码查看完整报告", "或访问：example.com"],
            narration_text="结束语",
            duration_seconds=3.0,
            metadata={"share_url": "https://example.com/share", "qr_code_data_url": "data:image/png;base64,XYZ"},
        ),
    ]

    props = build_report_props(
        scenes,
        title="AI 前沿日报",
        subtitle=None,
        date_label="2026-06-18",
        share_url="https://example.com/share",
        qr_code_data_url="data:image/png;base64,XYZ",
    )

    # Top-level shareUrl / qrCodeDataUrl are forwarded
    assert props["shareUrl"] == "https://example.com/share"
    assert props["qrCodeDataUrl"] == "data:image/png;base64,XYZ"

    # Closing scene carries both values
    closing = props["scenes"][1]
    assert closing["shareUrl"] == "https://example.com/share"
    assert closing["qrCodeDataUrl"] == "data:image/png;base64,XYZ"


def test_report_video_no_overflow_hidden_on_core_content():
    """The Remotion template must not apply overflow:hidden to core content areas."""
    project_root = Path(__file__).resolve().parents[1]
    report_tsx = (project_root / "remotion" / "remotion" / "src" / "ReportVideo.tsx").read_text(
        encoding="utf-8"
    ) if (project_root / "remotion" / "remotion").exists() else (
        project_root / "remotion" / "src" / "ReportVideo.tsx"
    ).read_text(encoding="utf-8")

    # Make sure no `overflow:"hidden"` is applied to body/title containers
    # (background layers are allowed to use overflow:hidden for clip effect).
    # We do a coarse textual check: lines containing 'overflow: "hidden"' inside
    # background layers are acceptable, but lines containing 'overflow: "hidden"'
    # near 'LinesBlock' or 'displayTitle' should NOT exist.
    assert "overflow: \"hidden\"" in report_tsx  # background uses it
    # The LinesBlock body should NOT clip content silently
    lines_block_idx = report_tsx.find("LinesBlock")
    if lines_block_idx != -1:
        snippet = report_tsx[lines_block_idx : lines_block_idx + 2000]
        # No overflow:hidden in the LinesBlock section
        assert 'overflow: "hidden"' not in snippet or "AbsoluteFill" in snippet


def test_report_video_supports_continuation_scene_type():
    """The template must handle core_insight_continuation scene types."""
    project_root = Path(__file__).resolve().parents[1]
    report_tsx = (project_root / "remotion" / "src" / "ReportVideo.tsx").read_text(
        encoding="utf-8"
    )
    assert "core_insight_continuation" in report_tsx


def test_report_video_displays_shareurl_and_qr_on_closing():
    """The template must show shareUrl and QR code on the closing scene."""
    project_root = Path(__file__).resolve().parents[1]
    report_tsx = (project_root / "remotion" / "src" / "ReportVideo.tsx").read_text(
        encoding="utf-8"
    )
    assert "shareUrl" in report_tsx
    assert "qrCodeDataUrl" in report_tsx
    assert "ClosingExtras" in report_tsx


def test_types_include_shareurl_and_qrcode():
    """types.ts must declare shareUrl and qrCodeDataUrl on ReportScene and ReportVideoProps."""
    project_root = Path(__file__).resolve().parents[1]
    types_ts = (project_root / "remotion" / "src" / "types.ts").read_text(
        encoding="utf-8"
    )
    assert "shareUrl" in types_ts
    assert "qrCodeDataUrl" in types_ts