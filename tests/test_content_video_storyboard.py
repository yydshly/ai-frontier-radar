"""Tests for the V2 full-report storyboard (no content truncation)."""
from __future__ import annotations

import dataclasses

import pytest

from app.application.content_video.models import VideoSourceSnapshot, VideoSourceSection
from app.application.content_video.storyboard import build_storyboard
from app.application.content_video.text_utils import (
    contains_ellipsis,
    is_fragment_line,
)


def _make_snapshot() -> VideoSourceSnapshot:
    sections = [
        VideoSourceSection(
            title="AdaMame：两阶段训练方案",
            summary=(
                "AdaMame 提出两阶段训练方案，"
                "在 12 种语言上实现准确率与语言一致性平衡，"
                "达到帕累托最优。"
            ),
            key_points=[
                "解决了大型推理模型的语言崩溃问题",
                "对低资源语言尤其有效",
            ],
            source_name="AdaMame 论文",
        ),
        VideoSourceSection(
            title="OSGuard：智能体安全基准",
            summary=(
                "OSGuard 填补了计算机操作安全评估的空白，"
                "提出 1500 个真实任务覆盖操作系统、办公软件和开发者工具。"
            ),
            source_name="OSGuard 论文",
        ),
        VideoSourceSection(
            title="NVIDIA：5500 亿参数混合专家模型",
            summary=(
                "NVIDIA 开源 5500 亿参数混合专家模型，"
                "在推理基准上达到开源 SOTA，效率提升 3 倍。"
            ),
            source_name="NVIDIA 技术博客",
        ),
        VideoSourceSection(
            title="CoRA：推理可靠性框架",
            summary=(
                "CoRA 框架通过对比反思增强推理可靠性，"
                "在数学和代码任务上平均提升 12%。"
            ),
            source_name="CoRA 论文",
        ),
        VideoSourceSection(
            title="Ling/Ring：低资源语言支持",
            summary=(
                "Ling/Ring 模型针对低资源语言进行微调，"
                "在 Swahili 等 7 种语言上超越 vanilla baseline 20%。"
            ),
            source_name="Ling/Ring 论文",
        ),
        VideoSourceSection(
            title="vanilla baseline 对比实验",
            summary="对比实验表明 vanilla baseline 在多语言场景下表现不稳定。",
            source_name="实验报告",
        ),
        VideoSourceSection(
            title="Mamba-Transformer 融合架构",
            summary="字节跳动发布万亿参数 Mamba-Transformer 融合架构，推理效率提升 5 倍。",
            source_name="字节跳动技术博客",
        ),
    ]
    return VideoSourceSnapshot(
        source_key="radar_2026-06-18",
        title="AI 前沿雷达 · 2026-06-18",
        subtitle="今日核心判断",
        date_label="2026-06-18",
        summary=(
            "今日 AI 研究呈现多维突破。"
            "多语言推理方面，AdaMame 解决大型推理模型的语言崩溃问题。"
            "智能体安全领域，OSGuard 基准填补计算机操作安全评估空白，"
            "CoRA 框架增强推理可靠性。"
            "效率优化上，NVIDIA 开源 5500 亿参数混合专家模型，"
            "字节跳动发布万亿参数 Mamba-Transformer 融合架构。"
        ),
        sections=sections,
        takeaways=[
            "AdaMame 在低资源语言上表现突出",
            "OSGuard 已成为业界事实标准",
            "NVIDIA 5500 亿参数模型推理效率提升 3 倍",
            "字节跳动融合架构引发关注",
        ],
        source_url="https://example.com/share/2026-06-18",
    )


class TestStoryboardCoverage:
    """All sections must appear in the storyboard — not just top 3."""

    def test_all_seven_sections_appear(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot, share_url="https://example.com/share/2026-06-18")

        all_text = " ".join(
            sc.visual_title + " " + sc.narration_text + " " + " ".join(sc.visual_lines)
            for sc in scenes
        )

        # All seven section keywords must appear
        for keyword in ["AdaMame", "OSGuard", "NVIDIA", "CoRA", "Ling", "Ring", "vanilla", "Mamba"]:
            assert keyword in all_text, f"{keyword} missing from storyboard"

    def test_low_resource_phrase_appears(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        all_text = " ".join(
            sc.visual_title + " " + sc.narration_text + " " + " ".join(sc.visual_lines)
            for sc in scenes
        )
        assert "低资源" in all_text
        assert "vanilla baseline" in all_text

    def test_no_section_dropped_when_more_than_three(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        # Should be at least 1 opening + 7 sections + closing = 9 scenes
        core_insight_scenes = [
            sc for sc in scenes
            if sc.scene_type in ("core_insight", "core_insight_continuation")
        ]
        # Continuation scenes share the same section_index; count distinct
        distinct_sections = set()
        for sc in core_insight_scenes:
            idx = (sc.metadata or {}).get("section_index")
            if idx is not None:
                distinct_sections.add(idx)
        assert len(distinct_sections) == 7, (
            f"Expected 7 distinct sections, got {len(distinct_sections)}: {distinct_sections}"
        )


class TestStoryboardNoTruncation:
    """No ellipsis should appear in any core scene."""

    def test_no_ellipsis_in_visual_titles(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        for sc in scenes:
            assert not contains_ellipsis(sc.visual_title), (
                f"Ellipsis in title of {sc.scene_id}: {sc.visual_title!r}"
            )

    def test_no_ellipsis_in_visual_lines(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        for sc in scenes:
            for line in sc.visual_lines:
                assert not contains_ellipsis(line), (
                    f"Ellipsis in line of {sc.scene_id}: {line!r}"
                )

    def test_no_ellipsis_in_narration(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        for sc in scenes:
            assert not contains_ellipsis(sc.narration_text), (
                f"Ellipsis in narration of {sc.scene_id}"
            )

    def test_no_fragment_lines(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        for sc in scenes:
            for line in sc.visual_lines:
                assert not is_fragment_line(line), (
                    f"Fragment line in {sc.scene_id}: {line!r}"
                )

    def test_long_overview_no_truncation(self):
        # Build an artificially long overview.
        snapshot = dataclasses.replace(
            _make_snapshot(),
            summary=(
                "今日 AI 研究呈现多维突破，涵盖多语言推理、智能体安全、效率优化、可解释性等多个方向。"
                "多语言推理方面，AdaMame 提出两阶段训练方案，在 12 种语言上实现准确率与语言一致性平衡，"
                "解决大型推理模型的语言崩溃问题，对低资源语言尤其重要。"
                "智能体安全领域，OSGuard 基准填补计算机操作安全评估的空白，"
                "提出 1500 个真实任务覆盖操作系统、办公软件和开发者工具。"
                "CoRA 框架通过对比反思增强推理可靠性，在数学和代码任务上平均提升 12%。"
                "效率优化上，NVIDIA 开源 5500 亿参数混合专家模型，"
                "字节跳动发布万亿参数 Mamba-Transformer 融合架构，推理效率提升 5 倍。"
                "可解释性方面，多个工作关注模型决策路径的可视化与因果归因。"
            ),
        )
        scenes = build_storyboard(snapshot)
        # No ellipsis anywhere
        for sc in scenes:
            for line in sc.visual_lines:
                assert not contains_ellipsis(line), f"Ellipsis: {line!r}"
            assert not contains_ellipsis(sc.narration_text)


class TestStoryboardStructure:
    """Storyboard must have the expected scene types in order."""

    def test_first_scene_is_opening(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        assert scenes[0].scene_type == "opening"
        assert scenes[0].scene_id == "scene_01"

    def test_last_scene_is_closing(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        assert scenes[-1].scene_type == "closing"

    def test_overview_precedes_core_sections(self):
        scenes = build_storyboard(_make_snapshot())
        overview_index = next(
            i for i, scene in enumerate(scenes)
            if scene.scene_type == "overview_paged"
        )
        core_index = next(
            i for i, scene in enumerate(scenes)
            if scene.scene_type == "core_insight"
        )
        assert overview_index < core_index

    def test_closing_has_share_url(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(
            snapshot, share_url="https://example.com/share/2026-06-18"
        )
        closing = scenes[-1]
        assert closing.metadata.get("share_url") == "https://example.com/share/2026-06-18"
        assert "share_url" in str(closing.metadata) or closing.metadata.get("share_url")

    def test_closing_carries_qr_placeholder(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(
            snapshot,
            share_url="https://example.com/share/2026-06-18",
            qr_code_data_url="data:image/png;base64,AAAA",
        )
        closing = scenes[-1]
        assert closing.metadata.get("qr_code_data_url") == "data:image/png;base64,AAAA"

    def test_opening_shows_full_title_and_count(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)
        opening = scenes[0]
        assert snapshot.title in opening.narration_text
        assert "7" in opening.narration_text  # 7 sections
        # Should NOT include top-3 chip list as the only content
        assert len(opening.visual_lines) <= 4
        assert all("AdaMame" not in line for line in opening.visual_lines)

    def test_long_title_uses_semantic_display_title_and_keeps_full_metadata(self):
        snapshot = dataclasses.replace(
            _make_snapshot(),
            sections=[
                VideoSourceSection(
                    title=(
                        "NVIDIA Nemotron 3 Ultra开源5500亿参数MoE模型，"
                        "推理吞吐量提升约6倍，精度相当。"
                    ),
                    summary=(
                        "NVIDIA Nemotron 3 Ultra开源5500亿参数MoE模型，"
                        "推理吞吐量提升约6倍，精度相当。"
                    ),
                )
            ],
        )
        core = next(
            scene for scene in build_storyboard(snapshot)
            if scene.scene_type == "core_insight"
        )
        assert "…" not in core.visual_title
        assert len(core.visual_title) < len(core.metadata["full_title"])
        assert "5500亿参数" in core.visual_title
        assert core.metadata["section_title"] in core.narration_text

    def test_all_supporting_notes_are_preserved(self):
        takeaways = [f"补充信息第{i}条包含完整结论。" for i in range(1, 8)]
        snapshot = dataclasses.replace(_make_snapshot(), takeaways=takeaways)
        scenes = build_storyboard(snapshot)
        supporting_text = " ".join(
            " ".join(scene.visual_lines)
            for scene in scenes
            if scene.scene_type == "supporting_notes"
        )
        for takeaway in takeaways:
            assert takeaway in supporting_text


class TestAudioVisualSync:
    """Each scene's narration must mention the same key entities as its visual."""

    def test_section_entities_appear_in_visual_or_narration(self):
        snapshot = _make_snapshot()
        scenes = build_storyboard(snapshot)

        # For each core section, find the scene and check entity coverage
        entity_per_section = [
            ("AdaMame", 1),
            ("OSGuard", 2),
            ("NVIDIA", 3),
            ("CoRA", 4),
            ("Ling/Ring", 5),
            ("vanilla", 6),
            ("Mamba-Transformer", 7),
        ]

        for entity, section_idx in entity_per_section:
            # Find scenes for this section
            section_scenes = [
                sc for sc in scenes
                if (sc.metadata or {}).get("section_index") == section_idx
            ]
            assert section_scenes, f"No scene found for section {section_idx}"
            # Combine text from all scenes for this section
            combined = ""
            for sc in section_scenes:
                combined += sc.visual_title + " " + sc.narration_text + " "
                combined += " ".join(sc.visual_lines) + " "
            assert entity in combined, (
                f"Section {section_idx} missing entity {entity!r}"
            )


class TestEmptyAndMinimalInputs:
    """Storyboard must handle empty/missing fields gracefully."""

    def test_no_sections(self):
        snapshot = dataclasses.replace(_make_snapshot(), sections=[])
        scenes = build_storyboard(snapshot)
        # Still has opening + closing
        assert scenes[0].scene_type == "opening"
        assert scenes[-1].scene_type == "closing"

    def test_no_summary(self):
        snapshot = dataclasses.replace(_make_snapshot(), summary="")
        scenes = build_storyboard(snapshot)
        # Should still build without errors
        assert len(scenes) >= 2

    def test_no_takeaways(self):
        snapshot = dataclasses.replace(_make_snapshot(), takeaways=[])
        scenes = build_storyboard(snapshot)
        # Should still build without errors
        assert len(scenes) >= 2

    def test_section_with_no_summary_uses_key_points(self):
        snapshot = dataclasses.replace(
            _make_snapshot(),
            sections=[
                VideoSourceSection(
                    title="短小节",
                    summary="",
                    key_points=["关键点一", "关键点二"],
                ),
            ],
        )
        scenes = build_storyboard(snapshot)
        # The key_points must appear somewhere
        all_text = " ".join(
            sc.visual_title + " " + sc.narration_text + " " + " ".join(sc.visual_lines)
            for sc in scenes
        )
        assert "关键点一" in all_text or "关键点二" in all_text
