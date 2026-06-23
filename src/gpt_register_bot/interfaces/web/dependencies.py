from __future__ import annotations

from gpt_register_bot.application.job_manager import JobManager
from gpt_register_bot.container import get_container


def get_job_manager() -> JobManager:
    return get_container().job_manager()
