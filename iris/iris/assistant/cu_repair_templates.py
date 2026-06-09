"""Computer Use 기계 Repair 템플릿 — LLM Repair 전 failure_kind별 고정 수리."""

from __future__ import annotations

from typing import Any, Sequence

from iris.assistant.action_plan import ComputerUsePlanItem
from iris.assistant.cu_checkpoint_verify import (
    CheckpointVerifyResult,
    extract_windows_summary,
)
from iris.config.app_index import display_name_for_key


def _resolve_title_sub(slots: dict[str, Any]) -> str:
    """slots·app_index에서 focus_window title_sub 추론."""
    for key in ("title_sub", "window_title_sub", "display_name"):
        val = str(slots.get(key) or "").strip()
        if val:
            return val
    app_key = str(slots.get("app_key") or "").strip()
    if app_key:
        return display_name_for_key(app_key) or app_key
    return ""


def _resolve_text_to_type(slots: dict[str, Any]) -> str:
    for key in ("text_to_type", "text", "message_text"):
        val = str(slots.get(key) or "").strip()
        if val:
            return val
    return ""


def _resolve_app_target(slots: dict[str, Any]) -> tuple[str, str]:
    app_key = str(slots.get("app_key") or "").strip()
    display_name = str(slots.get("display_name") or "").strip()
    if app_key and not display_name:
        display_name = display_name_for_key(app_key)
    return app_key, display_name


def _app_visible_in_windows(
    app_key: str,
    display_name: str,
    windows_summary: str,
) -> bool:
    """windows observation에 대상 앱이 보이는지 휴리스틱 판정."""
    blob = (windows_summary or "").lower()
    if not blob:
        return False
    if app_key and app_key.lower() in blob:
        return True
    if display_name and display_name.lower() in blob:
        return True
    return False


def _plan_item(
    index: int,
    tool: str,
    params: dict[str, Any],
    reason: str,
    *,
    checkpoint_id: str | None = None,
) -> ComputerUsePlanItem:
    return ComputerUsePlanItem(
        index=index,
        tool=tool,
        params=params,
        reason=reason,
        checkpoint_id=checkpoint_id,
    )


def build_mechanical_repair_steps(
    verify: CheckpointVerifyResult,
    slots: dict[str, Any],
    observations: Sequence[str],
) -> tuple[ComputerUsePlanItem, ...]:
    """failure_kind별 고정 repair_steps — 빈 튜플이면 LLM Repair로."""
    kind = (verify.failure_kind or "unknown").strip()
    windows = extract_windows_summary(observations)
    title_sub = _resolve_title_sub(slots)
    steps: list[ComputerUsePlanItem] = []

    if kind == "wrong_focus":
        if title_sub:
            steps.append(
                _plan_item(
                    -1,
                    "focus_window",
                    {"title_sub": title_sub},
                    f"기계 수리: 포커스 복구 ({title_sub})",
                )
            )

    elif kind == "text_missing":
        text = _resolve_text_to_type(slots)
        if title_sub:
            steps.append(
                _plan_item(
                    -1,
                    "focus_window",
                    {"title_sub": title_sub},
                    f"기계 수리: 입력 필드 포커스 ({title_sub})",
                )
            )
        if text:
            steps.append(
                _plan_item(
                    -2,
                    "type_text",
                    {"text": text},
                    f"기계 수리: 텍스트 재입력 ({text[:24]})",
                )
            )

    elif kind == "missing_app":
        app_key, display_name = _resolve_app_target(slots)
        if not app_key and not display_name:
            return ()
        if not _app_visible_in_windows(app_key, display_name, windows):
            params: dict[str, Any] = {}
            if app_key:
                params["app_key"] = app_key
            if display_name:
                params["display_name"] = display_name
            steps.append(
                _plan_item(
                    -1,
                    "launch_app",
                    params,
                    f"기계 수리: 앱 실행 ({display_name or app_key})",
                )
            )
        else:
            focus_title = title_sub or display_name or app_key
            if focus_title:
                steps.append(
                    _plan_item(
                        -1,
                        "focus_window",
                        {"title_sub": focus_title},
                        f"기계 수리: 앱 포커스 ({focus_title})",
                    )
                )

    return tuple(steps)
