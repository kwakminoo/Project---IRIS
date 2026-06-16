# Hybrid Router P0 결과

## 1. 기준 커밋

- 작업 시작: `feat/iris-ide-terminal` @ `8d0b78a`
- origin/main 기준: `0319560`

## 2. 브랜치 정리

- IDE 변경: `feat/iris-ide-terminal` (UI·테마 커밋 분리)
- 라우터 변경: `fix/hybrid-router-frontier-policy` (main 기반)

## 3. 변경 전 구조

Lane + 텍스트 정규식 → simple_lane 조기 반환 → Frontier 스킵

## 4. 변경 후 구조

```text
Safety / Pending / Recovery
→ Fast Path (Intent Catalog)
→ Unified Router 1회 → RouteAnalysis
→ Frontier Policy (operation graph)
   ├─ 단순: Lane 실행
   └─ 복합: Frontier → 실패 시 cached route
```

## 5. RouteAnalysis

`iris/iris/assistant/route_analysis.py` — OperationKind, RouteOperation, RouteAnalysis, parser, legacy adapter

## 6. Frontier 호출 기준

ORCHESTRATED, incomplete analysis, requires_frontier, dependent graph, response+execution, cross-capability, conditional/monitoring

## 7. simple_lane 조기 반환

제거 — structured 검사 후 마지막에 simple lane 허용

## 8. F 카테고리

5/5 Frontier 호출 (테스트 `test_f_category_invokes_frontier_once`)

## 9. 오탐 방지

6건 단순 요청 Frontier 0회 (`test_simple_requests_skip_frontier`)

## 10. 모델 호출 수

- Unified: 턴당 최대 1회 (`_route_once`)
- Frontier 실패 시 Unified 재호출 0회

## 11. 폴백 테스트

- `test_no_fallback_loop` PASS
- `test_fast_path_miss_calls_unified_once` PASS
- `test_unified_failure_has_bounded_fallback` PASS
- `test_frontier_failure_reuses_cached_unified_route` PASS

## 12. Steam 테스트

`test_route_steam_launch_not_search` — `getattr(assistant, "_settings", None)` 수정으로 PASS

## 13. 전체 테스트

- `732 passed, 60 skipped`
- `verify-next-stage.ps1` PASS

## 14. 실제 성능 측정

실제 Gemma 성능: 미측정  
사유: 모델 런타임 미사용 (Mock 구조 벤치마크만)

## 15. 남은 제한

- 실제 Gemma가 operations JSON을 안정적으로 생성하는지는 로컬 LLM 벤치 필요
- `frontier_first` 모드는 회귀 비교용 유지

## 16. 최종 판정

**READY WITH LIMITATIONS** — 구조·테스트·CI 통과, 실제 Gemma 라우팅 품질은 별도 측정 필요
