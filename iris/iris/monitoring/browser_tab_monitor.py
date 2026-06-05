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

# YouTube DOM play — 확장 ingest 이벤트 대기 상한
_DEFAULT_YOUTUBE_RESULTS_WAIT_SEC = 8.0
_INGEST_WAIT_SLICE_SEC = 0.05


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
        self._cond = threading.Condition()
        self._by_tab: Dict[int, BrowserTabPayload] = {}
        self._youtube_by_search_key: Dict[str, list[tuple[str, str]]] = {}
        self._last_ingest_at: float = 0.0
        self._ingest_count: int = 0

    def ingest(
        self,
        tab_id: int,
        title: str,
        url: str,
        visible_text: str,
        *,
        youtube_search_results: list[tuple[str, str]] | None = None,
    ) -> bool:
        """민감 URL이면 False. 성공 시 ingest 이벤트로 대기 중 스레드를 깨움."""
        if _SENSITIVE_URL.search(url or ""):
            return False
        vt = (visible_text or "")[: self._max_text]
        yt_pairs = list(youtube_search_results or [])[:8]
        with self._cond:
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
            self._last_ingest_at = time.time()
            self._ingest_count += 1
            self._cond.notify_all()
        return True

    def last_ingest_age_seconds(self) -> float | None:
        """마지막 확장 ingest 이후 경과 초. 없으면 None."""
        with self._cond:
            if self._last_ingest_at <= 0:
                return None
            return max(0.0, time.time() - self._last_ingest_at)

    def tracked_tab_count(self) -> int:
        with self._cond:
            return len(self._by_tab)

    def total_ingest_count(self) -> int:
        with self._cond:
            return self._ingest_count

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

    def _youtube_results_locked(self, search_url: str) -> list[tuple[str, str]] | None:
        """Condition 보유 중 호출 — YouTube 검색 결과 (제목, watch URL)."""
        key = self._search_url_key(search_url)
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

    def youtube_results_for_search(self, search_url: str) -> list[tuple[str, str]] | None:
        """YouTube 검색 URL과 매칭되는 DOM 결과 (제목, watch URL)."""
        with self._cond:
            return self._youtube_results_locked(search_url)

    def wait_for_youtube_search_results(
        self,
        search_url: str,
        *,
        timeout_sec: float = _DEFAULT_YOUTUBE_RESULTS_WAIT_SEC,
        after_ingest_count: int | None = None,
        wait_slice_sec: float = _INGEST_WAIT_SLICE_SEC,
    ) -> list[tuple[str, str]] | None:
        """
        이벤트·조건 기반 대기 — 결과가 있으면 즉시 반환, 타임아웃까지 ingest notify로 재검사.
        after_ingest_count: 지정 시 그 이후 새 ingest가 온 뒤에만 결과를 인정(검색 URL 연 직후용).
        """
        if not (search_url or "").strip():
            return None
        deadline = time.monotonic() + max(0.0, timeout_sec)
        wait_round = 0
        with self._cond:
            while True:
                if after_ingest_count is None or self._ingest_count > after_ingest_count:
                    pairs = self._youtube_results_locked(search_url)
                    if pairs:
                        return list(pairs)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                wait_round += 1
                self._cond.wait(timeout=min(wait_slice_sec, remaining))
        return None

    def snapshot_lines(self) -> List[str]:
        """가상 타깃용 텍스트 라인."""
        with self._cond:
            items = list(self._by_tab.values())
        lines: List[str] = []
        for p in items:
            lines.append(f"[tab {p.tab_id}] {p.title} | {p.url}")
            lines.append(p.visible_text[:2000])
        return lines

    def text_for_url_prefix(self, url_prefix: str) -> str:
        """등록된 탭 URL과 매칭되는 페이로드 텍스트."""
        with self._cond:
            items = list(self._by_tab.values())
        for p in items:
            if not url_prefix or (p.url and p.url.startswith(url_prefix.split("?")[0])):
                return f"{p.title}\n{p.url}\n{p.visible_text}"
        return ""

    def combined_text(self) -> str:
        return "\n".join(self.snapshot_lines())
