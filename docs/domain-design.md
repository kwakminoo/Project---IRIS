# Iris Domain Design / Iris 도메인 설계

## 1. Overview / 개요

This document defines the core domain concepts of Iris.

- 한국어 설명: 이 문서는 Iris의 핵심 도메인 개념을 정의합니다.

Iris has nine main domains:

1. Assistant / 비서
2. **Computer Use (PAV)** / Computer Use (인식·행동·검증)
3. Command / 명령
4. Automation / 자동화
5. Mode / 모드
6. Monitoring / 모니터링
7. Safety / 안전
8. Storage / 저장소
9. External Agent (Tier 4) / 외부 에이전트

The default execution path is a **multi-step agent loop**, not a single `AssistantResponse` turn.

---

## 1.1 Computer Use: Perception / Action / Verify

Computer Use is the cross-cutting domain for Jarvis-style PC control.

### PerceptionObservation / 인식 관측

Represents a summarized view of PC state at one step (not raw storage).

- 한국어 설명: 한 스텝 시점의 PC 상태 요약입니다. 원본 스크린샷·전체 OCR은 기본 저장하지 않습니다.

Fields:

- id
- active_window_title
- active_process_name
- open_windows_summary (from `list_open_windows`)
- uia_snapshot_summary
- ocr_or_vlm_scene_summary
- captured_at
- source: uia | ocr | vlm | hybrid

Sources:

- Active window / 활성 창
- `list_open_windows` / 열린 창 목록
- UIA snapshot summary / UIA 스냅샷 요약
- OCR or VLM scene summary / OCR·VLM 장면 요약

### ActionStep / 행동 스텝

Represents one tool invocation in the agent loop.

- 한국어 설명: 에이전트 루프에서 `AutomationToolRegistry`를 통해 실행하는 단일 조작입니다.

Fields:

- id
- tool_name (e.g. `launch_app`, `focus_window`, `type_text`, `click`, `run_shell`, `open_url`)
- arguments
- tier: 1 | 2 (1 = dedicated tool, 2 = universal GUI)
- risk_level
- requires_approval
- parent_loop_id
- step_index

Rule:

- Steps run **sequentially** inside `ComputerUseAgent` or extended `AgentOrchestrator`.
- CRITICAL_RISK steps block until `UserApproval` is granted.

### VerifyResult / 검증 결과

Represents outcome comparison after an `ActionStep`.

- 한국어 설명: 행동 후 재인식 결과를 목표와 비교한 판정입니다.

Fields:

- id
- action_step_id
- perception_observation_id
- status: success | failed | partial | unknown
- goal_match_score (optional)
- failure_reason
- suggested_next: retry | replan | shortcut | tier4_delegate
- verified_at

Rules:

- On **failed**: replan within the same loop; prefer keyboard shortcuts over fragile mouse paths.
- On repeated failure: optionally delegate to Tier 4 (`OpenClawAdapter`, `HermesAdapter`).

### AgentLoop / 에이전트 루프

Represents one multi-step Computer Use session for a user goal.

Fields:

- id
- user_command_id
- goal_text
- status: running | paused_approval | completed | failed | delegated_tier4
- max_steps
- current_step
- perception_observation_ids[]
- action_step_ids[]
- verify_result_ids[]
- started_at
- ended_at

---

## 1.2 Tier 4 External Agent / 외부 에이전트 (선택)

### ExternalAgentDelegation / 외부 에이전트 위임

Represents handoff when Iris loop cannot complete the goal.

Fields:

- id
- agent_loop_id
- agent_type: openclaw | hermes
- reason: failure | long_tail | user_requested
- delegated_at
- result_summary

Rule:

- OpenClaw and Hermes are **not** the Jarvis body. Iris orchestrator remains central; Tier 4 is fallback only.

---

## 2. UserCommand / 사용자 명령

Represents a user input from text or voice.

- 한국어 설명: 텍스트 또는 음성으로 들어온 사용자 입력을 나타냅니다.

Fields:

- id
- source: text | voice
- raw_text
- normalized_text
- created_at
- context

Examples:

- "작업 시작할게"
- "게임할래"
- "터미널 승인해줘"
- "GPT 답변 끝났어?"

---

## 3. AssistantResponse / 비서 응답

Represents Iris's response to the user.

- 한국어 설명: Iris가 사용자에게 보여주거나 말하는 응답입니다.

Fields:

- id
- text
- should_speak
- response_type: chat | confirmation | alert | error
- created_at

Examples:

- "어떤 작업을 실행할까요?"
- "터미널이 승인 대기 중입니다. 실행할까요?"

---

## 4. CommandIntent / 명령 의도

Represents classified user intent.

- 한국어 설명: 사용자 입력을 분류한 의도입니다.

Types:

- GENERAL_CHAT / 일반 대화
- APP_LAUNCH / 앱 실행
- WINDOW_CONTROL / 창 제어
- WEB_SEARCH / 웹 검색
- REPORT_GENERATION / 보고서 생성
- WORK_MODE / 작업 모드
- GAME_MODE / 게임 모드
- CREATIVE_MODE / 창작 모드
- MONITORING_STATUS / 모니터링 상태
- COMPUTER_ACTION / 컴퓨터 조작
- ALERT_RESPONSE / 알림 응답
- UNKNOWN / 알 수 없음

---

## 5. ActionRequest / 실행 요청

Represents a computer action Iris wants to perform.

- 한국어 설명: Iris가 수행하려는 컴퓨터 조작입니다.

Fields:

- id
- action_type
- target
- command
- risk_level
- requires_approval
- created_at

Examples:

- Launch Cursor / Cursor 실행
- Focus Terminal / 터미널 포커스
- Type "y" into terminal / 터미널에 "y" 입력
- Open Chrome tab / Chrome 탭 열기
- Arrange windows / 창 배치

Rule:

- LOW_RISK, MEDIUM_RISK, and HIGH_RISK can execute without extra approval.
  - 한국어: 1~3단계 작업은 추가 승인 없이 실행할 수 있습니다.
- CRITICAL_RISK requires user approval.
  - 한국어: 4단계 작업은 사용자 승인이 필요합니다.

---

## 6. UserApproval / 사용자 승인

Represents user confirmation for a CRITICAL_RISK action.

- 한국어 설명: 4단계 위험 작업에 대한 사용자 확인입니다.

Fields:

- id
- action_request_id
- approved: true | false
- approved_at
- approval_text

Rule:

- CRITICAL_RISK cannot be executed without approval.
  - 한국어: 4단계 위험 작업은 승인 없이 실행할 수 없습니다.

---

## 7. ExecutionLog / 실행 로그

Represents the result of an executed action.

- 한국어 설명: 실행된 작업의 결과 기록입니다.

Fields:

- id
- action_request_id
- result: success | failed | blocked
- risk_level
- approval_required
- message
- timestamp

---

## 8. PresetMode / 프리셋 모드

Represents a dynamic mode such as work, game, or creative mode.

- 한국어 설명: 작업, 게임, 창작처럼 여러 앱과 창 배치를 묶은 실행 모드입니다.

Fields:

- id
- mode_type: work | game | creative
- title
- suggested_apps
- suggested_layout
- risk_level

Important:

- Preset execution is auto-allowed unless it includes CRITICAL_RISK actions.
  - 한국어: 프리셋 실행은 4단계 위험 작업을 포함하지 않으면 자동 실행됩니다.

---

## 9. MonitoredTarget / 모니터링 대상

Represents a target Iris monitors.

- 한국어 설명: Iris가 상태를 지켜보는 창, 탭, 터미널, 화면 등의 대상입니다.

Fields:

- id
- type: current_screen | desktop_window | browser_tab | terminal_command | system_log
- title
- process_name
- url
- handle
- enabled
- status
- last_checked_at
- last_event

---

## 10. MonitoringEvent / 모니터링 이벤트

Represents an event detected from a monitored target.

- 한국어 설명: 모니터링 대상에서 감지된 상태 변화나 문제입니다.

Categories:

- NORMAL / 정상
- APPROVAL_WAITING / 승인 대기
- ERROR_DETECTED / 오류 감지
- GENERATION_FAILED / 생성 실패
- TASK_STALLED / 작업 정체
- RESPONSE_READY / 응답 완료
- BUILD_NOT_STARTED / 빌드 미시작
- USER_ACTION_REQUIRED / 사용자 조치 필요
- UNKNOWN / 알 수 없음

---

## 11. DetectionResult / 감지 결과

Represents the output of state detection.

- 한국어 설명: `state_detector.py`가 반환하는 감지 결과입니다.

Example:

Input:

```text
Proceed? (y/n)
```

Output:

```text
category: APPROVAL_WAITING
confidence: 0.95
reason: Terminal is waiting for user approval.
recommended_action: Ask whether to type y, then classify risk before execution.
```

한국어 설명: 터미널이 입력을 기다리는 상태를 감지하고, 실행 전 위험도 분류를 거칩니다.

---

## 12. SafetyPolicy / 안전 정책

Represents safety rules for blocking dangerous actions.

- 한국어 설명: 위험한 작업을 차단하거나 승인 필요로 분류하는 규칙입니다.

Approval required:

- Shell commands / 셸 명령
- File deletion / 파일 삭제
- Payment / 결제
- Password input / 비밀번호 입력
- Personal data submission / 개인정보 제출
- System setting changes / 시스템 설정 변경
- Sensitive browser actions / 민감 브라우저 조작

Auto-allowed:

- App launch / 앱 실행
- Window control / 창 제어
- Public web search / 공개 웹 검색
- Non-sensitive keyboard and mouse input / 민감하지 않은 키보드·마우스 입력

---

## 13. WebReport / 웹 보고서

Represents a report generated by the web agent.

- 한국어 설명: 웹 에이전트가 생성한 요약 보고서입니다.

Fields:

- id
- query
- title
- summary
- sources
- key_points
- created_at
