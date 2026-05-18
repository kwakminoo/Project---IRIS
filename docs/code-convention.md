# Iris Code Convention / Iris 코드 컨벤션

## 1. Basic Principles / 기본 원칙

Iris is a local-first personal AI assistant.

- 한국어 설명: Iris는 로컬 우선 개인 AI 비서입니다.

Code must follow these principles:

1. Separate responsibilities by feature.
   - 한국어: 기능별 책임을 분리합니다.
2. Do not put unrelated roles into one file.
   - 한국어: 관련 없는 역할을 한 파일에 넣지 않습니다.
3. Keep AI assistant, automation, monitoring, UI, storage, and safety layers separated.
   - 한국어: AI 비서, 자동화, 모니터링, UI, 저장소, 안전 계층을 분리합니다.
4. Use risk-based permission control.
   - 한국어: 위험도 기반 권한 제어를 사용합니다.
5. Do not store raw screenshots or full OCR text by default.
   - 한국어: 원본 스크린샷과 전체 OCR 텍스트는 기본 저장하지 않습니다.
6. Write Korean comments for important logic.
   - 한국어: 중요한 로직에는 한국어 주석을 작성합니다.
7. Do not hardcode API keys, personal paths, or sensitive information.
   - 한국어: API 키, 개인 경로, 민감 정보를 하드코딩하지 않습니다.

---

## 2. Python Version / Python 버전

Use Python 3.11 or newer.

- 한국어 설명: Python 3.11 이상을 기준으로 합니다.

---

## 3. File Structure / 파일 구조

| Folder / 폴더 | Role / 역할 |
|---|---|
| `ai/` | Gemma 4 client, prompt builder, response parser / Gemma 4 클라이언트, 프롬프트, 응답 파싱 |
| `assistant/` | Agent adapter, orchestrator, safety connection / 에이전트 어댑터, 오케스트레이터, 안전 연결 |
| `audio/` | STT, TTS, barge-in, microphone selection / STT, TTS, 끼어들기, 마이크 선택 |
| `automation/` | App launch, window control, keyboard/mouse input / 앱 실행, 창 제어, 키보드·마우스 입력 |
| `modes/` | Work, game, creative modes / 작업, 게임, 창작 모드 |
| `monitoring/` | Window/tab/log/screen monitoring / 창, 탭, 로그, 화면 모니터링 |
| `storage/` | SQLite database and logs / SQLite DB와 로그 |
| `ui/` | PyQt6 UI components / PyQt6 UI 컴포넌트 |
| `config/` | Settings, app paths, mode presets / 설정, 앱 경로, 모드 프리셋 |

---

## 4. Naming / 네이밍

Files, functions, and variables use `snake_case`.

- 한국어: 파일, 함수, 변수는 `snake_case`를 사용합니다.

Classes use `PascalCase`.

- 한국어: 클래스는 `PascalCase`를 사용합니다.

Constants use `UPPER_SNAKE_CASE`.

- 한국어: 상수는 `UPPER_SNAKE_CASE`를 사용합니다.

Examples:

```python
gemma_client.py
state_detector.py

class GemmaClient:
    pass

def launch_app() -> None:
    pass

DEFAULT_MONITOR_INTERVAL = 3
```

---

## 5. Type Hints / 타입 힌트

Public functions should use type hints.

- 한국어: public 함수에는 가능한 타입 힌트를 작성합니다.

```python
def detect_state(text: str, target_id: str) -> DetectionResult:
    ...

def save_log(message: str) -> None:
    ...
```

---

## 6. Exception Handling / 예외 처리

Optional or external features must not crash the whole app.

- 한국어: 선택 기능이나 외부 연동 실패가 앱 전체 종료로 이어지면 안 됩니다.

Examples:

- Gemma 4 connection / Gemma 4 연결
- STT / 음성 인식
- TTS / 음성 출력
- OCR / 화면 문자 인식
- Playwright / 웹 검색
- Chrome Extension communication / Chrome 확장 통신
- Windows UI Automation / Windows UI 자동화
- App launch / 앱 실행
- Window control / 창 제어

Required behavior:

- Log the error / 오류 로그 저장
- Tell the user briefly / 사용자에게 짧게 안내
- Use fallback behavior / 폴백 수행
- Keep the app running / 앱은 계속 실행

---

## 7. UI Rules / UI 규칙

Do not put heavy business logic in PyQt6 UI files.

- 한국어: PyQt6 UI 파일에 무거운 비즈니스 로직을 넣지 않습니다.

Good structure:

```text
ui/main_window.py          → screen layout and signal wiring / 화면 구성과 시그널 연결
core/command_router.py     → command classification / 명령 분류
automation/action_executor.py → execution / 실제 실행
storage/database.py        → persistence / 저장
```

Long-running work must run in a worker or thread.

- 한국어: 오래 걸리는 작업은 worker/thread로 분리합니다.

Examples:

- STT
- TTS
- OCR
- LLM call
- Playwright search
- Monitoring loop

---

## 8. Safety Rules / 안전 규칙

All computer actions must be classified by risk.

- 한국어: 모든 컴퓨터 조작은 위험도 분류를 거칩니다.

Current permission rule:

- LOW_RISK, MEDIUM_RISK, HIGH_RISK: auto-allowed.
  - 한국어: 1~3단계는 자동 실행 가능.
- CRITICAL_RISK: explicit approval required.
  - 한국어: 4단계는 명시적 승인 필요.

Bad example:

```python
def run_shell(command: str) -> None:
    subprocess.run(command, shell=True)
```

Good example:

```python
def run_shell(command: str, approved: bool) -> None:
    # 한국어 주석: 셸 명령은 4단계 위험 작업이므로 승인 없이 실행하지 않는다.
    if not approved:
        raise PermissionError("셸 명령은 사용자 승인이 필요합니다.")
    subprocess.run(command, shell=True)
```

Approval required:

- Shell commands / 셸 명령
- File deletion / 파일 삭제
- Payment / 결제
- Password input / 비밀번호 입력
- Personal information submission / 개인정보 제출
- System setting changes / 시스템 설정 변경
- Sensitive browser actions / 민감 브라우저 조작

---

## 9. Monitoring Rules / 모니터링 규칙

Collectors collect data; detectors classify state.

- 한국어: 수집기는 데이터만 모으고, 판단은 감지기가 담당합니다.

Good structure:

```text
terminal_log_collector.py
desktop_window_monitor.py
browser_tab_monitor.py
ocr_engine.py
state_detector.py
alert_generator.py
```

Monitoring must not store raw screenshots or full OCR text by default.

- 한국어: 모니터링은 원본 스크린샷이나 전체 OCR 텍스트를 기본 저장하지 않습니다.

---

## 10. Privacy Rules / 개인정보 보호 규칙

Default values:

```env
STORE_SCREENSHOTS=false
STORE_RAW_OCR_TEXT=false
```

Allowed storage:

- Event category / 이벤트 분류
- Confidence / 신뢰도
- Summarized reason / 요약 이유
- Recommended action / 추천 조치
- Target name / 대상 이름
- Timestamp / 발생 시간

Do not store:

- Raw screenshots / 원본 스크린샷
- Full OCR text / 전체 OCR 텍스트
- Full browser page text / 브라우저 전체 내용
- Passwords / 비밀번호
- Payment information / 결제 정보
- Personal information input / 개인정보 입력 내용

---

## 11. Commit Message Rules / 커밋 메시지 규칙

Format:

```text
type: message
```

Types:

| Type / 타입 | Meaning / 의미 |
|---|---|
| feat | New feature / 새 기능 |
| fix | Bug fix / 버그 수정 |
| docs | Documentation / 문서 |
| refactor | Refactor / 구조 개선 |
| test | Test / 테스트 |
| chore | Chore / 기타 작업 |
| style | Formatting / 포맷 |
| safety | Safety guard / 안전장치 |

---

## 12. Testing / 테스트

After implementation, run:

```bash
python -m compileall iris -q
python -m pytest -q
```

The app should run with:

```bash
python -m iris
```

---

## 13. Forbidden / 금지사항

- Rename Iris to another project name.
  - 한국어: Iris가 아닌 다른 프로젝트명으로 바꾸지 않습니다.
- Make Claude/Gemini API the default model.
  - 한국어: Claude/Gemini API를 기본 모델로 설정하지 않습니다.
- Execute CRITICAL_RISK actions without approval.
  - 한국어: 4단계 위험 작업을 승인 없이 실행하지 않습니다.
- Put all features in one file.
  - 한국어: 모든 기능을 한 파일에 넣지 않습니다.
- Store raw screenshots by default.
  - 한국어: 원본 스크린샷을 기본 저장하지 않습니다.
- Store full OCR text by default.
  - 한국어: 전체 OCR 텍스트를 기본 저장하지 않습니다.
- Hardcode personal paths.
  - 한국어: 개인 경로를 하드코딩하지 않습니다.
- Hardcode API keys.
  - 한국어: API 키를 하드코딩하지 않습니다.
- Put LLM call logic directly into UI code.
  - 한국어: UI 코드에 LLM 호출 로직을 직접 넣지 않습니다.
- Put execution control directly into monitoring collectors.
  - 한국어: 모니터링 수집기에 실행 조작을 직접 넣지 않습니다.
