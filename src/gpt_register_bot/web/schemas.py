from __future__ import annotations

from pydantic import BaseModel, Field


class StartJobRequest(BaseModel):
    total_runs: int = Field(default=1, ge=1, description="总执行次数")
    concurrency: int = Field(default=3, ge=1, le=32, description="并发线程数")
    cpa_url: str | None = Field(default=None, description="CPA 上传地址")
    cpa_token: str | None = Field(default=None, description="CPA Token")


class ActionResponse(BaseModel):
    ok: bool = True


class ProcessStateResponse(BaseModel):
    running: bool
    pid: int | None
    uptime_seconds: int
    command: str
    config: dict
    logs: list[str]
