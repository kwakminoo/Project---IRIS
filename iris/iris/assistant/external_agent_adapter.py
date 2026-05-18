"""Tier 4 외부 에이전트(OpenClaw/Hermes) 통합 — 로컬 Computer Use 실패 시에만 위임."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from iris.assistant.openclaw_adapter import OpenClawActionBackend, OpenClawResult
from iris.storage.database import Database

if TYPE_CHECKING:
    from iris.config.settings import Settings


@dataclass(frozen=True)
class ExternalAgentResult:
    """외부 CLI 실행 결과(내부용; 사용자에게 raw 노출 금지)."""

    success: bool
    message: str
    backend_id: str


@runtime_checkable
class ExternalAgentBackend(Protocol):
    """Tier 4 백엔드 공통 인터페이스."""

    @property
    def backend_id(self) -> str: ...

    def is_available(self) -> bool: ...

    def execute_task(self, goal: str, context: str) -> ExternalAgentResult: ...


class OpenClawBackend:
    """OpenClaw CLI — 기존 OpenClawActionBackend 래핑."""

    def __init__(self, inner: OpenClawActionBackend) -> None:
        self._inner = inner

    @property
    def backend_id(self) -> str:
        return "openclaw"

    def is_available(self) -> bool:
        # Tier 4: CLI만 있으면 시도 가능(OPENCLAW_ENABLED와 별개)
        return self._inner.cli_available()

    def execute_task(self, goal: str, context: str) -> ExternalAgentResult:
        prompt = f"{goal.strip()}\n\n--- Iris 컨텍스트 ---\n{context.strip()}"
        r: OpenClawResult = self._inner.execute_task(prompt)
        return ExternalAgentResult(r.success, r.message, self.backend_id)


class HermesBackend:
    """Hermes CLI(선택). 설치되지 않으면 Unavailable."""

    def __init__(self, cli_path: str, timeout_seconds: int) -> None:
        self._cli = cli_path.strip() or "hermes"
        self._timeout = max(5, timeout_seconds)

    @property
    def backend_id(self) -> str:
        return "hermes"

    def _resolve_exe(self) -> str | None:
        p = Path(self._cli)
        if p.is_file():
            return str(p)
        return shutil.which(self._cli)

    def is_available(self) -> bool:
        return self._resolve_exe() is not None

    def execute_task(self, goal: str, context: str) -> ExternalAgentResult:
        exe = self._resolve_exe()
        if not exe:
            return ExternalAgentResult(False, "Hermes CLI를 찾을 수 없습니다.", self.backend_id)
        # 실제 Hermes CLI 스펙에 맞게 추후 조정. 기본은 run + 단일 프롬프트.
        payload = f"{goal.strip()}\n\n{context.strip()}"
        try:
            proc = subprocess.run(
                [exe, "run", payload],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
            )
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            text = out or err or ("ok" if proc.returncode == 0 else "실패")
            return ExternalAgentResult(proc.returncode == 0, text, self.backend_id)
        except FileNotFoundError:
            return ExternalAgentResult(False, "Hermes 실행 파일을 찾을 수 없습니다.", self.backend_id)
        except subprocess.TimeoutExpired:
            return ExternalAgentResult(False, "Hermes 실행 시간 초과", self.backend_id)
        except OSError as e:
            return ExternalAgentResult(False, f"Hermes 실행 오류: {e}", self.backend_id)


def build_external_backend(settings: Settings) -> ExternalAgentBackend | None:
    """EXTERNAL_AGENT_BACKEND에 맞는 구현체. none/알 수 없음이면 None."""
    key = settings.external_agent_backend.strip().lower()
    if key == "openclaw":
        return OpenClawBackend(OpenClawActionBackend.from_settings(settings))
    if key == "hermes":
        return HermesBackend(
            settings.hermes_cli_path,
            settings.openclaw_timeout_seconds,
        )
    return None


def user_facing_tier4_line(success: bool) -> str:
    """ActionExecutor 등 LLM 요약 없이 사용자에게 줄 짧은 한국어."""
    if success:
        return (
            "Iris가 요청을 처리했습니다. "
            "결과가 의도와 다르면 화면을 확인한 뒤 다시 알려 주세요."
        )
    return (
        "Iris가 대안을 시도했으나 완료하지 못했습니다. "
        "조건을 바꿔 다시 요청해 주시면 감사하겠습니다."
    )


def tier4_delegate_active(settings: Settings | None) -> bool:
    """위임 경로가 켜져 있고 백엔드가 none이 아닌지."""
    if settings is None:
        return False
    if not settings.external_agent_fallback_enabled:
        return False
    return settings.external_agent_backend.strip().lower() != "none"


def external_backend_status_line(settings: Settings | None) -> str:
    """
    상태줄: Iris Local + 선택 Tier4 백엔드 가용성.
    사용자 메시지에는 브랜드 강조 없이 유지하되, 상태줄은 기술 식별용.
    """
    local = "Iris Local (Connected)"
    if settings is None:
        return f"Backend: {local} | OpenClaw (Unavailable) | Hermes (Unavailable)"

    oc_inner = OpenClawActionBackend.from_settings(settings)
    oc_state = "Connected" if oc_inner.cli_available() else "Unavailable"
    hb = HermesBackend(settings.hermes_cli_path, settings.openclaw_timeout_seconds)
    hm_state = "Connected" if hb.is_available() else "Unavailable"

    return f"Backend: {local} | OpenClaw ({oc_state}) | Hermes ({hm_state})"


def log_external_delegate(
    db: Database,
    *,
    goal: str,
    backend: str,
    success: bool,
    duration_ms: int,
    summary_ko: str,
) -> None:
    """SQLite logs.type = external_agent_delegate."""
    payload = json.dumps(
        {
            "goal": goal[:500],
            "backend": backend,
            "success": success,
            "duration_ms": duration_ms,
        },
        ensure_ascii=False,
    )
    db.insert_log("external_agent_delegate", payload, summary_ko[:500])


def run_external_delegate(
    backend: ExternalAgentBackend,
    *,
    goal: str,
    context: str,
) -> tuple[ExternalAgentResult, int]:
    """외부 백엔드 실행 + 소요 ms (로그는 호출측에서 요약과 함께 기록)."""
    t0 = time.perf_counter()
    res = backend.execute_task(goal, context)
    ms = int((time.perf_counter() - t0) * 1000)
    return res, ms
