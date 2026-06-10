"""Iris 일상 대화 모델별 응답 시간 벤치마크 (Ollama / GemmaClient)."""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from iris.ai.gemma_client import ChatMessage, GemmaClient
from iris.ai.thinking_policy import LlmPurpose
from iris.config.settings import load_settings

DIALOGUE_SYSTEM = (
    "당신은 Iris, 사용자의 로컬 AI 비서입니다. "
    "짧고 친절한 한국어로만 답하세요. 마크다운 없이 일반 문장만 쓰세요."
)

PROMPTS: list[tuple[str, str]] = [
    ("greeting", "안녕 아이리스, 오늘 기분 어때?"),
    ("thanks", "어제 도와줘서 고마워."),
    ("weather_chat", "요즘 날씨가 너무 덥지 않아?"),
    ("food", "점심 뭐 먹을지 추천해줘."),
    ("work", "오늘 회의가 많아서 좀 피곤해."),
    ("hobby", "주말에 게임이랑 영화 중에 뭐가 나을까?"),
    ("motivation", "운동하기 귀찮은데 응원 한마디 해줘."),
    ("smalltalk", "고양이 키우는 거 어떻게 생각해?"),
    ("planning", "내일 일찍 일어나려면 뭐부터 하면 좋을까?"),
    ("farewell", "이제 자러 갈게, 잘 자."),
]

MODELS: list[tuple[str, str]] = [
    ("gemma4:e2b", "e2b (경량)"),
    ("gemma4:e4b", "e4b (중형)"),
    ("gemma4:26b", "26b (대형)"),
]


@dataclass
class BenchRow:
    model: str
    label: str
    kind: str
    prompt: str
    sec: float
    chars: int
    ok: bool
    preview: str


def main() -> int:
    settings = load_settings()
    client = GemmaClient(settings, timeout_sec=600.0)
    rows: list[BenchRow] = []

    print("=== Iris 일상 대화 응답 시간 벤치마크 ===", flush=True)
    print(f"Ollama: {settings.ollama_base_url}", flush=True)
    print(
        f"thinking_mode: {settings.thinking_mode} (DIALOGUE_CHAT think=off)",
        flush=True,
    )
    print(flush=True)

    for model, label in MODELS:
        print(f"--- 모델: {model} ({label}) ---", flush=True)
        warmup = client.chat(
            [ChatMessage("system", DIALOGUE_SYSTEM), ChatMessage("user", "테스트")],
            purpose=LlmPurpose.DIALOGUE_CHAT,
            model_override=model,
        )
        print(f"  warmup ok chars={len(warmup)}", flush=True)

        for kind, prompt in PROMPTS:
            messages = [
                ChatMessage("system", DIALOGUE_SYSTEM),
                ChatMessage("user", prompt),
            ]
            t0 = time.perf_counter()
            try:
                reply = client.chat(
                    messages,
                    purpose=LlmPurpose.DIALOGUE_CHAT,
                    model_override=model,
                )
                sec = time.perf_counter() - t0
                ok = not reply.startswith("로컬 언어 모델")
                preview = reply.replace("\n", " ")[:80]
                rows.append(
                    BenchRow(model, label, kind, prompt, sec, len(reply), ok, preview)
                )
                print(
                    f"  [{kind:12}] {sec:6.2f}s | {len(reply):3}자 | {preview}",
                    flush=True,
                )
            except Exception as exc:
                sec = time.perf_counter() - t0
                rows.append(
                    BenchRow(model, label, kind, prompt, sec, 0, False, str(exc)[:80])
                )
                print(f"  [{kind:12}] FAIL {sec:.2f}s | {exc}", flush=True)
        print(flush=True)

    print("=== 요약 (초) ===", flush=True)
    summary: dict[str, dict[str, float | int]] = {}
    for model, label in MODELS:
        times = [r.sec for r in rows if r.model == model and r.ok]
        fails = sum(1 for r in rows if r.model == model and not r.ok)
        if not times:
            print(f"{model}: 실패만 {fails}건", flush=True)
            continue
        summary[model] = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "total": sum(times),
            "fails": fails,
        }
        print(
            f"{model} ({label}): "
            f"평균={statistics.mean(times):.2f}s, "
            f"중앙값={statistics.median(times):.2f}s, "
            f"최소={min(times):.2f}s, "
            f"최대={max(times):.2f}s, "
            f"합계={sum(times):.2f}s, "
            f"실패={fails}",
            flush=True,
        )

    out_path = Path(__file__).resolve().parent.parent / "tmp_model_latency_bench.json"
    payload = {
        "models_tested": [m for m, _ in MODELS],
        "note": "요청 e2d/e4d는 로컬 Ollama 태그 gemma4:e2b, gemma4:e4b로 매핑",
        "summary": summary,
        "rows": [asdict(r) for r in rows],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
