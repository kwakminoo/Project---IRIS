"""UIA 트리에서 LLM용 요약만 추출 (전체 덤프 금지)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

# interactive / readable control types (substring match on friendly class name)
_INTERACTIVE_TYPES = (
    "button",
    "edit",
    "combobox",
    "listitem",
    "menuitem",
    "checkbox",
    "radiobutton",
    "hyperlink",
    "tabitem",
    "treeitem",
    "document",
    "text",
    "pane",
)


@dataclass
class UiaElementSummary:
    name: str
    control_type: str
    bounds: tuple[int, int, int, int] | None
    automation_id: str = ""


def _normalize_control_type(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return "Unknown"
    # "ControlType.Button" → "Button"
    if "." in t:
        t = t.split(".")[-1]
    return t[:40]


def _element_text(elem: Any, max_len: int = 80) -> str:
    for attr in ("window_text", "name", "legacy_properties"):
        try:
            if attr == "legacy_properties":
                props = elem.legacy_properties() or {}
                tx = str(props.get("Name") or props.get("Value") or "")
            else:
                tx = str(getattr(elem, attr)() if callable(getattr(elem, attr)) else getattr(elem, attr))
        except Exception:
            tx = ""
        tx = (tx or "").strip()
        if tx and len(tx) > 1:
            return tx[:max_len]
    return ""


def _element_bounds(elem: Any) -> tuple[int, int, int, int] | None:
    try:
        r = elem.rectangle()
        return (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        return None


def _element_automation_id(elem: Any) -> str:
    try:
        props = elem.legacy_properties() or {}
        aid = str(props.get("AutomationId") or props.get("automation_id") or "")
        return aid[:80]
    except Exception:
        return ""


def _control_type_matches(elem: Any) -> bool:
    try:
        friendly = ""
        if hasattr(elem, "friendly_class_name"):
            friendly = str(elem.friendly_class_name() or "")
        if not friendly and hasattr(elem, "element_info"):
            friendly = str(getattr(elem.element_info, "control_type", "") or "")
        fl = friendly.lower()
        return any(k in fl for k in _INTERACTIVE_TYPES)
    except Exception:
        return True


def summarize_elements(
    elements: Sequence[Any],
    *,
    window_title: str = "",
    max_elements: int = 40,
    max_chars: int = 2048,
) -> Tuple[List[UiaElementSummary], str]:
    """요소 시퀀스에서 요약 리스트·JSON 문자열 생성 (mock tree 테스트용)."""
    summaries: List[UiaElementSummary] = []
    for elem in elements:
        if len(summaries) >= max_elements:
            break
        if not _control_type_matches(elem):
            continue
        name = _element_text(elem)
        if not name:
            continue
        raw_type = ""
        if hasattr(elem, "friendly_class_name") and callable(elem.friendly_class_name):
            raw_type = str(elem.friendly_class_name() or "")
        if not raw_type:
            raw_type = str(getattr(elem, "control_type", "") or "")
        ctype = _normalize_control_type(raw_type)
        summaries.append(
            UiaElementSummary(
                name=name,
                control_type=ctype,
                bounds=_element_bounds(elem),
                automation_id=_element_automation_id(elem),
            )
        )
    return summaries, format_uia_json(summaries, window_title, max_chars=max_chars)


def format_uia_json(
    summaries: Sequence[UiaElementSummary],
    window_title: str,
    *,
    max_chars: int = 2048,
) -> str:
    """LLM용 compact JSON (max_chars 이하)."""
    items = []
    for s in summaries:
        item: dict[str, Any] = {
            "name": s.name[:80],
            "type": s.control_type,
        }
        if s.automation_id:
            item["id"] = s.automation_id[:80]
        if s.bounds:
            item["bounds"] = list(s.bounds)
        items.append(item)
    payload = {"window": (window_title or "")[:200], "elements": items}
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    # 요소 수를 줄여 재시도
    trimmed = list(summaries)
    while len(trimmed) > 1 and len(text) > max_chars:
        trimmed = trimmed[: max(1, len(trimmed) // 2)]
        payload["elements"] = [
            {
                "name": s.name[:80],
                "type": s.control_type,
                **({"id": s.automation_id[:80]} if s.automation_id else {}),
            }
            for s in trimmed
        ]
        text = json.dumps(payload, ensure_ascii=False)
    return text[:max_chars]


def is_uia_summary_sparse(json_text: str, *, min_chars: int = 80) -> bool:
    """UIA 요약이 빈약한지 (OCR 폴백 트리거)."""
    if not json_text or len(json_text.strip()) < min_chars:
        return True
    try:
        data = json.loads(json_text)
        elements = data.get("elements") or []
        interactive = [
            e
            for e in elements
            if isinstance(e, dict)
            and str(e.get("type", "")).lower()
            not in ("text", "pane", "unknown")
        ]
        return len(interactive) == 0
    except Exception:
        return True


def snapshot_window_uia(
    title_sub: str,
    *,
    max_elements: int = 40,
    max_chars: int = 2048,
) -> Tuple[List[UiaElementSummary], str, str]:
    """
    pywinauto UIA로 창 스냅샷.
    반환: (summaries, json_text, matched_window_title)
    """
    title_sub = (title_sub or "").strip()
    if not title_sub:
        return [], "", ""

    try:
        from pywinauto import Desktop  # type: ignore
    except ImportError:
        return [], "", ""

    matched_title = ""
    try:
        desk = Desktop(backend="uia")
        for win in desk.windows():
            try:
                t = win.window_text() or ""
            except Exception:
                continue
            if title_sub.lower() not in t.lower():
                continue
            matched_title = t
            descendants: List[Any] = []
            try:
                descendants = list(win.descendants())
            except Exception:
                pass
            summaries, json_text = summarize_elements(
                descendants,
                window_title=t,
                max_elements=max_elements,
                max_chars=max_chars,
            )
            if summaries:
                return summaries, json_text, matched_title
            # descendants 비어 있으면 창 자체 텍스트 1개
            root_name = _element_text(win)
            if root_name:
                s = UiaElementSummary(
                    name=root_name,
                    control_type="Window",
                    bounds=_element_bounds(win),
                )
                return [s], format_uia_json([s], t, max_chars=max_chars), matched_title
    except Exception:
        pass
    return [], "", matched_title


def collect_window_text_legacy(title_sub: str) -> str:
    """모니터링 호환: UIA 요약 JSON 또는 빈 문자열."""
    _, json_text, _ = snapshot_window_uia(title_sub)
    if json_text:
        return json_text
    return ""


def click_uia_element(
    title_sub: str,
    *,
    name: str = "",
    automation_id: str = "",
) -> tuple[bool, str]:
    """name 또는 automation_id로 UIA 요소 클릭."""
    title_sub = (title_sub or "").strip()
    name = (name or "").strip()
    automation_id = (automation_id or "").strip()
    if not title_sub:
        return False, "window_title_sub가 필요합니다."
    if not name and not automation_id:
        return False, "name 또는 automation_id가 필요합니다."

    try:
        from pywinauto import Desktop  # type: ignore
    except ImportError:
        return False, "pywinauto가 없어 UIA 클릭을 할 수 없습니다. send_hotkey 또는 click(x,y)를 사용하세요."

    try:
        desk = Desktop(backend="uia")
        for win in desk.windows():
            try:
                t = win.window_text() or ""
            except Exception:
                continue
            if title_sub.lower() not in t.lower():
                continue
            for c in win.descendants():
                try:
                    tx = _element_text(c)
                    aid = _element_automation_id(c)
                    name_match = name and name.lower() in tx.lower()
                    id_match = automation_id and automation_id == aid
                    if not name_match and not id_match:
                        continue
                    if hasattr(c, "invoke"):
                        c.invoke()
                        return True, f"invoke: {tx or aid}"
                    if hasattr(c, "click_input"):
                        c.click_input()
                        return True, f"click: {tx or aid}"
                except Exception:
                    continue
            return False, f"'{title_sub}' 창에서 요소를 찾지 못했습니다."
    except Exception as e:
        return False, str(e)
    return False, "창을 찾지 못했습니다."
