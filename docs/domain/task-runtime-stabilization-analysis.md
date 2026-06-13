# Task Runtime 안정화 분석

> Phase 1 산출물 — 수정 전 실행 경로·갭·P0 우선순위 정리

## 1. 개요

Task Runtime 도메인(`domain/task`, `domain/execution`)과 Application 계층(`application/*`)은 1차 구현되어 있으나, **ComputerUseAgent가 실제 도구 실행 시 Task Runtime을 우회**하는 이중 트랙이 존재한다.

성공 기준: 모든 실행 가능한 사용자 요청이 Task → Plan → Step → Proposal → Attempt → Result → Verification → TaskResult 체인으로 기록되고, 검증 성공 후에만 Step이 완료되며, 앱 재시작 후 동일 Task ID로 복구 가능해야 한다.

## 2. 12개 실행 경로별 현황 (수정 전)

| # | 경로 | Task 생성 | Attempt/Result | Verification | P0 |
|---|------|-----------|----------------|--------------|-----|
| 1 | 일반 PAV | `on_cu_started` 후 Yes | `record_tool_result` | tool success = verify success | P0-3 |
| 2 | Quick Launch | No | No | No | P0-1 |
| 3 | Action Skill | No | No | No | P0-1 |
| 4 | Full Plan | Yes | 이중 트랙 | checkpoint verify 별도 | P0-3 |
| 5 | 1-Step/fallback | Yes | orphan plan_id 가능 | 동일 | P0-3, P0-4 |
| 6 | CRITICAL 승인 | Yes | proposal만 | checkpoint 저장 | — |
| 7 | 승인 재개 | 기존 Task | `_run_tool_direct`만 | 없음 | P0-2 |
| 8 | Checkpoint 검증 | Yes | attempt 연결 약함 | step 미반영 | P0-3 |
| 9 | ask_user | Yes → FAILED | — | — | P0-6 |
| 10 | max_steps | Yes → FAILED | — | — | P0-6 |
| 11 | 앱 재시작 | checkpoint write-only | — | — | P0-5 |
| 12 | Runtime init 실패 | silent None | — | — | P0-7 |

## 3. 핵심 코드 위치

| 문제 | 파일 | 설명 |
|------|------|------|
| Task 우회 | `assistant/computer_use_agent.py:127-166` | skill/quick launch가 `on_cu_started` 이전 |
| 이중 실행 | `assistant/computer_use_agent.py:1481-1545` | `run_tool=False` + `_run_tool_direct` |
| 승인 재개 우회 | `assistant/computer_use_agent.py:232-261` | 기록 없이 direct run |
| Tool=Verify | `application/execution_coordinator.py:186-200` | tool success 시 step succeeded |
| orphan Step | `infrastructure/adapters/cu_task_adapter.py:115-124` | `active_plan_id or new_id()` |
| ask_user→FAILED | `assistant/computer_use_agent.py:377-389` | `on_cu_finished(success=False)` |
| silent init | `assistant/agent_adapter.py:93-110` | `except: return None` |
| FK 미강제 | `storage/database.py:36-37` | `PRAGMA foreign_keys` 없음 |
| Recovery 미구현 | `application/recovery_service.py` | create/get만 |

## 4. P0 문제 목록

- **P0-1**: Action Skill, Quick Launch, Tier1 등 Task 생성 전 조기 반환
- **P0-2**: 승인 재개가 `execute_step`/`execute_proposal` 미사용
- **P0-3**: `ActionResult.tool_success`와 `VerificationResult` 혼동
- **P0-4**: Plan 없이 Step 저장, FK 미강제
- **P0-5**: RecoveryService 복원 미구현
- **P0-6**: ask_user/max_steps를 FAILED로 처리
- **P0-7**: Task Runtime init 실패 silent fallback

## 5. 목표 실행 흐름 (수정 후)

```
사용자 요청
→ begin_cu_session (Task + Ad-hoc Plan + Step)
→ 경로 선택 (Skill / Quick Launch / Tier1 / PAV)
→ execute_proposal 또는 execute_step(run_tool=True)
→ ActionAttempt + ActionResult
→ Step VERIFYING
→ Checkpoint/상태 검증 → VerificationResult
→ Step SUCCEEDED/FAILED (검증 후만)
→ Task 종료 또는 WAITING_* 상태
```

## 6. 관련 파일

- Domain: `iris/domain/task/`, `iris/domain/execution/`
- Application: `iris/application/task_service.py`, `execution_coordinator.py`, `approval_service.py`, `verification_service.py`, `recovery_service.py`, `runtime_factory.py`
- Adapter: `iris/infrastructure/adapters/cu_task_adapter.py`
- Agent: `iris/assistant/computer_use_agent.py`, `agent_adapter.py`
- Persistence: `iris/infrastructure/persistence/migrations.py`, `sqlite_repositories.py`, `iris/storage/database.py`
