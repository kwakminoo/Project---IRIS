"""keyboard_mouse_controller — smart type 경로."""

from __future__ import annotations

from unittest.mock import patch

from iris.automation import keyboard_mouse_controller as kmc
from iris.automation.text_input_controller import TypeTextOutcome


@patch("iris.automation.text_input_controller.type_text_smart")
def test_type_text_url_uses_smart_typewrite(mock_smart) -> None:
    url = "https://www.youtube.com/watch?v=abc111"
    mock_smart.return_value = TypeTextOutcome(True, "typewrite", "typewrite", verified=True)
    ok, reason = kmc.type_text_approved(url, approved=True)
    assert ok is True
    assert reason.startswith("typewrite:")
    mock_smart.assert_called_once()


def test_paste_text_approved_still_available_for_explicit_call() -> None:
    from unittest.mock import MagicMock

    text = "https://example.com"
    fake_gui = MagicMock()
    with patch.dict("sys.modules", {"pyautogui": fake_gui}):
        with patch(
            "iris.automation.keyboard_mouse_controller._clipboard_get_text",
            return_value="saved",
        ):
            with patch("iris.automation.keyboard_mouse_controller._clipboard_set_text"):
                ok, mode = kmc.paste_text_approved(text, approved=True)
    assert ok is True
    assert mode == "paste"
    fake_gui.hotkey.assert_called_once_with("ctrl", "v")
