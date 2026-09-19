"""Caller-owned persistence and canonical reload gates for V0.6-S1."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pit.models import (
    AreaRevision,
    ForecastRunSnapshotDaily,
    PhenologyObservation,
    RealizedWeatherObservation,
    WeatherForecastSnapshot,
)
from backend.app.pit.models import (
    ForecastRunSnapshot as ForecastRunSnapshotModel,
)
from backend.app.pit.schemas import (
    AreaRevisionInput,
    ForecastDailySnapshotInput,
    ForecastRunSnapshot,
    ForecastRunSnapshotInput,
    PhenologyObservationInput,
    RealizedWeatherObservationInput,
    WeatherForecastSnapshotInput,
)
from backend.app.pit.visibility import record_visible_at, weather_forecast_visible_at


class PITDataFoundationError(RuntimeError):
    code = "PIT_DATA_FOUNDATION_ERROR"
    status_code = 500


class PITIntegrityError(PITDataFoundationError):
    code = "PIT_PERSISTENCE_INTEGRITY_ERROR"


class PITConflictError(PITDataFoundationError):
    code = "PIT_PERSISTENCE_CONFLICT"
    status_code = 409


class PITNotFoundError(PITDataFoundationError):
    code = "PIT_RECORD_NOT_FOUND"
    status_code = 404


class PITWriteFailure(PITDataFoundationError):
    code = "PIT_WRITE_FAILURE"
    status_code = 503


class PITVisibilityRejected(PITIntegrityError):
    code = "PIT_INPUT_NOT_VISIBLE"


TModel = TypeVar("TModel")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PITIntegrityError("NAIVE_TIMESTAMP")
    return value.astimezone(UTC)


def _sha_match(expected: str, actual: str, field: str) -> None:
    if expected != actual:
        raise PITIntegrityError(f"{field.upper()}_MISMATCH")


def _decimal_close(left: Decimal, right: Decimal) -> bool:
    tolerance = Decimal("0.000001") + max(abs(left), abs(right)) * Decimal("1e-12")
    return abs(left - right) <= tolerance


def _daily_payload(rows: Iterable[ForecastDailySnapshotInput]) -> list[dict[str, Any]]:
    return [row.model_dump(mode="python") for row in rows]


class PITDataFoundationRepository:
    """Flush-only repository; transaction ownership stays with the caller."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _insert(self, model: TModel) -> TModel:
        try:
            self.session.add(model)
            await self.session.flush()
            return model
        except IntegrityError as exc:
            raise PITConflictError("PIT_INSERT_CONFLICT") from exc
        except SQLAlchemyError as exc:
            raise PITWriteFailure("PIT_INSERT_FAILED") from exc

    async def add_area_revision(self, item: AreaRevisionInput) -> AreaRevision:
        payload_hash = item.computed_payload_hash()
        if item.payload_hash is not None:
            _sha_match(item.payload_hash, payload_hash, "payload_hash")
        if item.supersedes_revision_id is not None:
            parent = await self.session.get(AreaRevision, item.supersedes_revision_id)
            if parent is None:
                raise PITIntegrityError("SUPERSEDED_AREA_REVISION_NOT_FOUND")
            if parent.base_id != item.base_id or parent.season != item.season:
                raise PITIntegrityError("AREA_REVISION_SCOPE_MISMATCH")
        model = AreaRevision(
            **item.model_dump(exclude={"payload_hash"}),
            payload_hash=payload_hash,
        )
        return await self._insert(model)

    async def get_area_revision(self, area_revision_id: str) -> AreaRevision:
        model = await self.session.get(AreaRevision, area_revision_id)
        if model is None:
            raise PITNotFoundError("AREA_REVISION_NOT_FOUND")
        payload = AreaRevisionInput.model_validate(
            {
                **{
                    key: getattr(model, key)
                    for key in (
                        "area_revision_id",
                        "base_id",
                        "season",
                        "area_mu",
                        "area_type",
                        "effective_from",
                        "effective_to",
                        "recorded_at",
                        "known_at",
                        "source",
                        "source_reference",
                        "basis",
                        "supersedes_revision_id",
                    )
                },
                "payload_hash": model.payload_hash,
            }
        )
        _sha_match(model.payload_hash, payload.computed_payload_hash(), "area_revision_payload")
        return model

    async def visible_area_revision(
        self,
        *,
        base_id: str,
        season: str,
        forecast_created_at: datetime,
    ) -> AreaRevision | None:
        cutoff = _utc(forecast_created_at)
        models = list(
            await self.session.scalars(
                select(AreaRevision)
                .where(
                    AreaRevision.base_id == base_id,
                    AreaRevision.season == season,
                    AreaRevision.known_at <= cutoff,
                    AreaRevision.effective_from <= cutoff,
                    or_(AreaRevision.effective_to.is_(None), AreaRevision.effective_to >= cutoff),
                )
                .order_by(AreaRevision.known_at.desc(), AreaRevision.recorded_at.desc())
            )
        )
        return models[0] if models else None

    async def add_weather_forecast_snapshot(
        self, item: WeatherForecastSnapshotInput
    ) -> WeatherForecastSnapshot:
        payload_hash = item.computed_payload_hash()
        if item.payload_hash is not None:
            _sha_match(item.payload_hash, payload_hash, "payload_hash")
        model = WeatherForecastSnapshot(
            **item.model_dump(exclude={"payload_hash"}),
            payload_hash=payload_hash,
        )
        return await self._insert(model)

    async def get_weather_forecast_snapshot(
        self, weather_snapshot_id: str
    ) -> WeatherForecastSnapshot:
        model = await self.session.get(WeatherForecastSnapshot, weather_snapshot_id)
        if model is None:
            raise PITNotFoundError("WEATHER_FORECAST_SNAPSHOT_NOT_FOUND")
        item = WeatherForecastSnapshotInput.model_validate(
            {
                **{
                    key: getattr(model, key)
                    for key in (
                        "weather_snapshot_id",
                        "provider",
                        "base_id",
                        "location_id",
                        "issued_at",
                        "fetched_at",
                        "known_at",
                        "valid_at",
                        "forecast_horizon_hours",
                        "temperature_min",
                        "temperature_max",
                        "temperature_mean",
                        "precipitation",
                        "relative_humidity",
                        "solar_radiation",
                        "wind_speed",
                        "raw_payload_reference",
                        "raw_payload_hash",
                        "normalized_payload_hash",
                    )
                },
                "payload_hash": model.payload_hash,
            }
        )
        _sha_match(model.payload_hash, item.computed_payload_hash(), "weather_payload")
        return model

    async def visible_weather_forecast_snapshots(
        self, *, weather_snapshot_ids: Iterable[str], forecast_created_at: datetime
    ) -> list[WeatherForecastSnapshot]:
        ids = sorted(set(weather_snapshot_ids))
        if not ids:
            return []
        models = list(
            await self.session.scalars(
                select(WeatherForecastSnapshot).where(
                    WeatherForecastSnapshot.weather_snapshot_id.in_(ids)
                )
            )
        )
        by_id = {model.weather_snapshot_id: model for model in models}
        if set(by_id) != set(ids):
            raise PITIntegrityError("WEATHER_SNAPSHOT_REFERENCE_NOT_FOUND")
        if not all(weather_forecast_visible_at(model, forecast_created_at) for model in models):
            raise PITVisibilityRejected("WEATHER_FORECAST_NOT_VISIBLE")
        return [by_id[item] for item in ids]

    async def add_realized_weather_observation(
        self, item: RealizedWeatherObservationInput
    ) -> RealizedWeatherObservation:
        payload_hash = item.computed_payload_hash()
        if item.payload_hash is not None:
            _sha_match(item.payload_hash, payload_hash, "payload_hash")
        model = RealizedWeatherObservation(
            **item.model_dump(exclude={"payload_hash"}),
            payload_hash=payload_hash,
        )
        return await self._insert(model)

    async def get_realized_weather_observation(
        self, weather_observation_id: str
    ) -> RealizedWeatherObservation:
        model = await self.session.get(RealizedWeatherObservation, weather_observation_id)
        if model is None:
            raise PITNotFoundError("REALIZED_WEATHER_OBSERVATION_NOT_FOUND")
        return model

    async def add_phenology_observation(
        self, item: PhenologyObservationInput
    ) -> PhenologyObservation:
        payload_hash = item.computed_payload_hash()
        if item.payload_hash is not None:
            _sha_match(item.payload_hash, payload_hash, "payload_hash")
        model = PhenologyObservation(
            **item.model_dump(exclude={"payload_hash"}),
            payload_hash=payload_hash,
        )
        return await self._insert(model)

    async def get_phenology_observation(self, observation_id: str) -> PhenologyObservation:
        model = await self.session.get(PhenologyObservation, observation_id)
        if model is None:
            raise PITNotFoundError("PHENOLOGY_OBSERVATION_NOT_FOUND")
        return model

    async def visible_phenology_observations(
        self, *, observation_ids: Iterable[str], forecast_created_at: datetime
    ) -> list[PhenologyObservation]:
        ids = sorted(set(observation_ids))
        if not ids:
            return []
        models = list(
            await self.session.scalars(
                select(PhenologyObservation).where(PhenologyObservation.observation_id.in_(ids))
            )
        )
        by_id = {model.observation_id: model for model in models}
        if set(by_id) != set(ids):
            raise PITIntegrityError("PHENOLOGY_REFERENCE_NOT_FOUND")
        if not all(record_visible_at(model, forecast_created_at) for model in models):
            raise PITVisibilityRejected("PHENOLOGY_NOT_VISIBLE")
        return [by_id[item] for item in ids]

    @staticmethod
    def _validate_input_snapshot(item: ForecastRunSnapshotInput) -> None:
        from backend.app.rolling_backtest.canonical import canonical_json_value

        _sha_match(
            item.input_snapshot_hash,
            _hash_input_snapshot(item.input_snapshot_json),
            "input_snapshot",
        )
        required = {
            "schema_version",
            "canonicalization_policy",
            "request",
            "base_identity",
            "target_season",
            "target_area",
            "area_revision_id",
            "prior_history",
            "weather_snapshot_ids",
            "phenology_observation_ids",
            "model",
            "forecast_mode",
            "coverage",
            "warnings",
            "forecast_created_at",
        }
        if not required.issubset(item.input_snapshot_json):
            raise PITIntegrityError("INPUT_SNAPSHOT_INCOMPLETE")
        snapshot = item.input_snapshot_json
        if snapshot["target_season"] != item.target_season:
            raise PITIntegrityError("INPUT_TARGET_SEASON_MISMATCH")
        if snapshot["area_revision_id"] != item.area_revision_id:
            raise PITIntegrityError("INPUT_AREA_REVISION_MISMATCH")
        if sorted(snapshot["weather_snapshot_ids"]) != sorted(item.weather_snapshot_ids):
            raise PITIntegrityError("INPUT_WEATHER_IDS_MISMATCH")
        if sorted(snapshot["phenology_observation_ids"]) != sorted(item.phenology_observation_ids):
            raise PITIntegrityError("INPUT_PHENOLOGY_IDS_MISMATCH")
        if snapshot["forecast_mode"] != item.forecast_mode:
            raise PITIntegrityError("INPUT_FORECAST_MODE_MISMATCH")
        if snapshot["forecast_created_at"] != canonical_json_value(item.forecast_created_at):
            raise PITIntegrityError("INPUT_FORECAST_CREATED_AT_MISMATCH")
        target_area_value = snapshot["target_area"].get("target_area_mu")
        if target_area_value is None:
            raise PITIntegrityError("INPUT_TARGET_AREA_MISSING")
        if Decimal(str(target_area_value)) != item.target_area_mu:
            raise PITIntegrityError("INPUT_TARGET_AREA_MISMATCH")
        if item.computed_result_hash() != item.result_hash:
            raise PITIntegrityError("RESULT_HASH_MISMATCH")

    async def _validate_forecast_dependencies(self, item: ForecastRunSnapshotInput) -> None:
        area = await self.session.get(AreaRevision, item.area_revision_id)
        if area is None:
            raise PITIntegrityError("AREA_REVISION_REFERENCE_NOT_FOUND")
        if area.base_id != item.base_id:
            raise PITIntegrityError("AREA_REVISION_BASE_MISMATCH")
        if (
            not record_visible_at(area, item.forecast_created_at)
            or _utc(area.effective_from) > _utc(item.forecast_created_at)
            or (
                area.effective_to is not None
                and _utc(area.effective_to) < _utc(item.forecast_created_at)
            )
        ):
            raise PITVisibilityRejected("AREA_REVISION_NOT_VISIBLE")
        weather = await self.visible_weather_forecast_snapshots(
            weather_snapshot_ids=item.weather_snapshot_ids,
            forecast_created_at=item.forecast_created_at,
        )
        if any(snapshot.base_id not in (None, item.base_id) for snapshot in weather):
            raise PITIntegrityError("WEATHER_SNAPSHOT_BASE_MISMATCH")
        phenology = await self.visible_phenology_observations(
            observation_ids=item.phenology_observation_ids,
            forecast_created_at=item.forecast_created_at,
        )
        if any(observation.base_id != item.base_id for observation in phenology):
            raise PITIntegrityError("PHENOLOGY_BASE_MISMATCH")

    @staticmethod
    def _validate_daily(item: ForecastRunSnapshotInput) -> None:
        expected_dates = [
            item.forecast_start_date + timedelta(days=index)
            for index in range((item.forecast_end_date - item.forecast_start_date).days + 1)
        ]
        actual_dates = [row.forecast_date for row in item.daily_curve]
        if actual_dates != expected_dates:
            raise PITIntegrityError("DAILY_FORECAST_DATE_GAP")
        if len(actual_dates) != len(set(actual_dates)):
            raise PITIntegrityError("DUPLICATE_DAILY_FORECAST_DATE")
        if abs(sum((row.normalized_share for row in item.daily_curve), Decimal(0)) - 1) > Decimal(
            "1e-12"
        ):
            raise PITIntegrityError("NORMALIZED_SHARE_SUM_MISMATCH")
        daily_total = sum((row.predicted_quantity_kg for row in item.daily_curve), Decimal(0))
        if not _decimal_close(daily_total, item.predicted_season_total_kg):
            raise PITIntegrityError("DAILY_TOTAL_CONSERVATION_MISMATCH")

    async def save_forecast_run_snapshot(
        self, item: ForecastRunSnapshotInput
    ) -> ForecastRunSnapshot:
        self._validate_input_snapshot(item)
        self._validate_daily(item)
        await self._validate_forecast_dependencies(item)
        existing = await self.session.get(ForecastRunSnapshotModel, item.forecast_run_id)
        if existing is not None:
            if existing.input_snapshot_hash != item.input_snapshot_hash:
                raise PITConflictError("FORECAST_RUN_ID_CONFLICT")
            return await self.get_forecast_run_snapshot(item.forecast_run_id)
        now = datetime.now(UTC)
        try:
            model = ForecastRunSnapshotModel(
                forecast_run_id=item.forecast_run_id,
                forecast_created_at=item.forecast_created_at,
                base_id=item.base_id,
                target_season=item.target_season,
                forecast_start_date=item.forecast_start_date,
                forecast_end_date=item.forecast_end_date,
                target_area_mu=item.target_area_mu,
                forecast_mode=item.forecast_mode,
                model_status=item.model_status,
                total_model_id=item.total_model_id,
                temporal_model_id=item.temporal_model_id,
                model_artifact_hashes=item.model_artifact_hashes,
                prior_history_season=item.prior_history_season,
                prior_history_quantity_kg=item.prior_history_quantity_kg,
                prior_history_coverage_status=item.prior_history_coverage_status,
                prior_history_source_hash=item.prior_history_source_hash,
                prior_history_identity_mapping_hash=item.prior_history_identity_mapping_hash,
                area_revision_id=item.area_revision_id,
                weather_snapshot_ids=sorted(set(item.weather_snapshot_ids)),
                phenology_observation_ids=sorted(set(item.phenology_observation_ids)),
                input_snapshot_json=item.input_snapshot_json,
                input_snapshot_hash=item.input_snapshot_hash,
                predicted_season_total_kg=item.predicted_season_total_kg,
                single_day_peak=item.single_day_peak,
                rolling_7day_peak=item.rolling_7day_peak,
                result_hash=item.result_hash,
                warnings=sorted(set(item.warnings)),
                daily_row_count=len(item.daily_curve),
                created_at=now,
            )
            self.session.add(model)
            await self.session.flush()
            self.session.add_all(
                [
                    ForecastRunSnapshotDaily(
                        forecast_run_id=item.forecast_run_id,
                        row_index=index,
                        forecast_date=row.forecast_date,
                        predicted_quantity_kg=row.predicted_quantity_kg,
                        normalized_share=row.normalized_share,
                    )
                    for index, row in enumerate(item.daily_curve)
                ]
            )
            await self.session.flush()
            return await self.get_forecast_run_snapshot(item.forecast_run_id)
        except PITDataFoundationError:
            raise
        except IntegrityError as exc:
            raise PITConflictError("FORECAST_SNAPSHOT_WRITE_CONFLICT") from exc
        except SQLAlchemyError as exc:
            raise PITWriteFailure("FORECAST_SNAPSHOT_WRITE_FAILED") from exc

    async def get_forecast_run_snapshot(self, forecast_run_id: str) -> ForecastRunSnapshot:
        model = await self.session.get(ForecastRunSnapshotModel, forecast_run_id)
        if model is None:
            raise PITNotFoundError("FORECAST_RUN_SNAPSHOT_NOT_FOUND")
        rows = list(
            await self.session.scalars(
                select(ForecastRunSnapshotDaily)
                .where(ForecastRunSnapshotDaily.forecast_run_id == forecast_run_id)
                .order_by(ForecastRunSnapshotDaily.row_index)
            )
        )
        if len(rows) != model.daily_row_count:
            raise PITIntegrityError("DAILY_ROW_COUNT_MISMATCH")
        daily = [
            ForecastDailySnapshotInput(
                forecast_date=row.forecast_date,
                predicted_quantity_kg=row.predicted_quantity_kg,
                normalized_share=row.normalized_share,
            )
            for row in rows
        ]
        item = ForecastRunSnapshotInput.model_validate(
            {
                "forecast_run_id": model.forecast_run_id,
                "forecast_created_at": model.forecast_created_at,
                "base_id": model.base_id,
                "target_season": model.target_season,
                "forecast_start_date": model.forecast_start_date,
                "forecast_end_date": model.forecast_end_date,
                "target_area_mu": model.target_area_mu,
                "forecast_mode": model.forecast_mode,
                "model_status": model.model_status,
                "total_model_id": model.total_model_id,
                "temporal_model_id": model.temporal_model_id,
                "model_artifact_hashes": model.model_artifact_hashes,
                "prior_history_season": model.prior_history_season,
                "prior_history_quantity_kg": model.prior_history_quantity_kg,
                "prior_history_coverage_status": model.prior_history_coverage_status,
                "prior_history_source_hash": model.prior_history_source_hash,
                "prior_history_identity_mapping_hash": model.prior_history_identity_mapping_hash,
                "area_revision_id": model.area_revision_id,
                "weather_snapshot_ids": model.weather_snapshot_ids,
                "phenology_observation_ids": model.phenology_observation_ids,
                "input_snapshot_json": model.input_snapshot_json,
                "input_snapshot_hash": model.input_snapshot_hash,
                "predicted_season_total_kg": model.predicted_season_total_kg,
                "daily_curve": _daily_payload(daily),
                "single_day_peak": model.single_day_peak,
                "rolling_7day_peak": model.rolling_7day_peak,
                "result_hash": model.result_hash,
                "warnings": model.warnings,
            }
        )
        self._validate_input_snapshot(item)
        self._validate_daily(item)
        return ForecastRunSnapshot(
            **item.model_dump(mode="python"),
            created_at=model.created_at,
        )


def _hash_input_snapshot(snapshot: dict[str, Any]) -> str:
    from backend.app.pit.canonical import hash_payload

    return hash_payload(snapshot)


__all__ = [
    "PITConflictError",
    "PITDataFoundationError",
    "PITDataFoundationRepository",
    "PITIntegrityError",
    "PITNotFoundError",
    "PITVisibilityRejected",
    "PITWriteFailure",
]
