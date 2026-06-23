# AGENTS.md

## Project Name / 프로젝트 이름

Iris

- 한국어 설명: 이 프로젝트의 이름은 항상 Iris입니다.
- 금지: DEXTER 또는 다른 이름으로 바꾸지 않습니다.

## Project Definition / 프로젝트 정의

Iris is a local-first **execution assistant** for Windows — not a chat-only bot.

- 한국어 설명: Iris는 Windows에서 동작하는 로컬 우선 **실행형** AI 비서입니다.
- 핵심 방향: 사용자 PC 상태를 **인식(Perception)**하고, 도구로 **조작(Action)**하며, 결과를 **검증(Verify)**하는 Jarvis형 비서입니다.
- 기본 실행 경로: 단일 턴 답변이 아니라 **multi-step agent loop** (인식 → 행동 → 검증 → 재계획).

Core concept:

> Iris does not only execute what the user commands. Iris watches the user's workflow, detects missed or stalled tasks, and helps continue them — through a Perception → Action → Verify loop on the user's PC.

- 한국어 설명: Iris는 사용자가 말한 것만 처리하는 도구가 아니라, 작업 흐름을 관찰하고 멈춘 작업을 찾아 **Computer Use 루프**로 이어가도록 돕는 비서입니다.

### Iris Differentiators / Iris만의 차별

These capabilities always run alongside Computer Use:

- Voice dialogue + barge-in / 음성 대화 + 말 끊기
- Hybrid monitoring (terminal, IDE, Chrome extension, OCR) → proactive suggestions / 하이브리드 모니터링 → 선제 제안
- SQLite logs and task session memory / SQLite 로그·작업 세션 기억
- Work, game, creative multi-turn modes / 작업·게임·창작 멀티턴 모드

### 4-Tier Execution Model / 4계층 실행 모델

| Tier | Name | Role |
|------|------|------|
| **1** | Dedicated tools | Fast deterministic: `get_system_info`, `launch_app`, `open_url`, `focus_window`, … |
| **2** | Universal GUI (Computer Use) | UIA/OCR/VLM + keyboard/mouse/window — app-agnostic, no per-app adapter required |
| **3** | Verify loop | Re-perceive UI/screen after each step; judge success/failure; replan (prefer shortcuts) |
| **4** | External agents (optional) | OpenClaw, Hermes — Iris orchestrator delegates only on **failure or long-tail** tasks |

- OpenClaw and Hermes are **Tier 4 fallbacks**, not the Jarvis body. Iris remains the central orchestrator.
- See `docs/architecture.md` and `docs/domain-design.md` for Perception / Action / Verify definitions.

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
15. Default path is multi-step Computer Use (Perception → Action → Verify), not single-turn chat.
    - 한국어: 기본 경로는 단일 턴 대화가 아니라 multi-step Computer Use 루프입니다.
16. Orchestrator may call Tier 1–2 automation tools sequentially; legacy "block direct manipulation tools" policy is deprecated.
    - 한국어: 오케스트레이터가 1~2계층 자동화 도구를 순차 호출합니다. 직접 조작 도구 금지 정책은 폐지 방향입니다.
17. OpenClaw/Hermes are optional Tier 4 fallbacks only when Iris loop fails or task is long-tail.
    - 한국어: OpenClaw/Hermes는 Iris 루프 실패·장기 꼬리 작업에만 선택 위임합니다.

## Permission Levels / 권한 단계

Computer Use agent loops and CRITICAL_RISK approval **coexist**: LOW/MEDIUM/HIGH tools run inside the loop; CRITICAL tools pause for explicit approval.

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

### Phase 1.5: Computer Use Agent / 1.5단계: Computer Use 에이전트

- Multi-step agent loop (Perception → Action → Verify) as default execution path / multi-step 루프 기본 경로
- `ComputerUseAgent` or extended `AgentOrchestrator` / Computer Use 오케스트레이션
- Tier 1 dedicated tools + Tier 2 universal GUI / 전용 도구 + 범용 GUI
- Tier 3 verify loop with replan / 검증 루프·재계획
- Tier 4 OpenClaw/Hermes fallback on failure / 실패 시 외부 에이전트 위임
- Unblock `action_plan.BLOCKED_TOOLS`, expand `ALLOWED_TOOLS` (Phase A code) / 도구 허용 목록 확장
- See `docs/implementation-plan.md#phase-15-computer-use-agent` for Phase A/B/C/D checklist

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

## Ponytail Development Mode / Ponytail 개발 모드

Use Ponytail for Iris development.

- English: Apply Ponytail's "lazy senior developer" rule to every Iris change: build the smallest correct implementation that satisfies the request.
- 한국어: Iris 개발에는 Ponytail의 "효율적인 시니어 개발자" 규칙을 적용합니다. 요청을 만족하는 가장 작은 올바른 구현을 우선합니다.
- English: Prefer no code, then Python standard library, then native Windows/platform features, then already-installed dependencies, before adding new code or dependencies.
- 한국어: 새 코드를 쓰기 전에 무구현, Python 표준 라이브러리, Windows/플랫폼 기본 기능, 기존 의존성 순서로 먼저 검토합니다.
- English: Do not add abstractions, frameworks, adapters, or broad refactors unless they are explicitly requested or clearly reduce real complexity in the current Iris architecture.
- 한국어: 명시 요청이 없거나 현재 Iris 구조의 실제 복잡도를 줄이지 않는다면 추상화, 프레임워크, 어댑터, 대규모 리팩터링을 추가하지 않습니다.
- English: Prefer deleting or simplifying code over adding code, while keeping Iris modules small and responsibilities separated.
- 한국어: 코드를 추가하기보다 삭제와 단순화를 우선하되, Iris 모듈 분리와 책임 분리는 유지합니다.
- English: Ponytail never overrides Iris safety rules, risk-based permission control, local-first design, privacy constraints, logging requirements, or fallback behavior.
- 한국어: Ponytail은 Iris의 안전 규칙, 위험도 기반 권한 제어, 로컬 우선 설계, 개인정보 보호 제약, 로그 요구사항, 폴백 동작보다 우선하지 않습니다.
- English: Mark intentional simplifications with a `ponytail:` comment when there is a known ceiling or future upgrade path.
- 한국어: 의도적인 단순화에 한계나 향후 확장 경로가 있으면 `ponytail:` 주석으로 표시합니다.
- English: Non-trivial logic should keep one small runnable check; use the existing Iris test commands before considering the work done.
- 한국어: 사소하지 않은 로직에는 작은 실행 가능 검증을 남기고, 완료 전 기존 Iris 테스트 명령을 사용합니다.

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
