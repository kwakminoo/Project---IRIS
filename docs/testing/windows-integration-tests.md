# Windows Integration Tests

## 목적

Task Runtime·Computer Use·승인·복구·SQLite 무결성 등 **컴포넌트 간 실제 연결**을 검증합니다.
Windows 기본 CI(`windows-py311`/`windows-py312`)에도 integration 마커 테스트가 포함되며, `test / windows-integration` Job에서 집중 실행합니다.

## 실행

```powershell
cd iris
python -m pytest -v -m "integration and not windows_smoke and not external_service and not requires_model" --timeout=180
```

## 검증 영역

| 영역 | 대표 테스트 모듈 |
|------|------------------|
| IrisAssistant → ComputerUseAgent | `test_task_runtime_phase1_injection`, `test_task_runtime_real_integration` |
| ComputerUseAgent → Task Runtime | `test_task_runtime_real_integration` |
| Quick Launch → Task·Plan·Step | `test_task_runtime_phase2_task_creation`, `test_task_runtime_stabilization` |
| Action Skill → Attempt·Verification | `test_task_runtime_skill_verification`, `test_task_runtime_phase3_recording` |
| Approval → ExecutionCoordinator | `test_execution_coordinator`, `test_task_runtime_stabilization` |
| Task 재시작 복구 | `test_task_runtime_recovery_commands`, `test_task_runtime_stabilization` |
| SQLite Migration | `test_sqlite_task_repositories`, `test_task_runtime_stabilization` |
| Foreign Key 무결성 | `test_task_runtime_stabilization::test_foreign_key_check_has_no_errors` |

## 마커 부착 규칙

- `iris/tests/conftest.py`의 `_INTEGRATION_MODULES` — 모듈 전체가 연결 검증인 파일
- `_INTEGRATION_TESTS` — 혼합 모듈 내 개별 테스트
- GUI·실앱 의존 테스트는 `windows_smoke` / `windows_smoke_gui` 사용

## 제외

- `external_service` — 외부 HTTP/API (예: 실제 IntegrationClient 호출)
- `requires_model` — Ollama/LM Studio 등 실제 LLM 필요
- `windows_smoke` — Notepad·UIA 실환경 (Smoke Workflow)

## 회귀 정책

- 실패 테스트를 skip으로 녹색 처리하지 않음
- Mock으로 실제 연결 검증을 제거하지 않음
- `continue-on-error` 사용 안 함
