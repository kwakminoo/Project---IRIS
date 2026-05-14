"""레거시 보조 유틸."""

from __future__ import annotations

import psutil


def is_process_running(name_substring: str) -> bool:
    """프로세스 이름 부분 문자열 매칭."""
    sub = name_substring.lower()
    for p in psutil.process_iter(attrs=["name"]):
        try:
            n = (p.info.get("name") or "").lower()
            if sub in n:
                return True
        except (psutil.Error, TypeError):
            continue
    return False
