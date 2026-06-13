# Iris 현재 도메인 분석

- 작성 목적: Task Runtime 리팩터링 전 as-is 구조 정리
- 기준 코드: `iris/iris/` (2026-06)

---

## 1. 현재 실행 흐름

```text
UI AgentWorker (workers.py)
  → TurnCoordinator.run_turn()
    → SafetyGuard.quick_block_user_text()
    → pending_cu 후속? → llm_approval → CU 재개
    → Frontier envelope (선택)
    → UnifiedRouter.route_user_turn()
    → _dispatch_routed_turn(RouteLane)
      → CHAT_ONLY / SEARCH / MULTI_TURN / DIRECT_ACTION / FAST_TOOL
      → ORCHESTRATED → AgentOrchestrator → IrisAssistant
      → COMPUTER_USE → IrisAssistant.run_computer_use_loop()
          → ComputerUseAgent.run() [PAV 루프]
            → AutomationToolRegistry.run()
            → cu_checkpoint_verify / cu_repair_planner
```

Computer Use가 기본 실행 경로이며, PC 조작은 `AutomationToolRegistry`를 통해 수행된다.

---

## 2. 주요 클래스 책임

| 클래스 | 파일 | 책임 | 계층 |
|--------|------|------|------|
| `TurnCoordinator` | `assistant/turn_coordinator.py` | 한 턴 라우팅·병합, CU/승인 분기 | Application |
| `IrisAssistant` | `assistant/agent_adapter.py` | 대화·모드·CU 루프 위임, ToolRegistry 경유 | Application |
| `UnifiedRouter` | `assistant/unified_router.py` | LLM JSON 라우팅 (함수 API) | Application |
| `AgentOrchestrator` | `assistant/orchestrator.py` | 메타 도구 루프 (PC 조작은 CU 위임) | Application |
| `ComputerUseAgent` | `assistant/computer_use_agent.py` | PAV, full-plan, repair, 승인 대기 | Application (과다 책임) |
| `AutomationToolRegistry` | `automation/tool_registry.py` | Tier1–2 도구 등록·실행·로깅 | Infrastructure |
| `SafetyGuard` | `assistant/safety_guard.py` | 위험 패턴 차단·평가 | Application |
| `MonitorManager` | `monitoring/monitor_manager.py` | 수집→감지→알림→DB | Infrastructure |
| `Database` | `storage/database.py` | SQLite 스키마·CRUD 전부 | Infrastructure |
| `MemoryManager` | `memory/memory_manager.py` | task_sessions JSON 요약 | Application |
| `DialogueContext` | `core/context_manager.py` | 멀티턴·승인 대기 메모리 상태 | UI/Application 경계 |

---

## 3. 현재 Task 관리 방식

| 개념 | 저장 위치 | 한계 |
|------|-----------|------|
| `task_sessions` | SQLite JSON (goal, tools_run, observations, approvals) | Task ID·상태·Plan 없음 |
| `ComputerUseContext` | CU 루프 인메모리 | 앱 종료 시 소실 |
| `PendingComputerUseGoal` | `DialogueContext` 메모리 | 승인 스냅샷, 영속 ApprovalRequest 없음 |
| `ComputerUseFullPlan` | ctx.full_plan (인메모리) | DB Plan 버전 관리 없음 |
| `recent_work` | SQLite | 작업 모드 제안용, CU 실행 추적과 분리 |

v2 설계의 `Task` / `Plan` / `PlanStep`은 코드에 미구현.

---

## 4. 승인 처리 흐름

```text
ActionProposal (없음 — 즉시 도구 호출)
  → AutomationToolRegistry.needs_approval() [CRITICAL만]
  → SafetyGuard (run_shell 등 도구 내부)
  → PendingComputerUseGoal 설정 (ctx.pending_cu)
  → task_sessions approvals_json 요약 저장
  → 사용자 후속 발화
  → llm_approval.resolve_followup_for_pending()
  → ComputerUseAgent.resume_after_critical_approval()
```

승인은 도구명+인수에 묶이지 않은 채 메모리에만 존재한다.

---

## 5. 실행과 검증 흐름

```text
Perceive (cu_perception)
  → Plan (step planner 또는 full plan 1회)
  → Act (_execute_tool → Registry)
  → Verify
      → mechanical_verify_checkpoint (cu_mechanical_verify)
      → verify_checkpoint_hybrid (cu_checkpoint_verify)
  → 실패 시 Repair (cu_repair_planner / cu_repair_templates)
  → Tier4 폴백 (external_agent_adapter)
```

검증 결과는 `CheckpointVerifyResult` 인메모리 + observations 문자열로만 남는다.

---

## 6. 모니터링 흐름

```text
MonitorManager.tick()
  → TargetRegistry 대상별 스니펫 수집
  → state_detector.detect_state() → DetectionResult
  → events 테이블 INSERT
  → NotificationPolicy 쿨다운
  → alert_emitted PyQt Signal
```

Task ID 연계 없음. `APPROVAL_WAITING` / `TASK_STALLED`는 category만 저장.

---

## 7. 저장 구조

`Database._init_schema()` 기준 15개 테이블:

1. logs
2. launcher_actions
3. recent_work
4. targets
5. events
6. actions (모니터링 실행 기록)
7. recent_target_states
8. **task_sessions** (레거시 작업 요약)
9. memory_summaries
10. user_preferences
11. automation_tool_logs
12. notification_log
13. notification_prefs
14. app_launcher_entries
15. integration_endpoints

- Repository 패턴 없음
- `schema_migrations` 없음
- 마이그레이션: `CREATE TABLE IF NOT EXISTS` + 레거시 `actions` rename 1건

---

## 8. 구조적 문제

1. **Task 개념 부재** — 실행·승인·검증이 하나의 추적 ID로 연결되지 않음
2. **이름 충돌** — `action_plan.PlanStep` vs 도메인 `PlanStep`
3. **승인 분산** — Registry, SafetyGuard, pending_cu, llm_approval에 분산, 영속 ApprovalRequest 없음
4. **God Class** — `ComputerUseAgent` (~1500줄)
5. **설계-구현 갭** — `iris-domain-design-v2.md` Task 파이프라인 미구현
6. **마이그레이션 부재** — 스키마 버전 관리 없음
7. **순환 의존 가능성** — IrisAssistant ↔ ComputerUseAgent ↔ TurnCoordinator
8. **중복 책임** — 승인 판단이 Registry와 SafetyGuard에 중복

---

## 9. 이번 리팩터링 범위

### 구현 (1차)

- `domain/` / `application/` / `infrastructure/` 패키지
- Task, Plan, PlanStep, ActionProposal, ActionAttempt, ActionResult, VerificationResult, TaskCheckpoint, TaskResult
- Repository + SQLite Migration (001~003)
- ExecutionCoordinator, TaskApplicationService, ApprovalService
- ComputerUseAgent optional Adapter (`task_runtime=None` 기본)
- Domain Events + 테스트

### 제외 (이번 단계)

- Eclipse Theia, Capability Router, 코딩 에이전트, Git Worktree
- UI 전면 재작성, task_sessions 제거
- ComputerUseAgent PAV 로직 분해
- AgentOrchestrator Task 연동

### 레거시 유지

- `ComputerUseAgent`, `AutomationToolRegistry`, `MonitorManager`
- `task_sessions`, `PendingComputerUseGoal`, `action_plan.PlanStep`
