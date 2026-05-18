"""automation 패키지.

실행기 import는 assistant 계층과 서로 참조하므로 lazy import로 유지한다.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ActionExecutor", "launch_by_key", "launch_executable"]


def __getattr__(name: str) -> Any:
    if name == "ActionExecutor":
        from iris.automation.action_executor import ActionExecutor

        return ActionExecutor
    if name in {"launch_by_key", "launch_executable"}:
        from iris.automation import process_launcher

        return getattr(process_launcher, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
