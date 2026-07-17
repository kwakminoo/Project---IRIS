"""코딩 패널 전용 프롬프트 조립 (AI 계층).

일반 어시스턴트 라우팅과 분리해, 코딩에 집중한 system 프롬프트를 만든다.
파서(iris.assistant.code_proposal)가 인식하는 형식(`파일: 경로` + 코드블록)을
모델이 따르도록 유도한다.
"""

from __future__ import annotations

from iris.ai.gemma_client import ChatMessage

_SYSTEM = (
    "당신은 Iris의 코딩 어시스턴트입니다. 사용자의 요청에 맞는 코드를 작성합니다.\n"
    "새 파일을 만들거나 기존 파일을 수정해야 하면 반드시 다음 형식으로 답하세요:\n"
    "1) 먼저 `파일: <워크스페이스 기준 상대경로>` 를 한 줄로 밝힙니다.\n"
    "2) 이어서 언어 표시가 있는 하나의 코드블록에 파일 전체 내용을 담습니다.\n"
    "예:\n"
    "파일: hello.py\n"
    "```python\n"
    "print('hello')\n"
    "```\n"
    "파일이 필요 없는 질문이면 코드블록 없이 간단히 설명하세요.\n"
    "로컬 우선 원칙에 따라 한국어로 간결하게 답합니다."
)


def build_coding_messages(user_text: str, context_block: str = "") -> list[ChatMessage]:
    """코딩 요청을 system + user 메시지로 만든다.

    IDE 컨텍스트(열린 파일·선택 영역)가 있으면 user 메시지에 덧붙인다.
    """
    content = (user_text or "").strip()
    block = (context_block or "").strip()
    if block:
        content = f"{content}\n\n{block}"
    return [
        ChatMessage(role="system", content=_SYSTEM),
        ChatMessage(role="user", content=content),
    ]
