from __future__ import annotations

from app.application.radar.share import _build_highlights


def test_build_highlights_links_references_to_articles_on_page():
    report = {
        "highlights": ["要点一"],
        "highlight_references": [[
            {
                "item_id": 12,
                "title": "页面内文章",
                "url": "https://example.com/in-page",
            },
            {
                "item_id": 13,
                "title": "页面外文章",
                "url": "https://example.com/external",
            },
        ]],
    }

    highlights = _build_highlights(report, {12})

    assert len(highlights) == 1
    assert highlights[0].text == "要点一"
    assert highlights[0].references[0].is_on_page is True
    assert highlights[0].references[1].is_on_page is False


def test_build_highlights_tolerates_missing_reference_group():
    highlights = _build_highlights({"highlights": ["要点一"]}, set())

    assert len(highlights) == 1
    assert highlights[0].references == []
