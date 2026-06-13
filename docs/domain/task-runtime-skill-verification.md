# Skill 검증 — 공통 VerificationResult 통합

## 문제

Skill Flow(text_compose, send_message)는 Tool attempt는 기록했으나 checkpoint 검증 결과가 `verification_results`에 저장되지 않았습니다.

## 해결

```text
Skill Step
→ run_tool_recorded() → ActionProposal / ActionAttempt / ActionResult
→ mechanical/LLM checkpoint
→ ComputerUseAgent.record_skill_checkpoint()
→ CuTaskAdapter.on_skill_checkpoint_verified()
→ VerificationService.record_skill_checkpoint()
→ finalize_step_from_verification()
→ on_cu_finished() (checkpoint 결과 우선)
```

## 규칙

- Skill 성공 문자열만으로 Task 완료 금지 (`_skill_final_achieved` 플래그)
- `PARTIAL`: 일부 checkpoint만 성공 시 `StepStatus.PARTIALLY_SUCCEEDED`
- Evidence에 `related_attempt_ids` 연결
- Attempt 없으면 VerificationResult 생성 안 함

## Checkpoint 예시

| Skill | Checkpoint |
|-------|------------|
| text_compose | cp_app_open, cp_focus, cp_text_typed |
| send_message | cp_message_sent |

## 관련 파일

- `iris/application/verification_service.py` — `record_skill_checkpoint()`
- `iris/infrastructure/adapters/cu_task_adapter.py` — `on_skill_checkpoint_verified()`
- `iris/assistant/computer_use_agent.py` — `record_skill_checkpoint()`
- `iris/assistant/text_compose_flow.py`
- `iris/assistant/send_message_flow.py`
