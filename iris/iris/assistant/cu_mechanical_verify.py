"""Computer Use 체크포인트 기계 검증 — LLM 호출 전 deterministic 판정."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Literal, Sequence

from iris.assistant.action_plan import ComputerUsePlanItem
from iris.assistant.cu_perception import PerceptionObservation
from iris.automation.text_input_verify import (
    normalize_for_compare,
    read_focused_field_text,
    text_matches_expected,
)
from iris.config.app_index import display_name_for_key

if TYPE_CHECKING:
    from iris.assistant.computer_use_agent import ComputerUseContext

MechanicalStatus = Literal["success", "failed", "inconclusive"]

_TITLE_MATCH_THRESHOLD = 0.55


@dataclass(frozen=True)
class MechanicalVerifyResult:
    checkpoint_id: str
    status: MechanicalStatus
    failure_kind: str
    gap: str
    progress_summary: str
    confidence: float  # 1.0=기계 확정, 0.5=inconclusive


def title_matches_app(
    app_key: str,
    title: str,
    *,
    display_name: str | None = None,
) -> bool:
    """app_index display_name/app_key 기반 창 제목 퍼지 매칭 (goal regex 금지)."""
    t = (title or "").strip()
    if not t:
        return False
    key = (app_key or "").strip().lower()
    disp = (display_name or display_name_for_key(app_key)).strip()
    disp_l = disp.lower()
    title_l = t.lower()
    if key and key in title_l:
        return True
    if disp_l and disp_l in title_l:
        return True
    if key:
        if SequenceMatcher(None, key, title_l).ratio() >= _TITLE_MATCH_THRESHOLD:
            return True
    if disp_l:
        if SequenceMatcher(None, disp_l, title_l).ratio() >= _TITLE_MATCH_THRESHOLD:
            return True
    return False


def _resolve_app_target(slots: dict[str, Any]) -> tuple[str, str]:
    app_key = str(slots.get("app_key") or "").strip()
    display_name = str(slots.get("display_name") or "").strip()
    if app_key and not display_name:
        display_name = display_name_for_key(app_key)
    return app_key, display_name


def _expected_type_text(
    slots: dict[str, Any],
    executed_plans: Sequence[ComputerUsePlanItem],
) -> str:
    for key in ("text_to_type", "text"):
        val = str(slots.get(key) or "").strip()
        if val:
            return val
    for item in reversed(list(executed_plans)):
        if item.tool == "type_text":
            return str(item.params.get("text") or "").strip()
    return ""


def _foreground_hwnd() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import win32gui  # type: ignore

        return int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return 0


def _window_text_blob(perception: PerceptionObservation | None) -> str:
    if perception is None:
        return ""
    parts = [
        perception.active_window_title,
        perception.open_windows_summary,
        perception.uia_snapshot_summary,
    ]
    return "\n".join(p for p in parts if p).strip()


def _verify_cp_app_open(
    *,
    perception: PerceptionObservation | None,
    slots: dict[str, Any],
) -> MechanicalVerifyResult:
    cp = "cp_app_open"
    app_key, display_name = _resolve_app_target(slots)
    if not app_key and not display_name:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="inconclusive",
            failure_kind="unknown",
            gap="app_key/display_name 없음",
            progress_summary="앱 식별 정보 부족",
            confidence=0.5,
        )
    blob = _window_text_blob(perception)
    if not blob:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="inconclusive",
            failure_kind="unknown",
            gap="창 목록 perception 없음",
            progress_summary="open_windows_summary 비어 있음",
            confidence=0.5,
        )
    matched = title_matches_app(app_key or display_name, blob, display_name=display_name or None)
    if matched:
        label = display_name or app_key
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="success",
            failure_kind="unknown",
            gap="",
            progress_summary=f"{label} 창 확인됨",
            confidence=1.0,
        )
    return MechanicalVerifyResult(
        checkpoint_id=cp,
        status="failed",
        failure_kind="missing_app",
        gap=f"{display_name or app_key} 창이 목록에 없음",
        progress_summary="대상 앱 창 미발견",
        confidence=1.0,
    )


def _verify_cp_focus(
    *,
    perception: PerceptionObservation | None,
    slots: dict[str, Any],
    cu_ctx: ComputerUseContext | Any,
) -> MechanicalVerifyResult:
    cp = "cp_focus"
    app_key, display_name = _resolve_app_target(slots)
    title_sub = str(slots.get("title_sub") or "").strip()
    active = (perception.active_window_title if perception else "") or ""

    last_hwnd = int(getattr(cu_ctx, "last_focus_hwnd", 0) or 0)
    fg_hwnd = _foreground_hwnd()
    if last_hwnd > 0 and fg_hwnd > 0 and last_hwnd == fg_hwnd:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="success",
            failure_kind="unknown",
            gap="",
            progress_summary="focus_window HWND와 전경 창 일치",
            confidence=1.0,
        )

    target_key = app_key or (display_name_for_key(title_sub) if title_sub else "")
    target_disp = display_name or title_sub
    if active and (target_key or target_disp):
        if title_matches_app(target_key or target_disp, active, display_name=target_disp or None):
            return MechanicalVerifyResult(
                checkpoint_id=cp,
                status="success",
                failure_kind="unknown",
                gap="",
                progress_summary=f"활성 창: {active[:80]}",
                confidence=1.0,
            )
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="failed",
            failure_kind="wrong_focus",
            gap=f"활성 창 '{active[:60]}'이 대상과 불일치",
            progress_summary="포커스 창 불일치",
            confidence=1.0,
        )

    return MechanicalVerifyResult(
        checkpoint_id=cp,
        status="inconclusive",
        failure_kind="unknown",
        gap="활성 창·HWND 정보 부족",
        progress_summary="포커스 기계 판정 불가",
        confidence=0.5,
    )


def _verify_cp_text_typed(
    *,
    perception: PerceptionObservation | None,
    slots: dict[str, Any],
    executed_plans: Sequence[ComputerUsePlanItem],
    cu_ctx: ComputerUseContext | Any,
) -> MechanicalVerifyResult:
    cp = "cp_text_typed"
    expected = _expected_type_text(slots, executed_plans)
    if not expected:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="inconclusive",
            failure_kind="unknown",
            gap="text_to_type 없음",
            progress_summary="입력 대상 텍스트 미지정",
            confidence=0.5,
        )

    if getattr(cu_ctx, "last_type_verify", None) is True:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="success",
            failure_kind="unknown",
            gap="",
            progress_summary=f"입력 검증됨: {expected[:40]}",
            confidence=1.0,
        )

    read_ok, actual = read_focused_field_text()
    if read_ok:
        if text_matches_expected(expected, actual):
            return MechanicalVerifyResult(
                checkpoint_id=cp,
                status="success",
                failure_kind="unknown",
                gap="",
                progress_summary="UIA 필드 값 일치",
                confidence=1.0,
            )
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="failed",
            failure_kind="text_partial" if actual else "text_missing",
            gap=f"기대 '{expected[:40]}' 실제 '{actual[:40]}'",
            progress_summary="입력 필드 불일치",
            confidence=1.0,
        )

    # UIA 읽기 실패 — scene_summary 부분 문자열이면 inconclusive
    scene = (perception.scene_summary if perception else "") or ""
    norm_exp = normalize_for_compare(expected)
    norm_scene = normalize_for_compare(scene)
    if norm_exp and norm_exp in norm_scene:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="inconclusive",
            failure_kind="unknown",
            gap="UIA 읽기 실패, OCR/scene에 텍스트 흔적",
            progress_summary="scene_summary 부분 일치 — LLM 확인 필요",
            confidence=0.5,
        )

    if getattr(cu_ctx, "last_type_verify", None) is False:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="failed",
            failure_kind="text_missing",
            gap="type_text 검증 실패",
            progress_summary="입력 검증 미통과",
            confidence=1.0,
        )

    return MechanicalVerifyResult(
        checkpoint_id=cp,
        status="inconclusive",
        failure_kind="unknown",
        gap="UIA·scene 모두 불충분",
        progress_summary="텍스트 입력 기계 판정 불가",
        confidence=0.5,
    )


def _verify_cp_message_sent(
    *,
    perception: PerceptionObservation | None,
    slots: dict[str, Any],
    executed_plans: Sequence[ComputerUsePlanItem],
    cu_ctx: ComputerUseContext | Any,
) -> MechanicalVerifyResult:
    """메시지 전송 — 입력창 비움·텍스트 소실로 기계 판정, 불명확 시 LLM."""
    _ = executed_plans, cu_ctx
    cp = "cp_message_sent"
    expected = str(slots.get("message_text") or "").strip()
    if not expected:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="inconclusive",
            failure_kind="unknown",
            gap="message_text 없음",
            progress_summary="전송 대상 메시지 미지정",
            confidence=0.5,
        )

    read_ok, actual = read_focused_field_text()
    if read_ok:
        if not actual.strip():
            return MechanicalVerifyResult(
                checkpoint_id=cp,
                status="success",
                failure_kind="unknown",
                gap="",
                progress_summary="입력창 비어 있음 — 전송 추정",
                confidence=1.0,
            )
        if not text_matches_expected(expected, actual):
            return MechanicalVerifyResult(
                checkpoint_id=cp,
                status="success",
                failure_kind="unknown",
                gap="",
                progress_summary="입력창에 전송 문구 없음",
                confidence=0.9,
            )
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="failed",
            failure_kind="text_partial",
            gap="입력창에 메시지가 남아 있음",
            progress_summary="전송 미확인",
            confidence=1.0,
        )

    scene = (perception.scene_summary if perception else "") or ""
    norm_exp = normalize_for_compare(expected)
    norm_scene = normalize_for_compare(scene)
    if norm_exp and norm_exp not in norm_scene:
        return MechanicalVerifyResult(
            checkpoint_id=cp,
            status="inconclusive",
            failure_kind="unknown",
            gap="UIA 읽기 실패, scene에 메시지 없음",
            progress_summary="전송 흔적 — LLM 확인 필요",
            confidence=0.5,
        )

    return MechanicalVerifyResult(
        checkpoint_id=cp,
        status="inconclusive",
        failure_kind="unknown",
        gap="입력창·scene 모두 불충분",
        progress_summary="메시지 전송 기계 판정 불가",
        confidence=0.5,
    )


def _verify_cp_final(
    *,
    cu_ctx: ComputerUseContext | Any,
) -> MechanicalVerifyResult:
    """하위 checkpoint_ok 마커 종합 — 불명확하면 inconclusive."""
    obs = list(getattr(cu_ctx, "observations", []) or [])
    ok_ids: set[str] = set()
    for line in obs:
        s = line.strip()
        if s.startswith("checkpoint_ok:"):
            rest = s[len("checkpoint_ok:") :].strip()
            cp_id = rest.split("|", 1)[0].strip()
            if cp_id:
                ok_ids.add(cp_id)
    required = ("cp_app_open", "cp_focus", "cp_text_typed")
    if all(r in ok_ids for r in required):
        return MechanicalVerifyResult(
            checkpoint_id="cp_final",
            status="success",
            failure_kind="unknown",
            gap="",
            progress_summary="하위 체크포인트 기계 종합 성공",
            confidence=0.9,
        )
    return MechanicalVerifyResult(
        checkpoint_id="cp_final",
        status="inconclusive",
        failure_kind="unknown",
        gap="goal 전체 달성 LLM 판정 필요",
        progress_summary="cp_final 기계 종합 불충분",
        confidence=0.5,
    )


def mechanical_verify_checkpoint(
    checkpoint_id: str,
    *,
    perception: PerceptionObservation | None,
    slots: dict[str, Any],
    executed_plans: Sequence[ComputerUsePlanItem],
    cu_ctx: ComputerUseContext | Any,
    executed_through_index: int = -1,
) -> MechanicalVerifyResult:
    """체크포인트별 기계 검증 — inconclusive만 LLM으로 위임."""
    _ = executed_through_index
    cp = str(checkpoint_id or "").strip()
    if cp == "cp_app_open":
        return _verify_cp_app_open(perception=perception, slots=slots)
    if cp == "cp_focus":
        return _verify_cp_focus(perception=perception, slots=slots, cu_ctx=cu_ctx)
    if cp == "cp_text_typed":
        return _verify_cp_text_typed(
            perception=perception,
            slots=slots,
            executed_plans=executed_plans,
            cu_ctx=cu_ctx,
        )
    if cp == "cp_message_sent":
        return _verify_cp_message_sent(
            perception=perception,
            slots=slots,
            executed_plans=executed_plans,
            cu_ctx=cu_ctx,
        )
    if cp == "cp_final":
        return _verify_cp_final(cu_ctx=cu_ctx)
    return MechanicalVerifyResult(
        checkpoint_id=cp or "unknown",
        status="inconclusive",
        failure_kind="unknown",
        gap=f"알 수 없는 checkpoint_id: {cp}",
        progress_summary="기계 검증 미지원",
        confidence=0.5,
    )
