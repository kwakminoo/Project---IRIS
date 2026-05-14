# Iris Code Convention

## 1. 기본 원칙

Iris는 로컬 기반 개인 AI 비서 프로젝트이다.

코드는 다음 원칙을 따른다.

1. 기능별 책임을 명확히 분리한다.
2. 한 파일에 여러 역할을 몰아넣지 않는다.
3. AI 비서, 자동화, 모니터링, UI, 저장소, 안전장치를 분리한다.
4. 모든 컴퓨터 조작은 Safety Guard와 사용자 승인 흐름을 거친다.
5. 원본 스크린샷과 전체 OCR 텍스트는 기본 저장하지 않는다.
6. 코드 주석은 중요한 로직에 한해 한국어로 작성한다.
7. 외부 API 키, 개인 경로, 민감 정보는 코드에 하드코딩하지 않는다.

---

## 2. Python 버전

Python 3.11 이상을 기준으로 한다.

---

## 3. 파일 구조 규칙

각 기능은 아래 폴더에 배치한다.

| 폴더 | 역할 |
|---|---|
| `ai/` | Gemma 4 클라이언트, 프롬프트 생성, 응답 파싱 |
| `assistant/` | 에이전트 어댑터, OpenCLO/OpenClaw 연동, Safety Guard |
| `audio/` | STT, TTS, barge-in |
| `automation/` | 앱 실행, 창 제어, 키보드·마우스 입력 |
| `modes/` | 작업 모드, 게임 모드, 창작 모드 |
| `monitoring/` | 창/탭/로그/화면 모니터링 |
| `storage/` | SQLite DB, 로그 저장 |
| `ui/` | PyQt6 UI 컴포넌트 |
| `config/` | 설정, 앱 경로, 프리셋 모드 |

---

## 4. 네이밍 규칙

### 파일명

소문자와 언더스코어를 사용한다.

좋은 예:

```python
gemma_client.py
state_detector.py
window_controller.py
action_executor.py

나쁜 예:

GemmaClient.py
stateDetector.py
window-control.py
클래스명

PascalCase를 사용한다.

class GemmaClient:
    pass

class ActionExecutor:
    pass

class MonitoringEvent:
    pass
함수명

snake_case를 사용한다.

def launch_app():
    pass

def ask_user_approval():
    pass

def detect_task_state():
    pass
상수명

대문자와 언더스코어를 사용한다.

DEFAULT_MONITOR_INTERVAL = 3
MAX_ALERT_REPEAT_COUNT = 2
5. 타입 힌트 규칙

가능한 모든 public 함수에는 타입 힌트를 작성한다.

def detect_state(text: str, target_id: str) -> DetectionResult:
    ...

반환값이 없으면 None을 명시한다.

def save_log(message: str) -> None:
    ...
6. 데이터 구조 규칙

도메인 객체는 가능하면 dataclass 또는 pydantic 모델로 정의한다.

예시:

from dataclasses import dataclass
from datetime import datetime

@dataclass
class MonitoringEvent:
    target_id: str
    category: str
    confidence: float
    reason: str
    recommended_action: str
    created_at: datetime
7. 예외 처리 규칙

외부 기능은 실패해도 앱 전체가 종료되면 안 된다.

해당 기능:

Gemma 4 연결
STT
TTS
OCR
Playwright
Chrome Extension 통신
Windows UI Automation
앱 실행
창 제어

예외 발생 시:

오류 로그 저장
사용자에게 짧게 안내
fallback 동작 수행
앱은 계속 실행

예시:

try:
    response = gemma_client.generate(prompt)
except Exception as exc:
    logger.exception("Gemma 4 응답 생성 실패")
    response = "현재 로컬 AI 연결이 불안정합니다. 기본 응답으로 처리합니다."
8. 로그 규칙

print()를 남발하지 않는다.
가능하면 logging 모듈을 사용한다.

로그 레벨:

레벨	용도
DEBUG	개발 중 상세 정보
INFO	정상 실행 기록
WARNING	복구 가능한 문제
ERROR	기능 실패
CRITICAL	앱 유지가 어려운 문제
9. UI 코드 규칙

PyQt6 UI 파일에는 비즈니스 로직을 많이 넣지 않는다.

좋은 구조:

ui/main_window.py
→ 화면 구성, 버튼 연결

core/command_router.py
→ 명령 분류

automation/action_executor.py
→ 실제 실행

storage/database.py
→ 기록 저장

UI 스레드에서 오래 걸리는 작업을 직접 실행하지 않는다.

오래 걸리는 작업:

STT
TTS
OCR
LLM 호출
Playwright 검색
모니터링 루프

이런 작업은 별도 worker/thread 구조로 분리한다.

10. 안전 규칙

컴퓨터 조작 함수는 반드시 승인 여부를 확인한다.

나쁜 예:

def type_text(text: str):
    pyautogui.write(text)

좋은 예:

def type_text(text: str, approved: bool):
    if not approved:
        raise PermissionError("사용자 승인 없이 키보드 입력을 실행할 수 없습니다.")
    pyautogui.write(text)

다음 작업은 기본 차단한다.

파일 삭제
결제
비밀번호 입력
개인정보 제출
시스템 설정 변경
위험한 쉘 명령
사용자 승인 없는 키보드·마우스 조작
11. 모니터링 코드 규칙

모니터링은 대상별 수집기와 판단기를 분리한다.

좋은 구조:

terminal_log_collector.py
desktop_window_monitor.py
browser_tab_monitor.py
ocr_engine.py
state_detector.py
alert_generator.py

수집기는 데이터를 모으기만 한다.
판단은 state_detector.py에서 한다.
알림 문장은 alert_generator.py에서 만든다.

12. 개인정보 보호 규칙

기본값:

STORE_SCREENSHOTS=false
STORE_RAW_OCR_TEXT=false

저장 가능한 것:

이벤트 카테고리
신뢰도
요약된 이유
추천 조치
대상 이름
발생 시간

저장하지 않는 것:

원본 스크린샷
전체 OCR 텍스트
브라우저 페이지 전체 내용
비밀번호
결제 정보
개인정보 입력 내용
13. Commit Message 규칙

커밋 메시지는 다음 형식을 사용한다.

type: message

타입:

타입	의미
feat	새로운 기능
fix	버그 수정
docs	문서 수정
refactor	구조 개선
test	테스트 추가
chore	설정/기타
style	포맷팅
safety	안전장치 관련 수정

예시:

feat: add Gemma local client
feat: implement work mode dialog
safety: block unapproved keyboard input
docs: add domain design document
14. 테스트 기준

기능 구현 후 최소한 다음을 확인한다.

python -m compileall iris -q
python -m iris

추후 테스트 코드가 추가되면 다음도 실행한다.

pytest
15. 금지사항

다음은 금지한다.

프로젝트명을 Iris가 아닌 다른 이름으로 변경
Claude/Gemini API를 기본 모델로 설정
사용자 승인 없는 컴퓨터 조작
한 파일에 모든 기능을 몰아넣기
원본 스크린샷 기본 저장
전체 OCR 텍스트 기본 저장
개인 경로 하드코딩
API 키 하드코딩
UI 코드에 LLM 호출 로직 직접 작성
모니터링 코드에 실행 조작 직접 작성