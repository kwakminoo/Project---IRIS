"""Chrome 확장 연결 상태 — 설정 UI·헬스 프로브."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings
    from iris.monitoring.browser_tab_monitor import BrowserTabMonitor

# 이 시간 이내 ingest가 있으면 「연결됨」
INGEST_CONNECTED_MAX_AGE_SEC = 180.0


class ExtensionLinkLevel(str, Enum):
    """확장 연결 단계."""

    SERVER_DOWN = "server_down"
    WAITING_EXTENSION = "waiting_extension"
    CONNECTED = "connected"


@dataclass(frozen=True)
class ChromeExtensionStatus:
    level: ExtensionLinkLevel
    summary: str
    detail: str
    port: int
    server_listening: bool
    health_ok: bool
    last_ingest_seconds_ago: float | None
    tracked_tab_count: int
    total_ingest_count: int


def resolve_chrome_extension_dir() -> "Path":
    """저장소 루트의 chrome-extension 폴더."""
    from pathlib import Path

    app_root = Path(__file__).resolve().parent.parent.parent
    return (app_root.parent / "chrome-extension").resolve()


def probe_extension_health(
    host: str,
    port: int,
    token: str = "",
    *,
    timeout_sec: float = 1.2,
) -> bool:
    """GET /health — 수신 서버 응답 여부."""
    url = f"http://{host}:{port}/health"
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status != 200:
                return False
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return bool(data.get("ok"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return False


def evaluate_extension_status(
    settings: Settings,
    browser: BrowserTabMonitor,
    *,
    server_active: bool,
) -> ChromeExtensionStatus:
    """설정창 표시용 상태 문자열."""
    host = settings.iris_extension_host or "127.0.0.1"
    port = int(settings.iris_extension_port)
    token = settings.iris_extension_token or ""

    health_ok = False
    if server_active:
        health_ok = probe_extension_health(host, port, token)

    age = browser.last_ingest_age_seconds()
    tabs = browser.tracked_tab_count()
    total = browser.total_ingest_count()

    if not server_active or not health_ok:
        return ChromeExtensionStatus(
            level=ExtensionLinkLevel.SERVER_DOWN,
            summary="미연결 — Iris 수신 서버 없음",
            detail=(
                f"127.0.0.1:{port} 에서 확장 데이터를 받지 못하고 있습니다. "
                "「동기화」로 Chrome 확장 설치·허용을 진행하세요."
            ),
            port=port,
            server_listening=bool(server_active and health_ok),
            health_ok=health_ok,
            last_ingest_seconds_ago=age,
            tracked_tab_count=tabs,
            total_ingest_count=total,
        )

    if age is None or age > INGEST_CONNECTED_MAX_AGE_SEC:
        wait_detail = (
            f"수신 서버는 동작 중입니다 (포트 {port}). "
            "Chrome에 Iris Tab Monitor가 설치·URL 규칙(예: YouTube)이 켜져 있는지 확인하세요."
        )
        if age is not None:
            wait_detail += f" 마지막 수신: {int(age)}초 전."
        else:
            wait_detail += " 아직 확장에서 데이터가 오지 않았습니다."
        return ChromeExtensionStatus(
            level=ExtensionLinkLevel.WAITING_EXTENSION,
            summary="대기 중 — 확장 설치·사이트 허용 필요",
            detail=wait_detail,
            port=port,
            server_listening=True,
            health_ok=True,
            last_ingest_seconds_ago=age,
            tracked_tab_count=tabs,
            total_ingest_count=total,
        )

    return ChromeExtensionStatus(
        level=ExtensionLinkLevel.CONNECTED,
        summary="연결됨 — Chrome 확장 동작 중",
        detail=(
            f"포트 {port} · 추적 탭 {tabs}개 · "
            f"마지막 수신 {int(age)}초 전 · 누적 ingest {total}회"
        ),
        port=port,
        server_listening=True,
        health_ok=True,
        last_ingest_seconds_ago=age,
        tracked_tab_count=tabs,
        total_ingest_count=total,
    )
