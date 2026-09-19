"""V0.6-S2 shadow forecast orchestration.

This module is deliberately an application boundary around the existing V0.5
BASE product and the V0.6-S1 PIT repository.  It does not contain forecast
mathematics, does not train a model, and does not treat realized/reanalysis
weather as a forecast.  A real weather provider can be supplied through the
small provider protocol; the default is an explicit unavailable provider.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Final, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.area_yield.base_product import (
    AreaForecastProductRequest,
    AreaForecastProductResult,
    forecast_base_area,
    resolve_prior_history,
)
from backend.app.area_yield.base_product_authority import (
    BaseAreaForecastError,
    BaseProductAuthority,
    load_base_product_authority,
)
from backend.app.pit.canonical import build_input_snapshot
from backend.app.pit.models import AreaRevision, PhenologyObservation
from backend.app.pit.persistence import (
    PITConflictError,
    PITDataFoundationError,
    PITDataFoundationRepository,
    PITNotFoundError,
)
from backend.app.pit.schemas import (
    AreaRevisionInput,
    ForecastDailySnapshotInput,
    ForecastRunSnapshot,
    ForecastRunSnapshotInput,
    WeatherForecastSnapshotInput,
)
from backend.app.pit.visibility import weather_forecast_visible_at

ForecastMode = Literal["SHADOW", "REPLAY"]
WeatherCaptureStatus = Literal["CAPTURED", "UNAVAILABLE", "FAILED"]

FORECAST_MODE_SHADOW: Final[Literal["SHADOW"]] = "SHADOW"
FORECAST_MODE_REPLAY: Final[Literal["REPLAY"]] = "REPLAY"
MODEL_STATUS_EXPERIMENTAL = "EXPERIMENTAL"
WEATHER_CAPTURED: Final[Literal["CAPTURED"]] = "CAPTURED"
WEATHER_UNAVAILABLE: Final[Literal["UNAVAILABLE"]] = "UNAVAILABLE"
WEATHER_FAILED: Final[Literal["FAILED"]] = "FAILED"
WEATHER_WARNING_UNAVAILABLE = "WEATHER_FORECAST_NOT_AVAILABLE"
WEATHER_WARNING_FAILED = "WEATHER_FORECAST_CAPTURE_FAILED"
REFERENCE_AREA_SOURCE = "v0_5_base_reference_registry_v1"
REFERENCE_AREA_BASIS = "REFERENCE_AREA_ONLY_SERVER_OWNED"


class ShadowForecastError(RuntimeError):
    """Machine-readable fail-closed error for one shadow execution."""

    status_code = 400

    def __init__(self, code: str, reason: str | None = None) -> None:
        super().__init__(reason or code)
        self.code = code
        self.reason = reason or code


class ShadowForecastAuthorityError(ShadowForecastError):
    status_code = 503


class ShadowForecastBlocked(ShadowForecastError):
    """A source/input condition prevents a valid shadow run."""


class WeatherForecastProviderError(RuntimeError):
    """Provider transport/configuration errors are never converted to data."""


class WeatherForecastProvider(Protocol):
    """Provider contract for genuine forecast-time/as-issued data."""

    provider_name: str

    def capture(
        self,
        *,
        base: Mapping[str, object],
        forecast_created_at: datetime,
        target_season: str,
    ) -> WeatherForecastCaptureResult: ...


@dataclass(frozen=True, slots=True)
class WeatherForecastCaptureResult:
    status: WeatherCaptureStatus
    provider: str | None
    snapshots: tuple[WeatherForecastSnapshotInput, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class UnavailableWeatherForecastProvider:
    """Explicit default until an as-issued provider is configured.

    The existing weather CSV/ERA5 capabilities are realized/historical data,
    so they intentionally cannot be adapted to this protocol.
    """

    provider_name: str = "UNCONFIGURED"

    def capture(
        self,
        *,
        base: Mapping[str, object],
        forecast_created_at: datetime,
        target_season: str,
    ) -> WeatherForecastCaptureResult:
        del base, forecast_created_at, target_season
        return WeatherForecastCaptureResult(
            status=WEATHER_UNAVAILABLE,
            provider=self.provider_name,
            reason="AS_ISSUED_FORECAST_PROVIDER_NOT_CONFIGURED",
        )


class ShadowForecastRequest(BaseModel):
    """Caller-visible shadow request; authority paths are not request fields."""

    model_config = ConfigDict(extra="forbid")

    base_id: str | None = Field(default=None, min_length=1, max_length=80)
    base_name: str | None = Field(default=None, min_length=1, max_length=200)
    target_season: str = Field(pattern=r"^\d{4}-\d{4}$")
    target_area_mu: Decimal | None = Field(default=None, gt=0)
    forecast_created_at: datetime | None = None
    forecast_run_id: str | None = Field(default=None, min_length=1, max_length=160)
    forecast_mode: ForecastMode = FORECAST_MODE_SHADOW

    @model_validator(mode="after")
    def validate_request(self) -> ShadowForecastRequest:
        if (self.base_id is None) == (self.base_name is None):
            raise ValueError("exactly one of base_id or base_name is required")
        if self.base_id is not None and re.fullmatch(r"base_[0-9a-f]{24}", self.base_id) is None:
            raise ValueError("base_id format is invalid")
        start_year = int(self.target_season[:4])
        if int(self.target_season[5:]) != start_year + 1:
            raise ValueError("target_season must contain consecutive years")
        if not 1 <= start_year <= 9998:
            raise ValueError("target_season is outside supported range")
        if self.forecast_created_at is not None:
            if (
                self.forecast_created_at.tzinfo is None
                or self.forecast_created_at.utcoffset() is None
            ):
                raise ValueError("forecast_created_at must be timezone-aware")
            self.forecast_created_at = self.forecast_created_at.astimezone(UTC)
        return self


@dataclass(frozen=True, slots=True)
class ShadowForecastExecution:
    snapshot: ForecastRunSnapshot
    weather_capture_status: WeatherCaptureStatus
    weather_provider: str | None
    model_output_result_hash: str

    @property
    def weather_snapshot_count(self) -> int:
        return len(self.snapshot.weather_snapshot_ids)


@dataclass(frozen=True, slots=True)
class ShadowForecastBatchItem:
    base_id: str
    status: Literal["SUCCESS", "BLOCKED", "FAILED"]
    execution: ShadowForecastExecution | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ShadowForecastBatchResult:
    items: tuple[ShadowForecastBatchItem, ...]

    @property
    def total_base_count(self) -> int:
        return len(self.items)

    @property
    def success_count(self) -> int:
        return sum(item.status == "SUCCESS" for item in self.items)

    @property
    def blocked_count(self) -> int:
        return sum(item.status == "BLOCKED" for item in self.items)

    @property
    def failed_count(self) -> int:
        return sum(item.status == "FAILED" for item in self.items)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _history_snapshot(
    *, base_id: str, target_season: str, authority: BaseProductAuthority
) -> dict[str, object]:
    try:
        row = resolve_prior_history(
            base_id,
            target_season,
            authority,
            "EXPERIMENTAL",
        )
    except BaseAreaForecastError as exc:
        raise ShadowForecastBlocked("PRIOR_HISTORY_NOT_AVAILABLE") from exc
    quantity = row.get("mapped_harvest_quantity_kg", row.get("harvest_total_kg"))
    source_hash = row.get("source_sha256")
    mapping_hash = row.get("identity_mapping_sha256")
    if quantity is None or not isinstance(source_hash, str) or not isinstance(mapping_hash, str):
        raise ShadowForecastAuthorityError("PRIOR_HISTORY_AUTHORITY_INVALID")
    coverage = str(row.get("coverage_status", "COMPLETE"))
    return {
        "season": str(row.get("season")),
        "quantity_kg": Decimal(str(quantity)),
        "coverage_status": coverage,
        "source_hash": source_hash,
        "identity_mapping_hash": mapping_hash,
    }


def _model_artifact_hashes(authority: BaseProductAuthority) -> dict[str, str]:
    try:
        temporal_hash = str(authority.model["research_artifacts"]["temporal_model_artifact_sha256"])
    except (KeyError, TypeError) as exc:
        raise ShadowForecastAuthorityError("MODEL_AUTHORITY_NOT_AVAILABLE") from exc
    return {
        "authority": authority.authority_hash,
        "model": authority.model_file_sha256,
        "temporal": temporal_hash,
    }


def _base_identity(base: Mapping[str, object]) -> dict[str, object]:
    return {
        "base_id": str(base["base_id"]),
        "canonical_base_name": str(base["canonical_base_name"]),
        "covered_farms": list(cast(Sequence[str], base["covered_farms"])),
    }


async def _ensure_reference_area_revision(
    repository: PITDataFoundationRepository,
    *,
    base: Mapping[str, object],
    authority: BaseProductAuthority,
    forecast_created_at: datetime,
) -> AreaRevision:
    base_id = str(base["base_id"])
    revision_id = f"v06-reference-area-{base_id}-{authority.registry_file_sha256[:16]}"
    try:
        return await repository.get_area_revision(revision_id)
    except PITNotFoundError:
        pass
    if forecast_created_at < _utc_now() - timedelta(seconds=5):
        raise ShadowForecastBlocked("AREA_NOT_AVAILABLE")
    try:
        area_mu = Decimal(str(base["productive_area_mu"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ShadowForecastAuthorityError("AREA_AUTHORITY_INVALID") from exc
    item = AreaRevisionInput(
        area_revision_id=revision_id,
        base_id=base_id,
        season="REFERENCE",
        area_mu=area_mu,
        area_type="REFERENCE_AREA",
        effective_from=forecast_created_at,
        recorded_at=forecast_created_at,
        known_at=forecast_created_at,
        source=REFERENCE_AREA_SOURCE,
        source_reference="configs/v0_5_base_reference_registry_v1.json",
        basis=REFERENCE_AREA_BASIS,
    )
    try:
        return await repository.add_area_revision(item)
    except PITConflictError:
        return await repository.get_area_revision(revision_id)


def _forecast_created_at(request: ShadowForecastRequest) -> datetime:
    value = request.forecast_created_at or _utc_now()
    if request.forecast_mode == FORECAST_MODE_SHADOW and value < _utc_now() - timedelta(seconds=5):
        raise ShadowForecastBlocked("SHADOW_FORECAST_CREATED_AT_MUST_BE_CURRENT")
    return value.astimezone(UTC)


def _weather_warnings(capture: WeatherForecastCaptureResult) -> list[str]:
    if capture.status == WEATHER_UNAVAILABLE:
        return [WEATHER_WARNING_UNAVAILABLE]
    if capture.status == WEATHER_FAILED:
        return [WEATHER_WARNING_FAILED]
    return []


async def _persist_weather_snapshots(
    repository: PITDataFoundationRepository,
    *,
    snapshots: Sequence[WeatherForecastSnapshotInput],
    base_id: str,
    forecast_created_at: datetime,
) -> list[str]:
    persisted_ids: list[str] = []
    for snapshot in snapshots:
        if snapshot.base_id is None or snapshot.base_id != base_id:
            raise ShadowForecastBlocked("WEATHER_SCOPE_UNBOUND")
        if not weather_forecast_visible_at(snapshot, forecast_created_at):
            raise ShadowForecastBlocked("INPUT_VISIBILITY_FAILED")
        try:
            stored = await repository.add_weather_forecast_snapshot(snapshot)
        except PITConflictError:
            stored = await repository.get_weather_forecast_snapshot(snapshot.weather_snapshot_id)
        persisted_ids.append(stored.weather_snapshot_id)
    return sorted(set(persisted_ids))


async def _visible_phenology_ids(
    repository: PITDataFoundationRepository,
    *,
    base_id: str,
    target_season: str,
    forecast_created_at: datetime,
) -> list[str]:
    observations: list[
        PhenologyObservation
    ] = await repository.visible_phenology_observations_for_scope(
        base_id=base_id,
        season=target_season,
        forecast_created_at=forecast_created_at,
    )
    return [observation.observation_id for observation in observations]


def _product_request(
    request: ShadowForecastRequest,
    *,
    base_id: str,
    target_area_mu: Decimal,
) -> AreaForecastProductRequest:
    return AreaForecastProductRequest(
        base_id=base_id,
        target_area_mu=_decimal_text(target_area_mu),
        target_season=request.target_season,
        forecast_mode="EXPERIMENTAL",
    )


def _snapshot_input(
    *,
    request: ShadowForecastRequest,
    forecast_created_at: datetime,
    base: Mapping[str, object],
    area_revision: AreaRevision,
    target_area_mu: Decimal,
    prior_history: Mapping[str, object],
    weather_snapshot_ids: Sequence[str],
    phenology_observation_ids: Sequence[str],
    model_artifact_hashes: Mapping[str, str],
    warnings: Sequence[str],
    product_result: AreaForecastProductResult,
) -> ForecastRunSnapshotInput:
    weather_status = WEATHER_CAPTURED if weather_snapshot_ids else WEATHER_UNAVAILABLE
    request_snapshot = {
        "base_id": str(base["base_id"]),
        "canonical_base_name": str(base["canonical_base_name"]),
        "target_season": request.target_season,
        "target_area_mu": _decimal_text(target_area_mu),
        "forecast_mode": request.forecast_mode,
        "weather_capture_status": weather_status,
    }
    input_json, input_hash = build_input_snapshot(
        request=request_snapshot,
        base_identity=_base_identity(base),
        target_season=request.target_season,
        target_area={"target_area_mu": target_area_mu},
        area_revision_id=area_revision.area_revision_id,
        prior_history=prior_history,
        weather_snapshot_ids=weather_snapshot_ids,
        phenology_observation_ids=phenology_observation_ids,
        model={
            "total_model_id": product_result.total_model_id,
            "temporal_model_id": product_result.temporal_model_id,
            "artifact_hashes": dict(model_artifact_hashes),
        },
        forecast_mode=request.forecast_mode,
        coverage={"prior_history_coverage_status": prior_history["coverage_status"]},
        forecast_created_at=forecast_created_at,
        warnings=warnings,
    )
    daily = [
        ForecastDailySnapshotInput(
            forecast_date=row.date,
            predicted_quantity_kg=Decimal(row.predicted_quantity_kg),
            normalized_share=Decimal(row.normalized_share),
        )
        for row in product_result.daily_curve
    ]
    candidate = ForecastRunSnapshotInput.model_validate(
        {
            "forecast_run_id": request.forecast_run_id or "pending",
            "forecast_created_at": forecast_created_at,
            "base_id": str(base["base_id"]),
            "target_season": request.target_season,
            "forecast_start_date": product_result.forecast_start_date,
            "forecast_end_date": product_result.forecast_end_date,
            "target_area_mu": target_area_mu,
            "forecast_mode": request.forecast_mode,
            "model_status": MODEL_STATUS_EXPERIMENTAL,
            "total_model_id": product_result.total_model_id,
            "temporal_model_id": product_result.temporal_model_id,
            "model_artifact_hashes": dict(model_artifact_hashes),
            "prior_history_season": prior_history["season"],
            "prior_history_quantity_kg": Decimal(str(prior_history["quantity_kg"])),
            "prior_history_coverage_status": prior_history["coverage_status"],
            "prior_history_source_hash": prior_history["source_hash"],
            "prior_history_identity_mapping_hash": prior_history["identity_mapping_hash"],
            "area_revision_id": area_revision.area_revision_id,
            "weather_snapshot_ids": list(weather_snapshot_ids),
            "phenology_observation_ids": list(phenology_observation_ids),
            "input_snapshot_json": input_json,
            "input_snapshot_hash": input_hash,
            "predicted_season_total_kg": Decimal(product_result.predicted_season_total_kg),
            "daily_curve": daily,
            "single_day_peak": product_result.single_day_peak.model_dump(mode="json"),
            "rolling_7day_peak": product_result.rolling_7day_peak.model_dump(mode="json"),
            "result_hash": "0" * 64,
            "warnings": list(warnings),
        }
    )
    return candidate.model_copy(update={"result_hash": candidate.computed_result_hash()})


async def run_shadow_forecast(
    session: AsyncSession,
    request: ShadowForecastRequest,
    *,
    weather_provider: WeatherForecastProvider | None = None,
    authority: BaseProductAuthority | None = None,
) -> ShadowForecastExecution:
    """Resolve PIT inputs, execute the frozen V0.5 product, and persist once."""

    authority_snapshot = authority or load_base_product_authority()
    created_at = _forecast_created_at(request)
    if request.base_id is not None:
        base = authority_snapshot.bases_by_id.get(request.base_id)
    else:
        base = authority_snapshot.bases_by_name.get(request.base_name or "")
    if base is None:
        raise ShadowForecastBlocked("UNREGISTERED_BASE")
    base_id = str(base["base_id"])
    repository = PITDataFoundationRepository(session)
    area_revision = await repository.visible_area_revision_for_forecast(
        base_id=base_id,
        target_season=request.target_season,
        forecast_created_at=created_at,
    )
    if area_revision is None:
        area_revision = await _ensure_reference_area_revision(
            repository,
            base=base,
            authority=authority_snapshot,
            forecast_created_at=created_at,
        )
    target_area_mu = request.target_area_mu or Decimal(str(area_revision.area_mu))
    prior_history = _history_snapshot(
        base_id=base_id,
        target_season=request.target_season,
        authority=authority_snapshot,
    )
    provider = weather_provider or UnavailableWeatherForecastProvider()
    try:
        capture = provider.capture(
            base=base,
            forecast_created_at=created_at,
            target_season=request.target_season,
        )
    except WeatherForecastProviderError:
        capture = WeatherForecastCaptureResult(
            status=WEATHER_FAILED,
            provider=getattr(provider, "provider_name", None),
            reason="WEATHER_PROVIDER_ERROR",
        )
    weather_ids = await _persist_weather_snapshots(
        repository,
        snapshots=capture.snapshots,
        base_id=base_id,
        forecast_created_at=created_at,
    )
    phenology_ids = await _visible_phenology_ids(
        repository,
        base_id=base_id,
        target_season=request.target_season,
        forecast_created_at=created_at,
    )
    warnings = sorted(
        set(_weather_warnings(capture))
        | (
            {"PRIOR_SEASON_HISTORY_COVERAGE_INCOMPLETE"}
            if prior_history["coverage_status"] == "INCOMPLETE"
            else set()
        )
    )
    try:
        product_result = forecast_base_area(
            _product_request(request, base_id=base_id, target_area_mu=target_area_mu),
            authority_snapshot,
        )
    except BaseAreaForecastError as exc:
        raise ShadowForecastBlocked(exc.code, exc.reason) from exc
    candidate = _snapshot_input(
        request=request,
        forecast_created_at=created_at,
        base=base,
        area_revision=area_revision,
        target_area_mu=target_area_mu,
        prior_history=prior_history,
        weather_snapshot_ids=weather_ids,
        phenology_observation_ids=phenology_ids,
        model_artifact_hashes=_model_artifact_hashes(authority_snapshot),
        warnings=warnings,
        product_result=product_result,
    )
    if request.forecast_run_id is None:
        candidate = candidate.model_copy(
            update={"forecast_run_id": f"shadow-{candidate.input_snapshot_hash[:40]}"}
        )
    saved = await repository.save_forecast_run_snapshot(candidate)
    return ShadowForecastExecution(
        snapshot=saved,
        weather_capture_status=capture.status,
        weather_provider=capture.provider,
        model_output_result_hash=product_result.result_hash,
    )


async def run_shadow_forecast_batch(
    session: AsyncSession,
    *,
    target_season: str,
    weather_provider: WeatherForecastProvider | None = None,
    authority: BaseProductAuthority | None = None,
) -> ShadowForecastBatchResult:
    """Run all registered bases in deterministic ID order with isolated items."""

    authority_snapshot = authority or load_base_product_authority()
    items: list[ShadowForecastBatchItem] = []
    base_ids = sorted(authority_snapshot.bases_by_id)
    for base_id in base_ids:
        request = ShadowForecastRequest(base_id=base_id, target_season=target_season)
        try:
            async with session.begin_nested():
                execution = await run_shadow_forecast(
                    session,
                    request,
                    weather_provider=weather_provider,
                    authority=authority_snapshot,
                )
            items.append(
                ShadowForecastBatchItem(base_id=base_id, status="SUCCESS", execution=execution)
            )
        except ShadowForecastBlocked as exc:
            items.append(
                ShadowForecastBatchItem(base_id=base_id, status="BLOCKED", error_code=exc.code)
            )
        except ShadowForecastError as exc:
            items.append(
                ShadowForecastBatchItem(base_id=base_id, status="FAILED", error_code=exc.code)
            )
        except PITDataFoundationError as exc:
            items.append(
                ShadowForecastBatchItem(base_id=base_id, status="FAILED", error_code=exc.code)
            )
    return ShadowForecastBatchResult(items=tuple(items))


def shadow_execution_payload(execution: ShadowForecastExecution) -> dict[str, object]:
    """Serialize the snapshot plus S2 capture status for CLI/tests."""

    payload = execution.snapshot.model_dump(mode="json")
    base_identity = execution.snapshot.input_snapshot_json.get("base_identity")
    if isinstance(base_identity, Mapping):
        payload["base_name"] = base_identity.get("canonical_base_name")
    payload["weather_capture_status"] = execution.weather_capture_status
    payload["weather_provider"] = execution.weather_provider
    payload["weather_snapshot_count"] = execution.weather_snapshot_count
    payload["model_output_result_hash"] = execution.model_output_result_hash
    payload["forecast_status"] = "SHADOW_EXPERIMENTAL"
    return payload


__all__ = [
    "FORECAST_MODE_REPLAY",
    "FORECAST_MODE_SHADOW",
    "ShadowForecastBatchResult",
    "ShadowForecastError",
    "ShadowForecastExecution",
    "ShadowForecastRequest",
    "ShadowForecastBlocked",
    "ShadowForecastAuthorityError",
    "UnavailableWeatherForecastProvider",
    "WeatherForecastCaptureResult",
    "WeatherForecastProvider",
    "WeatherForecastProviderError",
    "run_shadow_forecast",
    "run_shadow_forecast_batch",
    "shadow_execution_payload",
]
