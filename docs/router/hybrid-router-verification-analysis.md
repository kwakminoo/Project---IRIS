# Hybrid Router 검증 — 코드·실행 경로 분석

**검증 일시:** 2026-06-16  
**검증 브랜치:** `feat/iris-ide-terminal` (main 체크아웃 불가 — 로컬 변경 충돌)  
**HEAD:** `d119feb` — feat(iris-ide): implement real integrated terminal runtime  
**origin/main:** `0319560` — fix(ide): stabilize Theia shell loading and IDE re-entry  
**하이브리드 라우터 관련 커밋:** origin/main에 **미병합**. 작업 트리에 staged/unstaged로 존재 (`fast_path.py`, `frontier_policy.py`, `router_telemetry.py`, `turn_coordinator.py` 등)

## 작업 트리 상태 (미커밋)

- **Staged:** `fast_path.py`, `frontier_policy.py`, `router_telemetry.py`, `router_policy.py`, `settings.py` 등
- **Unstaged:** `turn_coordinator.py`, `unified_router.py`, `frontier_agent.py`, `frontier_policy.py`, 관련 테스트
- **Untracked:** `test_hybrid_router_flow.py`, `test_fast_path.py`, `test_frontier_policy.py`, `benchmark_router.py`, `benchmark-router.ps1`, 라우터 문서

---

## 실제 실행 경로 (TurnCoordinator.run_turn)

```text
1. quick_block_user_text (Safety)
2. pending_cu follow-up (_handle_pending_cu_followup)
3. recovery_turn_handler (try_handle_recovery_turn)
4. get_router_mode(settings) → RouterMode
5a. FRONTIER_FIRST → _run_frontier_first_path (Frontier 우선, 실패 시 Unified 1회)
5b. HYBRID / UNIFIED_ONLY → _run_hybrid_path
     ├─ Fast Path (resolve_fast_path) — LLM 없음
     ├─ _route_once (Unified Router 최대 1회)
     ├─ evaluate_frontier_need (복합만, UNIFIED_ONLY 제외)
     ├─ run_frontier_turn (조건부 1회)
     │    └─ 실패 시 cached routed_turn 재사용 (재호출 없음)
     └─ _dispatch_routed_turn → Lane 실행
```

---

## 10가지 질문 — 코드 근거

| # | 질문 | 답 | 근거 |
|---|------|-----|------|
| 1 | 첫 라우팅 단계 | Safety → Pending CU → Recovery → (모드) Fast Path | `turn_coordinator.py` L136–178, L229–253 |
| 2 | Frontier가 Unified보다 먼저? | **HYBRID/UNIFIED_ONLY: 아니오.** FRONTIER_FIRST 모드만 예외 | L182–195 vs L197–395 |
| 3 | Fast Path 연결 | **예** — `resolve_fast_path` → `_dispatch_fast_path` | L229–253, L538–569 |
| 4 | Unified 결과로 Frontier 판별 | **예** — `evaluate_frontier_need(user_text, routed_turn, ...)` | L282–289 |
| 5 | Frontier 실패 시 Unified 재사용 | **예** — `frontier is None` → `routed_turn` dispatch, `_route_once` 재호출 없음 | L375–395 |
| 6 | 동일 Turn Unified 2회? | **HYBRID: 없음** (`_route_once` 1회). FRONTIER_FIRST 실패 시 1회만 | L495–536, L480 |
| 7 | CHAT_ONLY → Dialogue stream | **예** — `delegate_dialogue_stream=True` | L656–673, L550–561 |
| 8 | 기본값 hybrid | **예** — `IRIS_ROUTER_MODE` 기본 `"hybrid"` | `settings.py` L328, `get_router_mode` L370–377 |
| 9 | 롤백 모드 동작 | **예 (실측)** — `frontier_first`: Frontier 1회/턴, `unified_only`: Frontier 0회 | 로컬 스크립트 실측 |
| 10 | Pending·Recovery 선행 | **예** — 라우터 진입 전 return | L154–178 |

---

## 필수 구조 존재 여부

| 구조 | 파일 | 상태 |
|------|------|------|
| `FastPathDecision` | `fast_path.py` L54–65 | ✅ |
| `FrontierDecision` | `frontier_policy.py` L41–46 | ✅ |
| `RouterMode` | `settings.py` L13–18 | ✅ |
| 라우팅 성능 계측 | `router_telemetry.py` `RouterTiming` | ✅ |
| Frontier 호출 이유 | `timing.frontier_reason`, `frontier_policy` signals | ✅ |
| 모델 호출 횟수 | `RouterTiming.inc_model_call`, `model_call_count` | ✅ |

## 기본 설정 (load_settings)

| 항목 | 환경변수 | 기본값 | 확인 |
|------|----------|--------|------|
| chat_fast_path_enabled | `IRIS_CHAT_FAST_PATH` | True | ✅ |
| unified_llm_router_enabled | `IRIS_UNIFIED_LLM_ROUTER` | True | ✅ |
| frontier_enabled | `IRIS_FRONTIER_ENABLED` | True | ✅ |
| frontier_complex_only | `IRIS_FRONTIER_COMPLEX_ONLY` | True | ✅ |
| router_mode | `IRIS_ROUTER_MODE` | **hybrid** | ✅ |
| text_tts_sync_mode | `IRIS_TEXT_TTS_SYNC_MODE` | **fast** | ✅ |

`get_router_mode()` 단일 정규화 — `turn_coordinator`만 사용, 다른 클래스가 `IRIS_ROUTER_MODE` 직접 파싱 없음.

---

## 금지 패턴 탐색

| 패턴 | 결과 |
|------|------|
| Turn 직후 무조건 Frontier | HYBRID에서 없음. `frontier_first` 모드만 Frontier 선호출 |
| Frontier 실패 후 Unified 재호출 | **없음** — `frontier_fallback_unified` 로그만, `_route_once` 재진입 없음 |
| Unified 실패 후 무조건 Frontier | **없음** — Frontier는 `evaluate_frontier_need` 조건부 |
| Fast Path가 Safety 우회 | **없음** — Safety는 L136 선행; Fast Path 실행은 `_dispatch_routed_turn` → `launch_app_by_key` / `request_automation_tool` |
| 동일 응답 중복 emit | 코드상 frontier_spoke 시 ack 스킵 패턴 존재 |
| 무한 fallback loop | **없음** — 단일 `_route_once`, Frontier 1회 시도 |

---

## 발견된 구조적 결함 (P0)

### `evaluate_frontier_need` — simple_lane 조기 반환

`frontier_policy.py` L91–110: Unified가 `CHAT_ONLY` 등 단순 레인을 반환하면 **텍스트 기반 복합 신호(`mixed_chat_and_execution` 등) 평가 전에** `use_frontier=False` 반환.

실측 (`evaluate_frontier_need` 직접 호출):

```text
"FastAPI 설명하고 파일 열어줘" + lane=CHAT_ONLY → frontier=False (simple_lane)
동일 문장 + lane=COMPUTER_USE      → frontier=True  (mixed_chat_and_execution)
```

**영향:** Unified가 복합 요청을 `CHAT_ONLY`로 분류하면 Frontier가 호출되지 않고 Dialogue로만 처리됨.  
매트릭스 F 카테고리 5건 전부 `frontier_mock=0`, `lane=CHAT_ONLY` (RoutingGemma 기본 응답 + 위 정책).

### Fast Path 인사말 누락

`수고했어` — `is_chat_only()` False → Fast Path 미매칭 → Unified 1회 호출 (불필요 LLM).

### 벤치마크 Mock 한계

`RoutingGemma` 기본 응답이 항상 `chat_only` → hybrid 모드 `frontier_invocations=0` (101 샘플). Mock이 Unified/Frontier 역할을 제대로 시뮬레이션하지 못함.

---

## Safety·Task Runtime

- Fast Path DIRECT_ACTION: `_run_direct_action` → `launch_app_by_key` / `request_automation_tool` (Task Runtime 경유)
- Fast Path FAST_TOOL: `request_automation_tool("get_system_info", ...)`
- 파일 삭제 요청: `quick_block_user_text` → `SAFETY_BLOCK` (라우터 미진입) ✅
- Pending CU: 라우터보다 선행 처리 테스트 통과 (`test_pending_cu_is_handled_before_router`)

## TTS·첫 화면

`main_window.py` L1286–1288: `TextTtsSyncMode.FAST`이면 스트림 청크 즉시 UI append, TTS 대기 없음.  
`mark_ui_first_character_active()` — 첫 청크 시 계측.

---

## 테스트 커버리지 갭

요청된 필수 테스트명 중 **미구현**:

- `test_no_fallback_loop`
- `test_fast_path_miss_calls_unified_once` (유사: `test_ambiguous_uses_unified_router`)
- `test_unified_failure_has_bounded_fallback`

구현됨:

- `test_frontier_failure_reuses_unified_route` ✅
- `test_frontier_failure_does_not_call_unified_twice` ✅
