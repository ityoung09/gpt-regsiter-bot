from __future__ import annotations

from pydantic import BaseModel

# Job request/state DTOs live in the application layer; re-export them so web
# handlers have a single import surface for request/response models.
from gpt_register_bot.application.dto import JobStateResponse, StartJobRequest

__all__ = ["ActionResponse", "JobStateResponse", "StartJobRequest"]


class ActionResponse(BaseModel):
    ok: bool = True
