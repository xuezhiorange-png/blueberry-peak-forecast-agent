from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException, localcontext

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.canonical import (
    CORE_FORECAST_AUTHORITY_REQUEST_SCHEMA_VERSION,
    CORE_FORECAST_AUTHORITY_RUN_SCHEMA_VERSION,
    CORE_FORECAST_CODE_AUTHORITY_SCHEMA_VERSION,
    CORE_FORECAST_DATE_BASIS,
    CORE_FORECAST_REQUEST_SCHEMA_VERSION,
    CORE_FORECAST_RUN_SCHEMA_VERSION,
    compute_core_forecast_code_authority_hash,
    compute_core_forecast_input_hash,
    compute_core_forecast_request_hash,
    compute_core_forecast_result_hash,
    compute_daily_curve_hash,
    compute_retention_policy_snapshot_hash,
    core_forecast_code_authority_payload,
)
from backend.app.core_forecast.metrics import compute_core_forecast_metrics
from backend.app.core_forecast.schemas import (
    OUTPUT_QUANTUM,
    QUANTILE_RANK,
    QUANTILES,
    CompleteCoreForecastMetricsResult,
    CompleteDailyMarketableCurveRequest,
    CompleteDailyMarketableCurveResult,
    CompleteDailyMarketableCurveRow,
    CoreForecastCodeAuthority,
    CoreForecastRunSummary,
    ExecuteCoreForecastRunRequest,
    PersistedCoreForecastRun,
    QuantileCoreForecastMetrics,
    RegisterCoreForecastCodeAuthority,
)
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

_FIXED_6_RE = re.compile(r"^(?:0|[1-9]\d*)\.\d{6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_QUANTITIES = (
    "natural_maturity_supply_kg",
    "opening_mature_inventory_kg",
    "available_mature_quantity_kg",
    "mature_inventory_loss_quantity_kg",
    "harvestable_mature_quantity_kg",
    "effective_harvest_capacity_kg",
    "model_harvested_marketable_quantity_kg",
    "closing_mature_inventory_kg",
    "unharvested_backlog_kg",
    "sorting_retention_rate",
    "postharvest_retention_rate",
    "effective_marketable_quantity_kg",
)


class CoreForecastPersistenceError(RuntimeError):
    """Base class for deterministic S4 persistence failures."""


class CoreForecastPersistenceConflictError(CoreForecastPersistenceError):
    """A canonical identity already exists with different content."""


class CoreForecastPersistenceIntegrityError(CoreForecastPersistenceError):
    """Persisted rows cannot be reconstructed into canonical output."""


class CoreForecastRecalculationError(CoreForecastPersistenceError):
    """A rerun request violates the immutable parent contract."""


class CoreForecastWriteFailure(CoreForecastPersistenceError):
    """A write failed without being a deterministic identity conflict."""


def _fixed_db_quantity(value: object, field_name: str) -> str:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise CoreForecastPersistenceIntegrityError(
            f"persisted {field_name} is not a Decimal value"
        )
    if not value.is_finite() or value < 0 or (value.is_signed() and value == 0):
        raise CoreForecastPersistenceIntegrityError(
            f"persisted {field_name} is not finite and non-negative"
        )
    with localcontext() as context:
        context.prec = max(80, len(value.as_tuple().digits) + 20)
        quantized = value.quantize(OUTPUT_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized != value:
        raise CoreForecastPersistenceIntegrityError(
            f"persisted {field_name} is not exactly representable at scale six"
        )
    rendered = format(quantized, "f")
    if _FIXED_6_RE.fullmatch(rendered) is None:
        raise CoreForecastPersistenceIntegrityError(f"persisted {field_name} is malformed")
    return rendered


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _hash(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CoreForecastPersistenceIntegrityError(f"persisted {field_name} is malformed")
    return value


def _metric_schema(model: CoreForecastMetricModel) -> QuantileCoreForecastMetrics:
    return QuantileCoreForecastMetrics(
        forecast_quantile=model.forecast_quantile,
        single_day_peak={
            "date": model.single_day_peak_date,
            "quantity_kg": _fixed_db_quantity(
                model.single_day_peak_quantity_kg, "single_day_peak_quantity_kg"
            ),
            "tie_break": model.single_day_tie_break,
        },
        sustained_7day_peak={
            "start_date": model.sustained_7day_start_date,
            "end_date": model.sustained_7day_end_date,
            "cumulative_quantity_kg": _fixed_db_quantity(
                model.sustained_7day_cumulative_quantity_kg,
                "sustained_7day_cumulative_quantity_kg",
            ),
            "daily_average_kg_per_day": _fixed_db_quantity(
                model.sustained_7day_daily_average_kg_per_day,
                "sustained_7day_daily_average_kg_per_day",
            ),
            "window_days": model.sustained_window_days,
            "metric": model.sustained_metric,
            "date_continuity": model.sustained_date_continuity,
            "tie_break": model.sustained_tie_break,
        },
        season_cumulative_effective_marketable_kg=_fixed_db_quantity(
            model.season_cumulative_effective_marketable_kg,
            "season_cumulative_effective_marketable_kg",
        ),
    )


def _daily_schema(model: CoreForecastDailyRowModel) -> CompleteDailyMarketableCurveRow:
    payload = {
        "date": model.date,
        "forecast_quantile": model.forecast_quantile,
        "farm_id": model.farm_id,
        "subfarm_id": model.subfarm_id,
        "variety_id": model.variety_id,
        "destination_factory_id": model.destination_factory_id,
        **{field: _fixed_db_quantity(getattr(model, field), field) for field in _QUANTITIES},
        "task8_forecast_run_id": model.task8_forecast_run_id,
        "task9_harvest_state_run_id": model.task9_harvest_state_run_id,
        "task8_artifact_hash": _hash(model.task8_artifact_hash, "task8_artifact_hash"),
        "task9_result_hash": _hash(model.task9_result_hash, "task9_result_hash"),
        "marketable_policy_version": model.marketable_policy_version,
        "marketable_policy_hash": _hash(model.marketable_policy_hash, "marketable_policy_hash"),
        "row_hash": _hash(model.row_hash, "row_hash"),
    }
    try:
        return CompleteDailyMarketableCurveRow.model_validate(payload)
    except (ValidationError, ValueError, TypeError) as exc:
        raise CoreForecastPersistenceIntegrityError(
            "persisted daily row schema is invalid"
        ) from exc


def _verify_daily_row_hash(row: CompleteDailyMarketableCurveRow) -> None:
    payload = row.model_dump(mode="json", exclude={"row_hash"})
    expected = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    if expected != row.row_hash:
        raise CoreForecastPersistenceIntegrityError("daily row hash integrity failed")


def _run_summary(model: CoreForecastRunModel) -> CoreForecastRunSummary:
    try:
        return CoreForecastRunSummary(
            run_id=model.id,
            status=model.status,
            run_schema_version=model.run_schema_version,
            request_schema_version=model.request_schema_version,
            date_basis=model.date_basis,
            forecast_input_hash=_hash(model.forecast_input_hash, "forecast_input_hash"),
            request_hash=_hash(model.request_hash, "request_hash"),
            result_hash=_hash(model.result_hash, "result_hash"),
            retention_policy_snapshot_hash=_hash(
                model.retention_policy_snapshot_hash,
                "retention_policy_snapshot_hash",
            ),
            curve_hash=_hash(model.curve_hash, "curve_hash"),
            metrics_hash=_hash(model.metrics_hash, "metrics_hash"),
            code_authority_id=model.code_authority_id,
            code_authority_hash=(
                None
                if model.code_authority_hash is None
                else _hash(model.code_authority_hash, "code_authority_hash")
            ),
            code_authority_available_at=(
                None
                if model.code_authority_available_at is None
                else _aware(model.code_authority_available_at)
            ),
            forecast_effective_cutoff_at=(
                None
                if model.forecast_effective_cutoff_at is None
                else _aware(model.forecast_effective_cutoff_at)
            ),
            rerun_of_run_id=model.rerun_of_run_id,
            forecast_season_id=model.forecast_season_id,
            forecast_season_code=model.forecast_season_code,
            forecast_start_date=model.forecast_start_date,
            forecast_end_date=model.forecast_end_date,
            destination_factory_id=model.destination_factory_id,
            task8_forecast_run_id=model.task8_forecast_run_id,
            task9_harvest_state_run_id=model.task9_harvest_state_run_id,
            daily_row_count=model.daily_row_count,
            metric_row_count=model.metric_row_count,
            created_at=_aware(model.created_at),
            completed_at=_aware(model.completed_at),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise CoreForecastPersistenceIntegrityError("persisted run summary is invalid") from exc


def _row_model(run_id: int, row: CompleteDailyMarketableCurveRow) -> CoreForecastDailyRowModel:
    payload = row.model_dump(mode="python", exclude={"row_hash"})
    for field in _QUANTITIES:
        payload[field] = Decimal(payload[field])
    return CoreForecastDailyRowModel(
        core_forecast_run_id=run_id,
        **payload,
        row_hash=row.row_hash,
    )


def _metric_model(run_id: int, metric: QuantileCoreForecastMetrics) -> CoreForecastMetricModel:
    peak = metric.single_day_peak
    sustained = metric.sustained_7day_peak
    return CoreForecastMetricModel(
        core_forecast_run_id=run_id,
        forecast_quantile=metric.forecast_quantile,
        single_day_peak_date=peak.date,
        single_day_peak_quantity_kg=Decimal(peak.quantity_kg),
        single_day_tie_break=peak.tie_break,
        sustained_7day_start_date=sustained.start_date,
        sustained_7day_end_date=sustained.end_date,
        sustained_7day_cumulative_quantity_kg=Decimal(sustained.cumulative_quantity_kg),
        sustained_7day_daily_average_kg_per_day=Decimal(sustained.daily_average_kg_per_day),
        sustained_window_days=sustained.window_days,
        sustained_metric=sustained.metric,
        sustained_date_continuity=sustained.date_continuity,
        sustained_tie_break=sustained.tie_break,
        season_cumulative_effective_marketable_kg=Decimal(
            metric.season_cumulative_effective_marketable_kg
        ),
    )


def _same_metric(left: QuantileCoreForecastMetrics, right: QuantileCoreForecastMetrics) -> bool:
    return left.model_dump(mode="json") == right.model_dump(mode="json")


def _validate_business_invariants(
    rows: tuple[CompleteDailyMarketableCurveRow, ...],
    request: CompleteDailyMarketableCurveRequest,
) -> None:
    expected_dates = tuple(
        request.forecast_start_date + timedelta(days=offset)
        for offset in range((request.forecast_end_date - request.forecast_start_date).days + 1)
    )
    expected_scopes = {
        (scope.farm_id, scope.subfarm_id, scope.variety_id) for scope in request.scopes
    }
    keys: set[tuple[date, int, int, int, str]] = set()
    by_series: defaultdict[tuple[int, int, int, str], list[CompleteDailyMarketableCurveRow]] = (
        defaultdict(list)
    )
    by_date_quantile: defaultdict[tuple[date, str], set[tuple[int, int, int]]] = defaultdict(set)
    for row in rows:
        if row.destination_factory_id != request.destination_factory_id:
            raise CoreForecastPersistenceIntegrityError("daily row factory scope mismatch")
        key = (row.date, row.farm_id, row.subfarm_id, row.variety_id, row.forecast_quantile)
        if key in keys:
            raise CoreForecastPersistenceIntegrityError("daily row business key is duplicated")
        keys.add(key)
        by_series[(row.farm_id, row.subfarm_id, row.variety_id, row.forecast_quantile)].append(row)
        by_date_quantile[(row.date, row.forecast_quantile)].add(
            (row.farm_id, row.subfarm_id, row.variety_id)
        )
        values = {field: _decimal(getattr(row, field)) for field in _QUANTITIES}
        if values["sorting_retention_rate"] < 0 or values["sorting_retention_rate"] > 1:
            raise CoreForecastPersistenceIntegrityError("sorting retention is outside [0, 1]")
        if values["postharvest_retention_rate"] < 0 or values["postharvest_retention_rate"] > 1:
            raise CoreForecastPersistenceIntegrityError("postharvest retention is outside [0, 1]")
        if values["available_mature_quantity_kg"] != (
            values["opening_mature_inventory_kg"] + values["natural_maturity_supply_kg"]
        ):
            raise CoreForecastPersistenceIntegrityError("available quantity invariant failed")
        if values["harvestable_mature_quantity_kg"] != (
            values["available_mature_quantity_kg"] - values["mature_inventory_loss_quantity_kg"]
        ):
            raise CoreForecastPersistenceIntegrityError("harvestable quantity invariant failed")
        if (
            values["model_harvested_marketable_quantity_kg"]
            > values["harvestable_mature_quantity_kg"]
            or values["model_harvested_marketable_quantity_kg"]
            > values["effective_harvest_capacity_kg"]
        ):
            raise CoreForecastPersistenceIntegrityError("harvest quantity constraint failed")
        if values["closing_mature_inventory_kg"] != (
            values["harvestable_mature_quantity_kg"]
            - values["model_harvested_marketable_quantity_kg"]
        ):
            raise CoreForecastPersistenceIntegrityError("closing inventory invariant failed")
        if values["unharvested_backlog_kg"] != values["closing_mature_inventory_kg"]:
            raise CoreForecastPersistenceIntegrityError("backlog invariant failed")
        with localcontext() as context:
            context.prec = 100
            effective = (
                values["model_harvested_marketable_quantity_kg"]
                * values["sorting_retention_rate"]
                * values["postharvest_retention_rate"]
            ).quantize(OUTPUT_QUANTUM, rounding=ROUND_HALF_EVEN)
        if effective != values["effective_marketable_quantity_kg"]:
            raise CoreForecastPersistenceIntegrityError("effective marketable formula failed")

    if not rows or {row.forecast_quantile for row in rows} != set(QUANTILES):
        raise CoreForecastPersistenceIntegrityError("daily quantile set is incomplete")
    if {row.date for row in rows} != set(expected_dates):
        raise CoreForecastPersistenceIntegrityError("daily date range is incomplete")
    for (current_date, quantile), scopes in by_date_quantile.items():
        if scopes != expected_scopes:
            raise CoreForecastPersistenceIntegrityError(
                f"daily scope set is incomplete for {current_date} {quantile}"
            )
    for series, series_rows in by_series.items():
        ordered = sorted(series_rows, key=lambda row: row.date)
        if tuple(row.date for row in ordered) != expected_dates:
            raise CoreForecastPersistenceIntegrityError(f"daily series is not complete: {series}")
        for index in range(len(ordered) - 1):
            previous = ordered[index]
            current = ordered[index + 1]
            if current.opening_mature_inventory_kg != previous.closing_mature_inventory_kg:
                raise CoreForecastPersistenceIntegrityError("daily continuity invariant failed")


class CoreForecastRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_code_authority(
        self,
        registration: RegisterCoreForecastCodeAuthority,
    ) -> CoreForecastCodeAuthority:
        """Persist a trusted authority before forecast execution.

        This method is deliberately separate from ``save_completed_run``:
        execution may reference an existing authority but never creates one.
        """

        canonical = RegisterCoreForecastCodeAuthority.model_validate(
            registration.model_dump(mode="python")
        )
        authority_hash = compute_core_forecast_code_authority_hash(canonical)
        existing = await self._session.scalar(
            select(CoreForecastCodeAuthorityModel).where(
                CoreForecastCodeAuthorityModel.authority_hash == authority_hash
            )
        )
        if existing is not None:
            return self._code_authority_schema(existing)
        model = CoreForecastCodeAuthorityModel(
            authority_schema_version=CORE_FORECAST_CODE_AUTHORITY_SCHEMA_VERSION,
            source_commit_sha=canonical.source_commit_sha,
            engine_code_hash=canonical.engine_code_hash,
            build_artifact_hash=canonical.build_artifact_hash,
            config_bundle_hash=canonical.config_bundle_hash,
            available_at=canonical.available_at.astimezone(UTC),
            canonical_payload=core_forecast_code_authority_payload(canonical),
            authority_hash=authority_hash,
        )
        self._session.add(model)
        await self._session.flush()
        return self._code_authority_schema(model)

    def _code_authority_schema(
        self,
        model: CoreForecastCodeAuthorityModel,
    ) -> CoreForecastCodeAuthority:
        try:
            authority = CoreForecastCodeAuthority(
                authority_id=model.id,
                authority_schema_version=model.authority_schema_version,
                source_commit_sha=model.source_commit_sha,
                engine_code_hash=_hash(
                    model.engine_code_hash,
                    "code_authority.engine_code_hash",
                ),
                build_artifact_hash=_hash(
                    model.build_artifact_hash,
                    "code_authority.build_artifact_hash",
                ),
                config_bundle_hash=_hash(
                    model.config_bundle_hash,
                    "code_authority.config_bundle_hash",
                ),
                available_at=_aware(model.available_at),
                authority_hash=_hash(
                    model.authority_hash,
                    "code_authority.authority_hash",
                ),
                created_at=_aware(model.created_at),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise CoreForecastPersistenceIntegrityError(
                "persisted code authority is invalid"
            ) from exc
        expected_payload = core_forecast_code_authority_payload(authority)
        if (
            model.canonical_payload != expected_payload
            or compute_core_forecast_code_authority_hash(authority) != authority.authority_hash
        ):
            raise CoreForecastPersistenceIntegrityError(
                "persisted code authority canonical identity does not round-trip"
            )
        return authority

    async def get_code_authority_by_id(
        self,
        authority_id: int,
    ) -> CoreForecastCodeAuthority | None:
        model = await self._session.get(CoreForecastCodeAuthorityModel, authority_id)
        return None if model is None else self._code_authority_schema(model)

    async def save_completed_run(
        self,
        *,
        request: ExecuteCoreForecastRunRequest,
        forecast_input_hash: str,
        request_hash: str,
        result_hash: str,
        retention_policy_snapshot_hash: str,
        curve: CompleteDailyMarketableCurveResult,
        metrics: CompleteCoreForecastMetricsResult,
        rerun_of_run_id: int | None,
        code_authority: CoreForecastCodeAuthority | None = None,
    ) -> PersistedCoreForecastRun:
        if (request.code_authority_id is None) != (code_authority is None):
            raise CoreForecastPersistenceIntegrityError(
                "request and persisted code authority must be coupled"
            )
        if code_authority is not None and request.code_authority_id != code_authority.authority_id:
            raise CoreForecastPersistenceIntegrityError(
                "request references a different code authority"
            )
        if code_authority is not None and request.forecast_effective_cutoff_at is None:
            raise CoreForecastPersistenceIntegrityError(
                "authority-bound run requires the persisted Task 9 forecast cutoff"
            )
        existing = await self.get_run_by_request_hash(request_hash)
        if existing is not None:
            if self._matches_existing(
                existing,
                request=request,
                forecast_input_hash=forecast_input_hash,
                request_hash=request_hash,
                result_hash=result_hash,
                retention_policy_snapshot_hash=retention_policy_snapshot_hash,
                curve=curve,
                metrics=metrics,
                rerun_of_run_id=rerun_of_run_id,
                code_authority=code_authority,
            ):
                return existing
            raise CoreForecastPersistenceConflictError(
                "request hash already exists with different canonical content"
            )

        if curve.status != "COMPLETED" or metrics.status != "COMPLETED":
            raise CoreForecastWriteFailure("only completed curve and metrics may be persisted")
        now = datetime.now(UTC)
        if (
            code_authority is not None
            and request.forecast_effective_cutoff_at is not None
            and code_authority.available_at > request.forecast_effective_cutoff_at
        ):
            raise CoreForecastPersistenceIntegrityError(
                "code authority is not available at the persisted Task 9 cutoff"
            )
        first_row = curve.rows[0]
        try:
            async with self._session.begin_nested():
                model = CoreForecastRunModel(
                    status="completed",
                    run_schema_version=(
                        CORE_FORECAST_AUTHORITY_RUN_SCHEMA_VERSION
                        if code_authority is not None
                        else CORE_FORECAST_RUN_SCHEMA_VERSION
                    ),
                    request_schema_version=(
                        CORE_FORECAST_AUTHORITY_REQUEST_SCHEMA_VERSION
                        if code_authority is not None
                        else CORE_FORECAST_REQUEST_SCHEMA_VERSION
                    ),
                    date_basis=CORE_FORECAST_DATE_BASIS,
                    forecast_input_hash=forecast_input_hash,
                    request_hash=request_hash,
                    result_hash=result_hash,
                    retention_policy_snapshot_hash=retention_policy_snapshot_hash,
                    curve_hash=curve.curve_hash,
                    metrics_hash=metrics.metrics_hash,
                    code_authority_id=(
                        code_authority.authority_id if code_authority is not None else None
                    ),
                    code_authority_hash=(
                        code_authority.authority_hash if code_authority is not None else None
                    ),
                    code_authority_available_at=(
                        code_authority.available_at if code_authority is not None else None
                    ),
                    forecast_effective_cutoff_at=(
                        request.forecast_effective_cutoff_at if code_authority is not None else None
                    ),
                    request_snapshot=request.model_dump(mode="json", exclude_none=True),
                    forecast_season_id=request.curve_request.forecast_season_id,
                    forecast_season_code=request.curve_request.forecast_season_code,
                    forecast_start_date=request.curve_request.forecast_start_date,
                    forecast_end_date=request.curve_request.forecast_end_date,
                    destination_factory_id=request.curve_request.destination_factory_id,
                    task8_forecast_run_id=request.curve_request.task8_forecast_run_id,
                    task8_artifact_hash=first_row.task8_artifact_hash,
                    task9_harvest_state_run_id=request.curve_request.task9_harvest_state_run_id,
                    task9_result_hash=first_row.task9_result_hash,
                    rerun_of_run_id=rerun_of_run_id,
                    daily_row_count=len(curve.rows),
                    metric_row_count=len(metrics.metrics),
                    created_at=now,
                    completed_at=now,
                )
                self._session.add(model)
                await self._session.flush()
                self._session.add_all([_row_model(model.id, row) for row in curve.rows])
                self._session.add_all([_metric_model(model.id, item) for item in metrics.metrics])
                await self._session.flush()
                run_id = model.id
        except IntegrityError as exc:
            existing = await self.get_run_by_request_hash(request_hash)
            if existing is not None and self._matches_existing(
                existing,
                request=request,
                forecast_input_hash=forecast_input_hash,
                request_hash=request_hash,
                result_hash=result_hash,
                retention_policy_snapshot_hash=retention_policy_snapshot_hash,
                curve=curve,
                metrics=metrics,
                rerun_of_run_id=rerun_of_run_id,
                code_authority=code_authority,
            ):
                return existing
            raise CoreForecastPersistenceConflictError(
                "canonical persistence identity conflict"
            ) from exc
        except CoreForecastPersistenceError:
            raise
        except (ValueError, TypeError, DecimalException, OverflowError) as exc:
            raise CoreForecastWriteFailure("core forecast write failed") from exc

        persisted = await self.load_complete_run(run_id)
        if persisted is None:
            raise CoreForecastPersistenceIntegrityError("saved run could not be reloaded")
        return persisted

    @staticmethod
    def _matches_existing(
        existing: PersistedCoreForecastRun,
        *,
        request: ExecuteCoreForecastRunRequest,
        forecast_input_hash: str,
        request_hash: str,
        result_hash: str,
        retention_policy_snapshot_hash: str,
        curve: CompleteDailyMarketableCurveResult,
        metrics: CompleteCoreForecastMetricsResult,
        rerun_of_run_id: int | None,
        code_authority: CoreForecastCodeAuthority | None,
    ) -> bool:
        return (
            existing.request == request
            and existing.run.forecast_input_hash == forecast_input_hash
            and existing.run.request_hash == request_hash
            and existing.run.result_hash == result_hash
            and existing.run.retention_policy_snapshot_hash == retention_policy_snapshot_hash
            and existing.run.rerun_of_run_id == rerun_of_run_id
            and existing.code_authority == code_authority
            and existing.daily_curve.model_dump(mode="json") == curve.model_dump(mode="json")
            and existing.metrics.model_dump(mode="json") == metrics.model_dump(mode="json")
        )

    async def get_run_by_id(self, run_id: int) -> PersistedCoreForecastRun | None:
        model = await self._session.get(CoreForecastRunModel, run_id)
        return None if model is None else await self._hydrate(model)

    async def get_run_by_request_hash(self, request_hash: str) -> PersistedCoreForecastRun | None:
        model = await self._session.scalar(
            select(CoreForecastRunModel).where(CoreForecastRunModel.request_hash == request_hash)
        )
        return None if model is None else await self._hydrate(model)

    async def get_run_by_result_hash(self, result_hash: str) -> PersistedCoreForecastRun | None:
        model = await self._session.scalar(
            select(CoreForecastRunModel).where(CoreForecastRunModel.result_hash == result_hash)
        )
        return None if model is None else await self._hydrate(model)

    async def list_recent_runs(self, *, limit: int = 100) -> tuple[CoreForecastRunSummary, ...]:
        if limit <= 0 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        models = await self._session.scalars(
            select(CoreForecastRunModel)
            .order_by(CoreForecastRunModel.created_at.desc(), CoreForecastRunModel.id.desc())
            .limit(limit)
        )
        return tuple(_run_summary(model) for model in models)

    async def list_daily_rows(self, run_id: int) -> tuple[CompleteDailyMarketableCurveRow, ...]:
        models = await self._session.scalars(
            select(CoreForecastDailyRowModel)
            .where(CoreForecastDailyRowModel.core_forecast_run_id == run_id)
            .order_by(
                CoreForecastDailyRowModel.date.asc(),
                CoreForecastDailyRowModel.farm_id.asc(),
                CoreForecastDailyRowModel.subfarm_id.asc(),
                CoreForecastDailyRowModel.variety_id.asc(),
                CoreForecastDailyRowModel.forecast_quantile.asc(),
                CoreForecastDailyRowModel.id.asc(),
            )
        )
        return tuple(_daily_schema(model) for model in models)

    async def list_metrics(self, run_id: int) -> tuple[QuantileCoreForecastMetrics, ...]:
        models = await self._session.scalars(
            select(CoreForecastMetricModel)
            .where(CoreForecastMetricModel.core_forecast_run_id == run_id)
            .order_by(CoreForecastMetricModel.forecast_quantile.asc())
        )
        metrics = tuple(_metric_schema(model) for model in models)
        return tuple(sorted(metrics, key=lambda item: QUANTILE_RANK[item.forecast_quantile]))

    async def load_complete_run(self, run_id: int) -> PersistedCoreForecastRun | None:
        model = await self._session.get(CoreForecastRunModel, run_id)
        return None if model is None else await self._hydrate(model)

    async def _hydrate(self, model: CoreForecastRunModel) -> PersistedCoreForecastRun:
        try:
            summary = _run_summary(model)
            request = ExecuteCoreForecastRunRequest.model_validate(model.request_snapshot)
            code_authority = (
                None
                if summary.code_authority_id is None
                else await self.get_code_authority_by_id(summary.code_authority_id)
            )
            if summary.code_authority_id is not None and code_authority is None:
                raise CoreForecastPersistenceIntegrityError("referenced code authority is missing")
            if code_authority is not None and (
                request.code_authority_id != code_authority.authority_id
                or summary.code_authority_hash != code_authority.authority_hash
                or summary.code_authority_available_at != code_authority.available_at
                or summary.forecast_effective_cutoff_at is None
                or request.forecast_effective_cutoff_at != summary.forecast_effective_cutoff_at
                or code_authority.available_at > summary.forecast_effective_cutoff_at
            ):
                raise CoreForecastPersistenceIntegrityError(
                    "run code authority identity or availability mismatch"
                )
            curve_request = request.curve_request
            policy_hash = compute_retention_policy_snapshot_hash(request.retention_policy)
            input_hash = compute_core_forecast_input_hash(
                curve_request,
                request.retention_policy,
                code_authority=code_authority,
                task9_authority_result_hash=(
                    model.task9_result_hash if code_authority is not None else None
                ),
                forecast_effective_cutoff_at=summary.forecast_effective_cutoff_at,
            )
            parent_request_hash = None
            if code_authority is not None and request.rerun_of_run_id is not None:
                parent = await self.get_run_by_id(request.rerun_of_run_id)
                if parent is None:
                    raise CoreForecastPersistenceIntegrityError(
                        "authority-bound rerun parent is missing"
                    )
                parent_request_hash = parent.run.request_hash
            request_hash = compute_core_forecast_request_hash(
                input_hash,
                request.rerun_of_run_id,
                authority_bound=code_authority is not None,
                rerun_of_request_hash=parent_request_hash,
            )
            if policy_hash != summary.retention_policy_snapshot_hash:
                raise CoreForecastPersistenceIntegrityError("retention policy hash mismatch")
            if input_hash != summary.forecast_input_hash or request_hash != summary.request_hash:
                raise CoreForecastPersistenceIntegrityError("request hash integrity failed")
            if (
                summary.forecast_season_id != curve_request.forecast_season_id
                or summary.forecast_season_code != curve_request.forecast_season_code
                or summary.forecast_start_date != curve_request.forecast_start_date
                or summary.forecast_end_date != curve_request.forecast_end_date
                or summary.destination_factory_id != curve_request.destination_factory_id
                or summary.task8_forecast_run_id != curve_request.task8_forecast_run_id
                or summary.task9_harvest_state_run_id != curve_request.task9_harvest_state_run_id
                or summary.rerun_of_run_id != request.rerun_of_run_id
            ):
                raise CoreForecastPersistenceIntegrityError(
                    "run lineage columns disagree with request"
                )

            rows = await self.list_daily_rows(model.id)
            if len(rows) != summary.daily_row_count:
                raise CoreForecastPersistenceIntegrityError("daily row count integrity failed")
            for row in rows:
                _verify_daily_row_hash(row)
            if rows:
                if any(
                    row.task8_forecast_run_id != summary.task8_forecast_run_id
                    or row.task9_harvest_state_run_id != summary.task9_harvest_state_run_id
                    for row in rows
                ):
                    raise CoreForecastPersistenceIntegrityError("daily lineage row mismatch")
                if any(row.task8_artifact_hash != model.task8_artifact_hash for row in rows):
                    raise CoreForecastPersistenceIntegrityError("Task 8 artifact hash mismatch")
                if any(row.task9_result_hash != model.task9_result_hash for row in rows):
                    raise CoreForecastPersistenceIntegrityError("Task 9 result hash mismatch")
            _validate_business_invariants(rows, curve_request)
            curve_hash = compute_daily_curve_hash(rows)
            if curve_hash != summary.curve_hash:
                raise CoreForecastPersistenceIntegrityError("curve hash integrity failed")
            curve = CompleteDailyMarketableCurveResult(
                status="COMPLETED",
                rows=rows,
                curve_hash=curve_hash,
                blockers=(),
            )
            metrics = compute_core_forecast_metrics(daily_curve=curve)
            if metrics.status != "COMPLETED" or metrics.metrics_hash != summary.metrics_hash:
                raise CoreForecastPersistenceIntegrityError("metrics integrity failed")
            stored_metrics = await self.list_metrics(model.id)
            if len(stored_metrics) != summary.metric_row_count:
                raise CoreForecastPersistenceIntegrityError("metric row count integrity failed")
            if tuple(item.forecast_quantile for item in stored_metrics) != QUANTILES:
                raise CoreForecastPersistenceIntegrityError("metric quantile order is invalid")
            if any(
                not _same_metric(left, right)
                for left, right in zip(stored_metrics, metrics.metrics, strict=True)
            ):
                raise CoreForecastPersistenceIntegrityError("metric row payload mismatch")
            result_hash = compute_core_forecast_result_hash(
                request_hash=summary.request_hash,
                forecast_input_hash=summary.forecast_input_hash,
                curve_hash=summary.curve_hash,
                metrics_hash=summary.metrics_hash,
                daily_row_count=len(rows),
                metric_row_count=len(stored_metrics),
                authority_bound=code_authority is not None,
                forecast_effective_cutoff_at=summary.forecast_effective_cutoff_at,
            )
            if result_hash != summary.result_hash:
                raise CoreForecastPersistenceIntegrityError("result hash integrity failed")
            return PersistedCoreForecastRun(
                run=summary,
                request=request,
                daily_curve=curve,
                metrics=metrics,
                code_authority=code_authority,
            )
        except CoreForecastPersistenceError:
            raise
        except (ValidationError, ValueError, TypeError, DecimalException, OverflowError) as exc:
            raise CoreForecastPersistenceIntegrityError(
                "persisted run failed integrity validation"
            ) from exc
