# Iris Architecture / Iris 아키텍처

## 1. System Overview / 시스템 개요

Iris is a local-first **execution assistant** — not a chat-only bot.

- 한국어 설명: Iris는 로컬 우선 **실행형** AI 비서입니다. 대화만 하는 챗봇이 아니라 PC 상태를 인식하고, 도구로 조작하고, 결과를 검증합니다.

Three major capabilities:

1. **Computer Use agent** — multi-step Perception → Action → Verify loop (default execution path).
   - 한국어: Computer Use 에이전트 — 인식·행동·검증 multi-step 루프(기본 실행 경로).
2. **Jarvis-like personal assistant** — voice, modes, web search, reports.
   - 한국어: 자비스형 개인 비서 — 음성, 모드, 웹 검색, 보고서.
3. **Hybrid multi-target workflow monitoring** — proactive suggestions from terminal, IDE, Chrome, OCR.
   - 한국어: 하이브리드 작업 모니터링 — 선제 제안.

### Iris-only differentiators (always parallel)

- Voice dialogue + barge-in
- Hybrid monitoring → proactive alerts
- SQLite logs and `task_sessions` memory
- Work / game / creative multi-turn modes

---

## 1.1 Four-Tier Execution Model / 4계층 실행 모델

```text
User goal
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Iris Orchestrator (ComputerUseAgent / AgentOrchestrator)   │
│                                                             │
│  Tier 1 — Dedicated tools     launch_app, open_url, …       │
│  Tier 2 — Universal GUI       UIA / OCR / VLM + input       │
│  Tier 3 — Verify loop         re-perceive → pass/fail       │
│  Tier 4 — External (optional) OpenClaw, Hermes on failure   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Safety Guard (CRITICAL_RISK approval inside loop)
```

| Tier | Layer | Responsibility |
|------|-------|----------------|
| **1** | `automation/` tool registry | Deterministic tools: `get_system_info`, `launch_app`, `open_url`, `focus_window`, … |
| **2** | Computer Use (UIA/OCR/VLM) | App-agnostic GUI: keyboard, mouse, window — no per-app adapter required |
| **3** | Verify loop | After each step: UI/screen re-perception; success/failure; replan (shortcuts preferred) |
| **4** | `assistant/` adapters | OpenClaw, Hermes — delegate only on Iris loop **failure** or **long-tail** tasks |

- **OpenClaw** and **Hermes** are optional Tier 4 fallbacks, not the Jarvis body.
- Legacy policy: `assistant/orchestrator.py` blocking direct manipulation tools in JSON plans → **deprecated**. Target: orchestrator **sequentially invokes** Tier 1–2 tools inside the agent loop. Code: unblock `action_plan.BLOCKED_TOOLS`, expand `ALLOWED_TOOLS` (see implementation plan Phase A).

### Perception / Action / Verify (PAV)

| Phase | Module paths | Output |
|-------|--------------|--------|
| **Perception** | `monitoring/`, `automation/` window readers | Active window, `list_open_windows`, UIA snapshot summary, OCR/VLM scene summary (no raw screenshot/full OCR storage by default) |
| **Action** | `automation/tool_registry.py` | `AutomationToolRegistry`: `launch_app`, `focus_window`, `type_text`, `click`, `run_shell`, `open_url`, … |
| **Verify** | Same as Perception + planner | Compare observation to goal; retry or alternate path in-loop |

---

## 1.2 Safety Guard + Computer Use Loop / 안전장치와 Computer Use 공존

- LOW_RISK, MEDIUM_RISK, HIGH_RISK actions may execute **inside** the agent loop without extra approval.
- CRITICAL_RISK actions (`run_shell`, file deletion, payment, password, system settings, sensitive browser) **pause the loop** until explicit user approval.
- Dangerous patterns may be blocked even when approved.
- 한국어: Computer Use 루프와 CRITICAL 승인은 공존합니다. 1~3단계는 루프 내 자동 실행, 4단계는 승인 후 재개합니다.

---

## 2. Layered Architecture / 계층 구조

```text
Iris
├── UI Layer              # 한국어: 화면과 사용자 입력
├── Assistant Layer       # 한국어: 대화 흐름과 에이전트 오케스트레이션
├── AI Layer              # 한국어: Gemma 4 로컬 LLM 연결
├── Audio Layer           # 한국어: STT, TTS, barge-in, 마이크 선택
├── Automation Layer      # 한국어: 앱 실행, 창 제어, 입력, 도구 실행
├── Mode Layer            # 한국어: 작업/게임/창작 모드
├── Monitoring Layer      # 한국어: 창, 탭, 터미널, 화면 상태 감지
├── Safety Layer          # 한국어: 위험도 분류와 차단
└── Storage Layer         # 한국어: SQLite 로그와 설정 기록
```

---

## 3. UI Layer / UI 계층

Path: `iris/ui/`

Responsibilities:

- Main window / 메인 창
- Chat panel / 채팅 패널
- Visualizer / 시각화
- Settings dialog / 설정 창
- Monitoring dashboard / 모니터링 대시보드
- Notification panel / 알림 패널
- Report window / 보고서 창

---

## 4. AI Layer / AI 계층

Path: `iris/ai/`

Responsibilities:

- Gemma 4 local LLM connection / Gemma 4 로컬 LLM 연결
- Prompt building / 프롬프트 조립
- Response parsing / 응답 파싱
- Fallback response / 폴백 응답

Primary model:

- Gemma 4 local / Gemma 4 로컬 모델

Optional:

- Other APIs only if explicitly requested / 다른 API는 사용자가 명시적으로 요청한 경우에만 선택 사용

---

## 5. Assistant Layer / 비서 계층

Path: `iris/assistant/`

Responsibilities:

- **ComputerUseAgent** (`iris/assistant/computer_use_agent.py`) — Tier 1–2 + Verify(A) 기본 경로: Gemma 한 스텝 JSON → `AutomationToolRegistry.run()` → observation → `step_complete` / `step_failed`
- **AgentOrchestrator** — 메타 도구만 (`safety_check`, `intent_route`, `assistant_dispatch`, `gemma_finalize`); PC 조작은 Computer Use로 위임
- `IrisAssistant.run_computer_use_loop()` — 텍스트·음성 공용 진입 API
- **TurnCoordinator** `RouteLane.COMPUTER_USE` — `CommandKind.COMPUTER_USE`, `COMPLEX_AUTOMATION` 전용 ( `APP_LAUNCH`는 `DIRECT_ACTION` 유지)
- Tool planning and sequential Tier 1–2 tool invocation / 도구 계획·순차 호출
- **Tier 4 adapters**: OpenClaw, Hermes (failure / long-tail delegation only)
- Safety guard connection / 안전장치 연결 (CRITICAL pause inside loop)
- Memory manager connection / 기억 시스템 연결

Orchestrator policy (target state):

- Deprecated: forbid direct manipulation tools in `action_plan` JSON.
- Target: `ComputerUseAgent` / `AgentOrchestrator` calls `AutomationToolRegistry` tools step-by-step with Verify between steps.
- Implementation: Phase A in `docs/implementation-plan.md` — `BLOCKED_TOOLS` removal, `ALLOWED_TOOLS` expansion.

---

## 6. Automation Layer / 자동화 계층

Path: `iris/automation/`

Responsibilities:

- App launching / 앱 실행
- Window focusing / 창 포커스
- Window arrangement / 창 배치
- Keyboard input / 키보드 입력
- Mouse clicking / 마우스 클릭
- Action execution / 액션 실행
- ToolRegistry risk handling / 도구 레지스트리 위험도 처리

Rule:

- LOW_RISK, MEDIUM_RISK, and HIGH_RISK actions may run without extra approval.
  - 한국어: 1~3단계 작업은 추가 승인 없이 실행할 수 있습니다.
- CRITICAL_RISK actions require explicit user approval.
  - 한국어: 4단계 작업은 명시적 사용자 승인이 필요합니다.
- Dangerous patterns may be blocked even when approved.
  - 한국어: 위험 패턴은 승인되어도 차단될 수 있습니다.

---

## 7. Mode Layer / 모드 계층

Path: `iris/modes/`

Responsibilities:

- Work mode / 작업 모드
- Game mode / 게임 모드
- Creative mode / 창작 모드
- Recent work suggestion / 최근 작업 제안

Work mode flow:

1. User says: "작업 시작할게"
   - 한국어: 사용자가 작업 시작 의도를 말합니다.
2. Iris asks what work to start.
   - 한국어: Iris가 어떤 작업인지 묻습니다.
3. Iris suggests recent work.
   - 한국어: 최근 작업을 제안합니다.
4. User selects or creates new work.
   - 한국어: 사용자가 작업을 선택하거나 새 작업을 말합니다.
5. Iris launches apps and arranges windows when the action is not CRITICAL_RISK.
   - 한국어: 4단계 위험 작업이 아니라면 앱 실행과 창 배치를 바로 수행합니다.

Game mode flow:

1. User says: "게임할래"
   - 한국어: 사용자가 게임 의도를 말합니다.
2. Iris asks which game.
   - 한국어: Iris가 어떤 게임인지 묻습니다.
3. Iris suggests related apps.
   - 한국어: 관련 앱을 제안합니다.
4. Iris launches the game environment when the action is not CRITICAL_RISK.
   - 한국어: 4단계 위험 작업이 아니라면 게임 환경을 바로 실행합니다.

---

## 8. Monitoring Layer / 모니터링 계층

Path: `iris/monitoring/`

Responsibilities:

- Register monitoring targets / 모니터링 대상 등록
- Collect status from each target / 대상별 상태 수집
- Detect stalled tasks / 멈춘 작업 감지
- Generate alerts / 알림 생성
- Connect alert to risk-based action / 알림을 위험도 기반 조치와 연결

Target-specific monitoring:

| Target / 대상 | Method / 방식 |
|---|---|
| Iris-launched terminal command / Iris가 실행한 터미널 명령 | stdout/stderr |
| Existing terminal window / 기존 터미널 창 | UI Automation + OCR |
| Cursor / VS Code / 코드 편집기 | UI Automation + OCR |
| Chrome tabs / Chrome 탭 | Chrome Extension + DOM |
| Current screen / 현재 화면 | Screenshot + OCR, raw storage disabled by default / 스크린샷 + OCR, 원본 저장 기본 꺼짐 |
| System errors / 시스템 오류 | Windows Event Log |
| Complex visual state / 복잡한 시각 상태 | Future VLM adapter / 향후 VLM 어댑터 |

---

## 9. Safety Layer / 안전 계층

Path: `iris/assistant/safety_guard.py`

Responsibilities:

- Risk classification / 위험도 분류
- Approval enforcement for CRITICAL_RISK / 4단계 위험 작업 승인 강제
- Dangerous action blocking / 위험 작업 차단
- Log blocked actions / 차단 기록 저장

---

## 10. Storage Layer / 저장소 계층

Path: `iris/storage/`

Database: SQLite

Tables:

- logs / 일반 로그
- actions / 모니터링 승인 후 실행 기록
- launcher_actions / 앱 실행 기록
- automation_tool_logs / 자동화 도구 실행 기록
- recent_work / 최근 작업
- targets / 모니터링 대상
- events / 모니터링 이벤트
- recent_target_states / 최근 대상 상태
- memory_summaries / 장기 요약 기억
- task_sessions / 작업 세션

---

## 10.1 Voice Pipeline (Jarvis turn-taking) / 음성 파이프라인

Path: `iris/audio/`

| Module | Role |
|--------|------|
| `voice_session.py` | Half-duplex 상태머신 — IDLE/CAPTURING/TRANSCRIBING/PROCESSING/SPEAKING/BARGE_LISTEN |
| `continuous_listen.py` | 단일 마이크 InputStream + RMS VAD + barge-in RMS (별도 스트림 없음) |
| `stt_engine.py` | faster-whisper + `SttResult` no-speech gate (segment metadata) |
| `vad_calibrator.py` | 시작 시 노이즈 플로어 측정 → speech/silence RMS |
| `echo_cancellation.py` | AEC 선택 적용 (미설치 시 half-duplex만) |
| `voice_gate.py` | 호출어·follow-up 윈도우 (TTS 중 타이머 정지) |

Policy:

- **듣지 말아야 할 때**: `VoiceSessionController.should_accept_capture()` — TTS/처리/변환 중 및 `VOICE_RESUME_DELAY_MS` tail 동안 discard.
- **들은 뒤 버릴 때**: Whisper `no_speech_prob` / `avg_logprob` — 문자열 블랙리스트 없음.
- **Barge-in**: `BARGE_LISTEN` 상태에서만 RMS 감시 → TTS `stop()` + 새 발화 수집.
- **Follow-up**: 호출어 1회 후 `VOICE_FOLLOWUP_SECONDS`(기본 8초) — TTS 중 타이머 pause/resume.

---

## 11. Main Flow / 메인 흐름

### 11.1 Computer Use Agent Loop (default) / Computer Use 루프 (기본)

```text
User input (text / voice)
→ Command Router → Intent classification
→ ComputerUseAgent / AgentOrchestrator
    loop until goal met or max steps:
        Perception  (active window, UIA, OCR/VLM summary)
        Plan        (Tier 1 tool vs Tier 2 GUI)
        Risk check  (CRITICAL → pause for approval)
        Action      (AutomationToolRegistry.execute)
        Verify      (re-perceive → success | fail)
        on fail     → replan (shortcut-first) or Tier 4 delegate
→ Safety Guard (always)
→ Log (SQLite)
→ Respond / speak to user
```

한국어 설명: 기본 경로는 multi-step 루프입니다. 매 스텝마다 인식·실행·검증을 반복하고, 4단계 위험 작업만 루프를 멈추고 승인을 받습니다.

### 11.2 Simple / rule-based fallback / 단순·규칙 기반 폴백

```text
User input
→ Command Router
→ Intent classification
→ Rule-based handler (modes, one-shot commands)
→ Risk classification
→ Safety Guard → Action Executor → Log → Respond
```

Used when a full agent loop is unnecessary (e.g. pure chat, mode entry prompts).

---

## 12. Monitoring Flow / 모니터링 흐름

```text
Monitoring target
→ Target-specific collector
→ State Detector
→ Monitoring Event
→ Alert Generator
→ Gemma 4 summary
→ Notification Panel
→ Risk-based action decision
→ Action Executor
```

한국어 설명: 모니터링 결과는 알림으로 이어지고, 필요한 조치는 위험도 정책에 따라 실행됩니다.
