# GitHub Actions

## 워크플로

| 파일 | 트리거 | 내용 |
|------|--------|------|
| `.github/workflows/test.yml` | push, PR | compileall + pytest (windows_smoke 제외) |
| `.github/workflows/windows-smoke.yml` | workflow_dispatch | `-m windows_smoke` |

## test.yml Job

- **test-windows**: Python 3.11, 3.12 matrix
- **test-linux**: Python 3.12 (Windows 의존 기능 제외 검증)

각 Job:

1. `pip install -r iris/requirements.txt`
2. `python -m compileall iris -q`
3. `python -m pytest -q --ignore=tests/test_windows_smoke.py`

## 정책

- `continue-on-error` 사용 안 함
- 핵심 테스트 skip 안 함 (integration·windows_smoke만 기본 제외)
- 실패 시 `.pytest_cache` artifact 업로드

## 로컬 동일 검증

```bash
python -m compileall iris -q
cd iris && python -m pytest -q
```
