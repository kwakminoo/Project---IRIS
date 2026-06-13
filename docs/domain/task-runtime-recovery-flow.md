# Task Runtime 재시작 복구 흐름

## 개요

앱 비정상 종료·승인 대기·사용자 입력 대기 후 재시작 시, Iris는 DB에 남은 Task를 탐색하고 사용자 명령으로만 재개합니다.

## 흐름

```text
앱 시작
→ main_window._check_recoverable_tasks()
→ RecoveryService.normalize_startup_tasks()
   (RUNNING → INTERRUPTED 정규화)
→ 채팅 안내 + ctx.active_task_id 설정

사용자 명령
→ TurnCoordinator.run_turn()
→ recovery_turn_handler.try_handle_recovery_turn()
```

## 사용자 명령

| 명령 | 동작 |
|------|------|
| 상태 확인 | `RecoverySnapshot` 조회·포맷 표시 |
| 계속 진행 | `resume_task()` + `slots["_resume_task_id"]` → `ComputerUseAgent.run()` |
| 작업 취소 | `abandon_task()` — pending Approval DENIED, Task CANCELLED |

## 동일 Task ID 유지

- `attach_task(task_id)` — 새 Task 생성 금지
- 기존 Plan/Step/Proposal ID 유지
- `WAITING_APPROVAL`: 기존 Proposal 복원, 만료 시 새 ApprovalRequest만 생성

## 안전 규칙

- 앱 시작 직후 Tool 자동 실행 없음
- `validate_resume_snapshot()` 실패 시 실행 차단
- 완료된 Attempt 중복 실행 방지: `proposal_has_completed_attempt()`

## 관련 파일

- `iris/application/recovery_service.py`
- `iris/application/recovery_commands.py`
- `iris/assistant/recovery_turn_handler.py`
- `iris/assistant/turn_coordinator.py`
- `iris/ui/main_window.py`
