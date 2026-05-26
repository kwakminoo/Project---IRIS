"""YouTube DOM watch URL 선택 단위 테스트."""

from __future__ import annotations

from iris.automation.youtube_dom import (
    extract_video_id,
    filter_youtube_watch_results,
    normalize_watch_url,
    parse_youtube_search_results,
    pick_watch_url,
    pick_watch_url_by_tokens,
)


def test_parse_mock_json_and_pick_url() -> None:
    raw = [
        {"title": "아이유 - 라일락 MV", "url": "https://www.youtube.com/watch?v=abc111"},
        {"title": "다른 가수 - 다른 곡", "url": "https://www.youtube.com/watch?v=xyz999"},
        {"title": "Shorts", "url": "https://www.youtube.com/shorts/bad"},
    ]
    candidates = filter_youtube_watch_results(parse_youtube_search_results(raw))
    assert len(candidates) == 2
    picked = pick_watch_url_by_tokens("아이유 라일락", candidates)
    assert picked is not None
    assert picked.url.endswith("v=abc111")
    assert "라일락" in picked.title


def test_normalize_watch_url_rejects_shorts_and_ads() -> None:
    assert normalize_watch_url("https://www.youtube.com/shorts/abc") is None
    assert normalize_watch_url("https://googleads.g.doubleclick.net/pagead") is None
    ok = normalize_watch_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=foo")
    assert ok is not None
    assert "v=dQw4w9WgXcQ" in ok


def test_extract_video_id() -> None:
    vid = extract_video_id("https://www.youtube.com/watch?v=abc123XYZ")
    assert vid == "abc123XYZ"


def test_pick_watch_url_with_ranker_callback() -> None:
    raw = parse_youtube_search_results(
        [
            {"title": "A song", "url": "https://www.youtube.com/watch?v=aaa"},
            {"title": "B song", "url": "https://www.youtube.com/watch?v=bbb"},
        ]
    )

    def ranker(titles: list[str]) -> str | None:
        assert len(titles) == 2
        return "B song"

    picked = pick_watch_url("query", raw, rank_pick_title=ranker)
    assert picked is not None
    assert picked.url.endswith("v=bbb")
