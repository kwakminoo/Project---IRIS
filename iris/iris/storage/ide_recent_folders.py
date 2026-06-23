"""IDE 최근 열었던 폴더 목록 — ~/.iris/ide-recent-folders.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_STORE = Path.home() / ".iris" / "ide-recent-folders.json"


def _load() -> list[dict[str, str]]:
  if not _STORE.is_file():
    return []
  try:
    data = json.loads(_STORE.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return []
  if not isinstance(data, list):
    return []
  return [row for row in data if isinstance(row, dict)]


def _save(rows: list[dict[str, str]]) -> None:
  _STORE.parent.mkdir(parents=True, exist_ok=True)
  _STORE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def list_recent_folders(limit: int = 5) -> list[tuple[str, str]]:
  """(폴더명, 전체 경로) — 최근 순."""
  rows = _load()
  out: list[tuple[str, str]] = []
  for row in rows:
    path = str(row.get("path", "")).strip()
    if not path:
      continue
    name = str(row.get("name", "")).strip() or Path(path).name or path
    out.append((name, path))
    if len(out) >= limit:
      break
  return out


def record_opened_folder(path: Path) -> None:
  """폴더 열기 시 목록 갱신 — 향후 Open folder 연결용."""
  resolved = str(path.expanduser().resolve())
  name = path.name or resolved
  rows = [r for r in _load() if str(r.get("path", "")) != resolved]
  rows.insert(
    0,
    {
      "name": name,
      "path": resolved,
      "opened_at": datetime.now(timezone.utc).isoformat(),
    },
  )
  _save(rows[:20])


def truncate_path_middle(path: str, max_len: int = 52) -> str:
  if len(path) <= max_len:
    return path
  head = max_len // 2 - 2
  tail = max_len - head - 3
  return f"{path[:head]}...{path[-tail:]}"
