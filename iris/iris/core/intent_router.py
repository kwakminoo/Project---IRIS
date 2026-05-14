"""Intent Router — 사용자 입력을 Tool Layer용 의도로 분류 (로컬 Gemma 호출 전 단계).

일반 대화는 Gemma가 처리하고, 최신 정보·주제별 질문은 웹 검색 도구를 거친 뒤
검색 스니펫을 Gemma에게 넘겨 요약하게 한다.
"""

from __future__ import annotations

from iris.core.command_router import CommandKind, classify_command


def route_user_intent(text: str) -> CommandKind:
    """사용자 원문을 `CommandKind`로 분류한다."""
    return classify_command(text)
