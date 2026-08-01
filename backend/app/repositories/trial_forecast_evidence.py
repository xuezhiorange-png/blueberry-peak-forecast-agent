"""Immutable Trial Forecast evidence persistence and scoped readback."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.core_forecast import CoreForecastRunModel
from backend.app.models.trial import (
    TRIAL_FORECAST_EVIDENCE_SCHEMA_VERSION,
    TrialForecastEvidenceModel,
    TrialResourceBindingModel,
)
from backend.app.repositories.trial_resource_binding import (
    TrialResourceBindingConflictError,
    TrialResourceKind,
    TrialResourceNotFoundError,
    authorize_trial_resource,
    create_forecast_binding_in_result_boundary,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

TRIAL_BUSINESS_SCOPE_SCHEMA_VERSION = "v0.2-trial-business-scope-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AREA_QUANTUM = Decimal("0.000001")


class TrialForecastEvidenceError(RuntimeError):
    """Base class for typed Trial Forecast evidence failures."""


class TrialForecastEvidenceInputError(TrialForecastEvidenceError):
    """The caller supplied a non-canonical or incomplete evidence value."""


class TrialForecastEvidenceNotFoundError(TrialForecastEvidenceError):
    """The requested Core Forecast or evidence row does not exist."""


class TrialForecastEvidenceConflictError(TrialForecastEvidenceError):
    """A replay or binding conflicts with an existing immutable identity."""


class TrialForecastEvidenceIntegrityError(TrialForecastEvidenceError):
    """Persisted evidence, its payload, or its binding is inconsistent."""


@dataclass(frozen=True)
class TrialForecastEvidence:
    evidence_schema_version: str
    public_forecast_id: str
    forecast_input_authority_hash: str
    authority_available_at: datetime
    farm_business_key: str
    subfarm_business_key_or_null: str | None
    season_business_key: str
    variety_business_key: str
    destination_factory_business_key: str
    plan_version: str
    plan_row_hash: str
    planting_area_mu: Decimal
    business_scope_hash: str
    canonical_payload: Mapping[str, object]
    forecast_evidence_hash: str
    created_at: datetime


@dataclass(frozen=True)
class _NormalizedEvidence:
    public_forecast_id: str
    forecast_input_authority_hash: str
    authority_available_at: datetime
    farm_business_key: str
    subfarm_business_key_or_null: str | None
    season_business_key: str
    variety_business_key: str
    destination_factory_business_key: str
    plan_version: str
    plan_row_hash: str
    planting_area_mu: Decimal
    business_scope_hash: str
    canonical_payload: dict[str, object]
    forecast_evidence_hash: str


def _sha256(value: str, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TrialForecastEvidenceInputError(f"{field} must be a lowercase SHA-256 hash")
    return value


def _key(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TrialForecastEvidenceInputError(f"{field} must be a normalized non-empty key")
    return value


def _optional_key(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    return _key(value, field=field)


def _utc(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TrialForecastEvidenceInputError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _area(value: Decimal, *, field: str = "planting_area_mu") -> Decimal:
    if isinstance(value, float) or not isinstance(value, Decimal):
        raise TrialForecastEvidenceInputError(f"{field} must be Decimal")
    if not value.is_finite() or value < 0:
        raise TrialForecastEvidenceInputError(f"{field} must be finite and non-negative")
    try:
        quantized = value.quantize(_AREA_QUANTUM)
    except InvalidOperation as exc:
        raise TrialForecastEvidenceInputError(f"{field} is not canonical") from exc
    if value != quantized:
        raise TrialForecastEvidenceInputError(f"{field} must have at most six decimal places")
    return quantized


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _area_text(value: Decimal) -> str:
    return f"{_area(value):.6f}"


def canonical_trial_business_scope_payload(
    *,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
    season_business_key: str,
    variety_business_key: str,
    destination_factory_business_key: str,
) -> dict[str, object]:
    """Return the only payload permitted to define a Trial business scope."""

    return {
        "schema_version": TRIAL_BUSINESS_SCOPE_SCHEMA_VERSION,
        "farm_business_key": _key(farm_business_key, field="farm_business_key"),
        "subfarm_business_key_or_null": _optional_key(
            subfarm_business_key_or_null,
            field="subfarm_business_key_or_null",
        ),
        "season_business_key": _key(season_business_key, field="season_business_key"),
        "variety_business_key": _key(variety_business_key, field="variety_business_key"),
        "destination_factory_business_key": _key(
            destination_factory_business_key,
            field="destination_factory_business_key",
        ),
    }


def compute_trial_business_scope_hash(
    *,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
    season_business_key: str,
    variety_business_key: str,
    destination_factory_business_key: str,
) -> str:
    payload = canonical_trial_business_scope_payload(
        farm_business_key=farm_business_key,
        subfarm_business_key_or_null=subfarm_business_key_or_null,
        season_business_key=season_business_key,
        variety_business_key=variety_business_key,
        destination_factory_business_key=destination_factory_business_key,
    )
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def canonical_trial_forecast_evidence_payload(
    *,
    public_forecast_id: str,
    forecast_input_authority_hash: str,
    authority_available_at: datetime,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
    season_business_key: str,
    variety_business_key: str,
    destination_factory_business_key: str,
    plan_version: str,
    plan_row_hash: str,
    planting_area_mu: Decimal,
) -> dict[str, object]:
    """Build canonical evidence without accepting a caller-provided scope hash."""

    public_id = _sha256(public_forecast_id, field="public_forecast_id")
    authority_hash = _sha256(
        forecast_input_authority_hash,
        field="forecast_input_authority_hash",
    )
    available_at = _utc(authority_available_at, field="authority_available_at")
    farm = _key(farm_business_key, field="farm_business_key")
    subfarm = _optional_key(
        subfarm_business_key_or_null,
        field="subfarm_business_key_or_null",
    )
    season = _key(season_business_key, field="season_business_key")
    variety = _key(variety_business_key, field="variety_business_key")
    factory = _key(
        destination_factory_business_key,
        field="destination_factory_business_key",
    )
    version = _key(plan_version, field="plan_version")
    plan_hash = _sha256(plan_row_hash, field="plan_row_hash")
    area = _area(planting_area_mu)
    scope_hash = compute_trial_business_scope_hash(
        farm_business_key=farm,
        subfarm_business_key_or_null=subfarm,
        season_business_key=season,
        variety_business_key=variety,
        destination_factory_business_key=factory,
    )
    return {
        "schema_version": TRIAL_FORECAST_EVIDENCE_SCHEMA_VERSION,
        "public_forecast_id": public_id,
        "forecast_input_authority_hash": authority_hash,
        "authority_available_at": _timestamp(available_at),
        "farm_business_key": farm,
        "subfarm_business_key_or_null": subfarm,
        "season_business_key": season,
        "variety_business_key": variety,
        "destination_factory_business_key": factory,
        "plan_version": version,
        "plan_row_hash": plan_hash,
        "planting_area_mu": _area_text(area),
        "business_scope_hash": scope_hash,
    }


def compute_trial_forecast_evidence_hash(
    *,
    public_forecast_id: str,
    forecast_input_authority_hash: str,
    authority_available_at: datetime,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
    season_business_key: str,
    variety_business_key: str,
    destination_factory_business_key: str,
    plan_version: str,
    plan_row_hash: str,
    planting_area_mu: Decimal,
) -> str:
    payload = canonical_trial_forecast_evidence_payload(
        public_forecast_id=public_forecast_id,
        forecast_input_authority_hash=forecast_input_authority_hash,
        authority_available_at=authority_available_at,
        farm_business_key=farm_business_key,
        subfarm_business_key_or_null=subfarm_business_key_or_null,
        season_business_key=season_business_key,
        variety_business_key=variety_business_key,
        destination_factory_business_key=destination_factory_business_key,
        plan_version=plan_version,
        plan_row_hash=plan_row_hash,
        planting_area_mu=planting_area_mu,
    )
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def _normalize_evidence(
    *,
    public_forecast_id: str,
    forecast_input_authority_hash: str,
    authority_available_at: datetime,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
    season_business_key: str,
    variety_business_key: str,
    destination_factory_business_key: str,
    plan_version: str,
    plan_row_hash: str,
    planting_area_mu: Decimal,
) -> _NormalizedEvidence:
    payload = canonical_trial_forecast_evidence_payload(
        public_forecast_id=public_forecast_id,
        forecast_input_authority_hash=forecast_input_authority_hash,
        authority_available_at=authority_available_at,
        farm_business_key=farm_business_key,
        subfarm_business_key_or_null=subfarm_business_key_or_null,
        season_business_key=season_business_key,
        variety_business_key=variety_business_key,
        destination_factory_business_key=destination_factory_business_key,
        plan_version=plan_version,
        plan_row_hash=plan_row_hash,
        planting_area_mu=planting_area_mu,
    )
    return _NormalizedEvidence(
        public_forecast_id=cast(str, payload["public_forecast_id"]),
        forecast_input_authority_hash=cast(str, payload["forecast_input_authority_hash"]),
        authority_available_at=_utc(authority_available_at, field="authority_available_at"),
        farm_business_key=cast(str, payload["farm_business_key"]),
        subfarm_business_key_or_null=cast(
            str | None,
            payload["subfarm_business_key_or_null"],
        ),
        season_business_key=cast(str, payload["season_business_key"]),
        variety_business_key=cast(str, payload["variety_business_key"]),
        destination_factory_business_key=cast(
            str,
            payload["destination_factory_business_key"],
        ),
        plan_version=cast(str, payload["plan_version"]),
        plan_row_hash=cast(str, payload["plan_row_hash"]),
        planting_area_mu=_area(planting_area_mu),
        business_scope_hash=cast(str, payload["business_scope_hash"]),
        canonical_payload=payload,
        forecast_evidence_hash=hashlib.sha256(
            canonical_json_dumps(payload).encode("utf-8")
        ).hexdigest(),
    )


def _aware_created_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _project_and_verify(row: TrialForecastEvidenceModel) -> TrialForecastEvidence:
    try:
        normalized = _normalize_evidence(
            public_forecast_id=row.public_forecast_id,
            forecast_input_authority_hash=row.forecast_input_authority_hash,
            authority_available_at=row.authority_available_at,
            farm_business_key=row.farm_business_key,
            subfarm_business_key_or_null=row.subfarm_business_key_or_null,
            season_business_key=row.season_business_key,
            variety_business_key=row.variety_business_key,
            destination_factory_business_key=row.destination_factory_business_key,
            plan_version=row.plan_version,
            plan_row_hash=row.plan_row_hash,
            planting_area_mu=Decimal(row.planting_area_mu),
        )
    except (TypeError, ValueError, InvalidOperation, TrialForecastEvidenceError) as exc:
        raise TrialForecastEvidenceIntegrityError() from exc
    if row.evidence_schema_version != TRIAL_FORECAST_EVIDENCE_SCHEMA_VERSION:
        raise TrialForecastEvidenceIntegrityError()
    if dict(row.canonical_payload) != normalized.canonical_payload:
        raise TrialForecastEvidenceIntegrityError()
    if row.business_scope_hash != normalized.business_scope_hash:
        raise TrialForecastEvidenceIntegrityError()
    if row.forecast_evidence_hash != normalized.forecast_evidence_hash:
        raise TrialForecastEvidenceIntegrityError()
    created_at = _aware_created_at(row.created_at)
    return TrialForecastEvidence(
        evidence_schema_version=row.evidence_schema_version,
        public_forecast_id=normalized.public_forecast_id,
        forecast_input_authority_hash=normalized.forecast_input_authority_hash,
        authority_available_at=normalized.authority_available_at,
        farm_business_key=normalized.farm_business_key,
        subfarm_business_key_or_null=normalized.subfarm_business_key_or_null,
        season_business_key=normalized.season_business_key,
        variety_business_key=normalized.variety_business_key,
        destination_factory_business_key=normalized.destination_factory_business_key,
        plan_version=normalized.plan_version,
        plan_row_hash=normalized.plan_row_hash,
        planting_area_mu=normalized.planting_area_mu,
        business_scope_hash=normalized.business_scope_hash,
        canonical_payload=dict(normalized.canonical_payload),
        forecast_evidence_hash=normalized.forecast_evidence_hash,
        created_at=created_at,
    )


async def _load_core_forecast(
    session: AsyncSession,
    public_forecast_id: str,
) -> CoreForecastRunModel:
    row = await session.scalar(
        select(CoreForecastRunModel).where(CoreForecastRunModel.request_hash == public_forecast_id)
    )
    if row is None:
        raise TrialForecastEvidenceNotFoundError()
    return row


async def _load_existing_evidence(
    session: AsyncSession,
    public_forecast_id: str,
) -> TrialForecastEvidenceModel | None:
    return cast(
        TrialForecastEvidenceModel | None,
        await session.scalar(
            select(TrialForecastEvidenceModel).where(
                TrialForecastEvidenceModel.public_forecast_id == public_forecast_id
            )
        ),
    )


async def _load_existing_binding(
    session: AsyncSession,
    public_forecast_id: str,
) -> TrialResourceBindingModel | None:
    return cast(
        TrialResourceBindingModel | None,
        await session.scalar(
            select(TrialResourceBindingModel).where(
                TrialResourceBindingModel.resource_kind == TrialResourceKind.FORECAST.value,
                TrialResourceBindingModel.public_resource_id == public_forecast_id,
            )
        ),
    )


def _validate_replay(
    existing: TrialForecastEvidence,
    expected: _NormalizedEvidence,
) -> None:
    if (
        existing.public_forecast_id != expected.public_forecast_id
        or existing.forecast_input_authority_hash != expected.forecast_input_authority_hash
        or existing.authority_available_at != expected.authority_available_at
        or existing.farm_business_key != expected.farm_business_key
        or existing.subfarm_business_key_or_null != expected.subfarm_business_key_or_null
        or existing.season_business_key != expected.season_business_key
        or existing.variety_business_key != expected.variety_business_key
        or existing.destination_factory_business_key != expected.destination_factory_business_key
        or existing.plan_version != expected.plan_version
        or existing.plan_row_hash != expected.plan_row_hash
        or existing.planting_area_mu != expected.planting_area_mu
        or existing.business_scope_hash != expected.business_scope_hash
        or dict(existing.canonical_payload) != expected.canonical_payload
        or existing.forecast_evidence_hash != expected.forecast_evidence_hash
    ):
        raise TrialForecastEvidenceConflictError()


async def create_forecast_evidence_and_binding_in_result_boundary(
    session: AsyncSession,
    *,
    public_forecast_id: str,
    owner_identity: str,
    forecast_input_authority_hash: str,
    authority_available_at: datetime,
    farm_business_key: str,
    subfarm_business_key_or_null: str | None,
    season_business_key: str,
    variety_business_key: str,
    destination_factory_business_key: str,
    plan_version: str,
    plan_row_hash: str,
    planting_area_mu: Decimal,
) -> TrialForecastEvidence:
    """Persist evidence and its Forecast binding without committing or rolling back."""

    if (
        not isinstance(owner_identity, str)
        or not owner_identity
        or owner_identity != owner_identity.strip()
    ):
        raise TrialForecastEvidenceInputError()
    expected = _normalize_evidence(
        public_forecast_id=public_forecast_id,
        forecast_input_authority_hash=forecast_input_authority_hash,
        authority_available_at=authority_available_at,
        farm_business_key=farm_business_key,
        subfarm_business_key_or_null=subfarm_business_key_or_null,
        season_business_key=season_business_key,
        variety_business_key=variety_business_key,
        destination_factory_business_key=destination_factory_business_key,
        plan_version=plan_version,
        plan_row_hash=plan_row_hash,
        planting_area_mu=planting_area_mu,
    )
    await _load_core_forecast(session, expected.public_forecast_id)
    existing_row = await _load_existing_evidence(session, expected.public_forecast_id)
    existing_binding = await _load_existing_binding(session, expected.public_forecast_id)
    if (existing_row is None) != (existing_binding is None):
        raise TrialForecastEvidenceIntegrityError()
    if existing_row is not None and existing_binding is not None:
        existing = _project_and_verify(existing_row)
        _validate_replay(existing, expected)
        if (
            existing_binding.owner_identity != owner_identity
            or existing_binding.business_scope_hash != expected.business_scope_hash
        ):
            raise TrialForecastEvidenceConflictError()
        return existing

    evidence_row = TrialForecastEvidenceModel(
        evidence_schema_version=TRIAL_FORECAST_EVIDENCE_SCHEMA_VERSION,
        public_forecast_id=expected.public_forecast_id,
        forecast_input_authority_hash=expected.forecast_input_authority_hash,
        authority_available_at=expected.authority_available_at,
        farm_business_key=expected.farm_business_key,
        subfarm_business_key_or_null=expected.subfarm_business_key_or_null,
        season_business_key=expected.season_business_key,
        variety_business_key=expected.variety_business_key,
        destination_factory_business_key=expected.destination_factory_business_key,
        plan_version=expected.plan_version,
        plan_row_hash=expected.plan_row_hash,
        planting_area_mu=expected.planting_area_mu,
        business_scope_hash=expected.business_scope_hash,
        canonical_payload=expected.canonical_payload,
        forecast_evidence_hash=expected.forecast_evidence_hash,
        created_at=datetime.now(UTC),
    )
    try:
        async with session.begin_nested():
            session.add(evidence_row)
            await session.flush()
            await create_forecast_binding_in_result_boundary(
                session,
                public_forecast_id=expected.public_forecast_id,
                owner_identity=owner_identity,
                business_scope_hash=expected.business_scope_hash,
            )
    except TrialResourceBindingConflictError as exc:
        raise TrialForecastEvidenceConflictError() from exc
    except IntegrityError as exc:
        replay_row = await _load_existing_evidence(session, expected.public_forecast_id)
        replay_binding = await _load_existing_binding(session, expected.public_forecast_id)
        if replay_row is None or replay_binding is None:
            raise TrialForecastEvidenceConflictError() from exc
        replay = _project_and_verify(replay_row)
        _validate_replay(replay, expected)
        if (
            replay_binding.owner_identity != owner_identity
            or replay_binding.business_scope_hash != expected.business_scope_hash
        ):
            raise TrialForecastEvidenceConflictError() from exc
        return replay
    return _project_and_verify(evidence_row)


async def load_forecast_evidence_by_public_id(
    session: AsyncSession,
    *,
    public_forecast_id: str,
) -> TrialForecastEvidence:
    public_id = _sha256(public_forecast_id, field="public_forecast_id")
    await _load_core_forecast(session, public_id)
    row = await _load_existing_evidence(session, public_id)
    if row is None:
        raise TrialForecastEvidenceNotFoundError()
    return _project_and_verify(row)


async def authorize_and_load_forecast_evidence(
    session: AsyncSession,
    *,
    public_forecast_id: str,
    owner_identity: str,
) -> TrialForecastEvidence:
    """Authorize the binding before loading complete evidence."""

    try:
        binding = await authorize_trial_resource(
            session,
            resource_kind=TrialResourceKind.FORECAST,
            public_resource_id=public_forecast_id,
            owner_identity=owner_identity,
        )
    except TrialResourceNotFoundError as exc:
        raise TrialForecastEvidenceNotFoundError() from exc
    try:
        evidence = await load_forecast_evidence_by_public_id(
            session,
            public_forecast_id=public_forecast_id,
        )
    except TrialForecastEvidenceNotFoundError as exc:
        raise TrialForecastEvidenceIntegrityError() from exc
    if binding.business_scope_hash != evidence.business_scope_hash:
        raise TrialForecastEvidenceIntegrityError()
    return evidence
