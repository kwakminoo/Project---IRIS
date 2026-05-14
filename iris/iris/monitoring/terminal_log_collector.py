"""Iris가 실행한 터미널 명령의 stdout/stderr 수집."""

from __future__ import annotations

import io
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def _pump_stream(stream: io.BufferedReader, out_q: "queue.Queue[Tuple[str, bytes]]", tag: str) -> None:
    try:
        for chunk in iter(lambda: stream.read(4096), b""):
            if not chunk:
                break
            out_q.put((tag, chunk))
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


@dataclass
class MonitoredCommandHandle:
    """논블로킹 로그 읽기 핸들."""

    proc: subprocess.Popen
    _q: "queue.Queue[Tuple[str, bytes]]" = field(default_factory=queue.Queue)
    _buf: bytearray = field(default_factory=bytearray)
    _threads: List[threading.Thread] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.proc.stdout:
            t = threading.Thread(
                target=_pump_stream,
                args=(self.proc.stdout, self._q, "out"),
                daemon=True,
            )
            t.start()
            self._threads.append(t)
        if self.proc.stderr:
            t = threading.Thread(
                target=_pump_stream,
                args=(self.proc.stderr, self._q, "err"),
                daemon=True,
            )
            t.start()
            self._threads.append(t)

    def poll_snippet(self, max_chars: int = 8000) -> str:
        """버퍼에서 가져와 UTF-8 디코드 (스니펫만)."""
        try:
            while True:
                _tag, chunk = self._q.get_nowait()
                self._buf.extend(chunk)
        except queue.Empty:
            pass
        raw = bytes(self._buf)[-max_chars:]
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def done(self) -> bool:
        return self.proc.poll() is not None


def start_monitored_command(
    args: List[str],
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    shell: bool = False,
) -> MonitoredCommandHandle:
    """stdout/stderr 파이프로 프로세스 시작."""
    proc = subprocess.Popen(  # noqa: S603
        args,
        cwd=cwd,
        env=env,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    return MonitoredCommandHandle(proc=proc)


class TerminalLogRegistry:
    """여러 모니터링 중인 터미널 핸들 보관."""

    def __init__(self) -> None:
        self._handles: dict[int, MonitoredCommandHandle] = {}

    def register(self, target_id: int, handle: MonitoredCommandHandle) -> None:
        self._handles[target_id] = handle

    def unregister(self, target_id: int) -> None:
        self._handles.pop(target_id, None)

    def snippet_for(self, target_id: int) -> str:
        h = self._handles.get(target_id)
        if not h:
            return ""
        return h.poll_snippet()
