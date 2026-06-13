# Task Runtime 복구

## RecoveryService API

- `list_recoverable_tasks()` — running, waiting_approval, waiting_user, waiting_resource, suspended, interrupted
- `load_recovery_snapshot(task_id)` — Task, Plan, Step, Checkpoint, Approval, Proposal, Attempt
- `can_resume(task_id)` — 복구 가능 여부
- `resume_task(task_id)` — RUNNING 전이
- `abandon_task(task_id)` — CANCELLED

## 앱 재시작 UX

`MainWindow._check_recoverable_tasks()` — recoverable task 있으면 chat에 3-option 안내:

- 계속 진행
- 상태 확인
- 작업 취소

## 승인 대기 복구

- DB의 `ApprovalRequest` + `ActionProposal` 복원
- 새 Tool 실행 금지 — `execute_proposal(proposal_id, approval_id)` 사용
- `pending.slots`에 `_task_id`, `_task_proposal_id`, `_task_approval_id` 저장

## Checkpoint

`create_checkpoint` snapshot: cu_mode, step_idx, approval_id, proposal_id, tool, params
