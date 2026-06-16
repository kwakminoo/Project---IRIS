"""Frontier 라우팅 매트릭스 — 카테고리별 10문장 × 이상 envelope / 오분류 시나리오."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import pytest

from iris.assistant.frontier_agent import _parse_frontier_envelope
from iris.assistant.router_policy import RouteLane
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from tests.support.fakes import (
    FakeGemma,
    frontier_envelope_json,
    make_routing_assistant,
)


class ExpectRoute(str, Enum):
    CHAT_STREAM = "chat_stream"
    SEARCH = "search"
    HYBRID = "hybrid"
    PC_EXEC = "pc_exec"


@dataclass(frozen=True)
class MatrixCase:
    category: str
    user_text: str
    expect: ExpectRoute


def _route_search(
    user_text: str,
    *,
    topic: str = "general",
    query: str | None = None,
    queries: list[str] | None = None,
    lane: str = "search",
    knowledge_lane: str = "search",
    needs_execution: bool = True,
) -> dict[str, object]:
    slots: dict[str, object] = {
        "query": query or user_text.strip()[:40],
        "search_topic": topic,
    }
    if queries:
        slots["queries"] = queries
        slots["answer_shape"] = "comparison"
    return {
        "intent": "search",
        "lane": lane,
        "knowledge_lane": knowledge_lane,
        "goal": user_text.strip()[:60],
        "task_type": "knowledge",
        "slots": slots,
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.9,
    }


def _route_chat_only() -> dict[str, object]:
    return {
        "intent": "chat",
        "lane": "chat_only",
        "knowledge_lane": "chat_only",
        "goal": "",
        "task_type": "unknown",
        "slots": {},
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.9,
    }


def _route_cu(goal: str) -> dict[str, object]:
    return {
        "intent": "computer_use",
        "lane": "computer_use",
        "knowledge_lane": "chat_only",
        "goal": goal,
        "task_type": "open_app",
        "slots": {},
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.9,
    }


def _ideal_envelope(case: MatrixCase) -> str:
    """카테고리별 이상적인 Frontier JSON."""
    if case.expect is ExpectRoute.CHAT_STREAM:
        return frontier_envelope_json(
            "네, 말씀해 주세요.",
            needs_execution=False,
            route=_route_chat_only(),
        )
    if case.expect is ExpectRoute.SEARCH:
        topic = "general"
        if "날씨" in case.user_text:
            topic = "weather"
        elif any(k in case.user_text for k in ("뉴스", "속보")):
            topic = "news"
        elif "영화" in case.user_text:
            topic = "movie"
        elif any(k in case.user_text for k in ("주가", "환율", "코인")):
            topic = "current_info"
        return frontier_envelope_json(
            "확인해볼게요.",
            needs_execution=True,
            route=_route_search(case.user_text, topic=topic),
        )
    if case.expect is ExpectRoute.HYBRID:
        return frontier_envelope_json(
            "찾아보면서 정리해볼게요.",
            needs_execution=True,
            route=_route_search(
                case.user_text,
                lane="hybrid",
                knowledge_lane="hybrid",
            ),
        )
    if case.expect is ExpectRoute.PC_EXEC:
        return frontier_envelope_json(
            "진행해볼게요.",
            needs_execution=True,
            route=_route_cu(case.user_text),
        )
    raise ValueError(case.expect)


# --- 카테고리별 10문장 ---

CHITCHAT: list[MatrixCase] = [
    MatrixCase("잡담", t, ExpectRoute.CHAT_STREAM)
    for t in (
        "안녕",
        "안녕 아이리스",
        "고마워",
        "잘 자",
        "심심해",
        "너 이름이 뭐야",
        "오늘 기분 어때",
        "ㅋㅋ 웃겨",
        "좋은 아침",
        "고생했어",
    )
]

SEARCH: list[MatrixCase] = [
    MatrixCase("검색", "오늘 날씨 어때?", ExpectRoute.SEARCH),
    MatrixCase("검색", "서울 내일 비 와?", ExpectRoute.SEARCH),
    MatrixCase("검색", "부산 현재 기온 알려줘", ExpectRoute.SEARCH),
    MatrixCase("검색", "오늘 주요 뉴스 요약해줘", ExpectRoute.SEARCH),
    MatrixCase("검색", "테슬라 주가 얼마야?", ExpectRoute.SEARCH),
    MatrixCase("검색", "원달러 환율 지금 얼마야?", ExpectRoute.SEARCH),
    MatrixCase("검색", "이번 주말 개봉 영화 뭐 있어?", ExpectRoute.SEARCH),
    MatrixCase("검색", "2026년 한국 대선 일정 알려줘", ExpectRoute.SEARCH),
    MatrixCase("검색", "아이폰 17 출시일 언제야?", ExpectRoute.SEARCH),
    MatrixCase("검색", "지금 비트코인 시세 알려줘", ExpectRoute.SEARCH),
]

COMPARISON: list[MatrixCase] = [
    MatrixCase("비교", "GPT랑 Gemini 차이가 뭐야?", ExpectRoute.SEARCH),
    MatrixCase("비교", "맥북 vs 윈도우 노트북 뭐가 나아?", ExpectRoute.SEARCH),
    MatrixCase("비교", "React와 Vue 장단점 비교해줘", ExpectRoute.SEARCH),
    MatrixCase("비교", "아이폰 16과 갤럭시 S25 비교", ExpectRoute.SEARCH),
    MatrixCase("비교", "콜드브루랑 아메리카노 차이", ExpectRoute.SEARCH),
    MatrixCase("비교", "Ollama와 LM Studio 뭐가 달라?", ExpectRoute.SEARCH),
    MatrixCase("비교", "넷플릭스와 디즈니플러스 비교", ExpectRoute.SEARCH),
    MatrixCase("비교", "PostgreSQL vs MySQL 어떤 게 나아?", ExpectRoute.SEARCH),
    MatrixCase("비교", "전기차랑 하이브리드 차 비교해줘", ExpectRoute.SEARCH),
    MatrixCase("비교", "ChatGPT Plus랑 Claude Pro 뭐가 좋아?", ExpectRoute.SEARCH),
]

DEFINITION: list[MatrixCase] = [
    MatrixCase("정의", "인공지능이 뭐야?", ExpectRoute.SEARCH),
    MatrixCase("정의", "양자컴퓨터란?", ExpectRoute.SEARCH),
    MatrixCase("정의", "블록체인이 뭔지 설명해줘", ExpectRoute.SEARCH),
    MatrixCase("정의", "RPC가 뭐야?", ExpectRoute.SEARCH),
    MatrixCase("정의", "인플레이션이란?", ExpectRoute.SEARCH),
    MatrixCase("정의", "HTTPS는 뭐야?", ExpectRoute.SEARCH),
    MatrixCase("정의", "트랜스포머 모델이 뭐야?", ExpectRoute.SEARCH),
    MatrixCase("정의", "마이크로서비스 아키텍처란?", ExpectRoute.SEARCH),
    MatrixCase("정의", "RAG가 뭔지 알려줘", ExpectRoute.SEARCH),
    MatrixCase("정의", "Docker가 뭐하는 거야?", ExpectRoute.SEARCH),
]

ABSTRACT: list[MatrixCase] = [
    MatrixCase("추상", "행복이란 뭐라고 생각해?", ExpectRoute.CHAT_STREAM),
    MatrixCase("추상", "인생에서 가장 중요한 건 뭐야?", ExpectRoute.CHAT_STREAM),
    MatrixCase("추상", "창의력 키우는 방법 알려줘", ExpectRoute.CHAT_STREAM),
    MatrixCase("추상", "번아웃 왔을 때 어떻게 해?", ExpectRoute.CHAT_STREAM),
    MatrixCase("추상", "좋은 리더의 조건은?", ExpectRoute.CHAT_STREAM),
    MatrixCase("추상", "AI 시장 앞으로 어떻게 될까?", ExpectRoute.HYBRID),
    MatrixCase("추상", "10년 뒤 프로그래밍 직업 전망은?", ExpectRoute.HYBRID),
    MatrixCase("추상", "기후변화가 경제에 미치는 영향은?", ExpectRoute.HYBRID),
    MatrixCase("추상", "한국 IT 업계 트렌드 정리해줘", ExpectRoute.HYBRID),
    MatrixCase("추상", "우주 개발의 미래 전망 알려줘", ExpectRoute.HYBRID),
]

PC_EXEC: list[MatrixCase] = [
    MatrixCase("PC실행", "메모장 켜줘", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "크롬 열어줘", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "계산기 실행해", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "VS Code 켜줘", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "탐색기 열어", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "디스코드 실행", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "스팀 켜줘", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "메모장이랑 크롬 같이 열어", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "유튜브에서 아이유 틀어줘", ExpectRoute.PC_EXEC),
    MatrixCase("PC실행", "https://example.com 열어", ExpectRoute.PC_EXEC),
]

ALL_IDEAL = CHITCHAT + SEARCH + COMPARISON + DEFINITION + ABSTRACT + PC_EXEC

# 오분류: 검색·비교인데 모델이 chat_only envelope를 내는 경우 (잔존 리스크)
MISCLASSIFIED_SEARCH = [
    "오늘 날씨 어때?",
    "GPT랑 Gemini 차이",
    "테슬라 주가",
    "인공지능이 뭐야",
    "2026년 대선 일정",
    "원달러 환율",
    "이번 주 영화",
    "비트코인 시세",
    "React vs Vue",
    "블록체인이란",
]


def _run_coordinator(
    tmp_path: Path,
    user_text: str,
    envelope_json: str,
    *,
    patch_cu: bool = True,
) -> object:
    from tests.support.fakes import make_test_assistant

    gemma = FakeGemma()
    assistant = make_test_assistant(
        tmp_path,
        gemma,
        settings_overrides={
            "unified_llm_router_enabled": True,
            "frontier_enabled": True,
            "router_mode": "frontier_first",
            "chat_fast_path_enabled": False,
            "router_telemetry_enabled": False,
        },
        db_name="matrix.db",
    )
    gemma.chat = lambda messages, purpose=None, **kw: envelope_json  # type: ignore[method-assign]
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]
    if patch_cu:
        from unittest.mock import patch

        with patch.object(
            assistant,
            "run_computer_use_loop",
            return_value="Iris: 완료했습니다.",
        ):
            return coord.run_turn(user_text)
    return coord.run_turn(user_text)


def _assert_expect(result: object, expect: ExpectRoute) -> None:
    if expect is ExpectRoute.CHAT_STREAM:
        assert result.delegate_frontier_stream is True
        assert not result.delegate_search
        assert not result.delegate_dialogue_stream
    elif expect in (ExpectRoute.SEARCH, ExpectRoute.HYBRID):
        assert result.delegate_search is True
        assert not result.delegate_frontier_stream
        if expect is ExpectRoute.HYBRID:
            assert "hybrid" in (result.search_meta_json or "")
    elif expect is ExpectRoute.PC_EXEC:
        assert not result.delegate_frontier_stream
        assert not result.delegate_search
        assert result.route in {
            RouteLane.COMPUTER_USE.value,
            RouteLane.DIRECT_ACTION.value,
            RouteLane.FAST_TOOL.value,
        }


@pytest.mark.parametrize("case", ALL_IDEAL, ids=lambda c: f"{c.category}:{c.user_text[:20]}")
def test_ideal_frontier_envelope_routing(tmp_path: Path, case: MatrixCase) -> None:
    """이상 envelope — 카테고리별 기대 라우트."""
    if case.expect is ExpectRoute.PC_EXEC:
        # catalog 의존 — CU/DIRECT 분기만 확인 (실행 mock)
        envelope = _ideal_envelope(case)
        result = _run_coordinator(tmp_path, case.user_text, envelope, patch_cu=True)
        _assert_expect(result, case.expect)
        return
    envelope = _ideal_envelope(case)
    parsed = _parse_frontier_envelope(
        json.loads(envelope), case.user_text, [], min_confidence=0.65
    )
    assert parsed is not None, f"parse failed: {case}"
    result = _run_coordinator(tmp_path, case.user_text, envelope, patch_cu=False)
    _assert_expect(result, case.expect)


@pytest.mark.parametrize("user_text", MISCLASSIFIED_SEARCH, ids=lambda t: t[:24])
def test_misclassified_chat_only_envelope_is_weak_path(tmp_path: Path, user_text: str) -> None:
    """모델이 search 질문에 chat_only envelope — 검색 없이 스트림 (잔존 리스크)."""
    bad = frontier_envelope_json(
        "정확한 정보는 웹 검색이 필요합니다.",
        needs_execution=False,
        route=_route_chat_only(),
    )
    parsed = _parse_frontier_envelope(
        json.loads(bad), user_text, [], min_confidence=0.65
    )
    assert parsed is not None  # 파서는 허용
    result = _run_coordinator(tmp_path, user_text, bad, patch_cu=False)
    assert result.delegate_frontier_stream is True
    assert not result.delegate_search


@pytest.mark.parametrize(
    "user_text,topic",
    [
        ("GPT랑 Gemini 차이", "comparison"),
        ("맥북 vs 윈도우", "comparison"),
    ],
)
def test_comparison_envelope_needs_queries_slot(
    tmp_path: Path, user_text: str, topic: str
) -> None:
    """비교 — queries 슬롯 있을 때 search 위임."""
    route = _route_search(
        user_text,
        topic=topic,
        queries=[f"{user_text} A", f"{user_text} B"],
    )
    envelope = frontier_envelope_json(
        "비교해볼게요.",
        needs_execution=True,
        route=route,
    )
    result = _run_coordinator(tmp_path, user_text, envelope, patch_cu=False)
    assert result.delegate_search is True
    meta = json.loads(result.search_meta_json or "{}")
    assert len(meta.get("queries") or []) >= 2


def test_search_without_query_slot_still_delegates(tmp_path: Path) -> None:
    """slots.query 비어 있어도 SEARCH 레인 위임 (검색어 추출은 downstream)."""
    route = _route_search("날씨", topic="weather", query="")
    route["slots"] = {"search_topic": "weather"}  # type: ignore[index]
    envelope = frontier_envelope_json(
        "확인할게요.",
        needs_execution=True,
        route=route,
    )
    result = _run_coordinator(tmp_path, "오늘 날씨", envelope, patch_cu=False)
    assert result.delegate_search is True
    assert result.search_query is None


def test_search_lane_needs_false_bypasses_chat_stream(tmp_path: Path) -> None:
    envelope = frontier_envelope_json(
        "잠시만요.",
        needs_execution=False,
        route=_route_search("서울 날씨", topic="weather"),
    )
    result = _run_coordinator(tmp_path, "서울 날씨", envelope, patch_cu=False)
    assert result.delegate_search is True
    assert not result.delegate_frontier_stream
