# Windows 스모크 테스트

## 실행

```bash
cd iris
python -m pytest tests/windows_smoke -m windows_smoke -v --timeout=120
```

기본 `pytest` 실행 시 `windows_smoke`·`integration`은 **자동 skip** (`conftest.py`).

GitHub Actions: **Actions → Windows Smoke → Run workflow**

## 디렉터리

```text
iris/tests/windows_smoke/
  conftest.py          # fixture, 실패 진단 hook
  diagnostics.py       # 창·프로세스·UIA·스크린샷
  smoke_tools.py       # smoke_requires_approval (CRITICAL 테스트 도구)
  test_smoke_scenarios.py
```

## 시나리오

| 테스트 | 검증 |
|--------|------|
| `test_smoke_notepad_launch_creates_verified_task` | launch_app → PID·창 → ActionAttempt/Result → Verification SUCCESS → Step SUCCEEDED → Task COMPLETED |
| `test_smoke_notepad_text_input_is_read_back` | fixture Notepad PID → 포커스 → type_text → UIA Document/Edit marker |
| `test_smoke_approval_executes_exact_proposal_once` | 승인 전 미실행 → WAITING_APPROVAL → grant → Attempt 1회 → marker 파일 |
| `test_smoke_runtime_restart_preserves_task_identity` | Runtime 재생성 → Task/Plan/Step/Proposal ID 유지, FK check |

## 제거된 테스트

| 이전 | 사유 |
|------|------|
| `test_smoke_input_conflict_log` | `assert ... or True` — 무효. ResourceLease 구현 전까지 `docs/testing/windows-smoke-diagnostics.md` TODO 참고 |

## 규칙

- 테스트가 **시작한 Notepad PID만** 종료 (`notepad_session` fixture)
- 사용자 파일 저장 안 함 — 종료 시 “저장 안 함” 처리
- CRITICAL shell·결제·삭제 금지
- 병렬 실행 금지 (GUI 포커스 충돌)

## 환경 변수

| 변수 | 기본 | 설명 |
|------|------|------|
| `IRIS_SMOKE_ARTIFACTS` | `artifacts/windows-smoke` | 진단 출력 경로 |
| `IRIS_SMOKE_SCREENSHOTS` | GITHUB_ACTIONS=1 이면 `1` | 실패 스크린샷 |

## CI Artifact

- `junit.xml`
- `pytest.log`
- `artifacts/windows-smoke/<test-name>/diagnostics.json`
- (활성화 시) `screenshot.png`
