"""media_play_user_reply — finalize 및 폴백."""

from __future__ import annotations

from iris.assistant.computer_use_agent import USER_QUESTION_PREFIX
from iris.assistant.media_play_user_reply import (
    MediaPlayOutcome,
    build_media_reply_payload,
    finalize_media_user_message,
)


def test_build_media_reply_payload_truncates() -> None:
    d = build_media_reply_payload(
        goal="x" * 500,
        query="q" * 200,
        platform="youtube",
        action="play",
        outcome=MediaPlayOutcome.YOUTUBE_DOM_EMPTY_AFTER_POLL,
        tier_path=("a", "b"),
        metrics={"n": 3},
        log_tags=["t1"],
    )
    assert len(d["goal"]) <= 200
    assert len(d["query"]) <= 120


def test_finalize_prepends_user_question_prefix() -> None:
    out = finalize_media_user_message(
        MediaPlayOutcome.LEGACY_GATE_NO_CANDIDATES,
        "검색 결과를 읽지 못했습니다.",
        query="테스트",
    )
    assert out.startswith(USER_QUESTION_PREFIX)


def test_finalize_no_prefix_for_open_url_fail() -> None:
    body = "페이지를 열지 못했습니다."
    out = finalize_media_user_message(
        MediaPlayOutcome.OPEN_URL_FAIL,
        body,
        query="테스트",
    )
    assert not out.startswith(USER_QUESTION_PREFIX)


def test_finalize_empty_uses_fallback() -> None:
    out = finalize_media_user_message(
        MediaPlayOutcome.SUCCESS_PLAY_DOM,
        "",
        query="아이유",
    )
    assert "아이유" in out or "재생" in out or "보" in out
