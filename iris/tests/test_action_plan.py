"""action_plan 파싱 테스트."""

from iris.assistant.action_plan import (
    default_plan,
    parse_action_plan,
    plan_to_json,
)


def test_parse_valid_plan() -> None:
    raw = """
    {
      "goal": "인사 응답",
      "steps": [
        {"tool": "safety_check", "args": {}},
        {"tool": "intent_route", "args": {}},
        {"tool": "assistant_dispatch", "args": {}},
        {"tool": "gemma_finalize", "args": {"only_if_no_direct_reply": true}}
      ]
    }
    """
    plan = parse_action_plan(raw)
    assert plan is not None
    assert plan.goal == "인사 응답"
    assert len(plan.steps) == 4
    assert plan.steps[-1].tool == "gemma_finalize"


def test_parse_rejects_blocked_tool() -> None:
    raw = '{"goal": "x", "steps": [{"tool": "app_launch", "args": {}}]}'
    assert parse_action_plan(raw) is None


def test_parse_appends_finalize_if_missing() -> None:
    raw = '{"goal": "x", "steps": [{"tool": "safety_check", "args": {}}]}'
    plan = parse_action_plan(raw)
    assert plan is not None
    assert plan.steps[-1].tool == "gemma_finalize"


def test_default_plan_has_finalize() -> None:
    plan = default_plan("안녕")
    assert plan.steps[-1].tool == "gemma_finalize"
    assert "안녕" in plan.goal


def test_plan_to_json_roundtrip_shape() -> None:
    plan = default_plan("테스트")
    text = plan_to_json(plan)
    assert '"steps"' in text
    assert "gemma_finalize" in text
