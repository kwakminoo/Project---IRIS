"""IDE Workspace 경로 해석."""

from __future__ import annotations

from pathlib import Path

from iris.config.settings import Settings


def _find_repo_root() -> Path:
  """iris 패키지 기준 저장소 루트 추정."""
  here = Path(__file__).resolve()
  for parent in here.parents:
    if (parent / "iris-ide").is_dir():
      return parent
    if (parent / ".git").is_dir():
      return parent
  return Path.cwd()


def resolve_ide_workspace(settings: Settings) -> Path:
  """
  Settings.ide_workspace_path 우선.
  미설정 시 빈 startup workspace (~/.iris/ide-empty-workspace) — 프로젝트 폴더 자동 미오픈.
  """
  raw = (settings.ide_workspace_path or "").strip()
  if raw:
    path = Path(raw).expanduser().resolve()
  else:
    path = (Path.home() / ".iris" / "ide-empty-workspace").resolve()
    path.mkdir(parents=True, exist_ok=True)
  if not path.exists():
    raise FileNotFoundError(f"IDE workspace 경로가 없습니다: {path}")
  if not path.is_dir():
    raise NotADirectoryError(f"IDE workspace는 디렉터리여야 합니다: {path}")
  return path
