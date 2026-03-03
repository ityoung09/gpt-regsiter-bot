from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gpt_register_bot.web.schemas import ActionResponse, ProcessStateResponse, StartJobRequest
from gpt_register_bot.web.services.process_manager import (
    ProcessAlreadyRunningError,
    ProcessManager,
    ProcessNotRunningError,
)


def build_api_router(manager: ProcessManager) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["control"])

    @router.get("/state", response_model=ProcessStateResponse)
    def get_state() -> ProcessStateResponse:
        return manager.snapshot()

    @router.post("/start", response_model=ActionResponse)
    def start_task(payload: StartJobRequest) -> ActionResponse:
        try:
            manager.start(payload)
        except ProcessAlreadyRunningError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ActionResponse(ok=True)

    @router.post("/stop", response_model=ActionResponse)
    def stop_task() -> ActionResponse:
        try:
            manager.stop()
        except ProcessNotRunningError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ActionResponse(ok=True)

    @router.post("/logs/clear", response_model=ActionResponse)
    def clear_logs() -> ActionResponse:
        manager.clear_logs()
        return ActionResponse(ok=True)

    return router
