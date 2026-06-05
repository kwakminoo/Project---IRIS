"""Unified LLM Router 단위 테스트 (FakeGemma)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

from iris.ai.gemma_client import FALLBACK_KO, ChatMessage
from iris.assistant.router_policy import RouteLane, resolve_route_lane
from iris.assistant.unified_router import (
    UNIFIED_ROUTER_SYSTEM,
    parse_unified_route_json,
    route_user_turn,
)
from iris.config.app_index import resolve_app_candidates_for_llm
from iris.core.command_router import CommandKind, legacy_classify_command
from iris.core.context_manager import DialogueContext


class _FakeGemma:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[Sequence[ChatMessage]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: object) -> str:
        self.calls.append(list(messages))
        return self.reply


def _assistant_with_steam(tmp_path: Path) -> SimpleNamespace:
    steam_exe = tmp_path / "steam.exe"
    steam_exe.write_bytes(b"x")
    return SimpleNamespace(
        _app_paths={"steam": str(steam_exe)},
        _db=None,
    )


def test_parse_launch_app_steam() -> None:
    raw = {
        "intent": "launch_app",
        "lane": "direct_action",
        "goal": "Steam 실행",
        "task_type": "open_app",
        "slots": {"app_key": "steam", "display_name": "Steam"},
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.9,
    }
    payload = parse_unified_route_json(raw, "스팀 실행해달라")
    assert payload is not None
    assert payload.intent == "launch_app"
    assert payload.lane is RouteLane.DIRECT_ACTION


def test_route_steam_launch_not_search(tmp_path: Path) -> None:
    catalog = [{"app_key": "steam", "display_name": "Steam"}]
    gemma = _FakeGemma(
        '{"intent":"launch_app","lane":"direct_action","goal":"Steam 실행",'
        '"task_type":"open_app","slots":{"app_key":"steam","display_name":"Steam"},'
        '"risk_hint":"low","needs_user_confirm":false,"confidence":0.95}'
    )
    routed = route_user_turn(
        "스팀 실행해달라",
        DialogueContext(),
        gemma,  # type: ignore[arg-type]
        assistant=_assistant_with_steam(tmp_path),
        app_catalog=catalog,
    )
    assert routed.lane is RouteLane.DIRECT_ACTION
    assert routed.kind is CommandKind.APP_LAUNCH
    assert routed.slots.get("app_key") == "steam"
    assert routed.lane is not RouteLane.SEARCH
    assert routed.lane is not RouteLane.COMPUTER_USE


def test_route_movie_search() -> None:
    gemma = _FakeGemma(
        '{"intent":"search","lane":"search","goal":"최신 영화 정보",'
        '"task_type":"unknown","slots":{"query":"요즘 영화","search_topic":"movie"},'
        '"risk_hint":"low","needs_user_confirm":false,"confidence":0.8}'
    )
    routed = route_user_turn("요즘 영화 뭐 있어", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.SEARCH
    assert routed.kind is CommandKind.MOVIE_SEARCH


def test_route_chat_only() -> None:
    gemma = _FakeGemma(
        '{"intent":"chat","lane":"chat_only","goal":"인사",'
        '"task_type":"unknown","slots":{},"risk_hint":"low",'
        '"needs_user_confirm":false,"confidence":0.9}'
    )
    routed = route_user_turn("안녕", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.CHAT_ONLY


def test_route_computer_use_kakao() -> None:
    gemma = _FakeGemma(
        '{"intent":"computer_use","lane":"computer_use",'
        '"goal":"카톡을 열고 철수에게 안녕 보내기",'
        '"task_type":"multi_step","slots":{"app_hint":"kakaotalk"},'
        '"risk_hint":"medium","needs_user_confirm":false,"confidence":0.85}'
    )
    routed = route_user_turn(
        "카톡 열고 철수에게 안녕 보내", DialogueContext(), gemma  # type: ignore[arg-type]
    )
    assert routed.lane is RouteLane.COMPUTER_USE


def test_fallback_on_llm_unavailable() -> None:
    gemma = _FakeGemma(FALLBACK_KO)
    text = "스팀 켜줘"
    routed = route_user_turn(text, DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.CHAT_ONLY
    assert routed.kind is CommandKind.GENERAL_CHAT


def test_steam_legacy_classify_after_launch_pattern_fix() -> None:
    assert legacy_classify_command("스팀 실행해달라") is CommandKind.APP_LAUNCH


def test_resolve_app_candidates_includes_steam_alias(tmp_path: Path) -> None:
    steam_exe = tmp_path / "steam.exe"
    steam_exe.write_bytes(b"x")
    catalog = resolve_app_candidates_for_llm(
        "스팀 실행해달라",
        {"steam": str(steam_exe)},
        top_k=8,
    )
    keys = [c["app_key"] for c in catalog]
    assert "steam" in keys


def test_unified_router_system_prompt() -> None:
    gemma = _FakeGemma(
        '{"intent":"chat","lane":"chat_only","goal":"x","task_type":"unknown",'
        '"slots":{},"risk_hint":"low","needs_user_confirm":false,"confidence":1}'
    )
    route_user_turn("안녕", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert gemma.calls[0][0].content == UNIFIED_ROUTER_SYSTEM


def test_unified_router_system_includes_media_slots_rules() -> None:
    assert "media_action" in UNIFIED_ROUTER_SYSTEM
    assert "platform_hint" in UNIFIED_ROUTER_SYSTEM
    assert "search_query" in UNIFIED_ROUTER_SYSTEM


def test_unified_router_system_knowledge_lane() -> None:
    assert "knowledge_lane" in UNIFIED_ROUTER_SYSTEM
    assert "hybrid" in UNIFIED_ROUTER_SYSTEM
    assert "slots.queries" in UNIFIED_ROUTER_SYSTEM or "queries" in UNIFIED_ROUTER_SYSTEM


def test_parse_knowledge_lane_syncs_lane() -> None:
    raw = {
        "intent": "search",
        "lane": "chat_only",
        "knowledge_lane": "search",
        "goal": "GPT와 Gemini 차이",
        "task_type": "knowledge",
        "slots": {
            "query": "GPT vs Gemini",
            "queries": ["OpenAI GPT", "Google Gemini"],
            "search_topic": "comparison",
            "answer_shape": "comparison",
        },
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.88,
    }
    payload = parse_unified_route_json(raw, "GPT랑 Gemini 차이")
    assert payload is not None
    assert payload.lane is RouteLane.SEARCH
    assert payload.knowledge_lane == "search"
    assert payload.slots.get("queries")


def test_parse_media_play_youtube() -> None:
    raw = {
        "intent": "computer_use",
        "lane": "computer_use",
        "goal": "유튜브에서 치챗 영상을 재생한다",
        "task_type": "media_play",
        "slots": {
            "platform_hint": "youtube",
            "media_action": "play",
            "search_query": "치챗",
            "user_request_summary": "유튜브에서 치챗 틀어줘",
        },
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.92,
    }
    payload = parse_unified_route_json(raw, "유튜브에서 치챗 틀어줘")
    assert payload is not None
    assert payload.task_type == "media_play"
    assert payload.slots["platform_hint"] == "youtube"
    assert payload.slots["media_action"] == "play"
    assert payload.slots["search_query"] == "치챗"


def test_parse_media_search_only() -> None:
    raw = {
        "intent": "computer_use",
        "lane": "computer_use",
        "goal": "유튜브에서 아이유 검색 결과를 연다",
        "task_type": "media_play",
        "slots": {
            "platform_hint": "youtube",
            "media_action": "search",
            "search_query": "아이유",
        },
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.88,
    }
    payload = parse_unified_route_json(raw, "유튜브에서 아이유 검색해줘")
    assert payload is not None
    assert payload.slots["media_action"] == "search"
    assert payload.slots["search_query"] == "아이유"


def test_route_media_play_passes_slots_to_cu() -> None:
    gemma = _FakeGemma(
        '{"intent":"computer_use","lane":"computer_use",'
        '"goal":"유튜브에서 치챗 영상을 재생한다","task_type":"media_play",'
        '"slots":{"platform_hint":"youtube","media_action":"play",'
        '"search_query":"치챗","user_request_summary":"유튜브에서 치챗 틀어줘"},'
        '"risk_hint":"low","needs_user_confirm":false,"confidence":0.9}'
    )
    routed = route_user_turn("유튜브에서 치챗 틀어줘", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.COMPUTER_USE
    assert routed.task_type == "media_play"
    assert routed.slots.get("media_action") == "play"
    assert routed.slots.get("search_query") == "치챗"
    assert routed.slots.get("platform_hint") == "youtube"


def test_route_media_search_spotify() -> None:
    gemma = _FakeGemma(
        '{"intent":"computer_use","lane":"computer_use",'
        '"goal":"스포티파이에서 뉴진스 검색 결과를 연다","task_type":"media_play",'
        '"slots":{"platform_hint":"spotify","media_action":"search",'
        '"search_query":"뉴진스"},'
        '"risk_hint":"low","needs_user_confirm":false,"confidence":0.85}'
    )
    routed = route_user_turn("스포티파이에서 뉴진스 찾아줘", DialogueContext(), gemma)  # type: ignore[arg-type]
    assert routed.lane is RouteLane.COMPUTER_USE
    assert routed.slots.get("platform_hint") == "spotify"
    assert routed.slots.get("media_action") == "search"
    assert routed.slots.get("search_query") == "뉴진스"


def test_parse_invalid_platform_hint_becomes_unknown() -> None:
    raw = {
        "intent": "computer_use",
        "lane": "computer_use",
        "goal": "브라우저에서 재생",
        "task_type": "media_play",
        "slots": {
            "platform_hint": "tidal",
            "media_action": "play",
            "search_query": "jazz",
        },
        "risk_hint": "low",
        "needs_user_confirm": False,
        "confidence": 0.7,
    }
    payload = parse_unified_route_json(raw, "재생해줘")
    assert payload is not None
    assert payload.slots["platform_hint"] == "unknown"
