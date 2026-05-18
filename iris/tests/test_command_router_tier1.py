"""Phase C — Tier 1 의도 분류·FAST_TOOL 라우팅."""

from iris.assistant.router_policy import RouteLane, resolve_route_lane
from iris.core.command_router import CommandKind, classify_command
from iris.core.context_manager import DialogueContext


def test_get_system_info_keywords() -> None:
    assert classify_command("지금 컴퓨터 사양 어떻게 돼?") is CommandKind.GET_SYSTEM_INFO
    assert classify_command("CPU 뭐야?") is CommandKind.GET_SYSTEM_INFO
    assert classify_command("RAM이 얼마야") is CommandKind.GET_SYSTEM_INFO


def test_open_url_with_https() -> None:
    assert (
        classify_command("크롬 열고 https://example.com/path 열어줘")
        is CommandKind.OPEN_URL
    )


def test_complex_multi_routes_computer_use() -> None:
    assert (
        classify_command("카톡 열고 철수에게 안녕이라고 보내줘")
        is CommandKind.COMPUTER_USE
    )


def test_resolve_lane_fast_tool_for_specs() -> None:
    text = "스펙 알려줘"
    k = classify_command(text)
    assert k is CommandKind.GET_SYSTEM_INFO
    r = resolve_route_lane(text, k, DialogueContext())
    assert r.lane is RouteLane.FAST_TOOL


def test_monitoring_still_resolves() -> None:
    text = "모니터링 상태 확인해줘"
    k = classify_command(text)
    assert k is CommandKind.MONITORING_STATUS
    r = resolve_route_lane(text, k, DialogueContext())
    assert r.lane is RouteLane.DIRECT_ACTION
