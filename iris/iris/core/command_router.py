"""사용자 입력 명령 유형 분류 (Intent Router / Tool Layer 공용)."""

from __future__ import annotations

import re
from enum import Enum, auto


class CommandKind(Enum):
    GENERAL_CHAT = auto()
    APP_LAUNCH = auto()
    WINDOW_CONTROL = auto()
    FILE_TASK = auto()
    WEB_SEARCH = auto()
    WORK_MODE = auto()
    GAME_MODE = auto()
    CREATIVE_MODE = auto()
    MONITORING_STATUS = auto()
    GET_SYSTEM_INFO = auto()
    OPEN_URL = auto()
    COMPUTER_ACTION = auto()
    COMPUTER_USE = auto()
    COMPLEX_AUTOMATION = auto()
    # --- Tool layer: 주제·최신 정보 검색 → 웹 에이전트 후 Gemma 요약 ---
    CURRENT_INFO_SEARCH = auto()
    MOVIE_SEARCH = auto()
    NEWS_SEARCH = auto()
    WEATHER_SEARCH = auto()


_WORK_PATTERNS = re.compile(
    r"(작업\s*시작|일해야|개발\s*시작|일\s*할게|작업\s*할게|업무\s*시작)",
    re.IGNORECASE,
)
_GAME_PATTERNS = re.compile(
    r"(게임할래|게임\s*할래|롤|배그|게임\s*시작|게임\s*켜)",
    re.IGNORECASE,
)
_CREATIVE_PATTERNS = re.compile(
    r"(이미지\s*작업|영상\s*편집|디자인\s*작업|창작)",
    re.IGNORECASE,
)
_WEB_PATTERNS = re.compile(
    r"(검색해줘|자료\s*찾아|요약해줘|보고서로\s*정리|웹\s*검색)",
    re.IGNORECASE,
)
_MONITOR_PATTERNS = re.compile(r"(모니터링|상태\s*확인|지금\s*뭐\s*해)", re.IGNORECASE)
_ALERT_PATTERNS = re.compile(r"(알림|경고)", re.IGNORECASE)
_TERMINAL_STATUS = re.compile(
    r"(터미널|콘솔|cmd|powershell|프롬프트).*(멈|멈춤|안\s*돌|응답\s*없|확인|어떤지|살아|봐줘|봐)",
    re.IGNORECASE,
)
_MOVIE_PATTERNS = re.compile(
    r"(영화|개봉작|상영작|박스오피스|극장가|스크린).*(뭐|추천|알려|있어|보여|해줘|궁금|볼만)|"
    r"요즘.*영화|영화.*(요즘|뭐\s*있|추천|볼만|상영)",
    re.IGNORECASE,
)
_NEWS_PATTERNS = re.compile(
    r"(뉴스|헤드라인|속보).*(뭐|알려|줘|해줘|정리)|오늘\s*뉴스|최신\s*뉴스",
    re.IGNORECASE,
)
_WEATHER_PATTERNS = re.compile(
    r"(날씨|기온|미세먼지|초미세|강수|황사|폭우|폭설|체감온도)",
    re.IGNORECASE,
)
_CURRENT_INFO_PATTERNS = re.compile(
    r"(최신|실시간).*(정보|소식|동향|이슈)|요즘\s*세계|요즘\s*무슨\s*일|"
    r"지금\s*세계|최근\s*이슈|요즘\s*뭐가\s*이슈",
    re.IGNORECASE,
)
_DANGER_COMPUTER = re.compile(
    r"(마우스\s*클릭|키보드|쉘\s*실행|rm\s+-rf|포맷|레지스트리\s*삭제)",
    re.IGNORECASE,
)
_LAUNCH = re.compile(r"(실행해줘|켜줘|열어줘|launch|open\s+app)", re.IGNORECASE)
_FILE_TASK = re.compile(
    r"(파일\s*찾아|문서\s*찾아|파일\s*검색|제안서|\.pptx|\.docx|\.pdf).*(찾아|검색|열어)|"
    r"(찾아줘|검색해).*(파일|문서|제안서)",
    re.IGNORECASE,
)
_COMPLEX_AUTO = re.compile(
    r"(자동으로\s*해|매크로|복잡한\s*작업|스크립트로\s*해|전부\s*한번에)",
    re.IGNORECASE,
)
# 복합·멀티 스텝 → Computer Use 루프 (단일 사양 조회는 GET_SYSTEM_INFO)
_COMPUTER_USE_MULTI = re.compile(
    r"(.+)(열고|켜고|하고\s*나서|한\s*다음|이어서)(.+)",
    re.IGNORECASE,
)
_GET_SYSTEM_INFO_PATTERN = re.compile(
    r"(사양|스펙|CPU|RAM|메모리|GPU|그래픽|그래픽카드|디스크|저장\s*공간|운영체제|\bOS\b)"
    r".*(알려|어떻게|몇|얼마|뭐야|확인|보여|조회|돼)|"
    r"(지금\s*)?(내\s*)?(컴퓨터|PC|시스템).*(사양|스펙|성능|상태|어떻게)|"
    r"(사양|스펙)\s*(이|가)?\s*(뭐|어떻게|야|지)",
    re.IGNORECASE,
)
_URL_IN_TEXT = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_OPEN_URL_VERB = re.compile(
    r"(열|켜|launch|open|보여|틀|재생|접속|들려|url|링크|주소|이동)",
    re.IGNORECASE,
)
_YOUTUBE_OPEN_HINT = re.compile(
    r"(유튜브|youtube|yt).*(틀|재생|열|켜|보|들)|"
    r"(틀|재생|열|켜).*(유튜브|youtube)",
    re.IGNORECASE,
)


def classify_command(text: str) -> CommandKind:
    """간단 휴리스틱 분류 (한국어 우선). 순서가 의도 정확도에 중요함."""
    t = text.strip()
    if not t:
        return CommandKind.GENERAL_CHAT

    if _WORK_PATTERNS.search(t):
        return CommandKind.WORK_MODE
    if _GAME_PATTERNS.search(t):
        return CommandKind.GAME_MODE
    if _CREATIVE_PATTERNS.search(t):
        return CommandKind.CREATIVE_MODE

    if _FILE_TASK.search(t):
        return CommandKind.FILE_TASK

    if _URL_IN_TEXT.search(t) and (_OPEN_URL_VERB.search(t) or _YOUTUBE_OPEN_HINT.search(t)):
        return CommandKind.OPEN_URL

    if _COMPUTER_USE_MULTI.search(t):
        return CommandKind.COMPUTER_USE

    if _GET_SYSTEM_INFO_PATTERN.search(t):
        return CommandKind.GET_SYSTEM_INFO

    if _COMPLEX_AUTO.search(t):
        return CommandKind.COMPLEX_AUTOMATION

    # 터미널/프로세스 상태 → 모니터링 (Manager·대시보드와 연계)
    if _TERMINAL_STATUS.search(t):
        return CommandKind.MONITORING_STATUS

    if _MOVIE_PATTERNS.search(t):
        return CommandKind.MOVIE_SEARCH
    if _NEWS_PATTERNS.search(t):
        return CommandKind.NEWS_SEARCH
    if _WEATHER_PATTERNS.search(t):
        return CommandKind.WEATHER_SEARCH
    if _CURRENT_INFO_PATTERNS.search(t):
        return CommandKind.CURRENT_INFO_SEARCH

    if _WEB_PATTERNS.search(t):
        return CommandKind.WEB_SEARCH
    if _MONITOR_PATTERNS.search(t):
        return CommandKind.MONITORING_STATUS
    if _ALERT_PATTERNS.search(t):
        return CommandKind.MONITORING_STATUS

    if _DANGER_COMPUTER.search(t):
        return CommandKind.COMPUTER_ACTION
    if _LAUNCH.search(t):
        return CommandKind.APP_LAUNCH

    if "창" in t and ("포커스" in t or "이동" in t or "크기" in t or "배치" in t):
        return CommandKind.WINDOW_CONTROL

    return CommandKind.GENERAL_CHAT
