# CI 구성

## Workflow

| 파일 | Job 이름 | 트리거 | OS |
|------|----------|--------|-----|
| `.github/workflows/test.yml` | `test / windows-py311` | push, PR, dispatch | windows-latest |
| `.github/workflows/test.yml` | `test / windows-py312` | push, PR, dispatch | windows-latest |
| `.github/workflows/test.yml` | `test / linux-domain` | push, PR, dispatch | ubuntu-latest |
| `.github/workflows/windows-smoke.yml` | `windows-smoke` | workflow_dispatch | windows-latest |

## Branch Protection (권장 Required Checks)

- `test / windows-py311`
- `test / windows-py312`
- `test / linux-domain`

`windows-smoke`는 수동 실행 — 초기 Required Check 아님.

## 의존성 설치

### Windows (로컬·CI)

```bash
cd iris
pip install -r requirements.txt
```

포함: `requirements-base.txt` + `requirements-windows.txt` + `requirements-dev.txt`

### Linux CI

```bash
cd iris
pip install -r requirements-base.txt -r requirements-dev.txt
```

Windows 전용 패키지(`pywin32`, `pywinauto` 등)는 설치하지 않음.

## CI 명령 (Windows·Linux 공통 패턴)

```bash
python -m compileall iris -q
cd iris && python -m pytest -q -m "not windows_smoke and not integration"
```

Linux 추가 제외:

```bash
python -m pytest -q -m "not windows_smoke and not integration and not windows_only"
```

## Badge (README 추가 예시)

```markdown
![Test](https://github.com/<owner>/IRIS/actions/workflows/test.yml/badge.svg)
```

## Artifact

| Workflow | 조건 | 내용 |
|----------|------|------|
| test.yml | failure | `.pytest_cache/` |
| windows-smoke.yml | always | `artifacts/windows-smoke/` (junit, log, diagnostics) |

## 로컬 동일 검증

```bash
python -m compileall iris -q
cd iris && python -m pytest -q
cd iris && python -m pytest tests/test_ci_config.py -q
```

## 정책

- `continue-on-error: true` 사용 안 함
- 실패 테스트 skip으로 CI 녹색 처리 금지
- Linux에서 Domain/Application 계층 import 가능 (Windows 전용 모듈 lazy import)
