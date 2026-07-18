from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel


class ActualHarvestActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: str = Field(min_length=1, max_length=256, strict=True)
    allowed_source_systems: frozenset[str]
    allowed_channels: frozenset[ActualHarvestImportChannel]
    may_create: bool = False
    may_append: bool = False
    may_preview: bool = False
    may_seal: bool = False
    may_cancel: bool = False


async def get_actual_harvest_actor() -> ActualHarvestActorContext:
    raise ActualHarvestApiError(
        ActualHarvestApiErrorCode.ACTUAL_HARVEST_AUTHORIZATION_UNAVAILABLE,
        "actual-harvest authorization is unavailable",
        status_code=503,
    )


ActorDep = Annotated[ActualHarvestActorContext, Depends(get_actual_harvest_actor)]


def require_actor_scope(
    actor: ActualHarvestActorContext,
    *,
    source_system: str,
    channel: ActualHarvestImportChannel,
    permission: str,
    submitted_by_identity: str | None = None,
) -> None:
    if submitted_by_identity is not None and actor.identity != submitted_by_identity:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.ACTUAL_HARVEST_ACTOR_MISMATCH,
            "actor identity does not match submitted identity",
            status_code=403,
        )
    if source_system not in actor.allowed_source_systems or channel not in actor.allowed_channels:
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.ACTUAL_HARVEST_SCOPE_FORBIDDEN,
            "actor is outside the requested source scope",
            status_code=403,
        )
    if not getattr(actor, permission):
        raise ActualHarvestApiError(
            ActualHarvestApiErrorCode.ACTUAL_HARVEST_SCOPE_FORBIDDEN,
            "actor is not authorized for this operation",
            status_code=403,
        )


__all__ = [
    "ActorDep",
    "ActualHarvestActorContext",
    "get_actual_harvest_actor",
    "require_actor_scope",
]
