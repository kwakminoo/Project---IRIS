# Hybrid Router 전환 결과

## 1. 변경 요약

- Frontier 우선 구조 → **Fast Path → Unified → 복합만 Frontier**
- `IRIS_CHAT_FAST_PATH` 복원 (기본 `true`)
- `IRIS_ROUTER_MODE=hybrid` (롤백: `frontier_first`)

## 2. 변경 전 라우팅

```
Safety → Frontier → Unified (폴백) → dispatch
```

## 3. 변경 후 라우팅

```
Safety / Pending / Recovery → Fast Path → Unified → Frontier(조건부) → dispatch
```

## 4. 신규 파일

- `iris/iris/assistant/fast_path.py`
- `iris/iris/assistant/frontier_policy.py`
- `iris/iris/assistant/router_telemetry.py`
- `iris/scripts/benchmark_router.py`
- `iris/scripts/summarize_router_timing.py`
- `scripts/benchmark-router.ps1`

## 5. 설정값

| 변수 | 기본값 |
|------|--------|
| IRIS_CHAT_FAST_PATH | true |
| IRIS_ROUTER_MODE | hybrid |
| IRIS_FRONTIER_COMPLEX_ONLY | true |
| IRIS_ROUTER_TELEMETRY | true |
| IRIS_TEXT_TTS_SYNC_MODE | fast |

## 6. 롤백

```env
IRIS_ROUTER_MODE=frontier_first
```

## 7. 테스트

```bash
python -m pytest iris/tests/test_fast_path.py iris/tests/test_frontier_policy.py iris/tests/test_hybrid_router_flow.py iris/tests/test_turn_coordinator.py -q
```

## 8. 성능 비교 (mock LLM, 101 samples)

| 모드 | avg_ms | frontier 호출 | unified 호출 |
|------|--------|---------------|--------------|
| hybrid | ~1.38 | 0 | 78 |
| frontier_first | ~0.05 | 101 | 0 |

실제 Gemma TTFT는 로컬 하드웨어 실측 필요. `iris/tmp_router_benchmark.json` 참고.

## 9. 남은 한계

- TTS fast 모드: 스트리밍 첫 토큰 즉시 표시, TTS는 뒤따름 (완전 분리는 후속)
- 실제 Gemma TTFT 벤치는 로컬 하드웨어 실측 필요

## 10. TTS 후속

`IRIS_TEXT_TTS_SYNC_MODE=synchronized` 로 기존 동기화 유지 가능.
