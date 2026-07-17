"""코딩 패널 코드 반영 — 파서/파일쓰기 순수 로직 테스트 (모델 불필요)."""

from __future__ import annotations

import pytest

from iris.ai.coding_prompt import build_coding_messages
from iris.assistant.code_apply_flow import apply_code_from_reply
from iris.assistant.code_proposal import parse_code_proposals
from iris.automation.code_file_writer import (
    PathSafetyError,
    commit_file_write,
    plan_file_write,
)

# --- 파서 테스트 ---------------------------------------------------------


def test_parse_fence_with_filename_in_info() -> None:
    reply = "만들어드릴게요.\n\n```python hello.py\nprint('hi')\n```\n"
    props = parse_code_proposals(reply)
    assert len(props) == 1
    assert props[0].path == "hello.py"
    assert props[0].language == "python"
    assert "print('hi')" in props[0].content


def test_parse_title_style_info() -> None:
    reply = "```python title=src/app.py\nx = 1\n```"
    props = parse_code_proposals(reply)
    assert len(props) == 1
    assert props[0].path == "src/app.py"


def test_parse_filename_from_label_line() -> None:
    reply = "파일: main.py\n\n```python\nprint(1)\n```"
    props = parse_code_proposals(reply)
    assert len(props) == 1
    assert props[0].path == "main.py"


def test_parse_filename_from_first_comment() -> None:
    reply = "```python\n# utils/helper.py\ndef f():\n    return 1\n```"
    props = parse_code_proposals(reply)
    assert len(props) == 1
    assert props[0].path == "utils/helper.py"


def test_parse_skips_block_without_filename() -> None:
    reply = "그냥 설명입니다.\n\n```python\nprint(1)\n```"
    assert parse_code_proposals(reply) == []


def test_parse_empty_reply() -> None:
    assert parse_code_proposals("") == []


def test_parse_rejects_parent_traversal_name() -> None:
    reply = "```python ../evil.py\nprint(1)\n```"
    assert parse_code_proposals(reply) == []


# --- 파일쓰기 테스트 -----------------------------------------------------


def test_plan_new_file(tmp_path) -> None:
    pending = plan_file_write(tmp_path, "hello.py", "print('hi')\n")
    assert pending.rel_path == "hello.py"
    assert pending.is_overwrite is False
    assert pending.abs_path == (tmp_path / "hello.py").resolve()


def test_plan_detects_overwrite(tmp_path) -> None:
    (tmp_path / "a.py").write_text("old", encoding="utf-8")
    pending = plan_file_write(tmp_path, "a.py", "new")
    assert pending.is_overwrite is True


def test_plan_blocks_parent_traversal(tmp_path) -> None:
    with pytest.raises(PathSafetyError):
        plan_file_write(tmp_path, "../escape.py", "x")


def test_plan_blocks_absolute_outside(tmp_path) -> None:
    with pytest.raises(PathSafetyError):
        plan_file_write(tmp_path, "C:/Windows/system32/evil.txt", "x")


def test_plan_blocks_empty_path(tmp_path) -> None:
    with pytest.raises(PathSafetyError):
        plan_file_write(tmp_path, "   ", "x")


def test_commit_writes_file(tmp_path) -> None:
    pending = plan_file_write(tmp_path, "sub/hello.py", "print('hi')\n")
    result = commit_file_write(pending, database=None, approved=True)
    assert result.success is True
    assert (tmp_path / "sub" / "hello.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_commit_denied_does_not_write(tmp_path) -> None:
    pending = plan_file_write(tmp_path, "hello.py", "x")
    result = commit_file_write(pending, database=None, approved=False)
    assert result.success is False
    assert not (tmp_path / "hello.py").exists()


def test_commit_logs_to_database(tmp_path) -> None:
    calls = []

    class FakeDb:
        def insert_automation_tool_log(self, tool, summary, approved, success, result):
            calls.append((tool, approved, success))

    pending = plan_file_write(tmp_path, "hello.py", "x")
    commit_file_write(pending, database=FakeDb(), approved=True)
    assert calls == [("write_file", True, True)]


# --- 오케스트레이션 테스트 -----------------------------------------------


def test_flow_applies_approved_file(tmp_path) -> None:
    reply = "만들어드릴게요.\n\n```python hello.py\nprint('hi')\n```"
    msg = apply_code_from_reply(reply, str(tmp_path), approve=lambda p: True)
    assert "✅" in msg
    assert (tmp_path / "hello.py").read_text(encoding="utf-8").startswith("print('hi')")


def test_flow_respects_denied_approval(tmp_path) -> None:
    reply = "```python hello.py\nprint('hi')\n```"
    msg = apply_code_from_reply(reply, str(tmp_path), approve=lambda p: False)
    assert "취소" in msg
    assert not (tmp_path / "hello.py").exists()


def test_flow_no_proposal_returns_empty(tmp_path) -> None:
    assert apply_code_from_reply("그냥 설명", str(tmp_path), approve=lambda p: True) == ""


def test_flow_without_workspace_warns(tmp_path) -> None:
    reply = "```python hello.py\nprint('hi')\n```"
    msg = apply_code_from_reply(reply, None, approve=lambda p: True)
    assert "워크스페이스" in msg


def test_flow_end_to_end_from_model_style_reply(tmp_path) -> None:
    # 프롬프트 형식(`파일: 경로` + 코드블록)을 따른 모델 응답을 반영까지 검증
    reply = "요청하신 파일입니다.\n\n파일: app/main.py\n```python\nprint('run')\n```"
    msg = apply_code_from_reply(reply, str(tmp_path), approve=lambda p: True)
    assert "✅" in msg
    assert (tmp_path / "app" / "main.py").read_text(encoding="utf-8").startswith("print('run')")


# --- 코딩 프롬프트 테스트 -------------------------------------------------


def test_build_coding_messages_has_system_and_user() -> None:
    msgs = build_coding_messages("hello.py 만들어줘")
    assert [m.role for m in msgs] == ["system", "user"]
    assert "hello.py 만들어줘" in msgs[1].content
    assert "파일:" in msgs[0].content  # 파일 형식 지시 포함


def test_build_coding_messages_appends_context() -> None:
    msgs = build_coding_messages("이 함수 고쳐줘", context_block="[열린 파일] a.py")
    assert "a.py" in msgs[1].content


def test_flow_reports_preview_to_approver(tmp_path) -> None:
    seen = {}

    def approve(pending):
        seen["preview"] = pending.preview()
        seen["overwrite"] = pending.is_overwrite
        return True

    reply = "```python hello.py\nprint('hi')\n```"
    apply_code_from_reply(reply, str(tmp_path), approve=approve)
    assert "hello.py" in seen["preview"]
    assert seen["overwrite"] is False
