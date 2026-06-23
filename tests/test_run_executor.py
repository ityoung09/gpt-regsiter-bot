from __future__ import annotations

from threading import Event

from gpt_register_bot.application.run_executor import RunExecutor, RunPlan


def test_run_executor_counts_success_and_failure() -> None:
    def run_once(**kwargs: object) -> bool:
        run_no = kwargs["run_no"]
        return run_no % 2 == 1

    executor = RunExecutor(run_once=run_once)
    summary = executor.execute(RunPlan(total_runs=4, concurrency=2), stop_event=Event())

    assert summary.succeeded == 2
    assert summary.failed == 2
    assert summary.skipped == 0


def test_run_executor_honors_stop_event() -> None:
    stop_event = Event()

    def run_once(**kwargs: object) -> bool:
        stop_event.set()
        return False

    executor = RunExecutor(run_once=run_once)
    summary = executor.execute(RunPlan(total_runs=3, concurrency=2), stop_event=stop_event)

    assert summary.skipped >= 1
