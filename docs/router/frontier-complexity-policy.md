# Frontier 복합 요청 판별 정책

구현: `iris/iris/assistant/frontier_policy.py` → `evaluate_frontier_need()`

## Frontier 호출 조건

| 신호 | 예시 |
|------|------|
| `mixed_chat_and_execution` | 설명 + 파일 열기 |
| `search_then_action` | 검색 + 요약 + 전송 |
| `multi_step_dependent` | 연결어 + 다중 동사 |
| `multi_capability` | 2+ 앱/도구 |
| `conditional_monitoring` | 완료 확인 + 재실행 |
| `plan_execute_verify` | 분석 + 수정 + 빌드 |
| `orchestrated_lane` | Unified `ORCHESTRATED` |
| `requires_frontier` | Router JSON 필드 |

## Frontier 미호출

- 단순 인사·감사 (Fast Path → Dialogue)
- CHAT_ONLY / 단독 SEARCH / HYBRID
- 단일 DIRECT_ACTION / FAST_TOOL / COMPUTER_USE
- 위험도만 높은 경우 (Safety Kernel 담당)
- 긴 문장만으로 호출하지 않음

## 설정

- `IRIS_FRONTIER_COMPLEX_ONLY=true` (기본)
- `IRIS_FRONTIER_COMPLEXITY_THRESHOLD=0.70`

## 강한 신호

`mixed_chat_and_execution` 등 강한 신호는 threshold 미만이어도 Frontier 호출.
