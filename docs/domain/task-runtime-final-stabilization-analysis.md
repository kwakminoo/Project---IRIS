# Task Runtime 최종 안정화 — 사전 분석

> 작성: 2026-06-14  
> 범위: 재시작 복구, Skill 검증 통합, Windows 스모크, GitHub Actions

---

## 1. 앱 시작 시 복구 가능한 Task를 찾는 위치

| 계층 | 파일 | 함수 |
|------|------|------|
| UI 진입 | `iris/iris/ui/main_window.py` | `_deferred_startup_services()` → `_check_recoverable_tasks()` |
| Runtime 조립 | `iris/iris/application/runtime_factory.py` | `build_task_runtime()` |
| 복구 조회 | `iris/iris/application/recovery_service.py` | `list_recoverable_tasks()` |
| DB | `iris/iris/infrastructure/persistence/sqlite_repositories.py` | `SqliteTaskRepository.get_recoverable()` |

복구 대상 상태: `RUNNING`, `WAITING_APPROVAL`, `WAITING_USER`, `WAITING_RESOURCE`, `SUSPENDED`, `INTERRUPTED`.

**갭:** `RUNNING`은 비정상 종료로 간주해 `INTERRUPTED`로 정규화 필요. 앱 시작 시 Tool 자동 실행 없음.

---

## 2. UI에서 "계속 진행" / "상태 확인" / "작업 취소" 처리 위치

| 명령 | 현재 | 목표 |
|------|------|------|
| 안내 문구 | `main_window._check_recoverable_tasks()` | 유지 |
| 상태 확인 | **미구현** | `recovery_turn_handler` + `RecoveryService.load_recovery_snapshot()` |
| 계속 진행 | CU pending 승인 재개만 존재 | `turn_coordinator` → `_resume_task_id` → `ComputerUseAgent.run()` |
| 작업 취소 | CU REJECT 시 `abandon_task`만 | 복구 전용 `abandon_task` 라우팅 |

`DialogueContext.active_task_id`가 복구 Task ID 역할 (`active_recovery_task_id` 필드 없음).

---

## 3. 기존 Task ID를 ComputerUseAgent에 전달하는 방법

```text
slots["_resume_task_id"] = task_id   # 재개 우선
slots["_task_id"] = task_id         # CRITICAL 승인 재개
ctx.active_task_id = task_id        # 앱 시작 복구 시 설정
```

`ComputerUseAgent.run()` → `CuTaskAdapter.attach_task(resume_tid)` — **새 Task 생성 안 함**.

---

## 4. RecoverySnapshot이 포함하는 정보

`iris/iris/application/recovery_service.py` — `RecoverySnapshot`:

- `task`, `plan`, `steps`, `active_step`
- `checkpoint`, `pending_approval`
- `latest_proposal`, `latest_attempt`

`load_recovery_snapshot()`이 DB에서 조립.

---

## 5. Skill 실행 검증 결과 저장 위치

| 경로 | 저장 | 갭 |
|------|------|-----|
| PAV checkpoint | `VerificationService.record_checkpoint_result()` → `verification_results` | 완료 |
| Quick Launch | `execute_tool_step()` lightweight verify | 완료 |
| Skill Flow | `run_tool_recorded()` → proposal/attempt/result | attempt OK |
| Skill checkpoint | mechanical/LLM verify → **DB log만** | **VerificationResult 미저장** |

목표: `record_skill_checkpoint()` → `on_checkpoint_verified()` → 공통 `VerificationResult`.

---

## 6. 실제 Windows 실행을 Mock 없이 검증할 수 있는 범위

| 시나리오 | 범위 | 제약 |
|----------|------|------|
| 메모장 실행/종료 | `launch_app` + 프로세스/창 확인 | 관리자 권한 불필요 |
| 텍스트 입력 | `type_text` + UIA/OCR | 사용자 파일 미수정 |
| 승인 후 재개 | 테스트 전용 low-risk tool | CRITICAL shell 금지 |
| 앱 재시작 복구 | DB + Runtime 재생성 | GUI 없이 service 레벨 가능 |
| 입력 충돌 관찰 | 로그·상태 기록만 | ResourceLease 미구현 |

마커: `@pytest.mark.windows_smoke` — 기본 CI 제외, 로컬/self-hosted 실행.

---

## 7. 현재 CI 구성 여부

**없음** — `.github/workflows/` 디렉터리 미존재.

로컬 검증: `python -m compileall iris -q`, `python -m pytest -q`.

`conftest.py`에 `integration` 마커만 존재 (`windows_smoke` 추가 예정).

---

## 8. 수정 예정 파일 목록

### P0 — 재시작 복구

- `iris/iris/application/recovery_service.py` — 정규화·검증·abandon 보강
- `iris/iris/application/recovery_commands.py` — **신규** 명령 분류·상태 포맷
- `iris/iris/assistant/recovery_turn_handler.py` — **신규** 턴 핸들러
- `iris/iris/assistant/turn_coordinator.py` — 복구 명령 라우팅
- `iris/iris/ui/main_window.py` — 시작 시 정규화 호출
- `iris/iris/application/task_service.py` — `mark_task_interrupted()`
- `iris/iris/application/approval_service.py` — 만료 승인 갱신

### P1 — Skill 검증

- `iris/iris/application/verification_service.py` — `record_skill_checkpoint()`
- `iris/iris/infrastructure/adapters/cu_task_adapter.py` — `on_skill_checkpoint_verified()`, `last_attempt_id`
- `iris/iris/assistant/computer_use_agent.py` — `record_skill_checkpoint()`, `_finish_fast_path_session` 보강
- `iris/iris/assistant/text_compose_flow.py`
- `iris/iris/assistant/send_message_flow.py`

### P2 — 테스트·CI·문서

- `iris/tests/test_task_runtime_recovery_commands.py` — **신규**
- `iris/tests/test_task_runtime_skill_verification.py` — **신규**
- `iris/tests/test_windows_smoke.py` — **신규**
- `iris/tests/conftest.py` — `windows_smoke` 마커
- `.github/workflows/test.yml` — **신규**
- `.github/workflows/windows-smoke.yml` — **신규**
- `docs/domain/task-runtime-*.md`, `docs/testing/*.md`
