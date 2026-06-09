"""pytest 공통 설정·테스트 더블."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pytest

from iris.ai.gemma_client import ChatMessage
from iris.config.settings import Settings, load_settings


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: Windows GUI 통합 테스트 (기본 실행 제외: pytest -m 'not integration')",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`-m` 미지정 시 integration 테스트 스킵."""
    if config.getoption("-m", default=None):
        return
    skip = pytest.mark.skip(reason="integration (run: pytest -m integration)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


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
