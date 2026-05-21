"""media_urls 단위 테스트."""

from __future__ import annotations

import pytest

from iris.automation.media_urls import (
    build_media_open_url,
    build_spotify_search_url,
    build_youtube_search_url,
)


def test_build_youtube_search_url_encodes_query() -> None:
    url = build_youtube_search_url("아이유 라일락")
    assert url.startswith("https://www.youtube.com/results?search_query=")
    assert "search_query=" in url
    assert "youtube.com/home" not in url


def test_build_youtube_search_url_empty_raises() -> None:
    with pytest.raises(ValueError):
        build_youtube_search_url("   ")


def test_build_media_open_url_unknown_uses_browser() -> None:
    url = build_media_open_url("unknown", "테스트")
    assert "google.com/search" in url


def test_build_spotify_search_url() -> None:
    url = build_spotify_search_url("뉴진스")
    assert "open.spotify.com/search" in url
