"""설정된 기본 웹 브라우저로 URL 열기."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from iris.config.settings import Settings

# 논리 키 → app_paths 키
_BROWSER_APP_KEYS: dict[str, str] = {
    "chrome": "chrome",
    "edge": "edge",
    "firefox": "firefox",
}

_BROWSER_LABELS: dict[str, str] = {
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "firefox": "Mozilla Firefox",
    "system": "Windows 기본 브라우저",
}

_DEFAULT_BROWSER = "chrome"


def normalize_browser_key(raw: str | None) -> str:
    """환경/설정 값을 허용된 브라우저 키로 정규화."""
    key = (raw or _DEFAULT_BROWSER).strip().lower()
    aliases = {
        "msedge": "edge",
        "microsoft": "edge",
        "microsoft edge": "edge",
        "google chrome": "chrome",
        "mozilla": "firefox",
        "default": "system",
        "windows": "system",
    }
    key = aliases.get(key, key)
    if key in _BROWSER_APP_KEYS or key == "system":
        return key
    return _DEFAULT_BROWSER


def browser_label(browser_key: str) -> str:
    return _BROWSER_LABELS.get(normalize_browser_key(browser_key), browser_key)


def list_installed_browser_options(app_paths: Dict[str, str]) -> list[tuple[str, str]]:
    """설정 콤보용 (키, 표시 이름) — 설치된 브라우저 + system."""
    options: list[tuple[str, str]] = []
    for key in ("chrome", "edge", "firefox"):
        if key in app_paths:
            options.append((key, _BROWSER_LABELS[key]))
    options.append(("system", _BROWSER_LABELS["system"]))
    return options or [("system", _BROWSER_LABELS["system"])]


def resolve_browser_key(settings: Settings | None = None) -> str:
    if settings is not None and hasattr(settings, "default_web_browser"):
        return normalize_browser_key(settings.default_web_browser)
    return normalize_browser_key(os.getenv("DEFAULT_WEB_BROWSER", _DEFAULT_BROWSER))


def resolve_browser_executable(browser_key: str, app_paths: Dict[str, str]) -> str | None:
    """브라우저 실행 파일 경로. system이면 None."""
    key = normalize_browser_key(browser_key)
    if key == "system":
        return None
    app_key = _BROWSER_APP_KEYS.get(key)
    if not app_key:
        return None
    return app_paths.get(app_key)


def open_url(
    url: str,
    browser_key: str,
    app_paths: Dict[str, str],
) -> tuple[bool, str]:
    """
    URL을 지정 브라우저에서 연다.
    반환: (성공 여부, 사용자 메시지)
    """
    key = normalize_browser_key(browser_key)
    if key == "system":
        try:
            webbrowser.open(url)
            return True, "Windows 기본 브라우저에서 URL을 열었습니다."
        except Exception as e:
            return False, str(e)

    exe = resolve_browser_executable(key, app_paths)
    if not exe:
        # 요청 브라우저 미설치 → system 폴백
        try:
            webbrowser.open(url)
            label = browser_label(key)
            return True, f"{label}을(를) 찾지 못해 Windows 기본 브라우저로 열었습니다."
        except Exception as e:
            return False, f"{browser_label(key)} 실행 파일을 찾을 수 없습니다: {e}"

    try:
        subprocess.Popen([exe, url], close_fds=True)  # noqa: S603
        return True, f"{browser_label(key)}에서 URL을 열었습니다."
    except Exception as e:
        return False, str(e)
