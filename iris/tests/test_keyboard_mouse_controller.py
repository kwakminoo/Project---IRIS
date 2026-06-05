"""keyboard_mouse_controller — URL 붙여넣기 경로."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.automation import keyboard_mouse_controller as kmc


def test_should_paste_for_watch_url() -> None:
    url = "https://www.youtube.com/watch?v=abc111"
    assert kmc._should_paste_instead_of_typewrite(url) is True


def test_should_not_paste_for_hangul() -> None:
    assert kmc._should_paste_instead_of_typewrite("아이유 라일락") is False


@patch("iris.automation.keyboard_mouse_controller._clipboard_set_text")
@patch("iris.automation.keyboard_mouse_controller._clipboard_get_text", return_value="saved")
def test_type_text_url_uses_clipboard_paste(
    mock_get: MagicMock,
    mock_set: MagicMock,
) -> None:
    url = "https://www.youtube.com/watch?v=abc111"
    fake_gui = MagicMock()
    with patch.dict("sys.modules", {"pyautogui": fake_gui}):
        ok, mode = kmc.type_text_approved(url, approved=True)
    assert ok is True
    assert mode == "paste"
    mock_set.assert_any_call(url)
    mock_set.assert_any_call("saved")
    fake_gui.hotkey.assert_called_once_with("ctrl", "v")
