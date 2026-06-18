"""Tests for content_video text utilities (content-preserving helpers)."""
from __future__ import annotations

import pytest

from app.application.content_video.text_utils import (
    contains_ellipsis,
    is_fragment_line,
    remove_ellipsis,
    split_bullet_to_pages,
    split_chinese_sentences,
    split_text_to_scene_pages,
)


class TestContainsEllipsis:
    def test_three_dots_detected(self):
        assert contains_ellipsis("题目...") is True

    def test_chinese_ellipsis_detected(self):
        assert contains_ellipsis("题目…") is True

    def test_chinese_double_ellipsis_detected(self):
        assert contains_ellipsis("题目……") is True

    def test_no_ellipsis(self):
        assert contains_ellipsis("题目完整") is False

    def test_empty(self):
        assert contains_ellipsis("") is False
        assert contains_ellipsis(None) is False  # type: ignore[arg-type]


class TestIsFragmentLine:
    def test_single_char_with_punct(self):
        assert is_fragment_line("题；") is True
        assert is_fragment_line("案，") is True
        assert is_fragment_line("问...") is True

    def test_full_phrase(self):
        assert is_fragment_line("完整的一句话") is False

    def test_two_chars(self):
        assert is_fragment_line("两字") is False

    def test_empty(self):
        assert is_fragment_line("") is False
        assert is_fragment_line("   ") is False


class TestRemoveEllipsis:
    def test_removes_three_dots(self):
        assert remove_ellipsis("题目...") == "题目"

    def test_removes_chinese_ellipsis(self):
        assert remove_ellipsis("题目…") == "题目"

    def test_no_ellipsis_unchanged(self):
        assert remove_ellipsis("完整") == "完整"

    def test_empty(self):
        assert remove_ellipsis("") == ""


class TestSplitChineseSentences:
    def test_basic(self):
        text = "今天天气很好。我们去看电影。"
        sentences = split_chinese_sentences(text)
        # Trailing punctuation is preserved (helpful for narration)
        assert sentences == ["今天天气很好。", "我们去看电影。"]

    def test_mixed_punctuation(self):
        text = "第一句；第二句！第三句？第四句"
        sentences = split_chinese_sentences(text)
        # All four should be present
        assert "第一句" in sentences[0]
        assert "第二句" in sentences[1]
        assert "第三句" in sentences[2]
        assert "第四句" in sentences[3]

    def test_no_fragment_output(self):
        text = "今日 AI 研究呈现多维突破。多语言推理方面，AdaMame 解决大型推理模型的语言崩溃问题。智能体安全领域，OSGuard 基准填补计算机操作安全评估空白，CoRA 框架增强推理可靠性。"
        sentences = split_chinese_sentences(text)
        assert len(sentences) > 0
        for s in sentences:
            assert not is_fragment_line(s), f"Fragment line: {s!r}"

    def test_empty(self):
        assert split_chinese_sentences("") == []
        assert split_chinese_sentences(None) == []  # type: ignore[arg-type]

    def test_preserves_all_information(self):
        text = "今日 AI 研究呈现多维突破。多语言推理方面，AdaMame 解决大型推理模型的语言崩溃问题。智能体安全领域，OSGuard 基准填补计算机操作安全评估空白，CoRA 框架增强推理可靠性。效率优化上，NVIDIA 开源 5500 亿参数混合专家模型。"
        sentences = split_chinese_sentences(text)
        joined = "".join(sentences)
        for keyword in ["今日 AI", "AdaMame", "OSGuard", "CoRA", "NVIDIA", "5500"]:
            assert keyword in joined, f"{keyword!r} missing from sentences"


class TestSplitTextToScenePages:
    def test_pagination_respects_lines_per_page(self):
        text = "第一句。第二句。第三句。第四句。第五句。第六句。"
        pages = split_text_to_scene_pages(
            text,
            max_lines_per_scene=2,
            max_chars_per_line=100,
        )
        assert len(pages) == 3
        assert len(pages[0]) == 2
        assert len(pages[1]) == 2
        assert len(pages[2]) == 2

    def test_no_truncation(self):
        text = (
            "今日 AI 研究呈现多维突破。"
            "多语言推理方面，AdaMame 解决大型推理模型的语言崩溃问题。"
            "智能体安全领域，OSGuard 基准填补计算机操作安全评估空白，"
            "CoRA 框架增强推理可靠性。"
            "效率优化上，NVIDIA 开源 5500 亿参数混合专家模型，"
            "字节跳动发布万亿参数 Mamba-Transformer 融合架构。"
        )
        pages = split_text_to_scene_pages(text, max_lines_per_scene=2)
        all_text = "".join("".join(p) for p in pages)
        for kw in ["AdaMame", "OSGuard", "CoRA", "NVIDIA", "Mamba"]:
            assert kw in all_text
        # No ellipsis anywhere
        for p in pages:
            for line in p:
                assert not contains_ellipsis(line)

    def test_empty_input(self):
        assert split_text_to_scene_pages("") == []


class TestSplitBulletToPages:
    def test_short_section_one_page(self):
        pages = split_bullet_to_pages(
            "标题",
            "一句话的 summary 内容。",
            [],
            None,
            max_lines_per_page=3,
        )
        assert len(pages) == 1
        assert len(pages[0]) >= 1

    def test_long_section_multi_page(self):
        summary = (
            "第一句完整内容。"
            "第二句完整内容。"
            "第三句完整内容。"
            "第四句完整内容。"
            "第五句完整内容。"
        )
        pages = split_bullet_to_pages(
            "标题",
            summary,
            [],
            None,
            max_lines_per_page=2,
        )
        assert len(pages) >= 2
        for p in pages:
            assert len(p) <= 2
        # No ellipsis
        for p in pages:
            for line in p:
                assert not contains_ellipsis(line)

    def test_uses_key_points_when_no_summary(self):
        pages = split_bullet_to_pages(
            "标题",
            None,
            ["要点一", "要点二"],
            None,
            max_lines_per_page=3,
        )
        assert len(pages) == 1
        assert any("要点" in line for line in pages[0])

    def test_uses_why_it_matters_as_fallback(self):
        pages = split_bullet_to_pages(
            "标题",
            None,
            [],
            "这一研究值得关注，因为该方法有效解决了核心问题。",
            max_lines_per_page=3,
        )
        assert len(pages) == 1
        assert any("值得" in line or "方法" in line for line in pages[0])

    def test_empty_section(self):
        pages = split_bullet_to_pages("标题", None, [], None)
        assert pages == []