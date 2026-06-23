from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from gpt_register_bot.application.dto import JobStateResponse, StartJobRequest
from gpt_register_bot.application.registration_service import RegistrationService
from gpt_register_bot.application.run_executor import RunExecutor, RunPlan
from gpt_register_bot.application.logging_buffer import LogBuffer, LogBufferHandler
from gpt_register_bot.config.settings import Settings

CORE_LOGGER_NAME = "gpt_register_bot"


class JobError(RuntimeError):
    """Base runtime error for job control service."""


class JobAlreadyRunningError(JobError):
    """Raised when start is requested while a job is already running."""


class JobNotRunningError(JobError):
    """Raised when stop is requested while no job is running."""


@dataclass
class JobRuntimeState:
    running: bool = False
    worker_thread: threading.Thread | None = None
    stop_event: threading.Event | None = None
    started_at: float | None = None
    config: dict | None = None
    command: str = ""


class JobManager:
    """Manages background registration job lifecycle for the Web console."""

    def __init__(
        self,
        settings: Settings,
        service_factory: Callable[[], RegistrationService],
    ) -> None:
        self._settings = settings
        self._service_factory = service_factory
        self._lock = threading.RLock()
        self._logs = LogBuffer(settings.max_log_lines)
        self._state = JobRuntimeState()

    def _is_running_unlocked(self) -> bool:
        return self._state.running

    def _reset_unlocked(self) -> None:
        self._state = JobRuntimeState()

    def _worker(self, payload: StartJobRequest, stop_event: threading.Event) -> None:
        self._logs.append("[system] job worker started")

        service = self._service_factory()
        executor = RunExecutor(run_once=service.generate_account)
        plan = RunPlan(
            total_runs=payload.total_runs,
            concurrency=payload.concurrency,
            proxy=payload.proxy,
            provider_key=payload.provider_key,
            cpa_url=payload.cpa_url,
            cpa_token=payload.cpa_token,
        )

        self._logs.append(
            f"[task] total runs: {plan.total_runs}, concurrency: {plan.concurrency}, "
            f"provider: {plan.provider_key}"
        )

        core_logger = logging.getLogger(CORE_LOGGER_NAME)
        handler = LogBufferHandler(self._logs)
        core_logger.addHandler(handler)
        previous_level = core_logger.level
        if previous_level == logging.NOTSET or previous_level > logging.INFO:
            core_logger.setLevel(logging.INFO)

        try:
            summary = executor.execute(plan=plan, stop_event=stop_event)
            self._logs.append(
                "[task] completed summary: "
                f"success={summary.succeeded}, failed={summary.failed}, "
                f"skipped={summary.skipped}"
            )
            if stop_event.is_set():
                self._logs.append("[task] stop signal processed")
        finally:
            core_logger.removeHandler(handler)
            core_logger.setLevel(previous_level)
            handler.close()
            with self._lock:
                self._reset_unlocked()
            self._logs.append("[system] worker exited")

    def start(self, payload: StartJobRequest) -> None:
        with self._lock:
            if self._is_running_unlocked():
                raise JobAlreadyRunningError("task is already running")

            safe_config = payload.model_dump()
            if safe_config.get("cpa_token"):
                safe_config["cpa_token"] = "******"

            self._logs.clear()
            self._logs.append("[system] web mode enabled")

            stop_event = threading.Event()
            worker = threading.Thread(
                target=self._worker,
                args=(payload, stop_event),
                daemon=True,
                name="register-job-worker",
            )

            self._state.running = True
            self._state.worker_thread = worker
            self._state.stop_event = stop_event
            self._state.started_at = time.time()
            self._state.config = safe_config
            self._state.command = (
                "gpt-register run "
                f"--total-runs {payload.total_runs} "
                f"--concurrency {payload.concurrency} "
                f"--provider {payload.provider_key}"
            )

            worker.start()

    def stop(self) -> None:
        with self._lock:
            if not self._is_running_unlocked() or self._state.stop_event is None:
                raise JobNotRunningError("no running task")

            stop_event = self._state.stop_event
            worker = self._state.worker_thread
            self._logs.append("[system] stopping worker...")

        stop_event.set()
        if worker is not None:
            worker.join(timeout=5)
            if worker.is_alive():
                self._logs.append(
                    "[system] stop signal sent, waiting current HTTP steps to return..."
                )

    def clear_logs(self) -> None:
        self._logs.clear()
        self._logs.append("[system] logs cleared")

    def snapshot(self) -> JobStateResponse:
        with self._lock:
            running = self._state.running
            pid = os.getpid() if running else None
            uptime = (
                int(time.time() - self._state.started_at)
                if running and self._state.started_at is not None
                else 0
            )
            command = self._state.command
            config = self._state.config or {}

        return JobStateResponse(
            running=running,
            pid=pid,
            uptime_seconds=uptime,
            command=command,
            config=config,
            logs=self._logs.tail(self._settings.max_log_tail),
        )
