# IRIS Windows CI 정책

## 공식 플랫폼

| 항목 | 값 |
|------|-----|
| Primary supported development platform | **Windows 11** |
| Required CI platform | **Windows** (`windows-latest`) |
| Linux CI | **experimental / deferred** |

Iris는 Windows 우선 실행형 비서입니다. 다음 단계(ProcessSession, Capability Registry 등) 진입 품질 관문은 **Windows CI 3 Job** 기준입니다.

## Required Checks (Branch Protection 권장)

| Check | 설명 |
|-------|------|
| `test / windows-py311` | Python 3.11 단위·Task Runtime·Migration |
| `test / windows-py312` | Python 3.12 동일 범위 |
| `test / windows-integration` | 컴포넌트 간 연결 integration |

`test / linux-domain`은 **Required Check 아님**. Linux 검증은 `.github/workflows/linux-experimental.yml`을 **수동 실행**합니다.

## pytest 마커와 CI 범위

| 마커 | Windows 기본 CI | Integration Job | Smoke Workflow |
|------|-----------------|-----------------|----------------|
| (기본) | 포함 | — | — |
| `integration` | 포함 | **선택 실행** | — |
| `windows_smoke` | 제외 | 제외 | 포함 |
| `windows_smoke_gui` | 제외 | 제외 | 선택(GUI) |
| `external_service` | 제외 | 제외 | 제외 |
| `requires_model` | 제외 | 제외 | 제외 |

### Windows 기본 CI 명령

```powershell
cd iris
python -m pytest -q -m "not windows_smoke and not external_service and not requires_model"
```

### Integration Job 명령

```powershell
cd iris
python -m pytest -v -m "integration and not windows_smoke and not external_service and not requires_model" --timeout=180
```

## Linux 보류

- Linux Domain 코드·`requirements-base.txt` 분리는 **유지**
- Linux 전용 코드 삭제 없음
- 향후 Linux 검증 재활성화: `linux-experimental.yml` dispatch

## 로컬 검증

```powershell
.\scripts\verify-next-stage.ps1
.\scripts\verify-next-stage.ps1 -IncludeSmoke
.\scripts\verify-next-stage.ps1 -IncludeSmoke -IncludeGuiSmoke
```
