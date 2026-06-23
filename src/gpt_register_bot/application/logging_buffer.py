from __future__ import annotations

import logging
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


class LogBufferHandler(logging.Handler):
    """Forward ``logging`` records into a :class:`LogBuffer`.

    The buffer owns the timestamp, so this handler emits only the level and
    message, keeping a single visual style across logging lines and the
    application's own ``LogBuffer.append`` calls.
    """

    def __init__(self, buffer: LogBuffer, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.levelno >= logging.WARNING:
                message = f"[{record.levelname.lower()}] {message}"
            self._buffer.append(message)
            if record.exc_info:
                traceback_text = logging.Formatter().formatException(record.exc_info)
                for line in traceback_text.splitlines():
                    self._buffer.append(line)
        except Exception:  # pragma: no cover - never let logging crash the job
            self.handleError(record)
