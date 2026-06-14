# GitHub Actions

> 상세: [ci-configuration.md](./ci-configuration.md)

## 워크플로

| 파일 | 트리거 | 내용 |
|------|--------|------|
| `.github/workflows/test.yml` | push, PR, dispatch | compileall + pytest (windows_smoke/integration 제외) |
| `.github/workflows/windows-smoke.yml` | workflow_dispatch | `-m windows_smoke` 실환경 GUI |

## test.yml Job

- **test / windows-py311** — Python 3.11, 전체 requirements
- **test / windows-py312** — Python 3.12, 전체 requirements
- **test / linux-domain** — Python 3.12, base + dev only

## 정책

- `continue-on-error` 사용 안 함
- Linux: Windows 전용 패키지 미설치
- 실패 시 `.pytest_cache` artifact 업로드
