"""search_providers — API 리서치·실패 판정 (HTTP mock)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from iris.agent.needs_agent import is_research_failure
from iris.agent.search_providers import (
    _parse_duckduckgo_html,
    fetch_duckduckgo_hits,
    fetch_open_meteo_hits,
    fetch_tmdb_hits,
    fetch_web_api_hits,
    is_research_failure as sp_is_failure,
)
from iris.agent.web_agent import SearchHit
from iris.core.command_router import CommandKind


def test_is_research_failure_empty() -> None:
    failed, reason = is_research_failure([])
    assert failed
    assert "비어" in reason


def test_is_research_failure_playwright_missing() -> None:
    hits = [
        SearchHit(
            title="Playwright 미설치",
            url="",
            snippet="pip install playwright",
            source_label="error",
        )
    ]
    failed, _ = is_research_failure(hits)
    assert failed


def test_is_research_failure_substantive_ok() -> None:
    hits = [
        SearchHit(
            title="서울 날씨",
            url="https://open-meteo.com/",
            snippet="서울 현재 날씨: 맑음, 기온 22°C, 습도 50%",
            source_label="open_meteo",
        )
    ]
    failed, reason = is_research_failure(hits)
    assert not failed
    assert reason == ""


def test_fetch_open_meteo_hits_mock() -> None:
    geo_resp = MagicMock()
    geo_resp.raise_for_status = MagicMock()
    geo_resp.json.return_value = {
        "results": [{"latitude": 37.5, "longitude": 127.0, "name": "Seoul"}]
    }
    fc_resp = MagicMock()
    fc_resp.raise_for_status = MagicMock()
    fc_resp.json.return_value = {
        "current": {
            "temperature_2m": 20.0,
            "relative_humidity_2m": 55,
            "weather_code": 0,
            "wind_speed_10m": 10.0,
        }
    }

    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        if "geocoding" in url:
            return geo_resp
        return fc_resp

    client = MagicMock()
    client.get = fake_get
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    with patch("iris.agent.search_providers.httpx.Client", return_value=client):
        hits = fetch_open_meteo_hits("서울 날씨")

    assert len(hits) == 1
    assert "기온" in hits[0].snippet
    assert hits[0].source_label == "open_meteo"
    failed, _ = sp_is_failure(hits)
    assert not failed


def test_fetch_tmdb_with_key_mock() -> None:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": [
            {"id": 1, "title": "테스트 영화", "overview": "줄거리", "release_date": "2024-01-01"}
        ]
    }
    client = MagicMock()
    client.get = MagicMock(return_value=resp)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    with patch.dict("os.environ", {"TMDB_API_KEY": "test-key"}, clear=False):
        with patch("iris.agent.search_providers.httpx.Client", return_value=client):
            hits = fetch_tmdb_hits("액션", max_results=1)
    assert len(hits) == 1
    assert hits[0].source_label == "tmdb"
    assert hits[0].title == "테스트 영화"


def test_fetch_tmdb_no_key() -> None:
    with patch.dict("os.environ", {"TMDB_API_KEY": ""}, clear=False):
        hits = fetch_tmdb_hits("인기 영화")
    assert len(hits) == 1
    assert hits[0].source_label == "provider_error"
    failed, reason = is_research_failure(hits)
    assert failed
    assert "API" in hits[0].snippet or "키" in hits[0].snippet or "설정" in reason


def test_parse_duckduckgo_html() -> None:
    html = """
    <html><body>
      <a class="result__a" href="https://example.com/a">첫 번째 결과</a>
      <a class="result__snippet">설명 스니펫 A</a>
      <a class="result__a" href="https://example.com/b">두 번째 결과</a>
      <a class="result__snippet">설명 스니펫 B</a>
    </body></html>
    """
    hits = _parse_duckduckgo_html(html, max_results=5)
    assert len(hits) == 2
    assert hits[0].source_label == "duckduckgo_html"
    assert hits[0].url == "https://example.com/a"
    assert "스니펫" in hits[0].snippet


def test_fetch_duckduckgo_hits_uses_ddgs_lib() -> None:
    lib_rows = [
        {"title": "Python.org", "href": "https://www.python.org/", "body": "공식 사이트 설명"},
    ]

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return False

        def text(self, query: str, max_results: int = 6):  # type: ignore[no-untyped-def]
            return iter(lib_rows)

    with patch("iris.agent.search_providers._load_ddgs_class", return_value=FakeDDGS):
        hits = fetch_duckduckgo_hits("Python")
    assert len(hits) == 1
    assert hits[0].source_label == "duckduckgo"
    assert hits[0].url == "https://www.python.org/"


def test_fetch_web_api_hits_duckduckgo_only() -> None:
    with patch(
        "iris.agent.search_providers.fetch_duckduckgo_hits",
        return_value=[
            SearchHit("t", "https://x", "본문 스니펫 충분히 길게", source_label="duckduckgo")
        ],
    ):
        hits, provider = fetch_web_api_hits("테스트")
    assert provider == "duckduckgo"
    assert len(hits) == 1


def test_assess_research_quality_good() -> None:
    from iris.agent.search_providers import assess_research_quality

    hits = [
        SearchHit(
            title=f"기사 {i}",
            url=f"https://site{i}.example.com/a",
            snippet="충분히 긴 본문 스니펫 " * 8,
            source_label="duckduckgo",
        )
        for i in range(4)
    ]
    q = assess_research_quality(hits)
    assert q.tier in ("good", "partial")
    assert q.score >= 0.38
    assert q.source_count == 4


def test_assess_research_quality_partial_not_binary_failure() -> None:
    from iris.agent.search_providers import assess_research_quality, is_research_failure

    hits = [
        SearchHit(
            title="짧은 결과",
            url="https://one.example/x",
            snippet="짧지만 답에 쓸 만한 한 줄 설명입니다.",
            source_label="duckduckgo",
        )
    ]
    q = assess_research_quality(hits)
    failed, _ = is_research_failure(hits)
    assert not failed
    assert q.tier in ("poor", "partial")


def test_research_for_intent_weather_uses_open_meteo() -> None:
    from iris.agent.search_providers import research_for_intent

    with patch(
        "iris.agent.search_providers.fetch_open_meteo_hits",
        return_value=[
            SearchHit("t", "https://x", "맑음 기온 1°C", source_label="open_meteo")
        ],
    ):
        hits, provider = research_for_intent("오늘 날씨", CommandKind.WEATHER_SEARCH)
    assert provider == "open_meteo"
    assert hits[0].source_label == "open_meteo"


def test_research_for_intent_skips_playwright_when_disabled() -> None:
    from iris.agent.search_providers import research_for_intent

    with patch(
        "iris.agent.search_providers.fetch_web_api_hits",
        return_value=([], ""),
    ), patch(
        "iris.agent.search_providers.playwright_research_fallback",
    ) as mock_pw:
        hits, provider = research_for_intent(
            "테스트",
            CommandKind.WEB_SEARCH,
            allow_playwright_fallback=False,
        )
    mock_pw.assert_not_called()
    assert hits == []
    assert provider == ""
