from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from gpt_register_bot.web.config import MAX_LOG_LINES, MAX_LOG_TAIL, SOURCE_SCRIPT_PATH
from gpt_register_bot.web.schemas import ProcessStateResponse, StartJobRequest
from gpt_register_bot.web.services.log_buffer import LogBuffer
from gpt_register_bot.web.services.run_executor import RunExecutor, RunPlan
from gpt_register_bot.web.services.source_runtime import SourceRuntimeError, SourceRuntimeService


class ProcessError(RuntimeError):
    """Base runtime error for web control service."""


class ProcessAlreadyRunningError(ProcessError):
    """Raised when start is requested while task is already running."""


class ProcessNotRunningError(ProcessError):
    """Raised when stop is requested while no task is running."""


@dataclass
class RuntimeState:
    running: bool = False
    worker_thread: threading.Thread | None = None
    stop_event: threading.Event | None = None
    started_at: float | None = None
    config: dict | None = None
    command: str = "service.runtime --total-runs 1 --concurrency 1"


class ProcessManager:
    """
    Runtime manager for web mode.

    Responsibilities:
    - start/stop lifecycle of background execution task
    - orchestrate concurrent run execution
    - expose read-only runtime snapshot for API layer
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._logs = LogBuffer(MAX_LOG_LINES)
        self._state = RuntimeState()

    def _is_running_unlocked(self) -> bool:
        return self._state.running

    def _reset_unlocked(self) -> None:
        self._state.running = False
        self._state.worker_thread = None
        self._state.stop_event = None
        self._state.started_at = None
        self._state.config = None
        self._state.command = "service.runtime --total-runs 1 --concurrency 1"

    def _worker(self, payload: StartJobRequest, stop_event: threading.Event) -> None:
        self._logs.append("[system] runtime worker started")

        runtime = SourceRuntimeService(
            source_path=SOURCE_SCRIPT_PATH,
            log=self._logs.append,
        )
        executor = RunExecutor(run_once=runtime.run_once, log=self._logs.append)
        plan = RunPlan(
            total_runs=payload.total_runs,
            concurrency=payload.concurrency,
            cpa_url=payload.cpa_url,
            cpa_token=payload.cpa_token,
        )

        self._logs.append(
            f"[task] total runs: {plan.total_runs}, concurrency: {plan.concurrency}"
        )

        try:
            summary = executor.execute(plan=plan, stop_event=stop_event)
            self._logs.append(
                "[task] completed summary: "
                f"success={summary.succeeded}, failed={summary.failed}, skipped={summary.skipped}"
            )
            if stop_event.is_set():
                self._logs.append("[task] stop signal processed")
        finally:
            with self._lock:
                self._reset_unlocked()
            self._logs.append("[system] worker exited")

    def start(self, payload: StartJobRequest) -> None:
        if not SOURCE_SCRIPT_PATH.exists():
            raise ValueError(f"source script not found: {SOURCE_SCRIPT_PATH}")

        # Preflight source runtime loading to fail fast at API layer.
        try:
            SourceRuntimeService(
                source_path=SOURCE_SCRIPT_PATH,
                log=lambda _: None,
            ).ensure_ready()
        except SourceRuntimeError as exc:
            raise ValueError(str(exc)) from exc

        with self._lock:
            if self._is_running_unlocked():
                raise ProcessAlreadyRunningError("task is already running")

            safe_config = payload.model_dump()
            if safe_config.get("cpa_token"):
                safe_config["cpa_token"] = "******"

            self._logs.clear()
            self._logs.append("[system] web mode enabled")
            self._logs.append("[system] source runtime loaded (in-process)")

            stop_event = threading.Event()
            worker = threading.Thread(
                target=self._worker,
                args=(payload, stop_event),
                daemon=True,
                name="source-runtime-worker",
            )

            self._state.running = True
            self._state.worker_thread = worker
            self._state.stop_event = stop_event
            self._state.started_at = time.time()
            self._state.config = safe_config
            self._state.command = (
                "service.runtime "
                f"--total-runs {payload.total_runs} --concurrency {payload.concurrency}"
            )

            worker.start()

    def stop(self) -> None:
        with self._lock:
            if not self._is_running_unlocked() or self._state.stop_event is None:
                raise ProcessNotRunningError("no running task")

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

    def snapshot(self) -> ProcessStateResponse:
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

        return ProcessStateResponse(
            running=running,
            pid=pid,
            uptime_seconds=uptime,
            command=command,
            config=config,
            logs=self._logs.tail(MAX_LOG_TAIL),
        )
