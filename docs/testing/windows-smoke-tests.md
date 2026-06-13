# Windows 스모크 테스트

## 실행

```bash
cd iris
python -m pytest -m windows_smoke -q
```

기본 `pytest` 실행 시 `windows_smoke` 테스트는 **자동 스킵**됩니다 (`conftest.py`).

## 시나리오

| 테스트 | 내용 |
|--------|------|
| `test_smoke_notepad_launch_and_verify` | 메모장 실행·프로세스 확인 |
| `test_smoke_notepad_type_text` | 메모장 실행·텍스트 입력 |
| `test_smoke_recovery_restart_same_task_id` | Runtime 재생성 후 동일 Task ID 재개 |
| `test_smoke_input_conflict_log` | 입력 충돌 진단 로그 |
| `test_smoke_approval_resume_with_test_tool` | low-risk tool 승인 경로 |

## 규칙

- 사용자 파일 미수정
- 관리자 권한 불필요
- 실패 시 `taskkill /IM notepad.exe /F`로 정리
- CRITICAL shell·결제·삭제 작업 금지

## CI

`windows-smoke.yml` — `workflow_dispatch` 수동 실행 전용.

## 파일

`iris/tests/test_windows_smoke.py`
