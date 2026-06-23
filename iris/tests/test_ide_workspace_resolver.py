"""IDE workspace 경로 해석 테스트."""

from __future__ import annotations

from pathlib import Path

from iris.infrastructure.ide.ide_workspace_resolver import resolve_ide_workspace


class _FakeSettings:
  ide_workspace_path = ""


def test_default_workspace_is_empty_startup_dir(
  tmp_path: Path, monkeypatch
) -> None:
  monkeypatch.setattr(
    "iris.infrastructure.ide.ide_workspace_resolver.Path.home",
    lambda: tmp_path,
  )
  ws = resolve_ide_workspace(_FakeSettings())
  assert ws == (tmp_path / ".iris" / "ide-empty-workspace").resolve()
  assert ws.is_dir()
