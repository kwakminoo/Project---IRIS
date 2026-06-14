# Windows Smoke 진단

## Helper (`tests/windows_smoke/diagnostics.py`)

| 함수 | 출력 |
|------|------|
| `capture_active_window()` | 활성 창 title, hwnd, pid |
| `dump_open_windows()` | 가시 창 목록 |
| `dump_process_state(pid)` | psutil 프로세스 상태 |
| `capture_screenshot(path)` | 전체 화면 PNG |
| `dump_uia_tree(hwnd)` | UIA 트리 JSON (depth 제한) |
| `dump_task_history(db, task_id)` | Task·Plan·Attempt·Verification |
| `write_diagnostic_bundle(test_name, **sections)` | 위 정보 + JSON 파일 |

## Artifact 경로

```text
artifacts/windows-smoke/<test-name>/
  diagnostics.json
  screenshot.png   # IRIS_SMOKE_SCREENSHOTS=1
```

## pytest 실패 hook

`tests/windows_smoke/conftest.py` — `pytest_runtest_makereport`에서 `windows_smoke` 실패 시 자동 저장.

## CI 업로드

`windows-smoke.yml` — `if: always()`:

- `iris/artifacts/windows-smoke/`
- `iris/.pytest_cache/`

## 스크린샷 비활성화 (로컬)

```powershell
$env:IRIS_SMOKE_SCREENSHOTS = "0"
python -m pytest tests/windows_smoke -m windows_smoke -v
```

## Notepad UIA Selector 폴백 순서

1. `control_type="Document"` (Windows 11 Notepad)
2. `control_type="Edit"` (레거시)
3. `descendants()` 편집 가능 컨트롤
4. 실패 시 `dump_uia_tree` → diagnostics.json

## Cleanup

| 대상 | 방식 |
|------|------|
| `notepad_session` fixture | `close_notepad_without_save` → `taskkill /PID <pid> /T` |
| CI always step | IRIS_SMOKE marker·무제 Notepad만 선택 종료 |
| **금지** | `taskkill /IM notepad.exe /F` (전체 사용자 메모장) |

## TODO — 입력 충돌 (ResourceLease 전)

다음은 **자동 스모크 테스트 대상 아님**:

- 사용자 입력 Hook 실시간 감지
- ResourceLease 기반 포커스/입력 임대
- 포커스 이탈 시 입력 차단

구현 후 `test_smoke_input_conflict_*` 시리즈 추가 예정.

## Task DB 덤프 (민감정보)

Smoke 테스트는 `tmp_path` SQLite만 사용. CI Artifact 업로드 시 전체 화면·사용자 DB 업로드 금지 — 테스트 DB만 `dump_task_history` JSON으로 포함.
