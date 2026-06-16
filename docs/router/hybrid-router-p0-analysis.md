# Hybrid Router P0 분석

## 기준 흐름

```text
Safety
→ Pending Computer Use
→ Recovery
→ Fast Path
→ Unified Router (1회)
→ RouteAnalysis 저장
→ Frontier Policy
→ Frontier 또는 기존 Lane 실행
```

## 1. simple_lane 조기 반환 (변경 전)

`frontier_policy.py`가 `RouteLane.CHAT_ONLY` 등 simple lane에서 `router_flag` 없으면 즉시 `simple_lane` 반환.
`requires_frontier`·operation graph 검사 전에 차단되어 복합 요청이 스킵됨.

## 2. CHAT_ONLY 오분류 원인

Unified Router가 lane만 반환하고 operation graph가 없어 구조화 판단 불가.
텍스트 정규식(`_EXPLAIN`, `_EXEC`)에 의존하던 이전 정책도 lane이 CHAT_ONLY면 무시됨.

## 3. Frontier 호출 전제조건 (변경 후)

- `RouteAnalysis` 기반
- ORCHESTRATED lane
- `requires_frontier` / incomplete analysis
- 의존 operation graph (단일 search→respond 제외)
- response + execution 결합
- cross-capability / conditional / monitoring 흐름

## 4. Unified Route 캐시

`TurnCoordinator._route_once()` — hybrid 경로에서 1회만 호출.
Frontier 실패 시 `routed_turn` 재사용 (`frontier_fallback_unified`).

## 5. Frontier 실패 폴백

`run_frontier_turn` → `None`이면 cached `routed_turn`으로 `_dispatch_routed_turn` — Unified 재호출 없음.

## 6. 라우터 중복 호출

`_route_once` 단일 진입. `frontier_first` 모드만 Frontier 실패 시 Unified 1회.

## 7. 테스트 실패 원인 (수정 전)

| 테스트 | 원인 |
|--------|------|
| `test_route_steam_launch_not_search` | `assistant._settings` AttributeError |
| Frontier F 카테고리 | simple_lane 조기 반환 |
| `test_hybrid_unified_delegates_search` | `route_analysis=None` → incomplete → Frontier |

## 8. 수정 파일

- `iris/iris/assistant/route_analysis.py` (신규)
- `iris/iris/assistant/unified_router.py`
- `iris/iris/assistant/frontier_policy.py`
- `iris/iris/assistant/router_policy.py`
- `iris/iris/assistant/fast_path.py`
- `iris/iris/assistant/turn_coordinator.py`
- `iris/tests/test_route_analysis.py` (신규)
- `iris/tests/test_frontier_policy.py`
- `iris/tests/test_hybrid_router_flow.py`
