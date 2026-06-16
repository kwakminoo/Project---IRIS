# Hybrid Router 검증 결과

**검증 일시:** 2026-06-16  
**기준 HEAD:** `d119feb2d7a1607faab8f3a7a102019922ffacce` (`feat/iris-ide-terminal`)  
**origin/main:** `0319560008f2585f7b964c08b681f0f983e725de`  
**판정:** **NOT READY**

---

## 1. 기준 커밋

| 항목 | 값 |
|------|-----|
| 현재 HEAD | `d119feb` |
| origin/main | `0319560` (HEAD보다 2커밋 뒤) |
| 하이브리드 라우터 | **작업 트리 미커밋** — main 미병합 |
| main checkout | 실패 (iris-ide package.json 로컬 변경 충돌) |

---

## 2. 실제 라우팅 구조

의도한 파이프라인이 `TurnCoordinator`에 **코드상 구현됨**:

```text
Safety / Pending / Recovery
→ (frontier_first 모드만 예외 분기)
→ Deterministic Fast Path
→ Unified Router (_route_once, 최대 1회)
→ evaluate_frontier_need (복합만, unified_only 제외)
→ run_frontier_turn (조건부)
→ Lane dispatch
```

Frontier 실패 시: cached `routed_turn` 재사용, Unified 재호출 없음 (`logs: frontier_fallback_unified`).

---

## 3. 변경 요구사항 반영 여부

| 요구사항 | 반영 | 비고 |
|----------|------|------|
| 일반 요청 → Fast/Unified | ⚠️ 부분 | 인사말 Fast Path 동작; `수고했어` 등 일부 누락 |
| 복합만 Frontier | ❌ | `simple_lane` 조기 반환으로 CHAT_ONLY 분류 시 Frontier 미호출 |
| Frontier 실패 시 재라우팅 없음 | ✅ | 테스트 통과 |
| 모델 호출 예산 (단순) | ⚠️ | Fast Chat 대부분 0 Unified; 일부 인사 Unified 1회 |
| Safety·Task Runtime 유지 | ✅ | Safety 선행; Fast Path → automation API |
| 기본 hybrid | ✅ | settings + get_router_mode |
| 롤백 모드 | ✅ | frontier_first / unified_only 실측 |

---

## 4. 요청별 라우팅 매트릭스

**조건:** `router_mode=hybrid`, `RoutingGemma` (Unified 기본 `chat_only` JSON), `run_frontier_turn` mock  
**실행:** 2026-06-16 로컬 `TurnCoordinator.run_turn`

### A. Fast Chat

| 입력 | Fast Path | Unified LLM | Frontier | 최종 Lane | 일치 |
|------|-----------|-------------|----------|-----------|------|
| 안녕 | ✅ fast_chat_greeting | 0 | 0 | CHAT_ONLY → dialogue | ✅ |
| 고마워 | ✅ | 0 | 0 | CHAT_ONLY | ✅ |
| 수고했어 | ❌ no_match | 1 | 0 | CHAT_ONLY | ⚠️ Unified 불필요 |
| 잘 자 | ✅ | 0 | 0 | CHAT_ONLY | ✅ |
| 너는 누구야? | ❌ | 1 | 0 | CHAT_ONLY | ⚠️ |
| 아이리스는 뭘 할 수 있어? | ✅ | 0 | 0 | CHAT_ONLY | ✅ |

### B. 일반 질문

| 입력 | Fast | Unified | Frontier | Lane | 일치 |
|------|------|---------|----------|------|------|
| FastAPI가 뭐야? | ❌ | 1 | 0 | CHAT_ONLY | ✅ (Dialogue) |
| 리스트/튜플 차이 설명 | ❌ | 1 | 0 | CHAT_ONLY | ✅ |
| Task 중심 구조 설명 | ❌ | 1 | 0 | CHAT_ONLY | ✅ |

### C. 단일 검색

| 입력 | Fast | Unified | Frontier | Lane | 일치 |
|------|------|---------|----------|------|------|
| 최신 AI 뉴스 찾아줘 | ❌ | 1 | 0 | CHAT_ONLY | ❌ Search 기대 |
| 오늘 기술 뉴스 검색 | ❌ | 1 | 0 | CHAT_ONLY | ❌ |

> Mock 한계: RoutingGemma가 search lane 미반환. 정책 단위 테스트(`test_simple_search_no_frontier`)는 통과.

### D. 단일 실행

| 입력 | Fast | Unified | Frontier | Lane | 일치 |
|------|------|---------|----------|------|------|
| 크롬 열어줘 | ❌ | 1 | 0 | CHAT_ONLY | ❌ Action 기대 |
| 메모장 실행 | ❌ | 1 | 0 | CHAT_ONLY | ❌ |
| IDE 화면 열어줘 | ❌ | 1 | 0 | CHAT_ONLY | ❌ |
| 시스템 상태 보여줘 | ✅ FAST_TOOL | 0 | 0 | FAST_TOOL | ✅ |

### E. Computer Use

| 입력 | Fast | Unified | Frontier | Lane | 일치 |
|------|------|---------|----------|------|------|
| 창 최소화 | ❌ | 1 | 0 | CHAT_ONLY | ❌ |
| 메모장에 입력 | ❌ | 1 | 0 | CHAT_ONLY | ❌ |

### F. Frontier (복합)

| 입력 | Fast | Unified | Frontier | Lane | 일치 |
|------|------|---------|----------|------|------|
| FastAPI 설명+파일 열기 | exclude | 1 | **0** | CHAT_ONLY | ❌ |
| 뉴스 찾아 요약+정리 | exclude | 1 | **0** | CHAT_ONLY | ❌ |
| 오류 분석+수정+빌드+테스트 | exclude | 1 | **0** | CHAT_ONLY | ❌ |
| 이미지 확인+재실행 | exclude | 1 | **0** | CHAT_ONLY | ❌ |
| 메일 찾아+답장 초안 | exclude | 1 | **0** | CHAT_ONLY | ❌ |

**원인:** (1) `evaluate_frontier_need` simple_lane 조기 반환, (2) Mock Unified가 `chat_only`만 반환.

`requires_frontier=True` + `COMPUTER_USE` lane 패치 시 Frontier 호출 테스트는 통과 (`test_explain_and_open_uses_frontier`).

### G. 장문 단순 (Frontier 오판 방지)

| 입력 | Frontier | 일치 |
|------|----------|------|
| 비동기 함수 장문 설명 | 0 | ✅ |
| 문장 다듬기 | 0 | ✅ |
| 긴 요약 | 0 | ✅ |

### H. 위험 단일 행동

| 입력 | Safety | Frontier | Lane | 일치 |
|------|--------|----------|------|------|
| 파일 삭제 | **BLOCK** | 0 | SAFETY | ✅ |
| 프로그램 설치 | — | 0 | CHAT_ONLY | ⚠️ Frontier 아님, 승인 경로 미검증 |
| 메일 보내기 | — | 0 | CHAT_ONLY | ⚠️ |

---

## 5. 모델 호출 횟수 (Mock 실측)

| 유형 | Unified | Frontier | Dialogue | 비고 |
|------|---------|----------|----------|------|
| Fast Chat (안녕) | 0 | 0 | UI 위임 1 | ✅ |
| Fast Chat (수고했어) | 1 | 0 | 1 | 예산 초과 |
| 일반 Chat | 1 | 0 | 1 | ✅ |
| 단일 Search (mock) | 1 | 0 | 1 | lane 오분류 |
| 시스템 상태 | 0 | 0 | 0 | FAST_TOOL |
| 복합 (F) | 1 | **0** | 1 | **Frontier 누락** |

- **평균/최대:** Mock 벤치마크 기준 hybrid `unified_invocations=78/101`, `frontier_invocations=0`
- **중복 호출:** Hybrid 경로에서 Unified 2회 호출 패턴 없음
- **Frontier 불필요 호출:** 단순 요청에서 Frontier 0 — ✅
- **예산 초과:** `수고했어` 등 Fast Path 미스

---

## 6. Frontier 호출·폴백 통계

| 모드 | 샘플 | Frontier 호출 | Unified 호출 | 비고 |
|------|------|---------------|--------------|------|
| hybrid | 101 | 0 | 78 | Mock, complex 미트리거 |
| frontier_first | 101 | 101 | 0 | 롤백 모드 정상 |
| unified_only | 101 | 0 | 78 | Frontier 0 — 정상 |

폴백: `test_frontier_failure_reuses_existing_unified_route`, `test_frontier_failure_does_not_call_unified_twice` **통과**.

---

## 7. 성능 비교

**실제 로컬 LLM 미사용 — Mock 기반 호출 경로·지연만 측정.**

출력: `iris/tmp_router_benchmark.json`

| 모드 | avg_ms | p50_ms | p95_ms | frontier | unified |
|------|--------|--------|--------|----------|---------|
| hybrid | 1.37 | 1.33 | 2.48 | 0 | 78 |
| frontier_first | 0.04 | 0.04 | 0.05 | 101 | 0 |
| unified_only | 1.24 | 1.34 | 2.34 | 0 | 78 |

- hybrid vs frontier_first: Mock에서 hybrid가 느림 (Unified LLM 호출 78회) — **의도된 trade-off**
- **first_visible_ms / TTFT / 실제 TTS:** 런타임 UI 미실측 — 코드만 확인 (`FAST` 모드 UI 선행)

---

## 8. TTS·첫 화면 출력

| 항목 | 결과 |
|------|------|
| 기본 `text_tts_sync_mode` | `fast` |
| FAST 모드 동작 | `_on_llm_stream_chunk`에서 즉시 append, TTS는 synchronized에서만 첫 문장 후 시작 |
| `ui_first_character_at` | `mark_ui_first_character_active()` 연결됨 |
| 실측 ui ≤ tts | **미검증** (GUI 런타임 미실행) |

---

## 9. Safety·Task Runtime 회귀

| 경로 | 결과 |
|------|------|
| Safety Policy | ✅ 삭제 요청 차단 |
| Pending CU | ✅ 라우터 선행 |
| Recovery | ✅ 코드 존재, 선행 return |
| Fast Path → automation | ✅ `request_automation_tool` / `launch_app_by_key` |
| Approval | ⚠️ 이번 매트릭스에서 CRITICAL 단일 행동 미검증 |

---

## 10. 전체 테스트 결과

### 라우터 전용 (144/145 통과)

```text
pytest iris/tests/test_turn_coordinator.py
     iris/tests/test_unified_router.py
     iris/tests/test_frontier_turn.py
     iris/tests/test_frontier_policy.py
     iris/tests/test_hybrid_router_flow.py
     iris/tests/test_fast_path.py
     iris/tests/test_frontier_routing.py
     iris/tests/test_frontier_routing_matrix.py
     iris/tests/test_router_telemetry.py

결과: 144 passed, 1 failed
실패: test_unified_router.py::test_route_steam_launch_not_search
      (AttributeError: SimpleNamespace._settings)
```

### verify-next-stage.ps1

- Compile: PASS
- Unit Tests: **FAIL** (4 failed / 735 passed)
- Integration: PASS
- Migration / FK: PASS

### 전체 iris/tests

`688 passed, 5 failed, 60 skipped` — 라우터 외 UI/TTS/IDE 실패 포함

---

## 11. 발견된 문제

### P0

1. **`evaluate_frontier_need` simple_lane 조기 반환** — Unified가 `CHAT_ONLY`이면 텍스트 복합 신호 무시 → Frontier 미호출
2. **복합 요청 F 카테고리 전부 Dialogue fallback** — 실측 5/5 Frontier 0회
3. **하이브리드 변경 미병합** — origin/main에 없음, 검증은 feature 브랜치 작업 트리 기준
4. **단위 테스트 실패** — unified_router 테스트 1건 + verify-next-stage 4건

### P1

1. Fast Path 인사말 커버리지 (`수고했어`, `너는 누구야?`)
2. 필수 테스트명 3건 미구현 (`test_no_fallback_loop` 등)
3. 벤치마크 Mock이 복합/검색 lane 미시뮬레이션 → Frontier 통계 0
4. 실제 LLM/TTS first_visible 실측 없음

---

## 12. 우선순위별 보완점

| 우선순위 | 작업 |
|----------|------|
| P0 | `frontier_policy.py`: simple_lane 반환 **전에** 텍스트 복합 신호 평가 |
| P0 | Unified Router가 복합 요청에 `requires_frontier` / non-simple lane 설정 검증 (통합 테스트) |
| P0 | `test_route_steam_launch_not_search` 수정 (`_settings` mock) |
| P1 | `is_chat_only`에 `수고했어` 등 인사 패턴 추가 |
| P1 | `test_no_fallback_loop`, `test_fast_path_miss_calls_unified_once`, `test_unified_failure_has_bounded_fallback` 추가 |
| P1 | 벤치마크 `RoutingGemma`에 요청별 lane 시뮬레이션 |
| P2 | main 브랜치 병합 후 재검증 |
| P2 | 실제 Ollama/Gemma 벤치마크 (first_visible_ms, TTFT) |

---

## 13. 최종 판정

### NOT READY

**근거:**

- 복합 요청이 단순 CHAT_ONLY로 처리되고 Frontier가 호출되지 않음 (정책 결함 + 실측)
- 전체 단위 테스트 게이트 실패
- 하이브리드 라우터가 main에 미병합
- 실제 성능·TTS 체감 미검증

**구조적으로 올바른 부분:**

- TurnCoordinator 파이프라인 순서
- Frontier 실패 시 Unified 재호출 없음
- Fast Path Safety 미우회
- 설정 기본값 hybrid
- 롤백 모드 분기
