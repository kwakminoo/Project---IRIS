"""코딩 응답에서 '파일 생성/수정 제안'을 추출한다.

젬마(LLM) 응답 텍스트를 파싱해 (파일 경로, 내용, 언어) 목록으로 만든다.
순수 로직 — 사이드 이펙트 없음. 실제 파일 쓰기는 automation 계층이 담당한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 코드펜스 블록: ```info\n...본문...```
_FENCE_RE = re.compile(r"```(?P<info>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)

# 확장자를 가진 상대 경로 후보 (예: hello.py, src/app.ts)
_FILENAME_RE = re.compile(r"(?P<name>[\w\-./]+\.[A-Za-z0-9]+)")

# 파일명을 명시하는 라벨 라인 (예: 파일: hello.py, File: main.py)
_LABEL_RE = re.compile(
    r"(?:파일명|파일|filename|file)\s*[:：]?\s*[`*\"']?"
    r"(?P<name>[\w\-./]+\.[A-Za-z0-9]+)",
    re.IGNORECASE,
)

# 코드 첫 줄 주석의 파일명 (# hello.py, // app.js, /* a.c */, <!-- x.html -->)
_COMMENT_NAME_RE = re.compile(
    r"^\s*(?:#|//|/\*|<!--)\s*(?P<name>[\w\-./]+\.[A-Za-z0-9]+)"
)


@dataclass
class CodeProposal:
    """생성/수정할 파일 제안."""

    path: str  # 워크스페이스 기준 상대 경로
    content: str  # 파일 내용
    language: str = ""  # 코드펜스 언어 표기 (선택)


def parse_code_proposals(reply: str) -> list[CodeProposal]:
    """응답에서 파일 제안 목록을 추출한다. 파일명을 못 찾은 블록은 건너뛴다."""
    if not reply:
        return []
    proposals: list[CodeProposal] = []
    for match in _FENCE_RE.finditer(reply):
        info = (match.group("info") or "").strip()
        body = match.group("body")
        if not body.strip():
            continue
        language, name = _parse_info(info)
        if not name:
            name = _name_from_preceding_text(reply, match.start())
        if not name:
            name = _name_from_first_comment(body)
        name = _clean_name(name)
        if not _looks_like_path(name):
            continue
        proposals.append(CodeProposal(path=name, content=body, language=language))
    return proposals


def _parse_info(info: str) -> tuple[str, str]:
    """코드펜스 info 문자열에서 (언어, 파일명)을 추출한다."""
    language = ""
    name = ""
    # 공백/콜론/등호로 토큰 분리 (```python title=hello.py, ```python:hello.py 등)
    for raw in re.split(r"[\s:=]+", info):
        tok = raw.strip().strip("\"'`")
        if not tok or tok.lower() == "title":
            continue
        if _looks_like_path(tok):
            name = name or tok
        elif not language and re.fullmatch(r"[A-Za-z0-9+#.\-]+", tok):
            language = tok
    return language, name


def _name_from_preceding_text(reply: str, fence_start: int) -> str:
    """코드블록 바로 앞 텍스트에서 파일명 힌트를 찾는다.

    ponytail: 근처 100자 창만 본다. 문장 속 예시 파일명 오탐 여지가 있어
    라벨(`파일:`) 우선, 없으면 마지막 파일명 토큰을 쓴다.
    """
    window = reply[max(0, fence_start - 100) : fence_start]
    label = None
    for label in _LABEL_RE.finditer(window):
        pass
    if label:
        return label.group("name")
    last = None
    for last in _FILENAME_RE.finditer(window):
        pass
    return last.group("name") if last else ""


def _name_from_first_comment(body: str) -> str:
    """코드 첫 비어있지 않은 줄의 주석에서 파일명을 찾는다."""
    for line in body.splitlines():
        if not line.strip():
            continue
        m = _COMMENT_NAME_RE.match(line)
        return m.group("name") if m else ""
    return ""


def _clean_name(name: str) -> str:
    return (name or "").strip().strip("`*\"'").replace("\\", "/").lstrip("./").strip()


def _looks_like_path(name: str) -> bool:
    """확장자를 가진 안전해 보이는 상대 경로인지 대략 검사한다."""
    name = (name or "").strip()
    if not name or name.startswith("/") or name.startswith("\\"):
        return False
    if ".." in name:
        return False
    return bool(re.search(r"\.[A-Za-z0-9]+$", name))
