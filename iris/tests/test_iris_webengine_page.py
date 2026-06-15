"""IrisWebEnginePage 헬퍼 테스트."""

from __future__ import annotations

from enum import Enum

from iris.ui.ide.iris_webengine_page import _enum_label


class _SampleLevel(Enum):
    INFO = 1


def test_enum_label_uses_name() -> None:
    assert _enum_label(_SampleLevel.INFO) == "INFO"


def test_enum_label_falls_back_to_str() -> None:
    assert _enum_label("plain") == "plain"
