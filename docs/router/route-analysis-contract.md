# RouteAnalysis 계약

## 모델

- `OperationKind`: respond, search, read, open, create, modify, execute, verify, monitor, send, ask_user
- `RouteOperation`: id, kind, goal, capability, target, depends_on, conditional_on, requires_verification
- `RouteAnalysis`: primary_goal, operations, requires_* 플래그, requested_capabilities, confidence, analysis_incomplete

## Unified Router JSON 확장

```json
{
  "operations": [{ "id": "op-1", "kind": "respond", "goal": "...", "capability": null, "depends_on": [] }],
  "requires_user_response": true,
  "requires_execution": false,
  "contains_cross_capability_flow": false,
  "requires_frontier": false
}
```

## 검증 규칙

- depends_on ID 존재
- 순환 의존 금지
- 실행 operation capability 필수
- declared flags vs derived flags 일치
- 불일치 시 `analysis_incomplete=true`

## Legacy Adapter

operations 없을 때 lane/intent/slots 메타만으로 최소 graph 생성. **user_text 키워드 추측 금지**.

## 복합성 정의

- 대화 + 실행
- 검색 결과 → 작성/실행 입력
- cross-capability 순차 연결
- 조건부·모니터링 흐름
- 단일 search→respond는 **단순** (Frontier 불필요)
