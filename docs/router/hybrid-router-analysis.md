# IRIS Hybrid Router — 현재 구조 분석

> 기준: Hybrid Router 전환 작업 전 (Frontier 우선 구조)

## 1. 라우팅 진입점

핵심: `iris/iris/assistant/turn_coordinator.py` → `TurnCoordinator.run_turn()`

```
사용자 요청
→ Safety (quick_block_user_text)
→ pending_cu 후속 (_handle_pending_cu_followup)
→ recovery (try_handle_recovery_turn)
→ Frontier 1회 LLM (frontier_enabled && !multi_turn)     ← 문제: 모든 일반 턴
→ 실패 시 Unified LLM Router (route_user_turn)
→ _dispatch_routed_turn (레인별 실행)
```

## 2. 요청 유형별 LLM 호출 횟수 (변경 전)

| # | 시나리오 | LLM 호출 | 경로 |
|---|----------|----------|------|
| 1 | 인사·감사·잡담 | 1 (FRONTIER) | delegate_frontier_stream |
| 2 | 일반 개념 질문 | 1~3 | Frontier → (실패) Unified + Dialogue |
| 3 | 최신 정보 검색 | 1~2 | Frontier SEARCH 또는 Unified |
| 4 | 명확한 앱 실행 | 1 (FRONTIER) | needs_execution + DIRECT/CU |
| 5 | 파일·창 제어 | 1 (FRONTIER) | COMPUTER_USE |
| 6 | Computer Use | 1 (FRONTIER) + CU loop | |
| 7 | Multi-turn 모드 | 0~1 | multi_turn 시 Frontier 스킵 |
| 8 | 대화+실행 혼합 | 1 (FRONTIER) | envelope |
| 9 | 여러 앱·Tool | 1 (FRONTIER) | |
| 10 | Frontier 파싱 실패 | 2 | Frontier + Unified |
| 11 | Unified 실패 | 1 | CHAT_ONLY 폴백 |
| 12 | TTS·화면 | Frontier 완성 후 prefetch 또는 Dialogue stream | |

## 3. Frontier 우선 호출 위치

- `turn_coordinator.py` L160-216: `run_frontier_turn()` — Unified Router **이전**
- `frontier_agent.py` L231: `gemma.chat(..., purpose=FRONTIER)`

## 4. Unified Router 폴백 위치

- `turn_coordinator.py` L218-237: Frontier `None` 반환 시에만 `route_user_turn()`
- `frontier_agent.py` L177 docstring: 실패 시 Unified 폴백 명시

## 5. Fast Path 비활성 위치

- `turn_coordinator.py` L218 주석: `regex fast path 제거`
- `settings.chat_fast_path_enabled` (IRIS_CHAT_FAST_PATH, 기본 False) — **런타임 미참조**
- `router_policy.is_chat_only()` / `is_ambiguous_for_fast_path()` — 테스트·멀티턴 분기만

## 6. router_policy 잔존 로직

- `is_chat_only()` — 인사·능력 질문 regex
- `is_ambiguous_for_fast_path()` — 실행 동사·URL·앱 alias 제외
- `resolve_route_lane()` — CommandKind → RouteLane 규칙

## 7. 단순 vs 복합 요청 흐름 (변경 전)

**단순 인사 "안녕":**
```
Frontier(LLM#1) → CHAT_ONLY → delegate_frontier_stream (완성본 표시)
```

**일반 질문 "파이썬이 뭐야":**
```
Frontier(LLM#1) → 실패 또는 SEARCH → Unified(LLM#2) → Search/Dialogue
```

**복합 "설명하고 파일 열어줘":**
```
Frontier(LLM#1) → envelope → dispatch (Unified 생략 가능)
```

## 8. 중복 모델 호출 조건

1. Frontier 저신뢰/JSON 실패 → Unified Router 추가 호출
2. Unified CHAT_ONLY → Dialogue 스트리밍 추가 호출 (Frontier 실패 경로)
3. Frontier CHAT_ONLY 성공 시 Dialogue 생략 (1회만)

## 9. 수정 예정 파일

| 파일 | 변경 |
|------|------|
| `turn_coordinator.py` | 라우팅 순서 재배선 |
| `fast_path.py` | 신규 — Deterministic Fast Path |
| `frontier_policy.py` | 신규 — 복합 요청 판별 |
| `router_telemetry.py` | 신규 — 성능 계측 |
| `unified_router.py` | complexity 필드, 프롬프트 경량화 |
| `frontier_agent.py` | routing_hint, 입력 축소 |
| `router_policy.py` | RoutedTurn complexity 필드 |
| `settings.py` | RouterMode, 신규 env |
| `main_window.py` | UI 첫 글자 계측, TTS fast 모드 |
| `tests/test_*.py` | hybrid 경로 테스트 |

## 10. 회귀 위험

- `test_greeting_uses_frontier_chat_only` — Fast Path + Dialogue로 변경
- `test_frontier_turn.py` — frontier_first 모드 분리 필요
- pending_cu / recovery / multi-turn — 라우터 앞단, 순서 유지
- Frontier CHAT_ONLY prefetch UI — 단순 대화에서 제거
- Unified JSON `orchestrated` lane 미포함 — 스키마 확장 필요
