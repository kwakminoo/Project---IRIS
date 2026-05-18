"""web_agent 리서치 헬퍼 단위 테스트 (Playwright 없이)."""

from iris.agent.needs_agent import GEMMA_SOURCE_ONLY_INSTRUCTION, format_hits_for_gemma_context
from iris.agent.web_agent import (
    SearchHit,
    build_body_snippet,
    extract_date_candidate,
    is_sensitive_url,
)


def test_is_sensitive_url_login() -> None:
    assert is_sensitive_url("https://example.com/login")
    assert is_sensitive_url("https://shop.com/checkout/pay")
    assert not is_sensitive_url("https://news.example.com/article/1")


def test_extract_date_candidate() -> None:
    meta = {"article:published_time": "2026-05-01T12:00:00Z"}
    assert extract_date_candidate("", meta) == "2026-05-01T12:00:00Z"
    text = "기사 본문 2026년 5월 10일 발행"
    assert "2026" in extract_date_candidate(text, None)


def test_build_body_snippet() -> None:
    paras = ["짧음", "이것은 충분히 긴 본문 단락입니다. " * 5, "또 다른 단락입니다. " * 4]
    snip = build_body_snippet(paras, max_chars=200)
    assert len(snip) <= 210
    assert "본문" in snip or "단락" in snip


def test_format_hits_for_gemma_no_speculation_instruction() -> None:
    hits = [
        SearchHit(
            title="테스트 기사",
            url="https://example.com/a",
            snippet="본문 요약 텍스트",
            date_candidate="2026-05-01",
        )
    ]
    ctx = format_hits_for_gemma_context("테스트", hits, intent_label="WEB_SEARCH")
    assert "추측" in ctx or "출처" in ctx
    assert GEMMA_SOURCE_ONLY_INSTRUCTION.split()[0] in ctx
    assert "example.com" in ctx
    assert "2026-05-01" in ctx


def test_format_hits_sensitive_flag() -> None:
    hits = [
        SearchHit(
            title="로그인",
            url="https://x.com/login",
            snippet="[민감 페이지]",
            read_only_restricted=True,
        )
    ]
    ctx = format_hits_for_gemma_context("q", hits, intent_label="WEB_SEARCH")
    assert "민감" in ctx
