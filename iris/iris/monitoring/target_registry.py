"""모니터링 대상 레지스트리 (메모리 + DB 동기화)."""

from __future__ import annotations

from typing import Dict, List, Optional

from iris.monitoring.models import MonitoredTarget, StatusCategory, TargetType
from iris.storage.database import Database


class TargetRegistry:
    """실행된 앱/창 후보 등록."""

    def __init__(self, db: Optional[Database] = None) -> None:
        self._db = db
        self._cache: Dict[str, MonitoredTarget] = {}

    def register(self, key: str, title_hint: str) -> None:
        """레거시 콜백: 키 + 제목 힌트."""
        self._cache[key] = MonitoredTarget(
            id=None,
            type=TargetType.DESKTOP_WINDOW,
            title=title_hint,
            process_name=key,
        )
        if self._db:
            self._db.merge_or_insert_desktop_target(title_hint, key)

    def list_memory(self) -> List[MonitoredTarget]:
        return list(self._cache.values())
