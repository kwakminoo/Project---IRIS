"""Computer Use 플래너 JSON params 별칭 → 실행 계약 키 정규화."""

from __future__ import annotations

from typing import Any

# uia_* / perceive_desktop 창 식별 별칭
_WINDOW_TITLE_ALIASES = (
    "window_title_sub",
    "title_sub",
    "title_hint",
    "title",
    "window_title",
)

# focus_window 전용 (OS 창 제목 부분 문자열)
_FOCUS_WINDOW_ALIASES = (
    "title_sub",
    "title_hint",
    "title",
    "window_title",
)


def _first_non_empty_str(params: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _coerce_hotkey_keys(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]
    if isinstance(raw, str) and raw.strip():
        sep = "+" if "+" in raw else ","
        return [k.strip() for k in raw.replace("+", sep).split(sep) if k.strip()]
    return []


def normalize_computer_use_params(tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """JSON 파싱 직후 1회 호출 — 플래너 별칭을 AutomationTool 계약 키로 보정."""
    out = dict(params)
    name = (tool or "").strip()

    if name == "focus_window":
        if not str(out.get("title_sub") or "").strip():
            sub = _first_non_empty_str(out, _FOCUS_WINDOW_ALIASES)
            if sub:
                out["title_sub"] = sub
        return out

    if name in ("uia_snapshot", "uia_click"):
        if not str(out.get("window_title_sub") or "").strip():
            sub = _first_non_empty_str(out, _WINDOW_TITLE_ALIASES)
            if sub:
                out["window_title_sub"] = sub
        return out

    if name == "perceive_desktop":
        if not str(out.get("focus_hint") or "").strip():
            hint = _first_non_empty_str(
                out,
                ("focus_hint", "title_hint", "title_sub", "title", "window_title"),
            )
            if hint:
                out["focus_hint"] = hint
        if not str(out.get("window_title_sub") or "").strip():
            sub = _first_non_empty_str(out, _WINDOW_TITLE_ALIASES)
            if sub:
                out["window_title_sub"] = sub
        return out

    if name == "send_hotkey":
        keys = out.get("keys")
        if keys is None or keys == "" or keys == []:
            single = out.get("key")
            if single is not None and single != "":
                out["keys"] = _coerce_hotkey_keys(single)
        return out

    return out
