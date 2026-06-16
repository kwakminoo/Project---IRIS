# Frontier Policy (최종)

## 판단 순서

1. frontier_enabled / router_mode
2. ORCHESTRATED lane
3. RouteAnalysis 없음 또는 incomplete
4. requires_frontier
5. dependent operation graph (search→respond 제외)
6. response + execution
7. cross-capability flow
8. conditional / monitoring
9. complex operation graph
10. simple lane → Frontier 불필요

## 금지

- user_text 접속사·키워드·문장 길이 검사
- 위험도만으로 Frontier 호출

## evidence

`FrontierDecision.evidence`에 `RouteAnalysis` 첨부 (로깅·테스트용).
