#!/usr/bin/env python3
"""Hybrid Router 벤치마크 — 실측 결과만 JSON으로 출력."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# iris 패키지 루트
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from iris.assistant.turn_coordinator import TurnCoordinator  # noqa: E402
from tests.support.fakes import RoutingGemma, make_test_assistant  # noqa: E402

SIMPLE_CHAT = [
    "안녕",
    "고마워",
    "수고했어",
    "잘 자",
    "뭐해?",
] * 4

GENERAL_QUESTIONS = [
    "파이썬이 뭐야?",
    "아이리스는 뭘 할 수 있어?",
    "이 문장을 자연스럽게 고쳐줘",
] * 7

SEARCH = [
    "최신 AI 뉴스를 찾아줘",
    "오늘 날씨 어때?",
] * 5

SINGLE_ACTION = [
    "크롬 열어줘",
    "메모장 실행해줘",
] * 10

COMPLEX = [
    "FastAPI가 뭔지 설명하고 프로젝트의 관련 코드도 열어줘",
    "최근 AI 뉴스를 찾아 요약하고 발표 문서에 정리해줘",
] * 10

AMBIGUOUS = [
    "그거 해줘",
    "아까 그거",
] * 5


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * p)
    idx = min(max(idx, 0), len(sorted_v) - 1)
    return sorted_v[idx]


def run_benchmark(mode: str, samples: list[str]) -> dict[str, object]:
    import tempfile

    latencies: list[float] = []
    frontier_hits = 0
    unified_hits = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gemma = RoutingGemma()
        assistant = make_test_assistant(
            tmp_path,
            gemma,
            settings_overrides={
                "router_mode": mode,
                "unified_llm_router_enabled": True,
                "frontier_enabled": mode != "unified_only",
                "frontier_complex_only": mode == "hybrid",
                "chat_fast_path_enabled": True,
                "router_telemetry_enabled": False,
            },
            db_name="bench.db",
        )
        coord = TurnCoordinator(assistant, gemma)  # type: ignore[arg-type]

        for text in samples:
            t0 = time.perf_counter()
            coord.run_turn(text)
            latencies.append((time.perf_counter() - t0) * 1000)
            for call in gemma.calls:
                if call and "Frontier" in call[0].content:
                    frontier_hits += 1
                    break
            else:
                for call in gemma.calls:
                    if call and "Unified Router" in call[0].content:
                        unified_hits += 1
                        break
            gemma.calls.clear()

        assistant._db.close()

    return {
        "mode": mode,
        "samples": len(samples),
        "avg_ms": statistics.mean(latencies) if latencies else None,
        "p50_ms": _percentile(latencies, 0.5),
        "p95_ms": _percentile(latencies, 0.95),
        "frontier_invocations": frontier_hits,
        "unified_invocations": unified_hits,
        "note": "mock LLM benchmark",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="IRIS router benchmark")
    parser.add_argument(
        "--modes",
        default="hybrid,frontier_first,unified_only",
        help="comma-separated router modes",
    )
    parser.add_argument(
        "--out",
        default=str(_ROOT / "tmp_router_benchmark.json"),
        help="output JSON path",
    )
    args = parser.parse_args()
    all_samples = SIMPLE_CHAT + GENERAL_QUESTIONS + SEARCH + SINGLE_ACTION + COMPLEX + AMBIGUOUS
    results = [run_benchmark(m.strip(), all_samples) for m in args.modes.split(",") if m.strip()]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
