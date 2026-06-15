# Windows Smoke 실행 가이드

## Workflow

- 파일: `.github/workflows/windows-smoke.yml`
- 트리거: **수동** (`workflow_dispatch`)
- 입력: `include_gui` — GUI smoke 포함 여부 (기본 `true`)

## 시나리오

| 테스트 | 유형 | 검증 |
|--------|------|------|
| `test_smoke_notepad_launch_creates_verified_task` | GUI | launch_app → PID·창·Verification |
| `test_smoke_notepad_text_input_is_read_back` | GUI | type_text → UIA 재확인 |
| `test_smoke_approval_executes_exact_proposal_once` | non-GUI | 승인 전 미실행 → 1회 실행 |
| `test_smoke_runtime_restart_preserves_task_identity` | non-GUI | Runtime 재생성 → 동일 Task ID |

## GitHub Actions 실행

```bash
gh workflow run windows-smoke.yml
gh workflow run windows-smoke.yml -f include_gui=false   # non-GUI만
gh run list --workflow windows-smoke.yml
gh run watch
```

UI: **Actions → Windows Smoke → Run workflow**

## Hosted Runner vs 로컬

| 구분 | non-GUI smoke | GUI smoke (Notepad·UIA) |
|------|---------------|-------------------------|
| GitHub Hosted (`windows-latest`) | **통과 가능** | Session 0 / 비대화형 제약으로 **불안정·실패 가능** |
| 로컬 Windows 11 | 통과 | **권장** |
| self-hosted Runner | 통과 | 대화형 세션 구성 시 통과 |

다음 단계 진입 조건 (B):

- GitHub **non-GUI smoke** 성공
- **로컬 Windows GUI smoke** 성공 + 로그/artifact 저장

## Cleanup 안전성

- 테스트 fixture가 `artifacts/windows-smoke/created-processes.json`에 **직접 생성한 PID만** 등록
- Workflow·로컬 스크립트는 `scripts/cleanup-smoke-processes.ps1`로 **등록 PID만** 종료
- 사용자가 기존에 연 메모장은 종료하지 않음
- PID 재사용 방지: `create_time` + 프로세스 이름 확인

## 로컬 실행

```powershell
cd iris
python -m pytest tests/windows_smoke -m "windows_smoke and not windows_smoke_gui" -v --timeout=120
python -m pytest tests/windows_smoke -m windows_smoke_gui -v --timeout=120
```

또는:

```powershell
.\scripts\verify-next-stage.ps1 -IncludeSmoke
.\scripts\verify-next-stage.ps1 -IncludeSmoke -IncludeGuiSmoke
```

## Artifact

`iris/artifacts/windows-smoke/`:

- `junit-nogui.xml`, `junit-gui.xml`
- `pytest-nogui.log`, `pytest-gui.log`
- `created-processes.json`
- 테스트별 `diagnostics.json`

## 금지

- `assert True`, `assert x or True`, `assert result is not None`만으로 통과 처리
- Mock으로 GUI 검증 대체
- 모든 `notepad.exe` 무조건 종료
