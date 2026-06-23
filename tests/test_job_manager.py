from __future__ import annotations

from pathlib import Path

import pytest

from gpt_register_bot.application.dto import StartJobRequest
from gpt_register_bot.application.job_manager import (
    JobAlreadyRunningError,
    JobManager,
    JobNotRunningError,
)
from gpt_register_bot.config.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, output_dir=tmp_path / "output")


def _manager(tmp_path: Path) -> JobManager:
    # The service factory is only invoked when a real worker starts; these
    # lifecycle tests never reach that path, so a stub factory is enough.
    return JobManager(_settings(tmp_path), service_factory=lambda: object())


def test_job_manager_idle_snapshot(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    state = manager.snapshot()

    assert state.running is False
    assert state.pid is None
    assert state.uptime_seconds == 0


def test_job_manager_rejects_duplicate_start(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager._state.running = True

    with pytest.raises(JobAlreadyRunningError):
        manager.start(StartJobRequest(total_runs=1))


def test_job_manager_stop_without_running(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    with pytest.raises(JobNotRunningError):
        manager.stop()


def test_job_manager_clear_logs(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager._logs.append("old line")
    manager.clear_logs()

    logs = manager.snapshot().logs
    assert any("logs cleared" in line for line in logs)
