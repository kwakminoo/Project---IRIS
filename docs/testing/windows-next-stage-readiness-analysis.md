# Windows 다음 단계 진입 준비 — 현황 분석

> 기준 커밋: `1f06c89` — Stabilize CI workflows and strengthen Windows smoke test verification.

## 1. 현재 Windows CI Job 구성

| Job | OS | Python | pytest 명령 |
|-----|-----|--------|-------------|
| `test / windows-py311` | windows-latest | 3.11 | `-m "not windows_smoke and not integration"` |
| `test / windows-py312` | windows-latest | 3.12 | `-m "not windows_smoke and not integration"` |
| `test / linux-domain` | ubuntu-latest | 3.12 | `-m "not windows_smoke and not integration and not windows_only"` |

Windows 기본 Job은 compileall, pytest-timeout 확인, 의존성 설치를 수행한다.
**문제:** Integration Test가 기본 Windows CI에서 전부 제외되어 Task Runtime·Computer Use 연결 검증이 PR 관문에 포함되지 않는다.

## 2. Integration Test가 제외되는 위치

`.github/workflows/test.yml` 43·80행:

```yaml
python -m pytest -q -m "not windows_smoke and not integration"
```

`iris/tests/conftest.py`의 `pytest_collection_modifyitems`는 `-m` 미지정 로컬 실행 시 integration/windows_smoke를 skip한다.
CI에서 `-m "not integration"`을 명시하면 integration 마커 테스트는 수집·제외된다.

## 3. integration 마커가 붙은 테스트 목록 (작업 전)

| 파일 | 테스트 |
|------|--------|
| `test_computer_use_integration.py` | `test_notepad_perceive_integration`, `test_send_hotkey_smoke` |

대부분의 Task Runtime·승인·복구·Migration 테스트는 integration 마커 없이 단위 Job에만 포함되거나, 별도 Job 없이 실행되지 않는다.

## 4. Windows Smoke 테스트 시나리오 목록

`iris/tests/windows_smoke/test_smoke_scenarios.py`:

| 테스트 | 영역 | GUI |
|--------|------|-----|
| `test_smoke_notepad_launch_creates_verified_task` | launch_app → PID·창·Verification | 예 |
| `test_smoke_notepad_text_input_is_read_back` | type_text → UIA 재확인 | 예 |
| `test_smoke_approval_executes_exact_proposal_once` | 승인 전 미실행 → 1회 실행 | 아니오 |
| `test_smoke_runtime_restart_preserves_task_identity` | Runtime 재생성 → 동일 Task ID | 아니오 |

## 5. Smoke Workflow의 실제 실행 가능성

- 트리거: `workflow_dispatch` (수동)
- Runner: `windows-latest`
- **non-GUI smoke** (승인·복구·FK): Hosted Runner에서 실행 가능
- **GUI smoke** (Notepad·UIA): Hosted Runner에서 Session 0 / 비대화형 데스크톱 제약으로 **불안정 또는 실패 가능**
- Cleanup: 제목 기반 `notepad` 프로세스 종료 — self-hosted/로컬에서 사용자 메모장 오종료 위험

## 6. Linux Job을 제거하거나 비필수로 전환하는 방법

권장:

1. `test.yml`에서 `linux-domain` Job 제거
2. `.github/workflows/linux-experimental.yml` 신설 — `on: workflow_dispatch` 만
3. Branch Protection Required Checks에서 `test / linux-domain` 제외
4. `docs/testing/windows-ci-policy.md`에 Windows 필수·Linux 실험적 정책 기록

Linux Domain 코드·requirements 분리 구조는 유지한다.

## 7. 다음 단계 진입을 막는 실제 문제

| # | 문제 | 영향 |
|---|------|------|
| 1 | Integration Test가 Windows 기본 CI에서 제외 | Task Runtime 연결 회귀 미탐지 |
| 2 | Integration 전용 Job 없음 | 컴포넌트 간 연결 검증 관문 부재 |
| 3 | Linux Job이 Required Check | Windows 우선 정책과 충돌 |
| 4 | Smoke Cleanup이 제목 기반 | 로컬/self-hosted 메모장 오종료 |
| 5 | 로컬 일괄 검증 스크립트 없음 | 개발자 품질 관문 분산 |
| 6 | `external_service`/`requires_model` 마커 미등록 | CI 제외 규칙 불완전 |
| 7 | GUI Smoke Hosted Runner 제약 미문서화 | 실패 원인 혼동 |

## 8. 수정 예정 파일 목록

| 파일 | 변경 |
|------|------|
| `.github/workflows/test.yml` | Windows 기본 pytest 범위, integration Job 추가, Linux 제거 |
| `.github/workflows/linux-experimental.yml` | 신규 — 수동 Linux 실험 |
| `.github/workflows/windows-smoke.yml` | non-GUI/GUI 분리, PID 기반 cleanup |
| `iris/pytest.ini` | 마커 정의 확장 |
| `iris/tests/conftest.py` | integration 자동 마킹, 마커 skip 정책 |
| `iris/tests/test_ci_config.py` | CI 정책 자동 검증 테스트 |
| `iris/tests/test_smoke_process_cleanup.py` | Smoke cleanup 검증 |
| `iris/tests/windows_smoke/conftest.py` | PID 등록 fixture |
| `iris/tests/windows_smoke/diagnostics.py` | created-processes.json |
| `iris/tests/windows_smoke/test_smoke_scenarios.py` | GUI 마커 |
| `scripts/verify-next-stage.ps1` | 로컬 품질 관문 |
| `scripts/cleanup-smoke-processes.ps1` | Workflow cleanup |
| `docs/testing/windows-ci-policy.md` | 신규 |
| `docs/testing/windows-integration-tests.md` | 신규 |
| `docs/testing/windows-smoke-execution.md` | 신규 |
| `docs/testing/windows-next-stage-readiness-result.md` | 신규 — 최종 판정 |
| `docs/testing/ci-configuration.md` | Windows 우선 정책 반영 |
| `iris/README.md` | Primary platform 명시 |
