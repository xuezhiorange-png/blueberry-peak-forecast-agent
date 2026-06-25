from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.harvest_state.schemas import Task9ABlockedOutput, Task9ACompletedOutput


class HarvestStateRunEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    status: Literal["completed", "blocked"]
    result_hash: str
    config_hash: str
    created_at: datetime
    output: Task9ACompletedOutput | Task9ABlockedOutput


class HarvestStateErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class HarvestStateErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: HarvestStateErrorDetail
