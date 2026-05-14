"""Windows Event Log 보조 수집 (앱 크래시·오류)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class EventLogSnippet:
    """요약 한 줄."""

    source: str
    message: str
    time_generated: str


def collect_recent_errors(max_events: int = 8) -> List[EventLogSnippet]:
    out: List[EventLogSnippet] = []
    try:
        import win32evtlog  # type: ignore
        import win32evtlogutil  # type: ignore
        import win32con  # type: ignore

        hand = win32evtlog.OpenEventLog(None, "Application")
        if not hand:
            return out
        try:
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            for ev in events or []:
                if len(out) >= max_events:
                    break
                et = int(ev.EventType)
                if et not in (win32con.EVENTLOG_ERROR_TYPE, win32con.EVENTLOG_WARNING_TYPE):
                    continue
                try:
                    msg = win32evtlogutil.SafeFormatMessage(ev, "Application")
                except Exception:
                    msg = str(ev.StringInserts or "")
                src = ev.SourceName or "Application"
                when = ev.TimeGenerated.Format("%Y-%m-%d %H:%M:%S") if ev.TimeGenerated else ""
                line = (msg or "").replace("\r", " ").replace("\n", " ")[:400]
                out.append(EventLogSnippet(source=src, message=line, time_generated=when))
        finally:
            win32evtlog.CloseEventLog(hand)
    except Exception:
        pass
    return out


def format_for_detector(snippets: List[EventLogSnippet]) -> str:
    return "\n".join(f"[{s.source}] {s.message}" for s in snippets)
