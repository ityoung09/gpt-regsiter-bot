from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunPlan:
    total_runs: int
    concurrency: int
    provider_key: str = "mailtm"
    proxy: str | None = None
    cpa_url: str | None = None
    cpa_token: str | None = None


@dataclass(frozen=True)
class RunSummary:
    succeeded: int
    failed: int
    skipped: int


class RunExecutor:
    """Concurrent executor for account generation runs."""

    def __init__(self, run_once: Callable[..., bool]) -> None:
        self._run_once = run_once

    def execute(self, plan: RunPlan, stop_event: Event) -> RunSummary:
        workers = max(1, min(plan.total_runs, plan.concurrency))
        logger.info("[task] thread pool workers: %s", workers)

        succeeded = 0
        failed = 0
        skipped = 0

        futures: dict[Future[bool], int] = {}
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="register-runner"
        ) as pool:
            for run_no in range(1, plan.total_runs + 1):
                future = pool.submit(
                    self._run_once,
                    thread_id=run_no,
                    run_no=run_no,
                    total_runs=plan.total_runs,
                    proxy=plan.proxy,
                    provider_key=plan.provider_key,
                    cpa_url=plan.cpa_url,
                    cpa_token=plan.cpa_token,
                    stop_event=stop_event,
                )
                futures[future] = run_no

            for future in as_completed(futures):
                run_no = futures[future]

                if future.cancelled():
                    skipped += 1
                    logger.info("[task] run %s/%s cancelled", run_no, plan.total_runs)
                    continue

                try:
                    ok = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    failed += 1
                    logger.error(
                        "run %s/%s future crashed: %s", run_no, plan.total_runs, exc
                    )
                    continue

                if ok:
                    succeeded += 1
                elif stop_event.is_set():
                    skipped += 1
                else:
                    failed += 1

        return RunSummary(succeeded=succeeded, failed=failed, skipped=skipped)
