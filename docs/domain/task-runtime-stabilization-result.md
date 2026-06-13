# Task Runtime 안정화 결과

## 1. 수정한 P0/P1 문제

| ID | 문제 | 조치 |
|----|------|------|
| P0-1 | Skill/Quick Launch Task 미생성 | `begin_cu_session` 모든 경로 선행 |
| P0-2 | 승인 재개 direct run | `execute_proposal` 통합 |
| P0-3 | Tool success = Step success | `StepStatus.VERIFYING`, finalize 분리 |
| P0-4 | orphan Step, FK 미강제 | `ensure_adhoc_plan`, PRAGMA foreign_keys, migration 005 |
| P0-5 | Recovery 미구현 | RecoveryService 확장 + startup UI |
| P0-6 | ask_user → FAILED | `WAITING_USER` / `SUSPENDED` 전이 |
| P0-7 | silent init fallback | TaskRuntimeHealth + 로그 |
| P1-1 | Application→Sqlite 직접 의존 | TaskRuntimeRepositories Protocol |
| P1-2 | Plan revision PK 충돌 | `create_revision` 새 plan id |
| P1-3 | 승인 만료 미검증 | `expires_at` grant/validate |

## 2. 변경된 실행 흐름

모든 CU 요청 → Task 생성 → execute_step/execute_proposal → VERIFYING → checkpoint finalize.

## 3. 승인 재개 통합

`execute_proposal(proposal_id, approval_id)` — grant·hash·expires 검증 후 Attempt/Result.

## 4. Verification 이후 Step 상태

`finalize_step_from_verification` — SUCCESS/PARTIAL만 succeeded, UNKNOWN은 succeeded 금지.

## 5. 앱 재시작 복구

RecoveryService + MainWindow chat 알림 + attach_task 재개.

## 6. DB 변경

- migration 005: previous_plan_id, superseded_at
- PRAGMA foreign_keys=ON
- save_step plan 존재 검증

## 7. 새 테스트

`tests/test_task_runtime_stabilization.py` — 27개 필수 테스트.

## 8. 기존 테스트

test_execution_coordinator, test_cu_critical_resume, test_computer_use_agent 회귀 통과.

## 9. 남은 레거시

- `_run_tool_direct` — perceive, Tier4, task_runtime=None 폴백
- `run_pending_cu_tool` — task_runtime 미주입

## 10. 다음 개선

- StepStatus 공식 전이 테이블
- PolicyDecision 영속
- events.related_* UI 연동
