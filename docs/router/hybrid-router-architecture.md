# Hybrid Router 아키텍처

## 변경 후 흐름

```
Safety / Pending / Recovery
→ Deterministic Fast Path (optional)
→ Unified LLM Router (1회)
→ Frontier Complexity Policy
→ Frontier (복합 요청만, 1회)
→ Lane 실행
```

## RouterMode

| 모드 | 설명 |
|------|------|
| `hybrid` (기본) | Fast → Unified → 복합만 Frontier |
| `frontier_first` | 긴급 롤백 — 기존 Frontier 우선 |
| `unified_only` | Frontier 비활성 |

## 주요 모듈

| 파일 | 역할 |
|------|------|
| `fast_path.py` | 규칙 기반 초경량 분기 |
| `unified_router.py` | 기본 LLM 라우터 |
| `frontier_policy.py` | 복합 요청 판별 |
| `frontier_agent.py` | 복합 오케스트레이션 envelope |
| `router_telemetry.py` | 성능 계측 |
| `turn_coordinator.py` | 파이프라인 오케스트레이션 |

## 모델 호출 예산 (hybrid)

| 요청 | Unified | Frontier | Dialogue |
|------|---------|----------|----------|
| 인사 (Fast) | 0 | 0 | 1 |
| 일반 질문 | 1 | 0 | 1 |
| 단순 검색 | 1 | 0 | 0 |
| 복합 | 1 | 1 | 0~1 |

## 폴백

- Fast Path 미매칭 → Unified
- Unified 실패 → CHAT_ONLY 안전 폴백
- Frontier 실패 → **캐시된 Unified 결과** (재호출 금지)
