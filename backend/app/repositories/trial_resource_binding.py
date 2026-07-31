"""Transaction-bound persistence and authorization for public Trial resources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.enums import ActualHarvestImportBatchStatus
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.models.trial import TrialResourceBindingModel

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TrialResourceKind(StrEnum):
    FORECAST = "FORECAST"
    QUALITY_REPORT = "QUALITY_REPORT"


class TrialResourceBindingError(RuntimeError):
    """Base class for safe Trial resource binding errors."""


class TrialResourceBindingConflictError(TrialResourceBindingError):
    def __init__(self) -> None:
        super().__init__("trial resource binding conflicts with an existing resource")


class TrialResourceNotFoundError(TrialResourceBindingError):
    def __init__(self) -> None:
        super().__init__("trial resource was not found")


class TrialResourceBindingInputError(TrialResourceBindingError):
    def __init__(self) -> None:
        super().__init__("trial resource binding input is invalid")


@dataclass(frozen=True)
class AuthorizedTrialResource:
    resource_kind: TrialResourceKind
    public_resource_id: str
    owner_identity: str
    business_scope_hash: str
    parent_forecast_public_id_or_null: str | None
    parent_import_id_or_null: str | None
    created_at: datetime


def _kind(value: TrialResourceKind | str) -> TrialResourceKind:
    try:
        return value if isinstance(value, TrialResourceKind) else TrialResourceKind(value)
    except ValueError as exc:
        raise TrialResourceBindingInputError() from exc


def _identity(value: str, *, hash_value: bool = False) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TrialResourceBindingInputError()
    if hash_value and _SHA256_RE.fullmatch(value) is None:
        raise TrialResourceBindingInputError()
    return value


def _project(row: TrialResourceBindingModel) -> AuthorizedTrialResource:
    created_at = row.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        created_at = created_at.replace(tzinfo=UTC)
    return AuthorizedTrialResource(
        resource_kind=TrialResourceKind(row.resource_kind),
        public_resource_id=row.public_resource_id,
        owner_identity=row.owner_identity,
        business_scope_hash=row.business_scope_hash,
        parent_forecast_public_id_or_null=row.parent_forecast_public_id,
        parent_import_id_or_null=row.parent_import_id,
        created_at=created_at,
    )


async def _existing_or_conflict(
    session: AsyncSession,
    *,
    resource_kind: TrialResourceKind,
    public_resource_id: str,
    owner_identity: str,
    business_scope_hash: str,
    parent_forecast_public_id: str | None,
    parent_import_id: str | None,
) -> AuthorizedTrialResource | None:
    existing = await session.scalar(
        select(TrialResourceBindingModel).where(
            TrialResourceBindingModel.resource_kind == resource_kind.value,
            TrialResourceBindingModel.public_resource_id == public_resource_id,
        )
    )
    if existing is None:
        return None
    if (
        existing.owner_identity != owner_identity
        or existing.business_scope_hash != business_scope_hash
        or existing.parent_forecast_public_id != parent_forecast_public_id
        or existing.parent_import_id != parent_import_id
    ):
        raise TrialResourceBindingConflictError()
    return _project(existing)


async def _insert_binding(
    session: AsyncSession,
    *,
    resource_kind: TrialResourceKind,
    public_resource_id: str,
    owner_identity: str,
    business_scope_hash: str,
    parent_forecast_public_id: str | None,
    parent_import_id: str | None,
) -> AuthorizedTrialResource:
    replay = await _existing_or_conflict(
        session,
        resource_kind=resource_kind,
        public_resource_id=public_resource_id,
        owner_identity=owner_identity,
        business_scope_hash=business_scope_hash,
        parent_forecast_public_id=parent_forecast_public_id,
        parent_import_id=parent_import_id,
    )
    if replay is not None:
        return replay
    row = TrialResourceBindingModel(
        resource_kind=resource_kind.value,
        public_resource_id=public_resource_id,
        owner_identity=owner_identity,
        business_scope_hash=business_scope_hash,
        parent_forecast_public_id=parent_forecast_public_id,
        parent_import_id=parent_import_id,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return _project(row)


async def create_forecast_binding_in_result_boundary(
    session: AsyncSession,
    *,
    public_forecast_id: str,
    owner_identity: str,
    business_scope_hash: str,
) -> AuthorizedTrialResource:
    """Insert or replay a Forecast binding without taking transaction ownership."""

    return await _insert_binding(
        session,
        resource_kind=TrialResourceKind.FORECAST,
        public_resource_id=_identity(public_forecast_id, hash_value=True),
        owner_identity=_identity(owner_identity),
        business_scope_hash=_identity(business_scope_hash, hash_value=True),
        parent_forecast_public_id=None,
        parent_import_id=None,
    )


async def create_quality_binding_in_result_boundary(
    session: AsyncSession,
    *,
    public_quality_report_id: str,
    owner_identity: str,
    business_scope_hash: str,
    parent_forecast_public_id: str,
    parent_import_id: str,
) -> AuthorizedTrialResource:
    """Insert or replay a Quality binding after proving both parents are scoped."""

    owner = _identity(owner_identity)
    forecast_id = _identity(parent_forecast_public_id, hash_value=True)
    import_id = _identity(parent_import_id)
    await _require_quality_parents(
        session,
        owner_identity=owner,
        parent_forecast_public_id=forecast_id,
        parent_import_id=import_id,
    )
    return await _insert_binding(
        session,
        resource_kind=TrialResourceKind.QUALITY_REPORT,
        public_resource_id=_identity(public_quality_report_id, hash_value=True),
        owner_identity=owner,
        business_scope_hash=_identity(business_scope_hash, hash_value=True),
        parent_forecast_public_id=forecast_id,
        parent_import_id=import_id,
    )


async def _require_quality_parents(
    session: AsyncSession,
    *,
    owner_identity: str,
    parent_forecast_public_id: str,
    parent_import_id: str,
) -> None:
    forecast = await session.scalar(
        select(TrialResourceBindingModel).where(
            TrialResourceBindingModel.resource_kind == TrialResourceKind.FORECAST.value,
            TrialResourceBindingModel.public_resource_id == parent_forecast_public_id,
            TrialResourceBindingModel.owner_identity == owner_identity,
        )
    )
    batch = await session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == parent_import_id,
            ActualHarvestImportBatchModel.submitted_by_identity == owner_identity,
            ActualHarvestImportBatchModel.status == ActualHarvestImportBatchStatus.COMMITTED.value,
        )
    )
    if forecast is None or batch is None:
        raise TrialResourceNotFoundError()


async def authorize_trial_resource(
    session: AsyncSession,
    *,
    resource_kind: TrialResourceKind | str,
    public_resource_id: str,
    owner_identity: str,
) -> AuthorizedTrialResource:
    """Authorize using one scoped query; mismatches remain indistinguishable."""

    try:
        kind = _kind(resource_kind)
        public_id = _identity(public_resource_id, hash_value=True)
        owner = _identity(owner_identity)
    except TrialResourceBindingInputError as exc:
        raise TrialResourceNotFoundError() from exc
    row = await session.scalar(
        select(TrialResourceBindingModel).where(
            TrialResourceBindingModel.resource_kind == kind.value,
            TrialResourceBindingModel.public_resource_id == public_id,
            TrialResourceBindingModel.owner_identity == owner,
        )
    )
    if row is None:
        raise TrialResourceNotFoundError()
    return _project(row)
