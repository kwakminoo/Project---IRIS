# Iris Architecture / Iris 아키텍처

## 1. System Overview / 시스템 개요

Iris is a local-first AI assistant with two major capabilities.

- 한국어 설명: Iris는 로컬 우선 AI 비서이며, 크게 두 가지 능력을 가집니다.

1. Jarvis-like personal AI assistant.
   - 한국어: 자비스형 개인 AI 비서.
2. Hybrid multi-target workflow monitoring.
   - 한국어: 여러 앱/창/탭/로그를 함께 보는 하이브리드 작업 모니터링.

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

- Agent adapter / 에이전트 어댑터
- Agent orchestrator / 에이전트 실행 루프
- Tool planning / 도구 계획
- Safety guard connection / 안전장치 연결
- Memory manager connection / 기억 시스템 연결

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

## 11. Main Flow / 메인 흐름

```text
User input
→ Command Router
→ Intent classification
→ Agent Orchestrator or rule-based handler
→ Risk classification
→ If CRITICAL_RISK: ask confirmation
→ If LOW/MEDIUM/HIGH: execute directly
→ Safety Guard
→ Action Executor
→ Log result
→ Respond to user
```

한국어 설명: 사용자 입력은 의도 분류 후 에이전트 또는 규칙 처리로 이동하고, 위험도에 따라 승인 또는 즉시 실행으로 나뉩니다.

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
