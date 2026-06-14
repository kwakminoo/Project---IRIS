# CI·Windows Smoke 개선 결과

> Generated-at: 2026-06-14

## 1. 기존 CI 실패 원인

| 원인 | 설명 |
|------|------|
| Linux + `requirements.txt` | `pywin32` 등 Windows 전용 wheel 미제공 → pip install 실패 가능 |
| pytest-timeout 미포함 | `windows-smoke.yml`의 `--timeout=120` 무력화 |
| Linux/Windows 동일 install | Windows UI 패키지를 Linux에 강제 설치 |

## 2. 운영체제별 의존성 처리

```text
iris/requirements-base.txt     # OS 독립
iris/requirements-windows.txt # pywin32, pywinauto, pygetwindow, pyautogui, screeninfo
iris/requirements-dev.txt     # pytest, pytest-timeout, pytest-cov
iris/requirements.txt         # -r base + windows + dev (로컬 Windows 전체)
```

- Linux CI: `pip install -r requirements-base.txt -r requirements-dev.txt`
- Windows CI: `pip install -r requirements.txt`

## 3. GitHub Actions Job 구성

| Job | Runner | Python | Required Check 이름 |
|-----|--------|--------|---------------------|
| windows-py311 | windows-latest | 3.11 | `test / windows-py311` |
| windows-py312 | windows-latest | 3.12 | `test / windows-py312` |
| linux-domain | ubuntu-latest | 3.12 | `test / linux-domain` |
| windows-smoke | windows-latest | 3.12 | (수동, Required 아님) |

## 4. Smoke Workflow 실행 방법

GitHub → Actions → **Windows Smoke** → Run workflow

로컬:

```bash
cd iris
python -m pytest tests/windows_smoke -m windows_smoke -v --timeout=120
```

## 5. 실제 Windows 검증 항목

| 테스트 | 검증 |
|--------|------|
| `test_smoke_notepad_launch_creates_verified_task` | launch_app, PID, 창, Attempt/Result, Verification SUCCESS, Step SUCCEEDED, Task COMPLETED |
| `test_smoke_notepad_text_input_is_read_back` | 포커스, type_text, UIA Document marker |
| `test_smoke_approval_executes_exact_proposal_once` | 승인 전 미실행, WAITING_APPROVAL, Attempt 1회, marker 파일 |
| `test_smoke_runtime_restart_preserves_task_identity` | Runtime 재생성, Task/Plan/Step/Proposal ID, FK check |

## 6. 제거한 무효 Assertion

- `assert any(...) or True` (`test_smoke_input_conflict_log`) — 테스트 삭제
- 전체 `taskkill /IM notepad.exe` — PID 추적 cleanup으로 대체

## 7. 테스트 Cleanup 방식

- `notepad_session`: 시작 PID만 `close_notepad_without_save` + `taskkill /PID`
- CI `always()` step: IRIS_SMOKE·무제 Notepad 선택 종료
- 사용자 메모장 일괄 종료 금지

## 8. 실패 Artifact 목록

`artifacts/windows-smoke/<test-name>/`:

- `diagnostics.json` — 활성 창, 열린 창, 프로세스, task history
- `screenshot.png` — `IRIS_SMOKE_SCREENSHOTS=1` 또는 GITHUB_ACTIONS

CI 업로드: `junit.xml`, `pytest.log`, diagnostics 디렉터리

## 9. 로컬 최종 실행 결과

| 명령 | 결과 |
|------|------|
| `python -m compileall iris -q` | OK |
| `pytest -m "not windows_smoke and not integration"` | **667 passed** |
| `pytest tests/test_ci_config.py` | **7 passed** |
| `pytest tests/windows_smoke -m windows_smoke` | **4 passed** |

환경: Windows, Python 3.13.7 (CI는 3.11/3.12 matrix)

## 10. 다음 단계 진입 가능 여부

| 항목 | 상태 |
|------|------|
| 기본 CI Branch Protection | Job 이름 정규화 완료 — GitHub 설정만 필요 |
| Windows Smoke self-hosted 정기 실행 | workflow_dispatch 안정 — runner 추가 후 cron 확장 가능 |
| 입력 충돌 자동 검증 | **불가** — ResourceLease 선행 필요 (`windows-smoke-diagnostics.md` TODO) |
| ProcessSession / ResourceLease | 본 작업 범위 외 |

## 부가 변경 (최소)

- `CuTaskAdapter._verify_launch_target`: launch_app 후 창 폴링 (최대 ~6초) — 스모크·실사용 안정화
- `AutomationToolRegistry.register_tool`: 스모크 전용 CRITICAL 도구 등록

## 변경 파일 요약

```text
iris/requirements*.txt
iris/pytest.ini
.github/workflows/test.yml
.github/workflows/windows-smoke.yml
iris/tests/windows_smoke/
iris/tests/test_ci_config.py
iris/tests/conftest.py
iris/iris/automation/tool_registry.py
iris/iris/infrastructure/adapters/cu_task_adapter.py
docs/testing/*.md
(삭제) iris/tests/test_windows_smoke.py
```
