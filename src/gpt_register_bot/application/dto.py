from __future__ import annotations

from pydantic import BaseModel, Field

from gpt_register_bot.config.settings import get_settings


class StartJobRequest(BaseModel):
    """Input contract for starting a registration job."""

    total_runs: int = Field(default=1, ge=1, description="总执行次数")
    concurrency: int = Field(
        default_factory=lambda: get_settings().default_concurrency,
        ge=1,
        le=32,
        description="并发线程数",
    )
    provider_key: str = Field(
        default_factory=lambda: get_settings().default_provider,
        description="临时邮箱提供商",
    )
    proxy: str | None = Field(default=None, description="HTTP 代理地址")
    cpa_url: str | None = Field(default=None, description="CPA 上传地址")
    cpa_token: str | None = Field(default=None, description="CPA Token")


class JobStateResponse(BaseModel):
    """Snapshot of the current job runtime."""

    running: bool
    pid: int | None
    uptime_seconds: int
    command: str
    config: dict
    logs: list[str]
