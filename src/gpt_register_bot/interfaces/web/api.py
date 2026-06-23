from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from gpt_register_bot.application.job_manager import (
    JobAlreadyRunningError,
    JobManager,
    JobNotRunningError,
)
from gpt_register_bot.interfaces.web.dependencies import get_job_manager
from gpt_register_bot.interfaces.web.schemas import (
    ActionResponse,
    JobStateResponse,
    StartJobRequest,
)


def build_api_router(manager: JobManager | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["control"])

    def _manager(injected: JobManager = Depends(get_job_manager)) -> JobManager:
        return manager or injected

    @router.get("/state", response_model=JobStateResponse)
    def get_state(job_manager: JobManager = Depends(_manager)) -> JobStateResponse:
        return job_manager.snapshot()

    @router.post("/start", response_model=ActionResponse)
    def start_task(
        payload: StartJobRequest,
        job_manager: JobManager = Depends(_manager),
    ) -> ActionResponse:
        try:
            job_manager.start(payload)
        except JobAlreadyRunningError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ActionResponse(ok=True)

    @router.post("/stop", response_model=ActionResponse)
    def stop_task(job_manager: JobManager = Depends(_manager)) -> ActionResponse:
        try:
            job_manager.stop()
        except JobNotRunningError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ActionResponse(ok=True)

    @router.post("/logs/clear", response_model=ActionResponse)
    def clear_logs(job_manager: JobManager = Depends(_manager)) -> ActionResponse:
        job_manager.clear_logs()
        return ActionResponse(ok=True)

    return router
