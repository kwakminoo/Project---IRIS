# CI·Windows Smoke 현황 분석

> Generated-at: 2026-06-14  
> 기준 브랜치: 작업 시점 working tree

## 1. 기본 CI Workflow

| 항목 | 작업 전 | 작업 후 |
|------|---------|---------|
| 파일 | `.github/workflows/test.yml` | 동일 (Job 분리·이름 정규화) |
| Windows | matrix 3.11/3.12 단일 Job | `windows-py311`, `windows-py312` 분리 |
| Linux | `ubuntu-latest`, `pip install -r requirements.txt` | `requirements-base.txt` + `requirements-dev.txt`만 설치 |
| 제외 | `--ignore=tests/test_windows_smoke.py` | `-m "not windows_smoke and not integration"` |
| pytest-timeout | 미설치 가능 | `requirements-dev.txt`에 명시 |

## 2. Linux에서 설치 불가 Windows 패키지

`requirements.txt`에 플랫폼 구분 없이 포함되어 있던 항목:

- `pywin32`
- `pywinauto`
- `pygetwindow`
- `pyautogui` (Windows GUI 자동화 전용 사용)
- `screeninfo` (Windows 디스플레이 정보)

→ `requirements-windows.txt`로 분리. Linux CI는 `requirements-base.txt` + `requirements-dev.txt`만 설치.

## 3. 테스트·개발 의존성

| 위치 | 내용 |
|------|------|
| 작업 전 | `pytest>=9.0.0`만 `requirements.txt` |
| 작업 후 | `requirements-dev.txt`: pytest, pytest-timeout, pytest-cov |

## 4. pytest marker

| marker | 등록 | 기본 실행 |
|--------|------|-----------|
| `integration` | conftest + pytest.ini | skip |
| `windows_smoke` | conftest + pytest.ini | skip |
| `windows_only` | pytest.ini (신규) | non-Windows skip |
| `slow` | pytest.ini (신규) | 포함 |

## 5. pytest-timeout

- `windows-smoke.yml`에서 `--timeout=120` 사용
- 작업 전: `pytest-timeout` 설치 보장 없음
- 작업 후: `requirements-dev.txt` + CI 설치 경로에 포함

## 6. Windows Smoke Workflow

| 항목 | 작업 전 | 작업 후 |
|------|---------|---------|
| 트리거 | `workflow_dispatch` | 동일 |
| 실행 | `-m windows_smoke -q --timeout=120` | `tests/windows_smoke` + JUnit XML + 로그 |
| Artifact | 실패 시 `.pytest_cache`만 | `always()` — junit, pytest.log, diagnostics |
| Cleanup | 없음 | `always()` notepad 정리 |

## 7. Smoke Test 검증 방식 (작업 전)

| 테스트 | 문제 |
|--------|------|
| `test_smoke_notepad_launch_and_verify` | 프로세스 존재만 확인, Task/Verification 미검증 |
| `test_smoke_notepad_type_text` | 입력 후 UIA 재확인 없음 |
| `test_smoke_recovery_restart_same_task_id` | Task ID만 확인, Plan/Proposal 미검증 |
| `test_smoke_input_conflict_log` | `assert ... or True` — 항상 통과 |
| `test_smoke_approval_resume_with_test_tool` | `get_system_info` (승인 불필요), 검증 불완전 |

추가 문제:

- `_kill_notepad()` — **모든** `notepad.exe` 강제 종료 (사용자 메모장 포함)
- 고정 `sleep()` 위주, 조건 대기 없음
- 실패 진단 artifact 없음

## 8. 항상 통과 Assertion

```python
# test_windows_smoke.py (제거됨)
assert any("input_conflict" in r.message.lower() for r in caplog.records) or True
```

## 9. 실패 시 정리·Artifact (작업 전)

- notepad 전체 taskkill
- Artifact: `.pytest_cache` (실패 시만)

## 10. 개선 방향 요약

1. OS별 requirements 분리
2. CI Job 이름 Branch Protection 준비 (`test / windows-py311` 등)
3. `tests/windows_smoke/` — fixture·diagnostics·강화 assertion
4. 입력 충돌 테스트 제거 → ResourceLease TODO 문서로 이동
5. 승인 테스트 — `smoke_requires_approval` 전용 CRITICAL 도구
