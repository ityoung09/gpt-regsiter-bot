from __future__ import annotations

import threading
import time
from collections import deque


class LogBuffer:
    """Thread-safe in-memory log storage with timestamping."""

    def __init__(self, max_lines: int) -> None:
        self._lock = threading.RLock()
        self._lines: deque[str] = deque(maxlen=max_lines)

    def append(self, message: str) -> None:
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with self._lock:
            self._lines.append(f"{now} {message}")

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    def tail(self, count: int) -> list[str]:
        with self._lock:
            if count <= 0:
                return []
            return list(self._lines)[-count:]
