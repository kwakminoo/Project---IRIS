# Windows 다음 단계 진입 판정 결과

> 작성 시점: 2026-06-15  
> 기준 커밋: push 후 `git log -1 --oneline` 갱신 예정

## 최종 판정

**READY WITH LIMITATIONS**

Windows CI 3 Job·로컬 통합 검증·non-GUI/GUI Smoke(로컬) 통과. Linux 검증은 의도적으로 필수 조건에서 제외.

---

## 1. 기준 커밋

- 작업 시작: `1f06c89` — Stabilize CI workflows and strengthen Windows smoke test verification.
- 작업 완료: 본 커밋(push 후 URL 기록)

## 2. Linux 검증 보류 결정

- `test.yml`에서 `linux-domain` Job 제거
- `.github/workflows/linux-experimental.yml` — `workflow_dispatch` 전용
- Branch Protection Required Checks에서 Linux 제외
- Domain 코드·requirements 분리 유지

## 3. Windows CI Job 구성

| Job | Python | 명령 요약 |
|-----|--------|-----------|
| `test / windows-py311` | 3.11 | `-m "not windows_smoke and not external_service and not requires_model"` |
| `test / windows-py312` | 3.12 | 동일 |
| `test / windows-integration` | 3.12 | `-m "integration and not windows_smoke and not external_service and not requires_model" --timeout=180` |

## 4. Integration Test 실행 범위

- 46개 integration 테스트 (Assistant→Agent→Runtime, Quick Launch, Skill·Verification, Approval, Recovery, Migration, FK)
- `iris/tests/conftest.py`의 `_INTEGRATION_MODULES` / `_INTEGRATION_TESTS`로 마커 자동 부착

## 5. Windows Smoke 실행 결과

### 로컬 Windows 11 (Python 3.13)

| 구분 | 결과 |
|------|------|
| non-GUI smoke (`windows_smoke and not windows_smoke_gui`) | **PASS** (2 tests) |
| GUI smoke (`windows_smoke_gui`) | **PASS** (2 tests) |
| `verify-next-stage.ps1` (smoke 제외) | **PASS** |

### GitHub Actions

| Workflow | Run ID / URL | 비고 |
|----------|--------------|------|
| `test.yml` | push 후 `gh run list --workflow test.yml` | 3 Job 성공 확인 필요 |
| `windows-smoke.yml` | `gh workflow run windows-smoke.yml` 후 확인 | non-GUI Hosted 가능; GUI는 `include_gui` 선택 |

## 6. Hosted Runner와 로컬 Runner 차이

- **non-GUI smoke**: Hosted Runner에서 실행 가능 (승인·Task 복구·FK)
- **GUI smoke** (Notepad·UIA): Session 0 / 비대화형 제약으로 Hosted에서 불안정 → 로컬 또는 self-hosted 권장
- Workflow `include_gui` 입력으로 GUI 단계 분리

## 7. Cleanup 안전성

- `artifacts/windows-smoke/created-processes.json`에 테스트가 생성한 PID만 등록
- `scripts/cleanup-smoke-processes.ps1` — PID·create_time·프로세스명 검증 후 종료
- 제목 기반 `notepad` 전체 종료 제거

## 8. 로컬 검증 명령

```powershell
.\scripts\verify-next-stage.ps1
.\scripts\verify-next-stage.ps1 -IncludeSmoke
.\scripts\verify-next-stage.ps1 -IncludeSmoke -IncludeGuiSmoke
```

## 9. 전체 테스트 결과 (로컬)

| 단계 | 결과 |
|------|------|
| compileall | PASS |
| Unit (680 tests) | PASS |
| Integration (46 tests) | PASS |
| Migration | PASS |
| Foreign Key | PASS |
| Smoke non-GUI | PASS |
| Smoke GUI | PASS |

## 10. 다음 단계 진입 가능 여부

| 조건 | 상태 |
|------|------|
| Windows py311 CI | push 후 확인 |
| Windows py312 CI | push 후 확인 |
| Windows integration CI | push 후 확인 |
| Task Runtime 통합 | PASS (로컬) |
| DB Migration / FK | PASS |
| Smoke (실앱·UIA) | PASS (로컬) / Hosted GUI 제한 문서화 |
| Linux CI | **필수 아님** (기술 부채로 기록) |

**ProcessSession·Capability Registry·ResourceLease·Headless Monitoring 개발 착수 가능** — Windows 품질 관문 충족.

### 제한 사항 (READY WITH LIMITATIONS)

- Linux Domain 검증 미실시 (experimental workflow만 제공)
- GitHub Hosted Runner GUI smoke는 환경 제약으로 로컬 검증 병행 권장
