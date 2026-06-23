from __future__ import annotations

import pytest

from gpt_register_bot.application.logging_buffer import LogBuffer


def test_log_buffer_append_and_tail() -> None:
    buffer = LogBuffer(max_lines=10)
    buffer.append("first")
    buffer.append("second")

    tail = buffer.tail(1)
    assert len(tail) == 1
    assert tail[0].endswith("second")


def test_log_buffer_clear() -> None:
    buffer = LogBuffer(max_lines=10)
    buffer.append("line")
    buffer.clear()
    assert buffer.tail(10) == []
