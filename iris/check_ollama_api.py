import sys

import httpx

from iris.config.settings import load_settings

# Windows 콘솔(cp949)에서 한글·이모지 출력 오류 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

settings = load_settings()
BASE = settings.ollama_base_url.rstrip("/")
MODEL = settings.gemma_model_name

IRIS_SYSTEM = (
    "당신은 Iris, 사용자의 로컬 AI 비서입니다. "
    "짧고 친절한 한국어로만 답하세요. 마크다운 없이 일반 문장만 쓰세요."
)

CASES = [
    ("user_only_think_false", False, [{"role": "user", "content": "안녕 아이리스"}]),
    ("iris_dialogue_think_false", False, [
        {"role": "system", "content": IRIS_SYSTEM},
        {"role": "user", "content": "안녕 아이리스"},
    ]),
    ("iris_capability_think_false", False, [
        {"role": "system", "content": IRIS_SYSTEM},
        {"role": "user", "content": "넌 뭘 할 수 있어?"},
    ]),
    ("iris_dialogue_think_true", True, [
        {"role": "system", "content": IRIS_SYSTEM},
        {"role": "user", "content": "안녕 아이리스"},
    ]),
]

def run_case(name, think, messages):
    payload = {"model": MODEL, "stream": False, "think": think, "messages": messages}
    r = httpx.post(f"{BASE}/api/chat", json=payload, timeout=300.0)
    r.raise_for_status()
    msg = r.json().get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = msg.get("thinking") or ""
    tlen = len(thinking) if isinstance(thinking, str) else 0
    print("=" * 60)
    print(f"[{name}] think={think}")
    print(f"  content_len={len(content)}")
    print(f"  thinking_len={tlen}")
    print(f"  content_preview={content[:300]!r}")
    if tlen and len(content) < 20:
        print(f"  thinking_preview={thinking[:300]!r}")

for name, think, msgs in CASES:
    run_case(name, think, msgs)
