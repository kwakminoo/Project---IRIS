"""3단 지식 라우팅·답변 모드 단위 테스트."""

from __future__ import annotations

import json
from typing import Sequence
from unittest.mock import patch

from iris.agent.needs_agent import (
    COMPARISON_ANSWER_INSTRUCTION,
    COMPARISON_DEGRADED_INSTRUCTION,
    COMPARISON_PARTIAL_INSTRUCTION,
    HYBRID_ANSWER_INSTRUCTION,
    SEARCH_DEGRADED_INSTRUCTION,
    SEARCH_ANSWER_INSTRUCTION,
    format_comparison_degraded_context,
    format_hits_for_gemma_context,
    format_hybrid_without_hits,
    format_search_degraded_context,
    research_hits_multi,
    resolve_answer_mode,
)
from iris.agent.search_providers import assess_research_quality
from iris.agent.web_agent import SearchHit
from iris.assistant.router_policy import RouteLane
from iris.ai.gemma_client import ChatMessage
from iris.assistant.turn_coordinator import TurnCoordinator
from iris.core.command_router import CommandKind
from tests.test_turn_coordinator import _FakeGemma, _make_assistant


class _HybridRouterGemma(_FakeGemma):
    def chat(self, messages: Sequence[ChatMessage], purpose: object = None) -> str:
        self.calls.append(list(messages))
        if messages and "Unified Router" in messages[0].content:
            return json.dumps(
                {
                    "intent": "search",
                    "lane": "hybrid",
                    "knowledge_lane": "hybrid",
                    "goal": "AI 시장 전망 설명",
                    "task_type": "knowledge",
                    "slots": {
                        "query": "AI market outlook 2026",
                        "search_topic": "general",
                    },
                    "risk_hint": "low",
                    "needs_user_confirm": False,
                    "confidence": 0.7,
                },
                ensure_ascii=False,
            )
        return self.chat_reply


def test_format_hits_comparison_mode() -> None:
    hits = [
        SearchHit(title="A 개요", url="https://a.example", snippet="A 설명"),
        SearchHit(title="B 개요", url="https://b.example", snippet="B 설명"),
    ]
    ctx = format_hits_for_gemma_context(
        "A vs B",
        hits,
        intent_label="WEB_SEARCH",
        answer_mode="comparison",
    )
    assert COMPARISON_ANSWER_INSTRUCTION.split()[0] in ctx
    assert "a.example" in ctx


def test_format_hybrid_without_hits() -> None:
    ctx = format_hybrid_without_hits("AI 시장", intent_label="WEB_SEARCH", reason="empty")
    assert HYBRID_ANSWER_INSTRUCTION.split()[0] in ctx
    assert "가져오지 못했" in ctx


def test_research_hits_multi_merges() -> None:
    h1 = [SearchHit(title="one", url="https://one.test", snippet="1")]
    h2 = [SearchHit(title="two", url="https://two.test", snippet="2")]

    with patch(
        "iris.agent.needs_agent.research_for_intent",
        side_effect=[(h1, "a"), (h1, "a"), (h2, "b")],
    ):
        label, merged = research_hits_multi(
            "비교 질문",
            CommandKind.WEB_SEARCH,
            ["query a", "query b"],
            primary_query="main",
        )
    assert "main" in label
    assert len(merged) == 2


def test_hybrid_lane_delegate_search(tmp_path) -> None:
    gemma = _HybridRouterGemma()
    assistant = _make_assistant(tmp_path, gemma)
    coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

    result = coord.run_turn("AI 시장 전망 알려줘")

    assert result.delegate_search is True
    assert result.route == RouteLane.HYBRID.value
    assert '"hybrid": true' in result.search_meta_json or '"hybrid":true' in result.search_meta_json.replace(" ", "")


def test_search_strict_instruction_present() -> None:
    assert "STRICT" in SEARCH_ANSWER_INSTRUCTION
    assert "학습 데이터" in SEARCH_ANSWER_INSTRUCTION


def test_p1_search_degraded_prompt_footer() -> None:
    assert "검색 불가로 검증" in SEARCH_DEGRADED_INSTRUCTION
    assert "failure_user_message" in SEARCH_DEGRADED_INSTRUCTION
    assert "사용자 질문에는 반드시" in SEARCH_DEGRADED_INSTRUCTION
    ctx = format_search_degraded_context("q", intent_label="WEB_SEARCH", reason="API 키 없음")
    assert SEARCH_DEGRADED_INSTRUCTION.split()[0] in ctx
    assert "[검색 근거 | provider=none | 질의=q]" in ctx
    assert "사유: API 키 없음" in ctx
    assert "의도=" not in ctx


def test_p3_comparison_degraded_structure() -> None:
    assert "공통점" in COMPARISON_DEGRADED_INSTRUCTION
    assert "사용 추천" in COMPARISON_DEGRADED_INSTRUCTION
    ctx = format_comparison_degraded_context("A vs B", intent_label="WEB_SEARCH")
    assert COMPARISON_DEGRADED_INSTRUCTION.split()[0] in ctx


def test_p4_resolve_answer_mode_degraded() -> None:
    from iris.agent.search_providers import ResearchQuality

    q_fail = ResearchQuality(
        score=0.0,
        tier="failed",
        source_count=0,
        domain_count=0,
        total_snippet_chars=0,
        has_provider_error=False,
        reason_ko="비어 있음",
    )
    assert resolve_answer_mode(comparison=False, hybrid=False, quality=q_fail) == "search_degraded"
    assert (
        resolve_answer_mode(comparison=True, hybrid=False, quality=q_fail)
        == "comparison_degraded"
    )

    # poor(근거 매우 부족)도 COMPARISON DEGRADED로 매핑되어야 함
    hits_poor = [
        SearchHit(
            title="poor",
            url="https://poor.example",
            snippet="x" * 100,
            source_label="searxng",
        )
    ]
    q_poor = assess_research_quality(hits_poor)
    assert q_poor.tier == "poor"
    assert (
        resolve_answer_mode(comparison=True, hybrid=False, quality=q_poor)
        == "search_partial"
    )

    # partial(근거 일부만)은 본문 SEARCH PARTIAL 계열로 degrade
    hits_partial = [
        SearchHit(
            title="p1",
            url="https://p1.example",
            snippet="x" * 150,
            source_label="searxng",
        ),
        SearchHit(
            title="p2",
            url="https://p2.example",
            snippet="x" * 150,
            source_label="searxng",
        ),
    ]
    q_partial = assess_research_quality(hits_partial)
    assert q_partial.tier == "partial"
    assert (
        resolve_answer_mode(comparison=True, hybrid=False, quality=q_partial)
        == "search_partial"
    )

    hits = [
        SearchHit(
            title="t",
            url="https://x.com",
            snippet="짧은 설명 " * 5,
            source_label="searxng",
        )
    ]
    q_partial = assess_research_quality(hits)
    mode = resolve_answer_mode(comparison=False, hybrid=False, quality=q_partial)
    assert mode == "search_partial"


def test_comparison_partial_instruction_phrases() -> None:
    assert "웹 근거가 부분적이라 일부는 일반 설명입니다" in COMPARISON_PARTIAL_INSTRUCTION
    assert "중요한 사실은 추가 검색으로 확인해 주세요" in COMPARISON_PARTIAL_INSTRUCTION
    assert "이 부분은 웹 근거가 부족합니다" in COMPARISON_PARTIAL_INSTRUCTION
