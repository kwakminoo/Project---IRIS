"""activity_privacy 스트림용 레닥션·한글 생략."""

from iris.core.activity_privacy import prepare_activity_line, summarize_tool_params


def test_prepare_masks_path_and_secrets() -> None:
    raw = 'LLM tokens sk-ABCDEFGHIJKLMNOP1234567890 path C:\\Users\\x\\secret\\file.txt'
    out = prepare_activity_line(raw)
    assert "[secret redacted]" in out or "redacted" in out
    assert "sk-ABCDE" not in out
    assert "Users" not in out or "[path redacted]" in out


def test_prepare_drops_hangul() -> None:
    assert prepare_activity_line("상태 업데이트") == "[Non-English trace omitted.]"


def test_summarize_launch_app_tool() -> None:
    s = summarize_tool_params(
        "launch_app", {"app_key": "code", "display_name": "Cursor"}
    )
    assert "app_key='code'" in s


def test_summarize_run_shell_withheld() -> None:
    assert "withheld" in summarize_tool_params("run_shell", {"command": "rm -rf /"})


def test_summarize_focus_window_title_sub() -> None:
    from iris.assistant.tool_param_normalize import normalize_computer_use_params

    p = normalize_computer_use_params("focus_window", {"title_hint": "Chrome"})
    assert summarize_tool_params("focus_window", p) == "title_sub='Chrome'"

