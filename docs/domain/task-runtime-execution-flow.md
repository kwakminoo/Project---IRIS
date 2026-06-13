# Task Runtime 실행 흐름 (수정 후)

## 공통 진입

```
사용자 요청
→ CuTaskAdapter.begin_cu_session (Task + Ad-hoc Plan + Step)
→ 경로 선택
→ ExecutionCoordinator.execute_step / execute_proposal
→ ActionAttempt + ActionResult
→ StepStatus.VERIFYING
→ Checkpoint 또는 lightweight verify
→ VerificationResult
→ Step SUCCEEDED / FAILED (검증 후만)
→ TaskResult
```

## 12개 경로

| 경로 | Task | 실행 | 검증 |
|------|------|------|------|
| Quick Launch | begin_cu_session | execute_tool_step | lightweight finalize |
| Action Skill | begin_cu_session | execute_tool_step | lightweight finalize |
| Tier1 | create_automation_task | execute_tool_step | lightweight finalize |
| PAV | begin_cu_session | on_tool_execute + record_tool_result | checkpoint verify |
| Full Plan | on_full_plan_created | _execute_tool | checkpoint verify |
| 1-Step fallback | ensure_active_plan | _execute_tool | checkpoint verify |
| CRITICAL 승인 | execute_step(run_tool=False) | — | checkpoint 저장 |
| 승인 재개 | attach_task | execute_proposal | checkpoint verify |
| ask_user | WAITING_USER | — | — |
| max_steps | SUSPENDED | — | — |
| 앱 재시작 | RecoveryService | resume_task | checkpoint 복원 |
| init 실패 | health.failed | legacy fallback 금지(로그) | — |

## execute_proposal

승인 재개와 일반 실행의 공통 경로. `approval_id`로 grant·hash·expires 검증 후 Attempt/Result 기록.
