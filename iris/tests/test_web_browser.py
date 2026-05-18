"""웹 브라우저 선택·URL 열기."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iris.automation.web_browser import (
    list_installed_browser_options,
    normalize_browser_key,
    open_url,
    resolve_browser_executable,
)
from iris.config.settings import Settings


def test_normalize_browser_aliases() -> None:
    assert normalize_browser_key("Microsoft Edge") == "edge"
    assert normalize_browser_key("msedge") == "edge"
    assert normalize_browser_key("default") == "system"
    assert normalize_browser_key("unknown") == "chrome"


def test_list_installed_browser_options_includes_system() -> None:
    opts = list_installed_browser_options({"chrome": r"C:\chrome.exe"})
    keys = [k for k, _ in opts]
    assert "chrome" in keys
    assert "system" in keys


def test_open_url_uses_chrome_executable() -> None:
    paths = {"chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe"}
    with patch("iris.automation.web_browser.subprocess.Popen") as popen:
        ok, msg = open_url("https://example.com", "chrome", paths)
    assert ok is True
    assert "Chrome" in msg
    popen.assert_called_once()
    args = popen.call_args[0][0]
    assert args[0] == paths["chrome"]
    assert args[1] == "https://example.com"


def test_open_url_system_uses_webbrowser() -> None:
    with patch("iris.automation.web_browser.webbrowser.open") as wb:
        ok, _ = open_url("https://example.com", "system", {})
    assert ok is True
    wb.assert_called_once_with("https://example.com")


def test_resolve_browser_key_from_settings() -> None:
    settings = MagicMock(spec=Settings)
    settings.default_web_browser = "edge"
    from iris.automation.web_browser import resolve_browser_key

    assert resolve_browser_key(settings) == "edge"


def test_resolve_browser_executable_system_is_none() -> None:
    assert resolve_browser_executable("system", {"chrome": "x"}) is None
    assert resolve_browser_executable("chrome", {"chrome": "x.exe"}) == "x.exe"
