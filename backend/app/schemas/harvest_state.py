from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

from backend.app.harvest_state.schemas import Task9ABlockedOutput, Task9ACompletedOutput


class HarvestStateRunEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    status: Literal["completed", "blocked"]
    result_hash: str
    config_hash: str
    created_at: datetime
    output: Task9ACompletedOutput | Task9ABlockedOutput

    @model_serializer(mode="wrap")
    def _serialize_legacy_output(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        payload = cast(dict[str, Any], handler(self))
        if self.output.output_schema_version == "task9a-output-v1":
            cast(dict[str, Any], payload["output"]).pop("forecast_season_id", None)
        return payload


class HarvestStateErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class HarvestStateErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: HarvestStateErrorDetail
