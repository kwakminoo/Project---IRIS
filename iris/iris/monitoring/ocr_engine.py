"""OCR (Tesseract 선택). 원문 전체는 기본 DB에 넣지 않음."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.config.settings import Settings

if TYPE_CHECKING:
    from iris.monitoring.screen_capture import CaptureResult


def ocr_image(settings: Settings, cap: "CaptureResult") -> str:
    """RGB bytes에서 텍스트 추출. 미설치 시 빈 문자열."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        img = Image.frombytes("RGB", (cap.width, cap.height), cap.rgb_bytes)
        text = pytesseract.image_to_string(img, lang="eng+kor")
        return text if isinstance(text, str) else ""
    except Exception:
        return ""


def ocr_for_storage(settings: Settings, text: str) -> tuple[str, str]:
    """
    저장용: (요약 또는 빈 문자열, 해시용 정규화 문자열).
    store_raw_ocr_text=False면 요약만 반환.
    """
    import hashlib

    norm = " ".join(text.split())[:2000]
    h = hashlib.sha256(norm.encode("utf-8", errors="replace")).hexdigest()
    if settings.store_raw_ocr_text:
        return text[:4000], h
    return (norm[:240] + ("…" if len(norm) > 240 else ""), h)
