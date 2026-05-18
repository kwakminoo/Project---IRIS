# AGENTS.md

## Project Name / 프로젝트 이름

Iris

- 한국어 설명: 이 프로젝트의 이름은 항상 Iris입니다.
- 금지: DEXTER 또는 다른 이름으로 바꾸지 않습니다.

## Project Definition / 프로젝트 정의

Iris is a local-first personal AI assistant for Windows.

- 한국어 설명: Iris는 Windows에서 동작하는 로컬 우선 개인 AI 비서입니다.
- 핵심 방향: 챗봇이 아니라 Jarvis처럼 대화, 앱 실행, 창 정리, 웹 검색, 보고서 생성, 작업 모니터링을 도와주는 비서입니다.

Core concept:

> Iris does not only execute what the user commands. Iris watches the user's workflow, detects missed or stalled tasks, and helps continue them.

- 한국어 설명: Iris는 사용자가 말한 것만 처리하는 도구가 아니라, 작업 흐름을 관찰하고 멈춘 작업이나 놓친 작업을 찾아 이어가도록 돕는 비서입니다.

## Core Principles / 핵심 원칙

1. The project name must always be Iris.
   - 한국어: 프로젝트 이름은 항상 Iris입니다.
2. Do not use DEXTER as a project name.
   - 한국어: DEXTER라는 이름을 사용하지 않습니다.
3. Use Gemma 4 local LLM as the primary model direction.
   - 한국어: 기본 모델 방향은 Gemma 4 로컬 LLM입니다.
4. Do not use Claude or Gemini API as the default model.
   - 한국어: Claude/Gemini API를 기본 모델로 쓰지 않습니다.
5. Claude/Gemini may only be optional fallback or testing tools if explicitly requested.
   - 한국어: Claude/Gemini는 사용자가 명시적으로 요청한 경우에만 테스트/폴백 용도로 사용할 수 있습니다.
6. Iris uses risk-based permission control.
   - 한국어: Iris는 위험도 기반 권한 정책을 사용합니다.
7. LOW_RISK, MEDIUM_RISK, and HIGH_RISK actions may run without extra approval.
   - 한국어: 1~3단계 위험도 작업은 추가 승인 없이 실행할 수 있습니다.
8. CRITICAL_RISK actions always require explicit user approval.
   - 한국어: 4단계 위험도 작업은 반드시 사용자 승인이 필요합니다.
9. Dangerous actions may still be blocked even when approved.
   - 한국어: 승인해도 위험 패턴은 차단될 수 있습니다.
10. Do not store raw screenshots by default.
    - 한국어: 원본 스크린샷은 기본 저장하지 않습니다.
11. Do not store full OCR text by default.
    - 한국어: 전체 OCR 텍스트는 기본 저장하지 않습니다.
12. Store only summarized events, logs, and action records.
    - 한국어: 요약 이벤트, 로그, 실행 기록만 저장합니다.
13. Keep AI assistant features and monitoring features separated by modules.
    - 한국어: AI 비서 기능과 모니터링 기능은 모듈을 분리합니다.
14. Build the system in phases. Do not implement everything in one file.
    - 한국어: 단계적으로 만들고, 한 파일에 모든 기능을 몰아넣지 않습니다.

## Permission Levels / 권한 단계

### Auto-Allowed: LOW_RISK / 자동 허용 1단계

- Read visible app/window state.
  - 한국어: 보이는 앱/창 상태 읽기.
- Web search and public page reading.
  - 한국어: 웹 검색과 공개 페이지 읽기.
- Current screen OCR summary without storing raw text.
  - 한국어: 원문 저장 없이 현재 화면 OCR 요약.

### Auto-Allowed: MEDIUM_RISK / 자동 허용 2단계

- Launch applications.
  - 한국어: 앱 실행.
- Open public URLs.
  - 한국어: 공개 URL 열기.
- Focus, move, and resize windows.
  - 한국어: 창 포커스, 이동, 크기 조정.
- File search and read-only exploration.
  - 한국어: 파일 검색과 읽기 전용 탐색.

### Auto-Allowed: HIGH_RISK / 자동 허용 3단계

- Keyboard input for non-sensitive workflows.
  - 한국어: 민감하지 않은 작업에서 키보드 입력.
- Mouse clicks for non-sensitive workflows.
  - 한국어: 민감하지 않은 작업에서 마우스 클릭.
- Multi-step automation that does not include critical actions.
  - 한국어: 4단계 위험 작업을 포함하지 않는 다단계 자동화.
- Work, game, and creative presets after Iris has enough information.
  - 한국어: 필요한 정보를 받은 뒤 작업/게임/창작 프리셋 실행.

### Approval Required: CRITICAL_RISK / 승인 필요 4단계

- Shell command execution.
  - 한국어: 셸 명령 실행.
- File deletion, destructive move, overwrite, or mass modification.
  - 한국어: 파일 삭제, 파괴적 이동, 덮어쓰기, 대량 변경.
- Payment, purchase, transfer, or financial confirmation.
  - 한국어: 결제, 구매, 송금, 금융 확인.
- Password input or authentication secret submission.
  - 한국어: 비밀번호나 인증 비밀값 입력.
- Personal information submission.
  - 한국어: 개인정보 제출.
- System setting changes, security settings, registry, firewall, permissions.
  - 한국어: 시스템 설정, 보안 설정, 레지스트리, 방화벽, 권한 변경.
- Browser actions involving login, payment, private forms, account settings, or sensitive data.
  - 한국어: 로그인, 결제, 비공개 폼, 계정 설정, 민감 정보가 있는 브라우저 조작.

## Main Features / 주요 기능

### Phase 1: Jarvis-like AI Assistant / 1단계: 자비스형 AI 비서

- Text chat / 텍스트 대화
- Voice input / 음성 입력
- Voice response / 음성 응답
- Barge-in while Iris is speaking / Iris가 말하는 중 끼어들기
- Gemma 4 local LLM connection / Gemma 4 로컬 LLM 연결
- Fallback response when local LLM is unavailable / 로컬 LLM 불가 시 폴백 응답
- App launching / 앱 실행
- Window focusing and arrangement / 창 포커스와 배치
- Work, game, creative modes / 작업, 게임, 창작 모드
- Web search through Playwright / Playwright 기반 웹 검색
- Report window / 보고서 창
- Recent work suggestion / 최근 작업 제안
- Risk-based computer control / 위험도 기반 컴퓨터 제어
- Safety guard / 안전장치
- SQLite logs / SQLite 로그

### Phase 2: Hybrid Monitoring / 2단계: 하이브리드 모니터링

- Terminal command stdout/stderr monitoring / 터미널 stdout/stderr 모니터링
- Existing terminal window monitoring using UI Automation and OCR / 기존 터미널 창 UI Automation/OCR 모니터링
- Cursor / VS Code window monitoring / Cursor 또는 VS Code 창 모니터링
- Chrome tab monitoring through Chrome Extension / Chrome 확장 기반 탭 모니터링
- Current screen OCR / 현재 화면 OCR
- Windows Event Log as supporting source / Windows 이벤트 로그 보조 수집
- VLM adapter for future visual understanding / 향후 시각 이해용 VLM 어댑터
- Event detection / 이벤트 감지
- Alert generation / 알림 생성
- Notification panel / 알림 패널
- User-approved action for CRITICAL_RISK alerts / 4단계 위험 알림은 사용자 승인 후 조치

## Recommended Tech Stack / 권장 기술 스택

- Python 3.11+
- PyQt6
- SQLite
- Gemma 4 local LLM
- Ollama or LM Studio compatible local API
- faster-whisper or whisper for STT
- pyttsx3 or edge-tts for TTS
- Playwright for web agent
- pywinauto
- pygetwindow
- pyautogui
- pywin32
- psutil
- pytesseract or easyocr
- Chrome Extension Manifest V3
- Optional future VLM: SmolVLM2 or similar lightweight model

한국어 설명: 위 기술은 Iris를 로컬 우선으로 만들기 위한 권장 스택입니다.

## Safety Rules / 안전 규칙

The following actions require explicit approval or may be blocked:

- 한국어: 아래 작업은 명시적 승인 필요 또는 차단 대상입니다.

- Shell commands.
  - 한국어: 셸 명령.
- File deletion or destructive file operations.
  - 한국어: 파일 삭제 또는 파괴적 파일 작업.
- Payment or purchase.
  - 한국어: 결제 또는 구매.
- Password input.
  - 한국어: 비밀번호 입력.
- Personal information submission.
  - 한국어: 개인정보 제출.
- System setting changes.
  - 한국어: 시스템 설정 변경.
- Sensitive browser actions involving login, payment, private forms, or account settings.
  - 한국어: 로그인, 결제, 비공개 폼, 계정 설정 관련 브라우저 조작.

## Coding Rules / 코딩 규칙

- Keep modules small.
  - 한국어: 모듈은 작게 유지합니다.
- Use clear responsibility separation.
  - 한국어: 책임을 명확히 분리합니다.
- Add Korean comments for important logic.
  - 한국어: 중요한 로직에는 한국어 주석을 작성합니다.
- Use type hints where practical.
  - 한국어: 가능한 곳에 타입 힌트를 사용합니다.
- Avoid hardcoding personal paths.
  - 한국어: 개인 경로를 하드코딩하지 않습니다.
- Put app paths in `config/app_paths.py`.
  - 한국어: 앱 경로는 `config/app_paths.py`에 둡니다.
- Put mode presets in `config/preset_modes.py`.
  - 한국어: 모드 프리셋은 `config/preset_modes.py`에 둡니다.
- Store logs in SQLite.
  - 한국어: 로그는 SQLite에 저장합니다.
- Add fallback behavior for optional components.
  - 한국어: 선택 기능에는 폴백을 둡니다.
- Never make the app crash just because STT, TTS, OCR, or LLM is unavailable.
  - 한국어: STT, TTS, OCR, LLM이 없어도 앱이 종료되면 안 됩니다.

## Code Convention / 코드 컨벤션

All code must follow `docs/code-convention.md`.

- 한국어: 모든 코드는 `docs/code-convention.md`를 따릅니다.

Important rules:

- Use Python 3.11+.
  - 한국어: Python 3.11 이상을 사용합니다.
- Use snake_case for files, functions, and variables.
  - 한국어: 파일, 함수, 변수는 snake_case를 사용합니다.
- Use PascalCase for classes.
  - 한국어: 클래스는 PascalCase를 사용합니다.
- Use type hints for public functions.
  - 한국어: public 함수에는 타입 힌트를 사용합니다.
- Keep UI, AI, automation, monitoring, storage, and safety layers separated.
  - 한국어: UI, AI, 자동화, 모니터링, 저장소, 안전 계층을 분리합니다.
- Do not put multiple unrelated responsibilities in one file.
  - 한국어: 관련 없는 여러 책임을 한 파일에 넣지 않습니다.
- Use risk-based permission control.
  - 한국어: 위험도 기반 권한 제어를 사용합니다.
- Do not store raw screenshots or full OCR text by default.
  - 한국어: 원본 스크린샷이나 전체 OCR 텍스트는 기본 저장하지 않습니다.
- Use Korean comments for important logic.
  - 한국어: 중요한 로직은 한국어 주석으로 설명합니다.

## Testing Rule / 테스트 규칙

Before considering an implementation complete, check:

```bash
python -m compileall iris -q
python -m pytest -q
```

The app should run with:

```bash
python -m iris
```

## Definition of Done / 완료 기준

A feature is done when:

- It runs without crashing.
  - 한국어: 앱이 크래시 없이 동작합니다.
- It has fallback behavior.
  - 한국어: 폴백 동작이 있습니다.
- It follows the risk-based permission policy.
  - 한국어: 위험도 기반 권한 정책을 따릅니다.
- It logs important events.
  - 한국어: 중요한 이벤트를 로그로 남깁니다.
- It does not break existing assistant features.
  - 한국어: 기존 비서 기능을 깨지 않습니다.
- It follows the local-first design.
  - 한국어: 로컬 우선 설계를 따릅니다.
