"""전용 API 품질 게이트 생략."""

from iris.agent.needs_agent import resolve_answer_mode
from iris.agent.search_providers import assess_research_quality, is_trusted_api_research
from iris.agent.web_agent import SearchHit
from iris.core.command_router import CommandKind


def _open_meteo_hit() -> SearchHit:
    return SearchHit(
        title="서울 날씨 (Open-Meteo)",
        url="https://open-meteo.com/en/docs#latitude=37.5665&longitude=126.9780",
        snippet="서울 현재 날씨: 대체로 맑음, 기온 30.9°C, 습도 69%, 풍속 5.5 km/h",
        source_label="open_meteo",
    )


def test_open_meteo_skips_web_quality_gate() -> None:
    hits = [_open_meteo_hit()]
    assert is_trusted_api_research(hits)
    q = assess_research_quality(hits)
    assert q.tier == "good"
    assert q.score == 1.0
    assert resolve_answer_mode(comparison=False, hybrid=False, quality=q) == "search"


def test_open_meteo_provider_error_still_fails() -> None:
    hits = [
        SearchHit(
            title="Open-Meteo 조회 실패",
            url="",
            snippet="[API 오류] timeout",
            source_label="provider_error",
        )
    ]
    assert not is_trusted_api_research(hits)
    q = assess_research_quality(hits)
    assert q.tier == "failed"
