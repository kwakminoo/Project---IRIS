"""pytest 공통 설정·테스트 더블."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any, Sequence

import pytest

from iris.ai.gemma_client import ChatMessage
from iris.config.settings import Settings, load_settings

# integration Job 대상 — 모듈 전체가 컴포넌트 연결 검증인 파일
_INTEGRATION_MODULES = frozenset({
    "test_task_runtime_real_integration",
    "test_task_runtime_phase1_injection",
    "test_task_runtime_phase2_task_creation",
    "test_task_runtime_phase3_recording",
    "test_task_runtime_skill_verification",
    "test_execution_coordinator",
    "test_cu_task_adapter",
})

# 혼합 모듈 내 integration 대상 개별 테스트
_INTEGRATION_TESTS = frozenset({
    ("test_task_runtime_stabilization", "test_quick_launch_creates_task"),
    ("test_task_runtime_stabilization", "test_action_skill_creates_task"),
    ("test_task_runtime_stabilization", "test_approved_action_records_attempt_and_result"),
    ("test_task_runtime_stabilization", "test_approval_resume_uses_existing_proposal"),
    ("test_task_runtime_stabilization", "test_checkpoint_success_completes_step"),
    ("test_task_runtime_stabilization", "test_foreign_key_check_has_no_errors"),
    ("test_task_runtime_stabilization", "test_migration_failure_is_not_silently_ignored"),
    ("test_task_runtime_stabilization", "test_running_task_is_discovered_after_restart"),
    ("test_task_runtime_stabilization", "test_waiting_approval_task_restores_pending_proposal"),
    ("test_task_runtime_stabilization", "test_resume_continues_same_task_id"),
    ("test_task_runtime_recovery_commands", "test_startup_discovers_recoverable_task"),
    ("test_task_runtime_recovery_commands", "test_continue_command_resumes_same_task_id"),
    ("test_task_runtime_recovery_commands", "test_waiting_approval_restores_existing_proposal"),
    ("test_task_runtime_recovery_commands", "test_resume_does_not_duplicate_completed_attempt"),
    ("test_sqlite_task_repositories", "test_plan_and_steps_persist"),
    ("test_sqlite_task_repositories", "test_schema_migrations_applied"),
})


def pytest_configure(config: pytest.Config) -> None:
    ini_markers = config.getini("markers") or []
    config.addinivalue_line("markers", "timeout(seconds): optional timeout marker")
    if not ini_markers:
        config.addinivalue_line(
            "markers",
            "integration: Iris 컴포넌트 간 실제 연결을 검증하는 테스트",
        )
        config.addinivalue_line("markers", "windows_only: Windows API가 필요한 테스트")
        config.addinivalue_line(
            "markers",
            "windows_smoke: 실제 Windows 앱과 UI를 조작하는 테스트",
        )
        config.addinivalue_line(
            "markers",
            "windows_smoke_gui: Windows GUI 세션이 필요한 스모크 테스트",
        )
        config.addinivalue_line(
            "markers",
            "external_service: 외부 API 또는 네트워크 서비스가 필요한 테스트",
        )
        config.addinivalue_line(
            "markers",
            "requires_model: 실제 AI 모델 실행이 필요한 테스트",
        )
        config.addinivalue_line("markers", "slow: 상대적으로 오래 걸리는 테스트")


def pytest_addoption(parser: pytest.Parser) -> None:
    """pytest-timeout이 없는 로컬 venv에서도 --timeout 옵션을 인식한다.

    pytest-timeout이 설치돼 있으면 그 플러그인이 --timeout을 등록하므로,
    스텁을 추가하면 'option names {--timeout} already added' 충돌이 난다.
    따라서 플러그인이 없을 때만 스텁을 등록한다.
    """
    import importlib.util

    if importlib.util.find_spec("pytest_timeout") is not None:
        return
    group = parser.getgroup("timeout")
    group.addoption(
        "--timeout",
        action="store",
        default=None,
        help="timeout in seconds (pytest-timeout compatible stub)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """integration 마커 자동 부착 및 `-m` 미지정 시 선택적 skip."""
    for item in items:
        module_stem = Path(str(item.fspath)).stem
        if module_stem in _INTEGRATION_MODULES or (module_stem, item.name) in _INTEGRATION_TESTS:
            if "integration" not in item.keywords:
                item.add_marker(pytest.mark.integration)

    if config.getoption("-m", default=None):
        return

    skip_int = pytest.mark.skip(reason="integration (run: pytest -m integration)")
    skip_smoke = pytest.mark.skip(reason="windows_smoke (run: pytest -m windows_smoke)")
    skip_ext = pytest.mark.skip(reason="external_service")
    skip_model = pytest.mark.skip(reason="requires_model")
    skip_win = pytest.mark.skip(reason="windows_only (Windows 전용)")

    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_int)
        if "windows_smoke" in item.keywords:
            item.add_marker(skip_smoke)
        if "external_service" in item.keywords:
            item.add_marker(skip_ext)
        if "requires_model" in item.keywords:
            item.add_marker(skip_model)
        if "windows_only" in item.keywords and "windows_smoke" not in item.keywords:
            if platform.system() != "Windows":
                item.add_marker(skip_win)


def load_test_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """load_settings 기반 — Settings 필드 추가 시 테스트 깨짐 방지."""
    from dataclasses import replace

    env_path = tmp_path / "test.env"
    env_path.write_text("", encoding="utf-8")
    base = load_settings(env_path)
    if overrides:
        return replace(base, **overrides)  # type: ignore[arg-type]
    return base


def accept_purpose_chat(
    messages: Sequence[ChatMessage],
    purpose: Any = None,
    **kwargs: Any,
) -> str:
    """FakeGemma 기본 chat 시그니처 — production GemmaClient와 호환."""
    _ = (messages, purpose, kwargs)
    return ""


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return load_test_settings(tmp_path)
