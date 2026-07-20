from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_policy import API_POLICY
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
    may_validate: bool = False
    may_commit: bool = False  # v0.2-S1


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
    hide_identity_mismatch: bool = False,
) -> None:
    if submitted_by_identity is not None and actor.identity != submitted_by_identity:
        if hide_identity_mismatch:
            raise ActualHarvestApiError(
                ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND,
                "actual-harvest import batch was not found",
                status_code=404,
            )
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


AUTHORIZATION_POLICY = API_POLICY.authorization_policy
BATCH_OWNER_AUTHORIZATION = API_POLICY.batch_owner_authorization
SOURCE_DOMAIN_SHARED_ADMIN = API_POLICY.source_domain_shared_admin


__all__ = [
    "ActorDep",
    "AUTHORIZATION_POLICY",
    "ActualHarvestActorContext",
    "BATCH_OWNER_AUTHORIZATION",
    "SOURCE_DOMAIN_SHARED_ADMIN",
    "get_actual_harvest_actor",
    "require_actor_scope",
]
