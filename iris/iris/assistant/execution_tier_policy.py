"""Computer Use 실행 우선순위 — 4계층 하이브리드 6단계 정책."""

from __future__ import annotations

import re
from typing import Any, Mapping

# 복합 PC 목표 — 단순 앱 열기 quick path 제외
COMPLEX_GOAL_RE = re.compile(
    r"(그리고|보내|입력|적어|써|작성|타이핑|검색|틀어|재생|메시지|삭제|설치|로그인|결제|파일|저장|붙여)",
    re.IGNORECASE,
)

# 실행 우선순위 (숫자 작을수록 우선)
TIER_DEDICATED_API = 1  # launch_app, open_url, get_system_info, call_integration
TIER_UIA = 2  # uia_click, uia_snapshot, perceive_desktop(인식)
TIER_HOTKEY = 3  # send_hotkey
TIER_INPUT_SIM = 4  # type_text, click — 사용자 입력과 충돌 가능
TIER_TERMINAL = 5  # run_shell (CRITICAL)
TIER_EXTERNAL = 6  # Tier4 OpenClaw/Hermes

TOOL_TIER_RANK: dict[str, int] = {
    "call_integration": TIER_DEDICATED_API,
    "get_system_info": TIER_DEDICATED_API,
    "launch_app": TIER_DEDICATED_API,
    "open_url": TIER_DEDICATED_API,
    "search_web": TIER_DEDICATED_API,
    "focus_window": TIER_DEDICATED_API,
    "list_open_windows": TIER_UIA,
    "uia_snapshot": TIER_UIA,
    "perceive_desktop": TIER_UIA,
    "read_screen_summary": TIER_UIA,
    "uia_click": TIER_UIA,
    "send_hotkey": TIER_HOTKEY,
    "type_text": TIER_INPUT_SIM,
    "click": TIER_INPUT_SIM,
    "run_shell": TIER_TERMINAL,
}

INPUT_CONFLICT_TOOLS: frozenset[str] = frozenset(
    {"type_text", "send_hotkey", "click"}
)

# 멀티스텝 — quick launch 우회
MULTI_STEP_TASK_TYPES: frozenset[str] = frozenset(
    {"multi_step", "send_message", "file", "window"}
)

EXECUTION_TIER_PLANNER_BLOCK = """## 실행 우선순위 (6단계 — 반드시 준수)
1. 전용 API: call_integration, launch_app, open_url, get_system_info, search_web
2. UI Automation: uia_click, uia_snapshot, perceive_desktop, list_open_windows
3. 단축키: send_hotkey
4. 가상 키보드/마우스: type_text, click(x,y) — 1~3이 불가할 때만
5. 터미널: run_shell — 셸이 필수일 때만 (승인 필요)
6. 외부 에이전트: 로컬 루프 실패 시 Iris가 Tier4로 위임 (플래너가 직접 호출하지 않음)
- integration_name이 slots에 있으면 call_integration을 최우선 검토하세요.
"""


def tool_tier_rank(tool_name: str) -> int:
    """도구 이름 → 실행 우선순위(1~6). 미등록은 4(입력 시뮬레이션) 취급."""
    return TOOL_TIER_RANK.get(tool_name.strip(), TIER_INPUT_SIM)


def is_input_conflict_tool(tool_name: str) -> bool:
    return tool_name.strip() in INPUT_CONFLICT_TOOLS


def input_conflict_message(tool_name: str, params: Mapping[str, Any] | None = None) -> str:
    """키보드·단축키·마우스 사용 전 사용자 안내 (음성·채팅)."""
    p = params or {}
    if tool_name == "type_text":
        preview = str(p.get("text") or "")[:24]
        detail = f" '{preview}…'" if preview else ""
        return (
            "잠시 키보드와 마우스 사용을 멈춰 주세요. "
            f"입력 충돌을 막기 위해 Iris가 키보드로 입력{detail}을 진행합니다."
        )
    if tool_name == "send_hotkey":
        keys = p.get("keys") or []
        if isinstance(keys, list):
            combo = "+".join(str(k) for k in keys[:6])
        else:
            combo = str(keys)
        return (
            "잠시 키보드 사용을 멈춰 주세요. "
            f"Iris가 단축키 {combo or '조합'}을 누릅니다."
        )
    return (
        "잠시 마우스와 키보드 사용을 멈춰 주세요. "
        "Iris가 화면을 클릭합니다."
    )


def should_skip_quick_launch(goal: str, slots: Mapping[str, Any] | None) -> bool:
    """단순 launch_app 빠른 경로를 건너뛸지."""
    from iris.assistant.action_skills import resolve_skill_id

    slot_map = slots or {}
    if resolve_skill_id(dict(slot_map)):
        return True
    task = str(slot_map.get("task_type") or "").lower()
    if task in MULTI_STEP_TASK_TYPES:
        return True
    if slot_map.get("integration_name"):
        return True
    if slot_map.get("text_to_type") or slot_map.get("message_text"):
        return True
    # deprecated: Unified Router slots 없을 때만 goal regex 폴백
    if not slot_map and COMPLEX_GOAL_RE.search(goal):
        return True
    return False
