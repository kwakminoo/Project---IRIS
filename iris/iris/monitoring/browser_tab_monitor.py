"""Chrome 확장에서 수신한 탭 상태 정규화."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List


_SENSITIVE_URL = re.compile(
    r"(checkout|payment|billing|password|signin|login|auth/|oauth|wallet|card)",
    re.IGNORECASE,
)


@dataclass
class BrowserTabPayload:
    tab_id: int
    title: str
    url: str
    visible_text: str
    timestamp: float = field(default_factory=time.time)
    youtube_search_results: list[tuple[str, str]] = field(default_factory=list)


class BrowserTabMonitor:
    """tab_id별 마지막 페이로드 (스니펫만 유지)."""

    def __init__(self, max_text: int = 4000) -> None:
        self._max_text = max_text
        self._lock = threading.Lock()
        self._by_tab: Dict[int, BrowserTabPayload] = {}
        self._youtube_by_search_key: Dict[str, list[tuple[str, str]]] = {}

    def ingest(
        self,
        tab_id: int,
        title: str,
        url: str,
        visible_text: str,
        *,
        youtube_search_results: list[tuple[str, str]] | None = None,
    ) -> bool:
        """민감 URL이면 False."""
        if _SENSITIVE_URL.search(url or ""):
            return False
        vt = (visible_text or "")[: self._max_text]
        yt_pairs = list(youtube_search_results or [])[:8]
        with self._lock:
            self._by_tab[tab_id] = BrowserTabPayload(
                tab_id=tab_id,
                title=title or "",
                url=url or "",
                visible_text=vt,
                youtube_search_results=yt_pairs,
            )
            if yt_pairs and "youtube.com/results" in (url or ""):
                key = self._search_url_key(url)
                if key:
                    self._youtube_by_search_key[key] = yt_pairs
        return True

    @staticmethod
    def _search_url_key(url: str) -> str:
        """search_query 기준 매칭 키 (쿼리 순서 무관)."""
        from urllib.parse import parse_qs, urlparse

        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            q = (qs.get("search_query") or [""])[0].strip().lower()
            if q:
                return q
        except Exception:
            pass
        base = (url or "").split("#")[0].split("?")[0].rstrip("/").lower()
        return base

    def youtube_results_for_search(self, search_url: str) -> list[tuple[str, str]] | None:
        """YouTube 검색 URL과 매칭되는 DOM 결과 (제목, watch URL)."""
        key = self._search_url_key(search_url)
        with self._lock:
            if key and key in self._youtube_by_search_key:
                return list(self._youtube_by_search_key[key])
            for p in self._by_tab.values():
                if not p.youtube_search_results:
                    continue
                if search_url and p.url and (
                    p.url == search_url
                    or p.url.startswith(search_url.split("#")[0])
                    or search_url.startswith(p.url.split("#")[0])
                ):
                    return list(p.youtube_search_results)
                if key and self._search_url_key(p.url) == key:
                    return list(p.youtube_search_results)
        return None

    def snapshot_lines(self) -> List[str]:
        """가상 타깃용 텍스트 라인."""
        with self._lock:
            items = list(self._by_tab.values())
        lines: List[str] = []
        for p in items:
            lines.append(f"[tab {p.tab_id}] {p.title} | {p.url}")
            lines.append(p.visible_text[:2000])
        return lines

    def text_for_url_prefix(self, url_prefix: str) -> str:
        """등록된 탭 URL과 매칭되는 페이로드 텍스트."""
        with self._lock:
            items = list(self._by_tab.values())
        for p in items:
            if not url_prefix or (p.url and p.url.startswith(url_prefix.split("?")[0])):
                return f"{p.title}\n{p.url}\n{p.visible_text}"
        return ""

    def combined_text(self) -> str:
        return "\n".join(self.snapshot_lines())
