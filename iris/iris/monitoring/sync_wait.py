"""조건·타임아웃 대기 — 고정 sleep 없이 성공 시 즉시 반환."""

from __future__ import annotations

import time
from collections.abc import Callable


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_sec: float,
    max_slice_sec: float = 0.05,
) -> bool:
    """
    predicate()가 True가 되면 즉시 True.
    타임아웃까지 짧은 슬라이스만 대기(이벤트 핸들러에서 notify와 함께 쓸 것).
    """
    if timeout_sec <= 0:
        return bool(predicate())
    deadline = time.monotonic() + timeout_sec
    while True:
        if predicate():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(max_slice_sec, remaining))
    return bool(predicate())
