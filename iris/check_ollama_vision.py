"""Ollama 비전 스모크 테스트 — gemma4 + PNG 1장 /api/chat 검증 (읽기 전용, DB 저장 없음)."""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys

import httpx

from iris.config.settings import load_settings

# Windows 콘솔(cp949)에서 한글 출력 오류 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 1×1 PNG (빨강) — PIL 없을 때 폴백
_MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

VISION_USER = (
    "첨부한 PNG 이미지 1장만 보고, 화면에 보이는 것을 한 문장으로 한국어로 설명해 주세요. "
    "마크다운 없이 일반 문장만 쓰세요."
)


def _tiny_png_bytes() -> bytes:
    """작은 테스트 PNG — 메모리만 사용."""
    try:
        import io

        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        img = Image.new("RGB", (128, 128), color=(30, 90, 200))
        draw = ImageDraw.Draw(img)
        draw.rectangle((16, 16, 112, 112), outline=(255, 255, 255), width=3)
        try:
            font = ImageFont.load_default()
            draw.text((24, 52), "IRIS", fill=(255, 255, 255), font=font)
        except Exception:
            draw.text((24, 52), "IRIS", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return _MIN_PNG


def _screen_png_bytes() -> bytes | None:
    """전체 화면 캡처 1장 → PNG bytes (디스크·DB 저장 없음)."""
    from iris.config.settings import load_settings as _ls
    from iris.monitoring import screen_capture

    settings = _ls()
    cap = screen_capture.capture_full_screen(settings)
    if cap is None:
        return None
    return screen_capture.capture_result_to_png_bytes(cap)


def _ollama_show_hint(model: str) -> None:
    """실패 시 library vs batiai 안내."""
    print("\n--- 모델 태그 확인 (비전 불가 시 V1 진행 전 변경 필요) ---")
    print(f"  터미널에서 실행: ollama show {model}")
    print("  · 공식 gemma4 (library 태그) → Text+Image 멀티모달 지원 가능")
    print("  · batiai 등 서드파티 태그 → text-only일 수 있음 → PNG 비전 실패 가능")
    print("  · 해결: ollama pull gemma4:26b (공식) 또는 멀티모달 지원 태그로 교체")
    try:
        proc = subprocess.run(
            ["ollama", "show", model],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdout.strip():
            print("\n[ollama show 출력 미리보기]")
            lines = proc.stdout.strip().splitlines()[:24]
            for line in lines:
                print(f"  {line}")
        elif proc.stderr.strip():
            print(f"  (ollama show stderr) {proc.stderr.strip()[:400]}")
    except FileNotFoundError:
        print("  (ollama CLI가 PATH에 없어 자동 조회를 건너뜁니다.)")
    except Exception as exc:
        print(f"  (ollama show 실행 실패: {exc})")


def run_vision_smoke(*, use_screen: bool) -> int:
    settings = load_settings()
    base = settings.ollama_base_url.rstrip("/")
    model = (settings.media_ranker_vision_model or "").strip() or settings.gemma_model_name
    backend = settings.gemma_backend

    print("=" * 60)
    print("Iris Ollama 비전 스모크 테스트")
    print(f"  OLLAMA_BASE_URL={base}")
    print(f"  GEMMA_BACKEND={backend!r}")
    print(f"  model={model!r}")
    print(f"  USE_LOCAL_LLM={settings.use_local_llm}")
    print(f"  image_source={'screen_capture' if use_screen else 'synthetic_png'}")

    if not settings.use_local_llm:
        print("\n[실패] USE_LOCAL_LLM=false — 비전 테스트를 건너뜁니다.")
        return 1

    if backend != "ollama":
        print(
            "\n[실패] GEMMA_BACKEND=openai_compatible — Ollama images 비전 미지원."
            "\n  .env에서 GEMMA_BACKEND=ollama 로 설정 후 다시 실행하세요."
        )
        return 1

    if use_screen:
        png = _screen_png_bytes()
        if not png:
            print("\n[실패] 화면 캡처에 실패했습니다. mss/PIL 설치 또는 --no-screen 으로 재시도.")
            return 1
    else:
        png = _tiny_png_bytes()

    print(f"  png_bytes={len(png)}")

    b64 = base64.b64encode(png).decode("ascii")
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": VISION_USER,
                "images": [b64],
            }
        ],
    }

    try:
        r = httpx.post(f"{base}/api/chat", json=payload, timeout=300.0)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        print(f"\n[실패] HTTP {exc.response.status_code if exc.response else '?'}: {exc}")
        if body:
            print(f"  response_preview={body!r}")
        _ollama_show_hint(model)
        return 1
    except Exception as exc:
        print(f"\n[실패] 요청 오류: {exc}")
        _ollama_show_hint(model)
        return 1

    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = msg.get("thinking") or ""
    tlen = len(thinking) if isinstance(thinking, str) else 0

    print("\n--- 결과 ---")
    print(f"  content_len={len(content)}")
    print(f"  thinking_len={tlen}")
    if content:
        print(f"  content_preview={content[:300]!r}")
        print("\n[성공] Ollama /api/chat + PNG 1장 비전 응답을 받았습니다.")
        return 0

    print("\n[실패] 응답 content가 비어 있습니다 (비전 미지원·think-only 가능성).")
    if tlen:
        print(f"  thinking_preview={(thinking[:200] if isinstance(thinking, str) else '')!r}")
    _ollama_show_hint(model)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ollama gemma4 비전 스모크 테스트 (PNG 1장, DB 저장 없음)",
    )
    parser.add_argument(
        "--screen",
        action="store_true",
        help="합성 PNG 대신 전체 화면 캡처 1장 사용 (기본: 작은 테스트 PNG)",
    )
    args = parser.parse_args()
    raise SystemExit(run_vision_smoke(use_screen=args.screen))


if __name__ == "__main__":
    main()
