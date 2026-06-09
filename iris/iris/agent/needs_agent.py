"""필요 자료 조사 에이전트 (웹 리서치 래퍼)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Literal, Sequence

from iris.agent.search_providers import (
    ResearchQuality,
    ResearchTier,
    assess_research_quality,
    failure_user_message,
    is_research_failure,
    playwright_research_fallback,
    research_for_intent,
)
from iris.core.activity_sink import push_activity_line
from iris.agent.web_agent import SearchHit, extract_query_from_text
from iris.core.command_router import CommandKind

# --- P1: SEARCH 실패 시에도 LLM 답변 (failure_user_message 즉시 종료 금지) ---
SEARCH_DEGRADED_INSTRUCTION = """[검색 실패·일반 지식 보완 모드 — SEARCH DEGRADED]
웹 검색에서 검증 가능한 근거를 가져오지 못했습니다. 사용자 질문에는 반드시 답하되, 아래 규칙을 지키세요.
답변 순서:
1) 널리 알려진 일반 개념·배경·비교 축으로 2~4문장 먼저 답합니다.
   - 표현은 "일반적으로는 …", "보통 …"처럼 조심스럽게 씁니다.
2) 최신 수치·가격·출시일·순위·법적 효력·"지금 기준"·"2025/2026년" 사실은 단정하지 마세요.
3) 모르는 세부는 지어내지 말고 "확인이 필요합니다"라고 합니다.
4) 답변 마지막에 반드시 아래 한 줄을 넣습니다:
   최신 정보는 검색 불가로 검증하지 못했습니다. 중요한 결정 전에는 공식 문서나 웹 검색으로 다시 확인해 주세요.
금지:
- failure_user_message처럼 설정·API 키 안내만 하고 질문에 답하지 않기
- 검색이 안 됐다는 사실을 숨기고 최신 사실을 확신 있는 톤으로 말하기
- 마크다운·이모지·번호 목록
형식: 일반 문장만, 짧고 명확하게."""

# Gemma 출처 기반 답변 — 검색 턴 전용 (STRICT, 근거 충분 시)
SEARCH_ANSWER_INSTRUCTION = """[검색 답변 모드 — STRICT]
아래 [검색 근거]만 사용해 사용자 질문에 답합니다. 학습 데이터·기억·추측으로 사실을 채우지 마세요.
답변 형식(마크다운·이모지 금지, 일반 문장만):
1) 한두 문장으로 핵심 답변.
2) 비교 질문이면: 공통점 1문장, 차이점 2~4문장(항목별).
3) 마지막 줄: 출처: (제목 또는 도메인 1~2개)
규칙:
- [검색 근거]에 없는 사실·수치·날짜·버전·가격·인명은 쓰지 마세요.
- 근거가 서로 모순되면 확정하지 말고 "출처마다 다르게 나옵니다"라고 짧게 말하세요.
- [민감 페이지]·[API 오류] 항목은 단정하지 마세요.
- 근거가 질문과 무관하거나 비어 있으면, 추측하지 말고 다음만 출력:
  "지금은 웹에서 확인할 만한 근거를 가져오지 못했어요. 잠시 후 다시 시도하거나 검색 API 설정을 확인해 주세요."
- "출처에서 확인되지 않았습니다"만 반복하지 마세요."""

# P4: 근거는 있으나 품질 점수가 낮을 때 (부분 답변 + degrade)
SEARCH_PARTIAL_INSTRUCTION = """[검색 부분 근거 모드 — PARTIAL]
[검색 근거]가 일부만 있습니다. 아래를 지키세요.
1) 근거에 있는 내용만 확실히 말하고, 출처를 밝히세요.
2) 근거에 없는 최신 숫자·가격·순위는 쓰지 마세요.
3) 일반적으로 알려진 배경은 "일반적으로는 …"로 짧게 보완할 수 있습니다.
4) 답 끝에 한 줄: 웹 근거가 부분적이라 일부는 일반 설명입니다. 중요한 사실은 추가 검색으로 확인해 주세요.
형식: 마크다운·이모지 금지, 일반 문장만."""

HYBRID_ANSWER_INSTRUCTION = """[하이브리드 답변 모드]
우선순위:
1) [검색 근거]에 있는 내용 → 반드시 우선 사용하고, 가능하면 출처를 밝히세요.
2) [검색 근거]에 없지만 일반적으로 알려진 배경 설명 → "일반적으로는 …"로 짧게 보완 가능.
3) 최신 숫자·가격·출시일·순위·법적 효력 → 근거 없으면 쓰지 말고 "웹에서 확인하지 못했습니다"라고 하세요.
답변 형식(마크다운·이모지 금지):
1) 핵심 답변 2~4문장.
2) 검색으로 확인된 부분과, 일반 설명으로 보완한 부분을 문장 안에서 구분 (과장 금지).
3) 마지막: 출처: … (검색 근거가 있을 때만). 근거가 거의 없으면:
   "웹 근거가 부족해 일반적인 설명 위주입니다. 중요한 결정 전에는 공식 문서를 확인해 주세요."
금지:
- 검색 실패를 숨기고 확신 있는 톤으로 최신 사실을 단정하기.
- 근거 없는 비교 우열("A가 무조건 낫다") 단정."""

# P3: 비교 질문 — 근거 충분 시 고정 구조
COMPARISON_ANSWER_INSTRUCTION = """[비교 답변 모드 — COMPARISON]
아래 [검색 근거]만 사용해 답하세요. 사용자는 두 개 이상 대상(A vs B)의 차이를 묻습니다. [검색 근거]를 A측·B측으로 나누어 읽고 답하세요.
구조(번호·마크다운 없이 문장으로, 순서 유지):
1) 한 줄 요약: 두 대상이 무엇인지, 어떤 종류의 것인지.
2) 공통점: 2~3문장 (둘 다 해당하는 점).
3) 차이점: 3~5문장. 다음 축 중 근거에 있는 것만 — 모델 성향·멀티모달·생태계·용도·접근 방식·비용 모델·개발사·라이선스.
4) 사용 추천 시나리오: "~을 주로 쓰면 …, ~을 주로 쓰면 …" (근거 있을 때만, "A가 무조건 낫다" 금지).
5) 마지막 줄: 출처: (제목 또는 도메인 1~2개)
규칙:
- 한쪽 출처만 있으면 다른 쪽은 단정하지 말고 "해당 주제는 웹 근거가 부족합니다"라고 하세요.
- 근거에 없는 스펙·가격·출시일·벤치마크 수치를 채우지 마세요."""

# P3: 비교 + 검색 실패/극히 부족 — 알고 있는 범위 + 불확실성 유지
COMPARISON_DEGRADED_INSTRUCTION = """[비교 답변 모드 — COMPARISON DEGRADED]
웹 검색 근거가 없거나 매우 부족합니다. 그래도 비교 질문이므로 답을 끊지 말고, 알고 있는 범위에서 구조를 유지하세요.
구조(마크다운·이모지 금지):
1) 한 줄 요약: A와 B가 무엇인지 (일반적 정의 수준).
2) 공통점: 2~3문장 ("일반적으로는 …").
3) 차이점: 3~5문장 — 모델 성향·멀티모달·생태계·용도·접근 방식·비용 모델 등 널리 알려진 축만. 불확실하면 "확인 필요"를 붙이세요.
4) 사용 추천 시나리오: "~이면 A, ~이면 B" 형태로 조심스럽게 (우열 단정 금지).
5) 마지막에 반드시:
   최신 정보는 검색 불가로 검증하지 못했습니다. 스펙·가격·최신 기능은 공식 문서나 웹 검색으로 확인해 주세요.
금지: 근거 없이 최신 버전·가격·성능 수치·"무조건 A가 낫다" 단정."""

COMPARISON_PARTIAL_INSTRUCTION = """[비교 답변 모드 — COMPARISON PARTIAL]
[검색 근거]가 일부만 있습니다. COMPARISON 구조를 유지하되, 근거 있는 축만 확실히 말하세요.
1) 요약: 한두 문장
2) 공통점: 2~3문장 (근거 있는 범위)
3) 차이점: 3~5문장 (근거에 있는 축만). 근거 없는 축은 "이 부분은 웹 근거가 부족합니다"로 짧게 표시
4) 사용 추천: "~이면 …" 형태로 조건부 제안
5) 출처: … (있을 때만)
마지막 한 줄: 웹 근거가 부분적이라 일부는 일반 설명입니다. 중요한 사실은 추가 검색으로 확인해 주세요."""

# P4: 품질 게이트 — 컨텍스트에 삽입되는 메타 (모델이 degrade 인지)
QUALITY_GATE_GOOD = "[품질 게이트] 근거 품질: 양호 — 출처를 우선해 답하세요."
QUALITY_GATE_PARTIAL = (
    "[품질 게이트] 근거 품질: 부분 — 확실한 출처만 단정하고, 나머지는 일반 설명·불확실성을 표시하세요."
)
QUALITY_GATE_POOR = (
    "[품질 게이트] 근거 품질: 낮음 — 짧은 부분 답변 + 부족 근거 안내. 최신 사실 단정 금지."
)

CHAT_ONLY_KNOWLEDGE_INSTRUCTION = """[지식 답변 모드 — CHAT_ONLY]
웹 검색 없이 답합니다. 다음을 지키세요.
- 확실한 일반 개념·절차·조언은 답해도 됩니다.
- 구체적 수치·날짜·제품 버전·가격·순위·최신 뉴스·"지금 기준" 비교는 단정하지 마세요.
  대신 "최신 정보는 확인이 필요합니다" 또는 "일반적으로는 …"로 말하세요.
- 두 제품·모델 비교 질문은 단정적 비교를 피하고, 차이를 말할 때는 널리 알려진 축(용도·생태계·접근 방식)만 조심스럽게 설명하세요.
- 모르면 "정확히 확인하려면 웹 검색이 필요합니다"라고 말하세요. 지어내지 마세요.
답변은 짧고 명확하게, 마크다운·이모지 없이 일반 문장만."""

GEMMA_SOURCE_ONLY_INSTRUCTION = SEARCH_ANSWER_INSTRUCTION

# 다중 검색 — 쿼리 상한·HTTP 병렬 워커 수
MAX_MULTI_SEARCH_QUERIES = 3
SEARCH_PARALLEL_WORKERS = 3

AnswerMode = Literal[
    "search",
    "hybrid",
    "comparison",
    "hybrid_empty",
    "search_degraded",
    "search_partial",
    "comparison_degraded",
    "comparison_partial",
]


def research_hits(user_text: str, *, max_pages: int = 5) -> tuple[str, List[SearchHit]]:
    q = extract_query_from_text(user_text)
    hits, _ = research_for_intent(q, CommandKind.WEB_SEARCH, max_pages=max_pages)
    return q, hits


def _query_hint_for_intent(
    user_text: str,
    intent: CommandKind,
    *,
    slot_query: str | None = None,
) -> str:
    if slot_query and str(slot_query).strip():
        return str(slot_query).strip()
    stripped = user_text.strip()
    if stripped:
        return stripped
    return "Iris assistant"


def research_hits_with_intent(
    user_text: str,
    intent: CommandKind,
    *,
    max_pages: int = 5,
    slot_query: str | None = None,
) -> tuple[str, List[SearchHit]]:
    q = _query_hint_for_intent(user_text, intent, slot_query=slot_query)
    hits, _provider = research_for_intent(q, intent, max_pages=max_pages)
    return q, hits


def _build_multi_query_list(
    queries: Sequence[str],
    *,
    primary_query: str | None = None,
) -> list[str]:
    """primary + 추가 queries — 중복 제거·상한 적용."""
    run_list: list[str] = []
    if primary_query and str(primary_query).strip():
        run_list.append(str(primary_query).strip())
    for q in queries:
        s = str(q).strip()
        if s and s not in run_list:
            run_list.append(s)
    if len(run_list) > MAX_MULTI_SEARCH_QUERIES:
        dropped = run_list[MAX_MULTI_SEARCH_QUERIES :]
        run_list = run_list[:MAX_MULTI_SEARCH_QUERIES]
        push_activity_line(
            f"Search: multi-query capped at {MAX_MULTI_SEARCH_QUERIES} "
            f"(dropped {len(dropped)})."
        )
    return run_list


def _merge_search_hits(
    merged: list[SearchHit],
    seen_urls: set[str],
    hits: Sequence[SearchHit],
) -> None:
    """URL 기준 dedupe 병합."""
    for h in hits:
        url_key = (h.url or "").strip()
        if url_key and url_key in seen_urls:
            continue
        if url_key:
            seen_urls.add(url_key)
        merged.append(h)


def _fetch_http_only(query: str, intent: CommandKind, *, max_pages: int) -> list[SearchHit]:
    """서브쿼리 1건 — DuckDuckGo/Open-Meteo 등 HTTP만 (Playwright 금지)."""
    hits, _ = research_for_intent(
        query,
        intent,
        max_pages=max_pages,
        allow_playwright_fallback=False,
    )
    return hits


def _parallel_http_research(
    run_list: list[str],
    intent: CommandKind,
    *,
    max_pages: int,
) -> list[SearchHit]:
    """다중 쿼리 HTTP 수집 — Playwright 없이 병렬."""
    workers = min(SEARCH_PARALLEL_WORKERS, len(run_list))
    push_activity_line(
        f"Search: multi-query parallel HTTP fetch queries={len(run_list)} workers={workers}."
    )
    merged: list[SearchHit] = []
    seen_urls: set[str] = set()

    if workers <= 1:
        for q in run_list:
            _merge_search_hits(merged, seen_urls, _fetch_http_only(q, intent, max_pages=max_pages))
        return merged

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_http_only, q, intent, max_pages=max_pages): q for q in run_list
        }
        for fut in as_completed(futures):
            try:
                batch = fut.result()
            except Exception as exc:
                push_activity_line(f"Search: parallel sub-query failed — {exc!s}")
                continue
            _merge_search_hits(merged, seen_urls, batch)
    return merged


def _maybe_playwright_after_merge(
    merged: list[SearchHit],
    seen_urls: set[str],
    representative_query: str,
    *,
    max_pages: int,
) -> None:
    """합산 품질이 partial 이하일 때만 Playwright 1회."""
    quality = assess_research_quality(merged)
    if quality.tier == "good":
        return
    pw_hits, _ = playwright_research_fallback(
        representative_query,
        max_pages=max_pages,
        log_prefix=(
            "Search: aggregate quality below good — Playwright Google fallback (once per turn)."
        ),
    )
    _merge_search_hits(merged, seen_urls, pw_hits)


def research_hits_multi(
    user_text: str,
    intent: CommandKind,
    queries: Sequence[str],
    *,
    max_pages: int = 5,
    primary_query: str | None = None,
) -> tuple[str, List[SearchHit]]:
    run_list = _build_multi_query_list(queries, primary_query=primary_query)
    if not run_list:
        return research_hits_with_intent(user_text, intent, max_pages=max_pages)

    if len(run_list) == 1:
        q = run_list[0]
        hits, _ = research_for_intent(q, intent, max_pages=max_pages)
        return q, hits

    merged = _parallel_http_research(run_list, intent, max_pages=max_pages)
    seen_urls = {(h.url or "").strip() for h in merged if (h.url or "").strip()}
    _maybe_playwright_after_merge(
        merged,
        seen_urls,
        run_list[0],
        max_pages=max_pages,
    )

    label = " | ".join(run_list[:4])
    return label, merged


def _infer_provider_name(hits: Sequence[SearchHit]) -> str:
    labels = [h.source_label for h in hits if h.source_label]
    if not labels:
        return "unknown"
    first = labels[0]
    if all(l == first for l in labels):
        return first
    return "mixed"


def quality_gate_lines(quality: ResearchQuality | None) -> list[str]:
    """P4 — 품질 점수 메타를 Gemma 컨텍스트에 주입."""
    if quality is None:
        return []
    meta = (
        f"[품질 점수] score={quality.score} tier={quality.tier} "
        f"sources={quality.source_count} domains={quality.domain_count} "
        f"snippet_chars={quality.total_snippet_chars}"
    )
    if quality.tier == "good":
        return [meta, QUALITY_GATE_GOOD]
    if quality.tier == "partial":
        return [meta, QUALITY_GATE_PARTIAL]
    if quality.tier == "poor":
        return [meta, QUALITY_GATE_POOR]
    return [meta, quality.reason_ko or "근거 없음"]


def resolve_answer_mode(
    *,
    comparison: bool,
    hybrid: bool,
    quality: ResearchQuality,
) -> AnswerMode:
    """P1/P3/P4 — 품질 tier로 답변 프롬프트 선택."""
    tier = quality.tier

    # P4 — tier gate 기반 degrade 규칙
    if tier == "good":
        if comparison:
            return "comparison"
        return "hybrid" if hybrid else "search"

    # partial/poor: 본문은 SEARCH PARTIAL 계열로 통일 (비교/하이브리드 구조 고정 해제)
    if tier in ("partial", "poor"):
        return "search_partial"

    # failed: 레인에 따라 P1/P3-B 또는 HYBRID 본문 + 근거 없음 헤더
    if tier == "failed":
        if hybrid:
            return "hybrid_empty"
        if comparison:
            return "comparison_degraded"
        return "search_degraded"

    # 안전장치(하위 호환): 알 수 없는 tier는 가장 보수적으로 search_degraded 처리
    return "search_degraded"


def _answer_instruction_for_mode(answer_mode: AnswerMode) -> str:
    return {
        "comparison": COMPARISON_ANSWER_INSTRUCTION,
        "comparison_degraded": COMPARISON_DEGRADED_INSTRUCTION,
        "comparison_partial": COMPARISON_PARTIAL_INSTRUCTION,
        "hybrid": HYBRID_ANSWER_INSTRUCTION,
        "hybrid_empty": HYBRID_ANSWER_INSTRUCTION,
        "search_degraded": SEARCH_DEGRADED_INSTRUCTION,
        "search_partial": SEARCH_PARTIAL_INSTRUCTION,
        "search": SEARCH_ANSWER_INSTRUCTION,
    }[answer_mode]


def format_hits_for_gemma_context(
    query: str,
    hits: Sequence[SearchHit],
    *,
    intent_label: str,
    provider_name: str | None = None,
    answer_mode: AnswerMode = "search",
    quality: ResearchQuality | None = None,
) -> str:
    provider = provider_name or _infer_provider_name(hits)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    instruction = _answer_instruction_for_mode(answer_mode)
    lines = [
        f"[검색 근거 | provider={provider} | 의도={intent_label} | 질의={query} | 수집={ts}]",
        *quality_gate_lines(quality),
        instruction,
        "",
    ]
    for i, h in enumerate(hits, 1):
        snip = (h.snippet or "").strip()
        lines.append(f"--- 출처 {i} ---")
        lines.append(f"제목: {h.title}")
        if h.url:
            lines.append(f"URL: {h.url}")
        if h.date_candidate:
            lines.append(f"날짜 후보: {h.date_candidate}")
        if h.read_only_restricted:
            lines.append("상태: [민감 페이지] 본문 추출 제한")
        if h.source_label == "provider_error":
            lines.append("상태: [API 오류]")
        if snip:
            lines.append(f"요약 스니펫: {snip}")
        lines.append("")
    return "\n".join(lines).strip()


def format_search_degraded_context(
    query: str,
    *,
    intent_label: str = "",
    reason: str = "",
) -> str:
    """P1 — SEARCH lane·tier=failed·비교 아님: 일반 지식 답 + 검증 불가 한 줄."""
    _ = intent_label  # 하위 호환; 컨텍스트 헤더에는 질의만 표기
    reason_text = (reason or "").strip() or "검색 결과 없음"
    return "\n".join(
        [
            f"[검색 근거 | provider=none | 질의={query}]",
            "(웹 검색에서 검증 가능한 근거를 가져오지 못했습니다.)",
            f"사유: {reason_text}",
            "",
            SEARCH_DEGRADED_INSTRUCTION,
        ]
    ).strip()


def format_comparison_degraded_context(
    query: str,
    *,
    intent_label: str,
    reason: str = "",
) -> str:
    """P3 — 비교 질문 + 검색 실패."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    reason_line = f"사유: {reason}" if reason else "사유: 검색 결과 없음"
    return "\n".join(
        [
            f"[검색 근거 | provider=none | 의도={intent_label} | 질의={query} | 수집={ts}]",
            "(비교 질문이나 웹 근거가 부족합니다.)",
            reason_line,
            "",
            COMPARISON_DEGRADED_INSTRUCTION,
        ]
    ).strip()


def format_hybrid_without_hits(query: str, *, intent_label: str, reason: str = "") -> str:
    """HYBRID lane 검색 실패 — hybrid_empty와 동일 계열."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    reason_line = f"사유: {reason}" if reason else "사유: 검색 결과 없음"
    return "\n".join(
        [
            f"[검색 근거 | provider=none | 의도={intent_label} | 질의={query} | 수집={ts}]",
            "(웹 검색에서 유효한 근거를 가져오지 못했습니다.)",
            reason_line,
            "",
            HYBRID_ANSWER_INSTRUCTION,
        ]
    ).strip()


__all__ = [
    "SEARCH_ANSWER_INSTRUCTION",
    "SEARCH_DEGRADED_INSTRUCTION",
    "SEARCH_PARTIAL_INSTRUCTION",
    "HYBRID_ANSWER_INSTRUCTION",
    "COMPARISON_ANSWER_INSTRUCTION",
    "COMPARISON_DEGRADED_INSTRUCTION",
    "COMPARISON_PARTIAL_INSTRUCTION",
    "CHAT_ONLY_KNOWLEDGE_INSTRUCTION",
    "QUALITY_GATE_GOOD",
    "QUALITY_GATE_PARTIAL",
    "QUALITY_GATE_POOR",
    "GEMMA_SOURCE_ONLY_INSTRUCTION",
    "failure_user_message",
    "format_hits_for_gemma_context",
    "format_hybrid_without_hits",
    "format_search_degraded_context",
    "format_comparison_degraded_context",
    "assess_research_quality",
    "resolve_answer_mode",
    "quality_gate_lines",
    "is_research_failure",
    "research_hits",
    "research_hits_with_intent",
    "research_hits_multi",
]
