"""OpenClaw를 Iris 내부 Action Backend로 호출하는 어댑터."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings


@dataclass(frozen=True)
class OpenClawResult:
    """OpenClaw CLI 실행 결과."""

    success: bool
    message: str


def openclaw_backend_status_label(backend: OpenClawActionBackend) -> str:
    """설정 화면·상태줄용 짧은 문구."""
    if not backend.enabled_flag():
        return "OpenClaw backend: Disabled"
    if backend.is_available():
        return "OpenClaw backend: Connected"
    return "OpenClaw backend: Unavailable"


class OpenClawActionBackend:
    """
    OpenClaw CLI를 subprocess로 호출.
    실제 CLI 인자는 배포 환경에 맞게 조정 가능(기본: run + 프롬프트).
    """

    def __init__(
        self,
        *,
        enabled: bool,
        cli_path: str,
        session_id: str,
        timeout_seconds: int,
    ) -> None:
        self._enabled = enabled
        self._cli = cli_path
        self._session = session_id
        self._timeout = max(5, timeout_seconds)

    @classmethod
    def from_settings(cls, settings: "Settings") -> "OpenClawActionBackend":
        return cls(
            enabled=settings.openclaw_enabled,
            cli_path=settings.openclaw_cli_path,
            session_id=settings.openclaw_session_id,
            timeout_seconds=settings.openclaw_timeout_seconds,
        )

    def enabled_flag(self) -> bool:
        """환경에서 기능 켜짐 여부."""
        return self._enabled

    def cli_available(self) -> bool:
        """CLI 실행 파일 경로 해석 가능 여부(Tier 4 등에서 OPENCLAW_ENABLED와 무관하게 사용)."""
        return self._resolve_cli_executable() is not None

    def is_available(self) -> bool:
        """설정이 켜져 있고 실행 파일을 찾을 수 있으면 True."""
        if not self._enabled:
            return False
        return self.cli_available()

    def _resolve_cli_executable(self) -> str | None:
        p = Path(self._cli)
        if p.is_file():
            return str(p)
        w = shutil.which(self._cli)
        return w

    def _base_cmd(self) -> list[str] | None:
        exe = self._resolve_cli_executable()
        if not exe:
            return None
        return [exe]

    def execute_task(self, task_description: str, session_id: str | None = None) -> OpenClawResult:
        """범용 작업 위임."""
        cmd = self._base_cmd()
        if not cmd:
            return OpenClawResult(False, "OpenClaw CLI 경로를 찾을 수 없습니다.")
        sess = session_id or self._session
        # 일반적인 패턴: openclaw run [--session ID] "프롬프트"
        args = [*cmd, "run", "--session", sess, task_description]
        return self._run_args(args)

    def launch_app(self, app_name: str) -> OpenClawResult:
        """앱 실행 전용 프롬프트."""
        return self.execute_task(f"다음 애플리케이션을 실행해 주세요: {app_name}")

    def handle_file_task(self, task_description: str) -> OpenClawResult:
        """파일 검색·열기 등."""
        return self.execute_task(f"[파일 작업] {task_description}")

    def handle_complex_automation(self, task_description: str) -> OpenClawResult:
        """복잡한 자동화."""
        return self.execute_task(f"[자동화] {task_description}")

    def _run_args(self, args: list[str]) -> OpenClawResult:
        try:
            r = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
            )
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            text = out or err or ("ok" if r.returncode == 0 else "실패")
            return OpenClawResult(r.returncode == 0, text)
        except FileNotFoundError:
            return OpenClawResult(False, "OpenClaw 실행 파일을 찾을 수 없습니다.")
        except subprocess.TimeoutExpired:
            return OpenClawResult(False, "OpenClaw 실행 시간 초과")
        except OSError as e:
            return OpenClawResult(False, f"OpenClaw 실행 오류: {e}")
