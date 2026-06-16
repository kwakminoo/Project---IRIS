# Router 성능 벤치마크

## 실행

```powershell
.\scripts\benchmark-router.ps1
```

또는:

```bash
python iris/scripts/benchmark_router.py --modes hybrid,frontier_first,unified_only
```

## 측정 항목

- 평균/P50/P95 지연 (mock LLM 기준)
- Frontier / Unified 호출 횟수
- 모드별 비교 (`tmp_router_benchmark.json`)

## 로그 요약

```bash
python iris/scripts/summarize_router_timing.py [db_path] [limit]
```

SQLite `router_timing` 로그에서 최근 N턴 통계.

## 주의

- 실제 Gemma 하드웨어 지연은 별도 실측 필요
- 벤치 스크립트는 `RoutingGemma` mock 사용
- 결과 문서에 미측정 항목은 명시
