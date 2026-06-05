"""BrowserTabMonitor — 이벤트·조건 기반 YouTube 결과 대기."""

from __future__ import annotations

import threading
import time

from iris.monitoring.browser_tab_monitor import BrowserTabMonitor


def test_wait_returns_immediately_when_results_present() -> None:
    monitor = BrowserTabMonitor()
    url = "https://www.youtube.com/results?search_query=fast"
    monitor.ingest(
        1,
        "YouTube",
        url,
        "x",
        youtube_search_results=[
            ("제목", "https://www.youtube.com/watch?v=abc123"),
        ],
    )
    t0 = time.monotonic()
    pairs = monitor.wait_for_youtube_search_results(url, timeout_sec=2.0)
    elapsed = time.monotonic() - t0
    assert pairs is not None
    assert len(pairs) == 1
    assert elapsed < 0.15


def test_wait_wakes_on_ingest_event() -> None:
    monitor = BrowserTabMonitor()
    url = "https://www.youtube.com/results?search_query=event"
    baseline = monitor.total_ingest_count()

    def _delayed_ingest() -> None:
        time.sleep(0.08)
        monitor.ingest(
            2,
            "YouTube",
            url,
            "results",
            youtube_search_results=[
                ("곡", "https://www.youtube.com/watch?v=evt111"),
            ],
        )

    threading.Thread(target=_delayed_ingest, daemon=True).start()
    t0 = time.monotonic()
    pairs = monitor.wait_for_youtube_search_results(
        url,
        timeout_sec=3.0,
        after_ingest_count=baseline,
    )
    elapsed = time.monotonic() - t0
    assert pairs is not None
    assert pairs[0][1].endswith("v=evt111")
    assert 0.05 <= elapsed < 1.5


def test_wait_timeout_without_ingest() -> None:
    monitor = BrowserTabMonitor()
    t0 = time.monotonic()
    pairs = monitor.wait_for_youtube_search_results(
        "https://www.youtube.com/results?search_query=missing",
        timeout_sec=0.2,
        after_ingest_count=monitor.total_ingest_count(),
    )
    elapsed = time.monotonic() - t0
    assert pairs is None
    assert elapsed >= 0.15
    assert elapsed < 0.6
