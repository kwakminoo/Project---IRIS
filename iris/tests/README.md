# Iris 테스트

## 실행

```powershell
cd iris
python -m pytest -q
python -m pytest -m integration   # Windows GUI 통합만
```

## 구조

| 경로 | 역할 |
|------|------|
| `conftest.py` | `load_test_settings`, integration 마커 |
| `support/fakes.py` | `FakeGemma`, `ApprovalGemma`, `RoutingGemma`, `make_test_assistant` |
| `test_*.py` | 모듈별 단위·통합 테스트 |

## 규칙 (현재 API 기준)

- Gemma mock은 반드시 `purpose=` 키워드를 받을 것.
- `Settings(...)` 수동 생성 금지 → `load_test_settings(tmp_path)` 사용.
- `IrisAssistant`는 `make_test_assistant` / `make_routing_assistant` 사용.
- 레거시 `AgentOrchestrator` 전용 스모크는 `test_safety_tool_registry.py`만 유지.
