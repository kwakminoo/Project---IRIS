"""uia_reader 요약·cap 테스트 (pywinauto 불필요)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iris.automation.uia_reader import (
    UiaElementSummary,
    format_uia_json,
    is_uia_summary_sparse,
    summarize_elements,
)


@dataclass
class _FakeElem:
    _text: str
    _type: str = "Button"
    _bounds: tuple[int, int, int, int] | None = (0, 0, 10, 10)
    _aid: str = ""

    def window_text(self) -> str:
        return self._text

    def friendly_class_name(self) -> str:
        return self._type

    def rectangle(self) -> Any:
        if not self._bounds:
            return None

        class _R:
            def __init__(self, b: tuple[int, int, int, int]) -> None:
                self.left, self.top, self.right, self.bottom = b

        return _R(self._bounds)

    def legacy_properties(self) -> dict[str, str]:
        return {"AutomationId": self._aid} if self._aid else {}


def test_format_uia_json_under_cap() -> None:
    elems = [_FakeElem(f"btn{i}", "Button", _aid=f"id{i}") for i in range(5)]
    summaries, js = summarize_elements(elems, window_title="Test", max_chars=2048)
    assert len(summaries) == 5
    assert len(js) <= 2048
    assert "Test" in js


def test_format_uia_json_truncates_many_elements() -> None:
    elems = [_FakeElem("x" * 50, "Button") for _ in range(200)]
    _, js = summarize_elements(elems, window_title="Big", max_chars=500)
    assert len(js) <= 500


def test_is_uia_summary_sparse_empty() -> None:
    assert is_uia_summary_sparse("")
    assert is_uia_summary_sparse('{"window":"w","elements":[]}')


def test_is_uia_summary_sparse_has_button() -> None:
    js = format_uia_json(
        [UiaElementSummary("OK", "Button", (0, 0, 1, 1))],
        "w",
    )
    assert not is_uia_summary_sparse(js)
