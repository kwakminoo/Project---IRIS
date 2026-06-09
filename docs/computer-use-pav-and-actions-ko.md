# Computer Use: PAV 루프와 PC 조작 설계

## PAV란?

**PAV**는 Iris Computer Use의 기본 실행 사이클입니다.

| 단계 | 영문 | 역할 |
|------|------|------|
| **P** | Perceive (인식) | `list_open_windows`, `perceive_desktop`, `uia_snapshot` 등으로 PC·창 상태 수집 |
| **A** | Act (행동) | `AutomationToolRegistry` 도구 1스텝 (`launch_app`, `type_text`, `uia_click` …) |
| **V** | Verify (검증) | Act 직후 다시 Perceive → 목표 달성 여부 판단, 미달 시 플래너가 다음 스텝 재계획 |

코드 진입점: `iris/iris/assistant/computer_use_agent.py` → `ComputerUseAgent.run()`.

```
loop_start (Perceive)
  → Planner LLM (한 스텝 JSON)
  → Act (도구 1개)
  → Verify (Perceive)
  → 반복 (최대 max_steps)
  → step_complete | step_failed | approval_required
```

**PAV의 장점:** 앱마다 어댑터 없이 범용 GUI로 목표를 맞출 수 있음.  
**PAV의 단점:** 스텝마다 LLM(·비전) 호출 → 느림, 플래너 실수 시 같은 도구 반복.

그래서 Iris는 **스킬(고정 플로우)** 과 **PAV**를 병행합니다.

- `MediaPlaybackFlow` — 유튜브 검색·재생 (이미 구현)
- `TextComposeFlow` — 메모장 등 텍스트 입력 (계획)
- `SendMessageFlow` — 카톡·디스코드 메시지 (계획)
- `VoipCallFlow` — 디스코드 통화 등 (계획)

---

## 사용자 입력과 충돌하지 않게 조작하는 방법

### 1. 실행 우선순위 (6단계)

`execution_tier_policy.py` 기준 — **숫자가 작을수록 먼저**.

1. **전용 API** — `launch_app`, `open_url`, `call_integration`
2. **UI Automation** — `uia_click`, `uia_snapshot`, `perceive_desktop`
3. **단축키** — `send_hotkey`
4. **가상 키보드/마우스** — `type_text`, `click(x,y)` — 1~3이 불가할 때만
5. **셸** — `run_shell` (CRITICAL, 승인 필요)
6. **Tier4** — OpenClaw/Hermes (로컬 실패 시)

메모장·카톡·디스코드는 가능하면 **2→3→4** 순으로 시도하고, `type_text`는 최후 수단.

### 2. 입력 충돌 도구 사전 안내

`type_text`, `send_hotkey`, `click` 실행 **직전**:

1. `input_conflict_message()`로 음성·채팅 안내  
   예: "잠시 키보드와 마우스 사용을 멈춰 주세요…"
2. `computer_use_input_notify_delay_seconds` (기본 2초) 대기  
3. 그 다음 도구 실행

설정: `Settings.computer_use_input_notify_delay_seconds`

### 3. 포커스·검증

- `focus_window` 성공 후 `type_text`
- `type_input_verify_enabled` — 입력 후 UIA/OCR로 짧게 검증 (`text_input_verify.py`)
- Act마다 Verify(재인식)로 화면 상태 확인

### 4. Router가 구조화한 slots (LLM 판단 → 코드 실행)

| task_type | 필수 slots | 실행 경로 |
|-----------|------------|-----------|
| `open_app` | `app_key` | quick `launch_app` 또는 스킬 1단계 |
| `compose_text` | `app_key`, `text_to_type` | TextCompose 스킬 |
| `send_message` | `app_key`, `message_text`, (선택) `recipient` | SendMessage 스킬 |
| `voip_call` | `app_key`, `target_name` | VoipCall 스킬 (UIA로 통화 버튼) |
| `multi_step` | `goal` | PAV 플래너 |

`COMPLEX_GOAL_RE` regex는 Router slots가 비었을 때만 폴백으로 유지.

### 5. 스킬 내부 공통 순서 (예: 메모장에 글 쓰기)

```
1. list_open_windows — 메모장 이미 열렸는지
2. 없으면 launch_app(notepad)
3. focus_window("메모장")
4. (선택) uia_snapshot — 편집 영역 확인
5. input_conflict 안내 + delay
6. type_text(본문) + verify
7. perceive_desktop — 완료 확인
8. tool_user_reply.format_pending_tool_user_message — 실제 result.message로 사용자에게 보고
```

### 6. 카톡 / 디스코드

- **메시지:** UIA로 채팅 입력창·전송 버튼 클릭 우선 → 불가 시 `type_text` + Enter 단축키
- **통화:** UIA로 사용자·통화 버튼 클릭; 로그인·2FA 필요 시 `ask_user`로 중단 (Safety Guard)
- **민감 작업:** 결제·비밀번호·계정 설정은 CRITICAL — 승인 또는 차단

### 7. 향후: 입력 유휴 감지 (선택)

- 마우스·키보드 idle N초 후 Act (Windows `GetLastInputInfo` 등)
- Iris UI가 LISTENING/EXECUTING일 때만 자동 입력
- 게임 모드에서는 `type_text` 비활성화 플래그

---

## 사용자 멘트 (UI)

휴리스틱 regex 마스킹 대신 **`tool_user_reply.py`** 가 다음을 정본으로 사용합니다.

- 승인 전: `AutomationTool.preview()` 문자열
- 실행 후: `AutomationToolResult.message` / `detail`
- early_ack: Router `slots` (`display_name`, `text_to_type`, `task_type` …)

미디어 플로우는 기존처럼 `media_play_user_reply.py` (LLM 합성 + 폴백).

---

## 구현 체크리스트

- [x] `tool_user_reply` — preview/result 기반 멘트
- [x] `action_skills` — 스킬 ID·매칭 골격
- [ ] `TextComposeFlow` — compose_text 스킬
- [ ] `SendMessageFlow` — send_message 스킬
- [ ] Unified Router — `text_to_type`, `message_text` 슬롯 강제
- [x] CRITICAL 승인 후 CU 루프 재개 (1스텝만 종료하지 않기)
- [x] Phase 6 — `monitor_hint:` observation 주입 (`cu_hint_injector.py`)
- [x] DialogueAgent 선제 모니터링 제안 (`proactive_suggestion.py` + `monitor_proposal`)
- [ ] `run_shell` + notepad 가드 (launch_app 강제)
