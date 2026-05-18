"""pytest 공통 설정."""

from __future__ import annotations

import pytest


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
