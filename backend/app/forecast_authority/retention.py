"""Append-only retention of complete production forecast authority.

The retention envelope is deliberately downstream of the existing production
owners.  ``capture_production_forecast_authority`` reads those owners and
freezes their identities plus the complete Task 8 daily curve in one
immutable envelope.  It never re-runs a model, derives a value from labels, or
updates an existing envelope.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.exceptions import (
    S3CanonicalIdentityConflictError,
    S3ContractInvariantViolationError,
    S3DecimalAssertionError,
)
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastRunModel,
)
from backend.app.models.core_forecast_task10_authority_binding import (
    CoreForecastTask10AuthorityBindingModel,
)
from backend.app.models.forecast_authority import (
    FORECAST_AUTHORITY_SCHEMA_VERSION,
    FORECAST_AUTHORITY_SCOPE_PRODUCTION,
    FORECAST_AUTHORITY_STATUS_CAPTURED,
    ForecastAuthorityCaptureModel,
    ForecastAuthorityDailyModel,
)
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.master_data import Factory, Farm, Season, Subfarm, Variety
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import LocationReference
from backend.app.models.production_plan import FarmSeasonVarietyPlan
from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherSourceLocation,
)
from backend.app.rolling_backtest.persisted_task10_authority_binding import (
    compute_binding_identity_hash,
)

FORECAST_AUTHORITY_POLICY_VERSION = "v0.3-s3-prospective-forecast-authority-retention-v1"


class ForecastAuthorityError(ValueError):
    """Base class for sanitized authority-capture/readback failures."""

    reason_code = "FORECAST_AUTHORITY_ERROR"


class ForecastAuthorityInputError(ForecastAuthorityError):
    reason_code = "FORECAST_AUTHORITY_INPUT_INVALID"


class ForecastAuthorityMissingError(ForecastAuthorityError):
    reason_code = "FORECAST_AUTHORITY_MISSING"


class ForecastAuthorityAmbiguousError(ForecastAuthorityError):
    reason_code = "FORECAST_AUTHORITY_AMBIGUOUS"


class ForecastAuthorityPostCutoffError(ForecastAuthorityError):
    reason_code = "FORECAST_AUTHORITY_POST_CUTOFF"


class ForecastAuthorityIntegrityError(ForecastAuthorityError):
    reason_code = "FORECAST_AUTHORITY_HASH_MISMATCH"


class ForecastAuthorityConflictError(ForecastAuthorityError):
    reason_code = "FORECAST_AUTHORITY_REPLAY_CONFLICT"


class ForecastAuthorityTestFixtureError(ForecastAuthorityError):
    reason_code = "TEST_FIXTURE_AUTHORITY_NOT_PROMOTABLE"


@dataclass(frozen=True, slots=True)
class ForecastAuthorityDailySource:
    """One complete Task 8 daily row supplied by an existing owner."""

    source_daily_prediction_id: int
    forecast_run_id: int
    prediction_date: date
    phenology_coordinate_day: Decimal
    p50_kg: Decimal
    p80_kg: Decimal
    p90_kg: Decimal
    cumulative_p50_kg: Decimal
    cumulative_p80_kg: Decimal
    cumulative_p90_kg: Decimal
    curve_share: Decimal
    confidence_level: str
    quality_flags: tuple[str, ...]
    source_created_at: datetime


@dataclass(frozen=True, slots=True)
class ForecastAuthoritySource:
    """Canonical source projection used by the append-only writer.

    The source projection contains owner snapshots, not newly computed
    business values.  Production callers should obtain it through
    ``build_forecast_authority_source_from_persisted_lineage``.
    """

    forecast_identity: str
    forecast_cutoff_at: datetime
    forecast_created_at: datetime
    forecast_available_at: datetime
    core_forecast_run_id: int
    code_authority_id: int
    code_authority_hash: str
    code_authority_available_at: datetime
    forecast_season_id: int
    destination_factory_id: int
    business_grain_snapshot: Mapping[str, Any]
    plan_id: int
    plan_version: int
    plan_row_hash: str
    plan_snapshot: Mapping[str, Any]
    location_reference_id: int
    weather_mapping_id: int | None
    base_temperature_search_run_id: int | None
    weather_snapshot: Mapping[str, Any]
    task8_forecast_run_id: int
    task8_model_run_id: int
    task8_artifact_id: int
    task8_model_version: str
    task8_config_hash: str
    task8_artifact_hash: str
    task8_snapshot: Mapping[str, Any]
    task9_run_id: int
    task9_result_hash: str
    task9_snapshot: Mapping[str, Any]
    task10_training_run_id: int
    task10_training_signature: str
    task10_prediction_run_id: int
    task10_prediction_input_signature: str
    task10_prediction_hash: str
    task10_binding_id: int
    task10_binding_hash: str
    task10_snapshot: Mapping[str, Any]
    core_snapshot: Mapping[str, Any]
    governance_snapshot: Mapping[str, Any]
    daily_predictions: tuple[ForecastAuthorityDailySource, ...]


@dataclass(frozen=True, slots=True)
class ForecastAuthorityCaptureResult:
    """Result of one append-only capture attempt."""

    capture_id: int
    authority_hash: str
    reused_existing: bool
    write_count: int


@dataclass(frozen=True, slots=True)
class PersistedForecastAuthorityDaily:
    prediction_date: date
    p50_kg: Decimal
    p80_kg: Decimal
    p90_kg: Decimal
    cumulative_p50_kg: Decimal
    cumulative_p80_kg: Decimal
    cumulative_p90_kg: Decimal
    phenology_coordinate_day: Decimal
    curve_share: Decimal
    confidence_level: str
    quality_flags: tuple[str, ...]
    source_daily_prediction_id: int
    source_created_at: datetime
    row_hash: str


@dataclass(frozen=True, slots=True)
class PersistedForecastAuthority:
    """PIT-visible read model returned from the durable retention envelope."""

    forecast_identity: str
    forecast_cutoff_at: datetime
    forecast_available_at: datetime
    business_grain_snapshot: Mapping[str, Any]
    plan_snapshot: Mapping[str, Any]
    weather_snapshot: Mapping[str, Any]
    task8_snapshot: Mapping[str, Any]
    task9_snapshot: Mapping[str, Any]
    task10_snapshot: Mapping[str, Any]
    core_snapshot: Mapping[str, Any]
    governance_snapshot: Mapping[str, Any]
    daily_predictions: tuple[PersistedForecastAuthorityDaily, ...]
    authority_hash: str


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ForecastAuthorityInputError()
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(canonical_json_bytes(payload).decode("utf-8")))
    except (
        TypeError,
        ValueError,
        OverflowError,
        S3CanonicalIdentityConflictError,
        S3ContractInvariantViolationError,
        S3DecimalAssertionError,
    ) as exc:
        raise ForecastAuthorityInputError() from exc


def _hash_payload(payload: Mapping[str, Any]) -> str:
    try:
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    except (
        TypeError,
        ValueError,
        OverflowError,
        S3CanonicalIdentityConflictError,
        S3ContractInvariantViolationError,
        S3DecimalAssertionError,
    ) as exc:
        raise ForecastAuthorityInputError() from exc


def _require_sha(value: str, *, allow_non_sha: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        if allow_non_sha:
            return value
        raise ForecastAuthorityInputError()
    return value


def _require_positive(value: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ForecastAuthorityInputError()
    return value


def _require_finite_decimal(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ForecastAuthorityInputError()
    return value


def _require_stored_decimal(
    value: Decimal,
    *,
    quantum: Decimal = Decimal("0.000001"),
) -> Decimal:
    """Require a Decimal that survives its existing DB owner exactly."""
    parsed = _require_finite_decimal(value)
    quantized = parsed.quantize(quantum)
    if parsed != quantized:
        raise ForecastAuthorityInputError()
    return parsed


def _require_snapshot(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ForecastAuthorityInputError()
    return value


def _require_snapshot_identity(
    snapshot: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
    nested: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Reject an owner snapshot that contradicts the retained owner fields."""
    for key, expected_value in expected.items():
        if key in snapshot and snapshot[key] != expected_value:
            raise ForecastAuthorityIntegrityError()
    for container, nested_expected in (nested or {}).items():
        value = snapshot.get(container)
        if not isinstance(value, Mapping):
            continue
        for key, expected_value in nested_expected.items():
            if key in value and value[key] != expected_value:
                raise ForecastAuthorityIntegrityError()


def _require_visible_timestamp(value: datetime | None, cutoff: datetime) -> datetime:
    if value is None:
        raise ForecastAuthorityMissingError()
    normalized = _utc(value)
    if normalized > cutoff:
        raise ForecastAuthorityPostCutoffError()
    return normalized


def _contains_test_marker(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(
            marker in lowered
            for marker in (
                "test_fixture",
                "test-fixture",
                "s2-fixture",
                "synthetic",
                "2026-demo",
            )
        )
    if isinstance(value, Mapping):
        return any(
            _contains_test_marker(key) or _contains_test_marker(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_test_marker(item) for item in value)
    return False


def _model_snapshot(row: Any) -> dict[str, Any]:
    """Build a canonical, value-preserving snapshot from an existing ORM owner."""
    payload: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = _utc(value)
        payload[column.name] = value
    return _canonical_dict(payload)


def _daily_payload(source: ForecastAuthorityDailySource) -> dict[str, Any]:
    return _canonical_dict(
        {
            "source_daily_prediction_id": source.source_daily_prediction_id,
            "forecast_run_id": source.forecast_run_id,
            "prediction_date": source.prediction_date,
            "phenology_coordinate_day": _require_stored_decimal(
                source.phenology_coordinate_day
            ),
            "p50_kg": _require_stored_decimal(source.p50_kg),
            "p80_kg": _require_stored_decimal(source.p80_kg),
            "p90_kg": _require_stored_decimal(source.p90_kg),
            "cumulative_p50_kg": _require_stored_decimal(source.cumulative_p50_kg),
            "cumulative_p80_kg": _require_stored_decimal(source.cumulative_p80_kg),
            "cumulative_p90_kg": _require_stored_decimal(source.cumulative_p90_kg),
            "curve_share": _require_stored_decimal(
                source.curve_share,
                quantum=Decimal("0.0000000001"),
            ),
            "confidence_level": source.confidence_level,
            "quality_flags": source.quality_flags,
            "source_created_at": _utc(source.source_created_at),
        }
    )


def _identity_payload(source: ForecastAuthoritySource, source_lineage_hash: str) -> dict[str, Any]:
    return {
        "authority_schema_version": FORECAST_AUTHORITY_SCHEMA_VERSION,
        "policy_version": FORECAST_AUTHORITY_POLICY_VERSION,
        "forecast_identity": source.forecast_identity,
        "forecast_cutoff_at": _utc(source.forecast_cutoff_at),
        "core_forecast_run_id": source.core_forecast_run_id,
        "source_lineage_hash": source_lineage_hash,
    }


def _lineage_hash(source: ForecastAuthoritySource, hashes: Mapping[str, str]) -> str:
    return _hash_payload(
        {
            "core_forecast_run_id": source.core_forecast_run_id,
            "code_authority_id": source.code_authority_id,
            "code_authority_hash": source.code_authority_hash,
            "task8_forecast_run_id": source.task8_forecast_run_id,
            "task8_model_run_id": source.task8_model_run_id,
            "task8_artifact_id": source.task8_artifact_id,
            "task8_authority_hash": hashes["task8_authority_hash"],
            "task9_run_id": source.task9_run_id,
            "task9_result_hash": source.task9_result_hash,
            "task9_authority_hash": hashes["task9_authority_hash"],
            "task10_training_run_id": source.task10_training_run_id,
            "task10_prediction_run_id": source.task10_prediction_run_id,
            "task10_binding_id": source.task10_binding_id,
            "task10_authority_hash": hashes["task10_authority_hash"],
            "core_authority_hash": hashes["core_authority_hash"],
        }
    )


def _build_capture_payload(
    source: ForecastAuthoritySource,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], str]:
    if _contains_test_marker(source.business_grain_snapshot) or any(
        _contains_test_marker(snapshot)
        for snapshot in (
            source.plan_snapshot,
            source.weather_snapshot,
            source.task8_snapshot,
            source.task9_snapshot,
            source.task10_snapshot,
            source.core_snapshot,
            source.governance_snapshot,
        )
    ):
        raise ForecastAuthorityTestFixtureError()
    for snapshot in (
        source.business_grain_snapshot,
        source.plan_snapshot,
        source.weather_snapshot,
        source.task8_snapshot,
        source.task9_snapshot,
        source.task10_snapshot,
        source.core_snapshot,
        source.governance_snapshot,
    ):
        _require_snapshot(snapshot)
    if not source.forecast_identity or not isinstance(source.forecast_identity, str):
        raise ForecastAuthorityInputError()
    _require_sha(source.forecast_identity)
    for value in (
        source.code_authority_hash,
        source.plan_row_hash,
        source.task8_config_hash,
        source.task8_artifact_hash,
        source.task9_result_hash,
        source.task10_training_signature,
        source.task10_prediction_input_signature,
        source.task10_prediction_hash,
        source.task10_binding_hash,
    ):
        _require_sha(value)
    for owner_id in (
        source.core_forecast_run_id,
        source.code_authority_id,
        source.forecast_season_id,
        source.destination_factory_id,
        source.plan_id,
        source.location_reference_id,
        source.task8_forecast_run_id,
        source.task8_model_run_id,
        source.task8_artifact_id,
        source.task9_run_id,
        source.task10_training_run_id,
        source.task10_prediction_run_id,
        source.task10_binding_id,
    ):
        _require_positive(owner_id)
    _require_positive(source.plan_version)
    for optional_owner_id in (source.weather_mapping_id, source.base_temperature_search_run_id):
        if optional_owner_id is not None:
            _require_positive(optional_owner_id)
    cutoff = _utc(source.forecast_cutoff_at)
    created = _utc(source.forecast_created_at)
    available = _utc(source.forecast_available_at)
    code_available = _utc(source.code_authority_available_at)
    if created > cutoff or available > cutoff or code_available > cutoff:
        raise ForecastAuthorityPostCutoffError()
    if available < created:
        raise ForecastAuthorityIntegrityError()
    _require_snapshot_identity(
        source.business_grain_snapshot,
        expected={
            "season_id": source.forecast_season_id,
            "destination_factory_id": source.destination_factory_id,
        },
        nested={
            "season": {"id": source.forecast_season_id},
            "factory": {"id": source.destination_factory_id},
        },
    )
    _require_snapshot_identity(
        source.plan_snapshot,
        expected={
            "id": source.plan_id,
            "version": source.plan_version,
            "row_hash": source.plan_row_hash,
        },
    )
    _require_snapshot_identity(
        source.weather_snapshot,
        expected={
            "mapping_id": source.weather_mapping_id,
            "base_temperature_run_id": source.base_temperature_search_run_id,
        },
        nested={
            "location_reference": {"id": source.location_reference_id},
            "weather_mapping": {"id": source.weather_mapping_id},
            "base_temperature_search_run": {"id": source.base_temperature_search_run_id},
        },
    )
    _require_snapshot_identity(
        source.task8_snapshot,
        expected={
            "run_id": source.task8_forecast_run_id,
            "model_run_id": source.task8_model_run_id,
            "artifact_id": source.task8_artifact_id,
        },
        nested={
            "forecast_run": {"id": source.task8_forecast_run_id},
            "model_run": {"id": source.task8_model_run_id},
            "artifact": {"id": source.task8_artifact_id},
        },
    )
    _require_snapshot_identity(
        source.task9_snapshot,
        expected={"run_id": source.task9_run_id, "result_hash": source.task9_result_hash},
        nested={"run": {"id": source.task9_run_id, "result_hash": source.task9_result_hash}},
    )
    _require_snapshot_identity(
        source.task10_snapshot,
        expected={
            "training_run_id": source.task10_training_run_id,
            "prediction_run_id": source.task10_prediction_run_id,
            "binding_id": source.task10_binding_id,
        },
        nested={
            "binding": {"id": source.task10_binding_id},
            "prediction_run": {"id": source.task10_prediction_run_id},
            "training_run": {"id": source.task10_training_run_id},
        },
    )
    _require_snapshot_identity(
        source.core_snapshot,
        expected={"run_id": source.core_forecast_run_id, "request_hash": source.forecast_identity},
        nested={
            "run": {
                "id": source.core_forecast_run_id,
                "request_hash": source.forecast_identity,
            }
        },
    )
    if not source.daily_predictions:
        raise ForecastAuthorityInputError()

    canonical_daily = tuple(_daily_payload(item) for item in source.daily_predictions)
    ordered_daily = tuple(
        sorted(canonical_daily, key=lambda item: cast(str, item["prediction_date"]))
    )
    dates = [date.fromisoformat(cast(str, item["prediction_date"])) for item in ordered_daily]
    if len(set(dates)) != len(dates):
        raise ForecastAuthorityIntegrityError()
    if dates != [dates[0] + timedelta(days=index) for index in range(len(dates))]:
        raise ForecastAuthorityIntegrityError()
    for item in ordered_daily:
        _require_positive(cast(int, item["source_daily_prediction_id"]))
        _require_positive(cast(int, item["forecast_run_id"]))
        if item["forecast_run_id"] != source.task8_forecast_run_id:
            raise ForecastAuthorityIntegrityError()
        if not isinstance(item["confidence_level"], str) or not item["confidence_level"]:
            raise ForecastAuthorityInputError()
        quality_flags = item["quality_flags"]
        if not isinstance(quality_flags, list) or any(
            not isinstance(flag, str) or not flag for flag in quality_flags
        ):
            raise ForecastAuthorityInputError()
        for numeric_field in (
            "p50_kg",
            "p80_kg",
            "p90_kg",
            "cumulative_p50_kg",
            "cumulative_p80_kg",
            "cumulative_p90_kg",
        ):
            numeric = Decimal(cast(str, item[numeric_field]))
            if numeric < 0:
                raise ForecastAuthorityIntegrityError()
        if Decimal(cast(str, item["p50_kg"])) > Decimal(cast(str, item["p80_kg"])):
            raise ForecastAuthorityIntegrityError()
        if Decimal(cast(str, item["p80_kg"])) > Decimal(cast(str, item["p90_kg"])):
            raise ForecastAuthorityIntegrityError()
        if datetime.fromisoformat(cast(str, item["source_created_at"])) > cutoff:
            raise ForecastAuthorityPostCutoffError()

    snapshots = {
        "business_grain_hash": _hash_payload(source.business_grain_snapshot),
        "plan_authority_hash": _hash_payload(source.plan_snapshot),
        "weather_authority_hash": _hash_payload(source.weather_snapshot),
        "task8_authority_hash": _hash_payload(source.task8_snapshot),
        "task9_authority_hash": _hash_payload(source.task9_snapshot),
        "task10_authority_hash": _hash_payload(source.task10_snapshot),
        "core_authority_hash": _hash_payload(source.core_snapshot),
    }
    source_lineage_hash = _lineage_hash(source, snapshots)
    authority_identity_hash = _hash_payload(_identity_payload(source, source_lineage_hash))
    daily_hashes = tuple(_hash_payload(item) for item in ordered_daily)
    task8_daily_artifact_hash = _hash_payload({"rows": daily_hashes})
    canonical_parent = _canonical_dict(
        {
            "authority_schema_version": FORECAST_AUTHORITY_SCHEMA_VERSION,
            "authority_scope": FORECAST_AUTHORITY_SCOPE_PRODUCTION,
            "status": FORECAST_AUTHORITY_STATUS_CAPTURED,
            "forecast_identity": source.forecast_identity,
            "forecast_cutoff_at": cutoff,
            "forecast_created_at": created,
            "forecast_available_at": available,
            "core_forecast_run_id": source.core_forecast_run_id,
            "code_authority_id": source.code_authority_id,
            "code_authority_hash": source.code_authority_hash,
            "code_authority_available_at": code_available,
            "forecast_season_id": source.forecast_season_id,
            "destination_factory_id": source.destination_factory_id,
            "business_grain_hash": snapshots["business_grain_hash"],
            "business_grain_snapshot": source.business_grain_snapshot,
            "plan_id": source.plan_id,
            "plan_version": source.plan_version,
            "plan_row_hash": source.plan_row_hash,
            "plan_authority_hash": snapshots["plan_authority_hash"],
            "plan_snapshot": source.plan_snapshot,
            "location_reference_id": source.location_reference_id,
            "weather_mapping_id": source.weather_mapping_id,
            "base_temperature_search_run_id": source.base_temperature_search_run_id,
            "weather_authority_hash": snapshots["weather_authority_hash"],
            "weather_snapshot": source.weather_snapshot,
            "task8_forecast_run_id": source.task8_forecast_run_id,
            "task8_model_run_id": source.task8_model_run_id,
            "task8_artifact_id": source.task8_artifact_id,
            "task8_model_version": source.task8_model_version,
            "task8_config_hash": source.task8_config_hash,
            "task8_artifact_hash": source.task8_artifact_hash,
            "task8_authority_hash": snapshots["task8_authority_hash"],
            "task8_snapshot": source.task8_snapshot,
            "task9_run_id": source.task9_run_id,
            "task9_result_hash": source.task9_result_hash,
            "task9_authority_hash": snapshots["task9_authority_hash"],
            "task9_snapshot": source.task9_snapshot,
            "task10_training_run_id": source.task10_training_run_id,
            "task10_training_signature": source.task10_training_signature,
            "task10_prediction_run_id": source.task10_prediction_run_id,
            "task10_prediction_input_signature": source.task10_prediction_input_signature,
            "task10_prediction_hash": source.task10_prediction_hash,
            "task10_binding_id": source.task10_binding_id,
            "task10_binding_hash": source.task10_binding_hash,
            "task10_authority_hash": snapshots["task10_authority_hash"],
            "task10_snapshot": source.task10_snapshot,
            "core_authority_hash": snapshots["core_authority_hash"],
            "core_snapshot": source.core_snapshot,
            "governance_snapshot": source.governance_snapshot,
            "source_lineage_hash": source_lineage_hash,
            "task8_daily_artifact_hash": task8_daily_artifact_hash,
            "daily_row_count": len(ordered_daily),
            "authority_identity_hash": authority_identity_hash,
        }
    )
    authority_hash = _hash_payload(canonical_parent)
    return canonical_parent, ordered_daily, authority_hash


def _expected_parent_payload(row: ForecastAuthorityCaptureModel) -> dict[str, Any]:
    return _canonical_dict(
        {
            "authority_schema_version": row.authority_schema_version,
            "authority_scope": row.authority_scope,
            "status": row.status,
            "forecast_identity": row.forecast_identity,
            "forecast_cutoff_at": _utc(row.forecast_cutoff_at),
            "forecast_created_at": _utc(row.forecast_created_at),
            "forecast_available_at": _utc(row.forecast_available_at),
            "core_forecast_run_id": row.core_forecast_run_id,
            "code_authority_id": row.code_authority_id,
            "code_authority_hash": row.code_authority_hash,
            "code_authority_available_at": _utc(row.code_authority_available_at),
            "forecast_season_id": row.forecast_season_id,
            "destination_factory_id": row.destination_factory_id,
            "business_grain_hash": row.business_grain_hash,
            "business_grain_snapshot": row.business_grain_snapshot,
            "plan_id": row.plan_id,
            "plan_version": row.plan_version,
            "plan_row_hash": row.plan_row_hash,
            "plan_authority_hash": row.plan_authority_hash,
            "plan_snapshot": row.plan_snapshot,
            "location_reference_id": row.location_reference_id,
            "weather_mapping_id": row.weather_mapping_id,
            "base_temperature_search_run_id": row.base_temperature_search_run_id,
            "weather_authority_hash": row.weather_authority_hash,
            "weather_snapshot": row.weather_snapshot,
            "task8_forecast_run_id": row.task8_forecast_run_id,
            "task8_model_run_id": row.task8_model_run_id,
            "task8_artifact_id": row.task8_artifact_id,
            "task8_model_version": row.task8_model_version,
            "task8_config_hash": row.task8_config_hash,
            "task8_artifact_hash": row.task8_artifact_hash,
            "task8_authority_hash": row.task8_authority_hash,
            "task8_snapshot": row.task8_snapshot,
            "task9_run_id": row.task9_run_id,
            "task9_result_hash": row.task9_result_hash,
            "task9_authority_hash": row.task9_authority_hash,
            "task9_snapshot": row.task9_snapshot,
            "task10_training_run_id": row.task10_training_run_id,
            "task10_training_signature": row.task10_training_signature,
            "task10_prediction_run_id": row.task10_prediction_run_id,
            "task10_prediction_input_signature": row.task10_prediction_input_signature,
            "task10_prediction_hash": row.task10_prediction_hash,
            "task10_binding_id": row.task10_binding_id,
            "task10_binding_hash": row.task10_binding_hash,
            "task10_authority_hash": row.task10_authority_hash,
            "task10_snapshot": row.task10_snapshot,
            "core_authority_hash": row.core_authority_hash,
            "core_snapshot": row.core_snapshot,
            "governance_snapshot": row.governance_snapshot,
            "source_lineage_hash": row.source_lineage_hash,
            "task8_daily_artifact_hash": row.task8_daily_artifact_hash,
            "daily_row_count": row.daily_row_count,
            "authority_identity_hash": row.authority_identity_hash,
        }
    )


def _expected_daily_payload(row: ForecastAuthorityDailyModel) -> dict[str, Any]:
    return _canonical_dict(
        {
            "source_daily_prediction_id": row.source_daily_prediction_id,
            "forecast_run_id": row.forecast_run_id,
            "prediction_date": row.prediction_date,
            "phenology_coordinate_day": row.phenology_coordinate_day,
            "p50_kg": row.p50_kg,
            "p80_kg": row.p80_kg,
            "p90_kg": row.p90_kg,
            "cumulative_p50_kg": row.cumulative_p50_kg,
            "cumulative_p80_kg": row.cumulative_p80_kg,
            "cumulative_p90_kg": row.cumulative_p90_kg,
            "curve_share": row.curve_share,
            "confidence_level": row.confidence_level,
            "quality_flags": row.quality_flags,
            "source_created_at": _utc(row.source_created_at),
        }
    )


def _verify_capture_rows(
    parent: ForecastAuthorityCaptureModel,
    daily_rows: Sequence[ForecastAuthorityDailyModel],
) -> None:
    if (
        parent.authority_schema_version != FORECAST_AUTHORITY_SCHEMA_VERSION
        or parent.authority_scope != FORECAST_AUTHORITY_SCOPE_PRODUCTION
        or parent.status != FORECAST_AUTHORITY_STATUS_CAPTURED
        or parent.daily_row_count <= 0
    ):
        raise ForecastAuthorityIntegrityError()
    for value in (
        parent.forecast_identity,
        parent.authority_identity_hash,
        parent.business_grain_hash,
        parent.plan_row_hash,
        parent.plan_authority_hash,
        parent.weather_authority_hash,
        parent.code_authority_hash,
        parent.task8_config_hash,
        parent.task8_artifact_hash,
        parent.task8_authority_hash,
        parent.task9_result_hash,
        parent.task9_authority_hash,
        parent.task10_training_signature,
        parent.task10_prediction_input_signature,
        parent.task10_prediction_hash,
        parent.task10_binding_hash,
        parent.task10_authority_hash,
        parent.core_authority_hash,
        parent.source_lineage_hash,
        parent.task8_daily_artifact_hash,
        parent.authority_hash,
    ):
        _require_sha(value)
    for owner_id in (
        parent.core_forecast_run_id,
        parent.code_authority_id,
        parent.forecast_season_id,
        parent.destination_factory_id,
        parent.plan_id,
        parent.location_reference_id,
        parent.task8_forecast_run_id,
        parent.task8_model_run_id,
        parent.task8_artifact_id,
        parent.task9_run_id,
        parent.task10_training_run_id,
        parent.task10_prediction_run_id,
        parent.task10_binding_id,
    ):
        _require_positive(owner_id)
    if parent.weather_mapping_id is not None:
        _require_positive(parent.weather_mapping_id)
    if parent.base_temperature_search_run_id is not None:
        _require_positive(parent.base_temperature_search_run_id)
    required_snapshots = (
        (parent.business_grain_snapshot, ("grain", "season", "factory", "grains")),
        (parent.plan_snapshot, ("id", "farm_id", "season_id", "variety_id", "version")),
        (
            parent.weather_snapshot,
            ("location_reference", "weather_mapping", "weather_source_location"),
        ),
        (parent.task8_snapshot, ("forecast_run", "model_run", "artifact", "daily_row_ids")),
        (parent.task9_snapshot, ("run", "member_row_count")),
        (
            parent.task10_snapshot,
            ("binding", "prediction_run", "training_run", "prediction_row_hashes"),
        ),
        (parent.core_snapshot, ("run", "daily_row_hashes")),
        (parent.governance_snapshot, ("policy_version", "model_identity", "source_identity")),
    )
    for snapshot, keys in required_snapshots:
        _require_snapshot(snapshot)
        if any(key not in snapshot for key in keys):
            raise ForecastAuthorityIntegrityError()
    parent_payload = _expected_parent_payload(parent)
    if parent.canonical_payload != parent_payload:
        raise ForecastAuthorityIntegrityError()
    if _hash_payload(parent_payload) != parent.authority_hash:
        raise ForecastAuthorityIntegrityError()
    identity_payload = {
        "authority_schema_version": FORECAST_AUTHORITY_SCHEMA_VERSION,
        "policy_version": FORECAST_AUTHORITY_POLICY_VERSION,
        "forecast_identity": parent.forecast_identity,
        "forecast_cutoff_at": _utc(parent.forecast_cutoff_at),
        "core_forecast_run_id": parent.core_forecast_run_id,
        "source_lineage_hash": parent.source_lineage_hash,
    }
    if _hash_payload(identity_payload) != parent.authority_identity_hash:
        raise ForecastAuthorityIntegrityError()
    snapshot_hashes = (
        (parent.business_grain_snapshot, parent.business_grain_hash),
        (parent.plan_snapshot, parent.plan_authority_hash),
        (parent.weather_snapshot, parent.weather_authority_hash),
        (parent.task8_snapshot, parent.task8_authority_hash),
        (parent.task9_snapshot, parent.task9_authority_hash),
        (parent.task10_snapshot, parent.task10_authority_hash),
        (parent.core_snapshot, parent.core_authority_hash),
    )
    if any(_hash_payload(snapshot) != expected_hash for snapshot, expected_hash in snapshot_hashes):
        raise ForecastAuthorityIntegrityError()
    expected_lineage = _hash_payload(
        {
            "core_forecast_run_id": parent.core_forecast_run_id,
            "code_authority_id": parent.code_authority_id,
            "code_authority_hash": parent.code_authority_hash,
            "task8_forecast_run_id": parent.task8_forecast_run_id,
            "task8_model_run_id": parent.task8_model_run_id,
            "task8_artifact_id": parent.task8_artifact_id,
            "task8_authority_hash": parent.task8_authority_hash,
            "task9_run_id": parent.task9_run_id,
            "task9_result_hash": parent.task9_result_hash,
            "task9_authority_hash": parent.task9_authority_hash,
            "task10_training_run_id": parent.task10_training_run_id,
            "task10_prediction_run_id": parent.task10_prediction_run_id,
            "task10_binding_id": parent.task10_binding_id,
            "task10_authority_hash": parent.task10_authority_hash,
            "core_authority_hash": parent.core_authority_hash,
        }
    )
    if expected_lineage != parent.source_lineage_hash:
        raise ForecastAuthorityIntegrityError()
    if parent.authority_scope != FORECAST_AUTHORITY_SCOPE_PRODUCTION:
        raise ForecastAuthorityTestFixtureError()
    if _contains_test_marker(parent.canonical_payload):
        raise ForecastAuthorityTestFixtureError()
    if len(daily_rows) != parent.daily_row_count or not daily_rows:
        raise ForecastAuthorityIntegrityError()
    ordered_rows = sorted(daily_rows, key=lambda item: item.prediction_date)
    if [row.prediction_date for row in ordered_rows] != [
        ordered_rows[0].prediction_date + timedelta(days=index)
        for index in range(len(ordered_rows))
    ]:
        raise ForecastAuthorityIntegrityError()
    row_hashes: list[str] = []
    source_prediction_ids: set[int] = set()
    cutoff = _utc(parent.forecast_cutoff_at)
    for row in ordered_rows:
        _require_positive(row.id)
        _require_positive(row.source_daily_prediction_id)
        _require_positive(row.forecast_run_id)
        if (
            row.forecast_run_id != parent.task8_forecast_run_id
            or row.source_daily_prediction_id in source_prediction_ids
        ):
            raise ForecastAuthorityIntegrityError()
        source_prediction_ids.add(row.source_daily_prediction_id)
        expected = _expected_daily_payload(row)
        if row.canonical_payload != expected or _hash_payload(expected) != row.row_hash:
            raise ForecastAuthorityIntegrityError()
        if _utc(row.source_created_at) > cutoff:
            raise ForecastAuthorityPostCutoffError()
        for quantity in (
            row.phenology_coordinate_day,
            row.p50_kg,
            row.p80_kg,
            row.p90_kg,
            row.cumulative_p50_kg,
            row.cumulative_p80_kg,
            row.cumulative_p90_kg,
        ):
            _require_stored_decimal(quantity)
        _require_stored_decimal(row.curve_share, quantum=Decimal("0.0000000001"))
        if row.p50_kg < 0 or row.p80_kg < row.p50_kg or row.p90_kg < row.p80_kg:
            raise ForecastAuthorityIntegrityError()
        row_hashes.append(row.row_hash)
    if _hash_payload({"rows": row_hashes}) != parent.task8_daily_artifact_hash:
        raise ForecastAuthorityIntegrityError()
    daily_row_ids = parent.task8_snapshot["daily_row_ids"]
    if not isinstance(daily_row_ids, list) or any(
        _require_positive(value) != value for value in daily_row_ids
    ) or tuple(daily_row_ids) != tuple(row.source_daily_prediction_id for row in ordered_rows):
        raise ForecastAuthorityIntegrityError()
    prediction_row_hashes = parent.task10_snapshot["prediction_row_hashes"]
    if (
        not isinstance(prediction_row_hashes, list)
        or not prediction_row_hashes
        or any(not isinstance(value, str) for value in prediction_row_hashes)
    ):
        raise ForecastAuthorityIntegrityError()
    for prediction_row_hash in prediction_row_hashes:
        _require_sha(prediction_row_hash)


def _parent_values(
    source: ForecastAuthoritySource,
    parent_payload: Mapping[str, Any],
    authority_hash: str,
) -> dict[str, Any]:
    return {
        "authority_schema_version": FORECAST_AUTHORITY_SCHEMA_VERSION,
        "authority_scope": FORECAST_AUTHORITY_SCOPE_PRODUCTION,
        "status": FORECAST_AUTHORITY_STATUS_CAPTURED,
        "forecast_identity": source.forecast_identity,
        "forecast_cutoff_at": _utc(source.forecast_cutoff_at),
        "forecast_created_at": _utc(source.forecast_created_at),
        "forecast_available_at": _utc(source.forecast_available_at),
        "core_forecast_run_id": source.core_forecast_run_id,
        "code_authority_id": source.code_authority_id,
        "code_authority_hash": source.code_authority_hash,
        "code_authority_available_at": _utc(source.code_authority_available_at),
        "forecast_season_id": source.forecast_season_id,
        "destination_factory_id": source.destination_factory_id,
        "business_grain_hash": parent_payload["business_grain_hash"],
        "business_grain_snapshot": cast(dict[str, Any], parent_payload["business_grain_snapshot"]),
        "plan_id": source.plan_id,
        "plan_version": source.plan_version,
        "plan_row_hash": source.plan_row_hash,
        "plan_authority_hash": parent_payload["plan_authority_hash"],
        "plan_snapshot": cast(dict[str, Any], parent_payload["plan_snapshot"]),
        "location_reference_id": source.location_reference_id,
        "weather_mapping_id": source.weather_mapping_id,
        "base_temperature_search_run_id": source.base_temperature_search_run_id,
        "weather_authority_hash": parent_payload["weather_authority_hash"],
        "weather_snapshot": cast(dict[str, Any], parent_payload["weather_snapshot"]),
        "task8_forecast_run_id": source.task8_forecast_run_id,
        "task8_model_run_id": source.task8_model_run_id,
        "task8_artifact_id": source.task8_artifact_id,
        "task8_model_version": source.task8_model_version,
        "task8_config_hash": source.task8_config_hash,
        "task8_artifact_hash": source.task8_artifact_hash,
        "task8_authority_hash": parent_payload["task8_authority_hash"],
        "task8_snapshot": cast(dict[str, Any], parent_payload["task8_snapshot"]),
        "task9_run_id": source.task9_run_id,
        "task9_result_hash": source.task9_result_hash,
        "task9_authority_hash": parent_payload["task9_authority_hash"],
        "task9_snapshot": cast(dict[str, Any], parent_payload["task9_snapshot"]),
        "task10_training_run_id": source.task10_training_run_id,
        "task10_training_signature": source.task10_training_signature,
        "task10_prediction_run_id": source.task10_prediction_run_id,
        "task10_prediction_input_signature": source.task10_prediction_input_signature,
        "task10_prediction_hash": source.task10_prediction_hash,
        "task10_binding_id": source.task10_binding_id,
        "task10_binding_hash": source.task10_binding_hash,
        "task10_authority_hash": parent_payload["task10_authority_hash"],
        "task10_snapshot": cast(dict[str, Any], parent_payload["task10_snapshot"]),
        "core_authority_hash": parent_payload["core_authority_hash"],
        "core_snapshot": cast(dict[str, Any], parent_payload["core_snapshot"]),
        "governance_snapshot": cast(dict[str, Any], parent_payload["governance_snapshot"]),
        "source_lineage_hash": parent_payload["source_lineage_hash"],
        "task8_daily_artifact_hash": parent_payload["task8_daily_artifact_hash"],
        "daily_row_count": parent_payload["daily_row_count"],
        "canonical_payload": dict(parent_payload),
        "authority_identity_hash": parent_payload["authority_identity_hash"],
        "authority_hash": authority_hash,
    }


def _daily_values(
    capture_id: int,
    source: ForecastAuthorityDailySource,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "forecast_authority_capture_id": capture_id,
        "source_daily_prediction_id": source.source_daily_prediction_id,
        "forecast_run_id": source.forecast_run_id,
        "prediction_date": source.prediction_date,
        "phenology_coordinate_day": source.phenology_coordinate_day,
        "p50_kg": source.p50_kg,
        "p80_kg": source.p80_kg,
        "p90_kg": source.p90_kg,
        "cumulative_p50_kg": source.cumulative_p50_kg,
        "cumulative_p80_kg": source.cumulative_p80_kg,
        "cumulative_p90_kg": source.cumulative_p90_kg,
        "curve_share": source.curve_share,
        "confidence_level": source.confidence_level,
        "quality_flags": list(source.quality_flags),
        "source_created_at": _utc(source.source_created_at),
        "canonical_payload": dict(payload),
        "row_hash": _hash_payload(payload),
    }


async def _load_capture_by_identity(
    session: AsyncSession,
    forecast_identity: str,
) -> ForecastAuthorityCaptureModel | None:
    rows = list(
        await session.scalars(
            select(ForecastAuthorityCaptureModel).where(
                ForecastAuthorityCaptureModel.forecast_identity == forecast_identity
            )
        )
    )
    if len(rows) > 1:
        raise ForecastAuthorityAmbiguousError()
    return rows[0] if rows else None


async def capture_forecast_authority(
    session: AsyncSession,
    *,
    source: ForecastAuthoritySource,
) -> ForecastAuthorityCaptureResult:
    """Append one complete production authority envelope.

    A replay with the same canonical identity and content returns ``write_count
    == 0``.  Any same-identity content drift is rejected; this function never
    updates or deletes a previous capture.
    """

    parent_payload, daily_payloads, authority_hash = _build_capture_payload(source)
    existing = await _load_capture_by_identity(session, source.forecast_identity)
    if existing is not None:
        if existing.core_forecast_run_id != source.core_forecast_run_id:
            raise ForecastAuthorityConflictError()
        daily_rows = list(
            await session.scalars(
                select(ForecastAuthorityDailyModel)
                .where(ForecastAuthorityDailyModel.forecast_authority_capture_id == existing.id)
                .order_by(ForecastAuthorityDailyModel.prediction_date.asc())
            )
        )
        _verify_capture_rows(existing, daily_rows)
        if (
            existing.authority_hash != authority_hash
            or existing.canonical_payload != parent_payload
        ):
            raise ForecastAuthorityConflictError()
        expected_hashes = tuple(_hash_payload(item) for item in daily_payloads)
        if tuple(row.row_hash for row in daily_rows) != expected_hashes:
            raise ForecastAuthorityConflictError()
        return ForecastAuthorityCaptureResult(
            capture_id=existing.id,
            authority_hash=existing.authority_hash,
            reused_existing=True,
            write_count=0,
        )

    existing_core = list(
        await session.scalars(
            select(ForecastAuthorityCaptureModel).where(
                ForecastAuthorityCaptureModel.core_forecast_run_id == source.core_forecast_run_id
            )
        )
    )
    if len(existing_core) > 1:
        raise ForecastAuthorityAmbiguousError()
    if existing_core:
        raise ForecastAuthorityConflictError()

    parent = ForecastAuthorityCaptureModel(
        **_parent_values(source, parent_payload, authority_hash),
        created_at=datetime.now(UTC),
    )
    try:
        async with session.begin_nested():
            session.add(parent)
            await session.flush()
            session.add_all(
                [
                    ForecastAuthorityDailyModel(**_daily_values(parent.id, source_item, payload))
                    for source_item, payload in zip(
                        sorted(source.daily_predictions, key=lambda item: item.prediction_date),
                        daily_payloads,
                        strict=True,
                    )
                ]
            )
            await session.flush()
    except IntegrityError as exc:
        replay = await _load_capture_by_identity(session, source.forecast_identity)
        if replay is None:
            raise ForecastAuthorityConflictError() from exc
        daily_rows = list(
            await session.scalars(
                select(ForecastAuthorityDailyModel).where(
                    ForecastAuthorityDailyModel.forecast_authority_capture_id == replay.id
                )
            )
        )
        _verify_capture_rows(replay, daily_rows)
        if replay.authority_hash != authority_hash:
            raise ForecastAuthorityConflictError() from exc
        return ForecastAuthorityCaptureResult(
            capture_id=replay.id,
            authority_hash=replay.authority_hash,
            reused_existing=True,
            write_count=0,
        )
    return ForecastAuthorityCaptureResult(
        capture_id=parent.id,
        authority_hash=authority_hash,
        reused_existing=False,
        write_count=1 + len(daily_payloads),
    )


async def load_pit_visible_forecast_authority(
    session: AsyncSession,
    *,
    forecast_identity: str,
    cutoff_at: datetime,
) -> PersistedForecastAuthority:
    """Load one complete production authority visible at ``cutoff_at``."""

    if not isinstance(forecast_identity, str):
        raise ForecastAuthorityInputError()
    _require_sha(forecast_identity)
    requested_cutoff = _utc(cutoff_at)
    parent = await _load_capture_by_identity(session, forecast_identity)
    if parent is None:
        raise ForecastAuthorityMissingError()
    if (
        _utc(parent.forecast_cutoff_at) > requested_cutoff
        or _utc(parent.forecast_created_at) > requested_cutoff
        or _utc(parent.forecast_available_at) > requested_cutoff
        or _utc(parent.code_authority_available_at) > requested_cutoff
    ):
        raise ForecastAuthorityPostCutoffError()
    daily_rows = list(
        await session.scalars(
            select(ForecastAuthorityDailyModel)
            .where(ForecastAuthorityDailyModel.forecast_authority_capture_id == parent.id)
            .order_by(ForecastAuthorityDailyModel.prediction_date.asc())
        )
    )
    _verify_capture_rows(parent, daily_rows)
    if any(_utc(row.source_created_at) > requested_cutoff for row in daily_rows):
        raise ForecastAuthorityPostCutoffError()
    daily = tuple(
        PersistedForecastAuthorityDaily(
            prediction_date=row.prediction_date,
            p50_kg=row.p50_kg,
            p80_kg=row.p80_kg,
            p90_kg=row.p90_kg,
            cumulative_p50_kg=row.cumulative_p50_kg,
            cumulative_p80_kg=row.cumulative_p80_kg,
            cumulative_p90_kg=row.cumulative_p90_kg,
            phenology_coordinate_day=row.phenology_coordinate_day,
            curve_share=row.curve_share,
            confidence_level=row.confidence_level,
            quality_flags=tuple(row.quality_flags),
            source_daily_prediction_id=row.source_daily_prediction_id,
            source_created_at=_utc(row.source_created_at),
            row_hash=row.row_hash,
        )
        for row in daily_rows
    )
    return PersistedForecastAuthority(
        forecast_identity=parent.forecast_identity,
        forecast_cutoff_at=_utc(parent.forecast_cutoff_at),
        forecast_available_at=_utc(parent.forecast_available_at),
        business_grain_snapshot=parent.business_grain_snapshot,
        plan_snapshot=parent.plan_snapshot,
        weather_snapshot=parent.weather_snapshot,
        task8_snapshot=parent.task8_snapshot,
        task9_snapshot=parent.task9_snapshot,
        task10_snapshot=parent.task10_snapshot,
        core_snapshot=parent.core_snapshot,
        governance_snapshot=parent.governance_snapshot,
        daily_predictions=daily,
        authority_hash=parent.authority_hash,
    )


async def build_forecast_authority_source_from_persisted_lineage(
    session: AsyncSession,
    *,
    core_forecast_run_id: int,
) -> ForecastAuthoritySource:
    """Project existing production owner rows into a retention source.

    This is intentionally strict: a complete Task 8/Task 9/Core/Task 10
    chain and its plan/weather/master-data inputs are required.  The function
    does not select a latest row and does not synthesize missing authority.
    """

    core = await session.get(CoreForecastRunModel, core_forecast_run_id)
    if (
        core is None
        or core.status != "completed"
        or core.forecast_effective_cutoff_at is None
        or core.code_authority_id is None
        or core.code_authority_hash is None
    ):
        raise ForecastAuthorityMissingError()
    code = await session.get(CoreForecastCodeAuthorityModel, core.code_authority_id)
    task8 = await session.get(MaturityForecastRun, core.task8_forecast_run_id)
    if code is None or task8 is None:
        raise ForecastAuthorityMissingError()
    model_run = await session.get(MaturityModelRun, task8.model_run_id)
    artifact = await session.get(MaturityModelArtifact, task8.artifact_id)
    plan = await session.get(FarmSeasonVarietyPlan, task8.plan_id)
    location = await session.get(LocationReference, task8.location_reference_id)
    mapping = (
        await session.get(LocationWeatherMapping, task8.weather_mapping_id)
        if task8.weather_mapping_id is not None
        else None
    )
    base_temperature = (
        await session.get(BaseTemperatureSearchRun, task8.base_temperature_search_run_id)
        if task8.base_temperature_search_run_id is not None
        else None
    )
    task9 = await session.get(HarvestStateRun, core.task9_harvest_state_run_id)
    binding_rows = list(
        await session.scalars(
            select(CoreForecastTask10AuthorityBindingModel).where(
                CoreForecastTask10AuthorityBindingModel.core_forecast_run_id == core.id
            )
        )
    )
    if (
        model_run is None
        or artifact is None
        or plan is None
        or location is None
        or mapping is None
        or base_temperature is None
        or task9 is None
        or len(binding_rows) != 1
    ):
        raise ForecastAuthorityMissingError()
    binding = binding_rows[0]
    prediction = await session.get(ResidualModelPredictionRun, binding.task10_prediction_run_id)
    training = (
        await session.get(ResidualModelTrainingRun, prediction.training_run_id)
        if prediction is not None and prediction.training_run_id is not None
        else None
    )
    if prediction is None or training is None:
        raise ForecastAuthorityMissingError()
    if (
        model_run.status != "completed"
        or task8.status != "completed"
        or artifact.run_id != model_run.id
        or task8.model_run_id != model_run.id
        or task8.artifact_id != artifact.id
        or task8.plan_id != plan.id
        or task8.location_reference_id != location.id
        or task8.weather_mapping_id != mapping.id
        or task8.base_temperature_search_run_id != base_temperature.id
        or task9.status != "completed"
        or task9.maturity_forecast_run_id != task8.id
        or task9.maturity_model_run_id != model_run.id
        or task9.maturity_model_artifact_id != artifact.id
        or task9.destination_factory_id != core.destination_factory_id
        or task9.forecast_season_id != core.forecast_season_id
        or task9.maturity_forecast_source_signature != task8.source_signature
        or task9.maturity_model_source_signature != model_run.source_signature
        or task9.maturity_model_artifact_hash != artifact.artifact_hash
        or binding.task9_run_id != task9.id
        or binding.task10_prediction_run_id != prediction.id
        or prediction.execution_status != "completed"
        or prediction.task9_run_id != task9.id
        or prediction.task9_result_hash != task9.result_hash
        or prediction.training_run_id != training.id
        or training.execution_status != "completed"
        or training.eligibility_status != "eligible"
        or prediction.expected_prediction_row_count <= 0
    ):
        raise ForecastAuthorityIntegrityError()
    if core.code_authority_id != code.id or core.code_authority_hash != code.authority_hash:
        raise ForecastAuthorityIntegrityError()
    if core.task8_artifact_hash != artifact.artifact_hash:
        raise ForecastAuthorityIntegrityError()
    if core.task9_result_hash != task9.result_hash:
        raise ForecastAuthorityIntegrityError()
    from backend.app.core_forecast.persistence import (
        CoreForecastPersistenceIntegrityError,
        CoreForecastRunRepository,
    )

    try:
        persisted_core = await CoreForecastRunRepository(session).load_complete_run(core.id)
    except CoreForecastPersistenceIntegrityError as exc:
        raise ForecastAuthorityIntegrityError() from exc
    if persisted_core is None or persisted_core.run.result_hash != core.result_hash:
        raise ForecastAuthorityIntegrityError()
    expected_binding_hash = compute_binding_identity_hash(
        core_forecast_run_id=core.id,
        core_forecast_result_hash=core.result_hash,
        task9_run_id=core.task9_harvest_state_run_id,
        task9_result_hash=core.task9_result_hash,
        task10_prediction_run_id=prediction.id,
        task10_prediction_hash=prediction.prediction_hash,
    )
    if binding.binding_identity_hash != expected_binding_hash:
        raise ForecastAuthorityIntegrityError()
    cutoff = _utc(core.forecast_effective_cutoff_at)
    for timestamp in (
        code.available_at,
        core.created_at,
        core.completed_at,
        model_run.finished_at,
        task8.finished_at,
        training.finished_at,
        prediction.completed_at,
        binding.created_at,
        base_temperature.finished_at,
    ):
        _require_visible_timestamp(timestamp, cutoff)
    if (
        plan.available_at > cutoff.date()
        or location.valid_from > cutoff.date()
        or mapping.available_at > cutoff.date()
    ):
        raise ForecastAuthorityPostCutoffError()
    if (
        mapping.location_reference_id != location.id
        or mapping.weather_source_location_id <= 0
        or base_temperature.selected_base_temperature is None
    ):
        raise ForecastAuthorityIntegrityError()
    daily_rows = list(
        await session.scalars(
            select(MaturityDailyPredictionModel)
            .where(MaturityDailyPredictionModel.forecast_run_id == task8.id)
            .order_by(MaturityDailyPredictionModel.prediction_date.asc())
        )
    )
    if len(daily_rows) == 0 or any(_utc(row.created_at) > cutoff for row in daily_rows):
        raise ForecastAuthorityPostCutoffError()
    daily = tuple(
        ForecastAuthorityDailySource(
            source_daily_prediction_id=row.id,
            forecast_run_id=row.forecast_run_id,
            prediction_date=row.prediction_date,
            phenology_coordinate_day=row.phenology_coordinate_day,
            p50_kg=row.p50_kg,
            p80_kg=row.p80_kg,
            p90_kg=row.p90_kg,
            cumulative_p50_kg=row.cumulative_p50_kg,
            cumulative_p80_kg=row.cumulative_p80_kg,
            cumulative_p90_kg=row.cumulative_p90_kg,
            curve_share=row.curve_share,
            confidence_level=row.confidence_level,
            quality_flags=tuple(row.quality_flags),
            source_created_at=_utc(row.created_at),
        )
        for row in daily_rows
    )
    core_rows = list(
        await session.scalars(
            select(CoreForecastDailyRowModel)
            .where(CoreForecastDailyRowModel.core_forecast_run_id == core.id)
            .order_by(
                CoreForecastDailyRowModel.date.asc(),
                CoreForecastDailyRowModel.forecast_quantile.asc(),
                CoreForecastDailyRowModel.farm_id.asc(),
                CoreForecastDailyRowModel.subfarm_id.asc(),
                CoreForecastDailyRowModel.variety_id.asc(),
            )
        )
    )
    if len(core_rows) != core.daily_row_count:
        raise ForecastAuthorityIntegrityError()
    prediction_rows = list(
        await session.scalars(
            select(ResidualModelPredictionRow)
            .where(ResidualModelPredictionRow.prediction_run_id == prediction.id)
            .order_by(
                ResidualModelPredictionRow.arrival_local_date.asc(),
                ResidualModelPredictionRow.destination_factory_id.asc(),
            )
        )
    )
    if len(prediction_rows) != prediction.expected_prediction_row_count:
        raise ForecastAuthorityIntegrityError()

    season = await session.get(Season, core.forecast_season_id)
    factory = await session.get(Factory, core.destination_factory_id)
    if season is None or factory is None:
        raise ForecastAuthorityMissingError()
    scope_ids = sorted({(row.farm_id, row.subfarm_id, row.variety_id) for row in core_rows})
    farm_ids = {item[0] for item in scope_ids}
    farms = {
        row.id: row
        for row in await session.scalars(
            select(Farm).where(Farm.id.in_(farm_ids))
        )
    }
    subfarms = {
        row.id: row
        for row in await session.scalars(
            select(Subfarm).where(Subfarm.id.in_({item[1] for item in scope_ids}))
        )
    }
    varieties = {
        row.id: row
        for row in await session.scalars(
            select(Variety).where(Variety.id.in_({item[2] for item in scope_ids}))
        )
    }
    if (
        len(farms) != len({item[0] for item in scope_ids})
        or len(subfarms) != len({item[1] for item in scope_ids})
        or len(varieties) != len({item[2] for item in scope_ids})
    ):
        raise ForecastAuthorityMissingError()
    business_grain_snapshot = {
        "grain": "SEASON_X_FARM_X_SUBFARM_X_VARIETY",
        "season": _model_snapshot(season),
        "factory": _model_snapshot(factory),
        "grains": [
            {
                "season_id": season.id,
                "season_business_key": season.code,
                "farm_id": farm_id,
                "farm_business_key": farms[farm_id].name,
                "subfarm_id": subfarm_id,
                "subfarm_business_key": subfarms[subfarm_id].name,
                "variety_id": variety_id,
                "variety_business_key": varieties[variety_id].code,
                "destination_factory_id": factory.id,
                "destination_factory_business_key": factory.code or factory.name,
            }
            for farm_id, subfarm_id, variety_id in scope_ids
        ],
    }
    weather_source = await session.get(WeatherSourceLocation, mapping.weather_source_location_id)
    if weather_source is None:
        raise ForecastAuthorityMissingError()
    if mapping.weather_source_location_id != weather_source.id:
        raise ForecastAuthorityIntegrityError()
    task8_snapshot = {
        "forecast_run": _model_snapshot(task8),
        "model_run": _model_snapshot(model_run),
        "artifact": _model_snapshot(artifact),
        "daily_row_ids": [row.id for row in daily_rows],
    }
    task9_snapshot = {
        "run": _model_snapshot(task9),
        "member_row_count": task9.member_row_count,
    }
    task10_snapshot = {
        "binding": _model_snapshot(binding),
        "prediction_run": _model_snapshot(prediction),
        "training_run": _model_snapshot(training),
        "prediction_row_hashes": [row.prediction_row_hash for row in prediction_rows],
    }
    core_snapshot = {
        "run": _model_snapshot(core),
        "daily_row_hashes": [row.row_hash for row in core_rows],
    }
    weather_snapshot = {
        "location_reference": _model_snapshot(location),
        "weather_mapping": _model_snapshot(mapping),
        "weather_source_location": _model_snapshot(weather_source),
        "base_temperature_search_run": _model_snapshot(base_temperature),
    }
    governance_snapshot = {
        "policy_version": FORECAST_AUTHORITY_POLICY_VERSION,
        "model_identity": {
            "task8_model_version": model_run.model_version,
            "task8_config_hash": model_run.config_hash,
            "task8_artifact_hash": artifact.artifact_hash,
        },
        "parameter_identity": core.retention_policy_snapshot_hash,
        "source_identity": {
            "task8_source_signature": task8.source_signature,
            "task9_result_hash": task9.result_hash,
            "task10_prediction_input_signature": prediction.prediction_input_signature,
        },
        "code_identity": code.authority_hash,
    }
    return ForecastAuthoritySource(
        forecast_identity=core.request_hash,
        forecast_cutoff_at=cutoff,
        forecast_created_at=_utc(core.created_at),
        forecast_available_at=_utc(core.completed_at),
        core_forecast_run_id=core.id,
        code_authority_id=code.id,
        code_authority_hash=code.authority_hash,
        code_authority_available_at=_utc(code.available_at),
        forecast_season_id=core.forecast_season_id,
        destination_factory_id=core.destination_factory_id,
        business_grain_snapshot=business_grain_snapshot,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_row_hash=plan.row_hash,
        plan_snapshot=_model_snapshot(plan),
        location_reference_id=location.id,
        weather_mapping_id=mapping.id,
        base_temperature_search_run_id=base_temperature.id,
        weather_snapshot=weather_snapshot,
        task8_forecast_run_id=task8.id,
        task8_model_run_id=model_run.id,
        task8_artifact_id=artifact.id,
        task8_model_version=model_run.model_version,
        task8_config_hash=model_run.config_hash,
        task8_artifact_hash=artifact.artifact_hash,
        task8_snapshot=task8_snapshot,
        task9_run_id=task9.id,
        task9_result_hash=task9.result_hash,
        task9_snapshot=task9_snapshot,
        task10_training_run_id=training.id,
        task10_training_signature=training.training_signature,
        task10_prediction_run_id=prediction.id,
        task10_prediction_input_signature=prediction.prediction_input_signature,
        task10_prediction_hash=prediction.prediction_hash,
        task10_binding_id=binding.id,
        task10_binding_hash=binding.binding_identity_hash,
        task10_snapshot=task10_snapshot,
        core_snapshot=core_snapshot,
        governance_snapshot=governance_snapshot,
        daily_predictions=daily,
    )


async def capture_production_forecast_authority(
    session: AsyncSession,
    *,
    core_forecast_run_id: int,
) -> ForecastAuthorityCaptureResult:
    """Capture the complete authority chain for a production Core forecast."""

    source = await build_forecast_authority_source_from_persisted_lineage(
        session,
        core_forecast_run_id=core_forecast_run_id,
    )
    return await capture_forecast_authority(session, source=source)
