# Task Runtime 마이그레이션 가이드

---

## 1. DB 마이그레이션

프로젝트는 SQL 파일 대신 Python 마이그레이션을 사용한다.

- 위치: [`iris/iris/infrastructure/persistence/migrations.py`](../../iris/iris/infrastructure/persistence/migrations.py)
- 버전 테이블: `schema_migrations(version, applied_at)`
- 적용 시점: `Database.__init__` → `_run_task_runtime_migrations()`

| 버전 | 내용 |
|------|------|
| `001_create_task_runtime` | tasks, task_plans, task_steps, task_checkpoints, task_results |
| `002_create_execution_records` | action_proposals, action_attempts, action_results, verification_results |
| `003_create_approval_records` | approval_requests |
| `004_events_task_link` | events.related_task_id, related_plan_step_id, related_action_attempt_id |

**원칙**: 기존 15개 테이블·데이터 삭제 없음. `task_sessions` 병행 유지.

---

## 2. 레거시 ↔ Task Runtime 매핑

| 레거시 | Task Runtime |
|--------|----------------|
| `task_sessions.current_goal` | `tasks.goal` |
| `task_sessions.tools_run_json` | `action_attempts` + `action_proposals.tool_name` |
| `task_sessions.observations_json` | `verification_results`, `action_results.output_summary` |
| `task_sessions.approvals_json` | `approval_requests` |
| `ComputerUseFullPlan` (메모리) | `task_plans` + `task_steps` |
| `PendingComputerUseGoal` (메모리) | `approval_requests` + `task_checkpoints.snapshot_json` |
| `ComputerUseContext` (메모리) | `task_checkpoints.snapshot_json` |

---

## 3. Adapter 활성화

- `IrisAssistant._ensure_task_runtime()` — lazy 초기화
- `ComputerUseAgent(task_runtime=CuTaskAdapter)` — IrisAssistant 경유 시 자동 주입
- 테스트에서 `ComputerUseAgent(..., task_runtime=None)` — 기존 회귀 유지

---

## 4. 승인 바인딩

`approval_requests.arguments_hash` = SHA256(JSON sorted keys).

`npm test` 승인은 다른 셸 명령에 재사용 불가. `ApprovalService.grant()` 시 tool_name·arguments 일치 검증.

---

## 5. 데이터 마이그레이션 (미구현 — Phase 2)

기존 `task_sessions` → `tasks` 일괄 이전 스크립트는 아직 없음.

권장 순서:
1. 신규 CU 세션은 Task Runtime만 사용 (현재)
2. `task_sessions` 읽기 전용 유지
3. Phase 2에서 batch migration + `task_sessions` deprecated

---

## 6. 롤백

새 테이블만 추가되므로 앱 코드에서 `task_runtime=None`으로 비활성화하면 레거시 경로만 사용.

DB 롤백은 새 테이블 DROP (데이터 손실 주의) — 수동.
