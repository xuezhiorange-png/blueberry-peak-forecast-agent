"""S3-A daily rowset materialization orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.s3_daily_rowset.actuals import (
    S2ActualsSourcePort,
    window_contains_test_partition,
)
from backend.app.s3_daily_rowset.exclusion import is_cell_level_excluded
from backend.app.s3_daily_rowset.forecast_port import (
    ForecastAvailability,
    IncumbentDailyCurveProvider,
)
from backend.app.s3_daily_rowset.identity import compute_rowset_identity_sha256
from backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source import (
    LiveAcceptedS2TrainValActualsBindingEnvelope,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DailyRow,
    DailyRowsetResult,
    DailyRowStatus,
    DatasetIdentity,
    DatasetIdentityMismatchError,
    EvaluationInstanceCell,
    HorizonWindowRequest,
    MaterializationOutcome,
    ReasonCode,
    WindowKind,
)
from backend.app.s3_daily_rowset.window import (
    complete_season_window_dates,
    derive_season_year,
    expected_forecast_target_date,
    horizon_window_dates,
    window_within_default_month_scope,
)


@dataclass(frozen=True, slots=True)
class DailyRowsetMaterializerWithLiveActualsOutcome:
    materializer: DailyRowsetMaterializerService | None
    binding_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope


def build_daily_rowset_materializer_with_live_actuals(
    forecast_provider: IncumbentDailyCurveProvider,
    *,
    dataset_identity: DatasetIdentity | None = None,
) -> DailyRowsetMaterializerWithLiveActualsOutcome:
    from backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source import (
        bind_live_accepted_s2_train_val_actuals_source,
    )

    bind_outcome = bind_live_accepted_s2_train_val_actuals_source()
    if not bind_outcome.envelope.bound or bind_outcome.actuals_source is None:
        return DailyRowsetMaterializerWithLiveActualsOutcome(
            materializer=None,
            binding_envelope=bind_outcome.envelope,
        )
    identity = dataset_identity or DatasetIdentity(
        dataset_id=EXPECTED_DATASET_ID,
        dataset_version=EXPECTED_DATASET_VERSION,
        materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    )
    return DailyRowsetMaterializerWithLiveActualsOutcome(
        materializer=DailyRowsetMaterializerService(
            dataset_identity=identity,
            actuals_source=bind_outcome.actuals_source,
            forecast_provider=forecast_provider,
        ),
        binding_envelope=bind_outcome.envelope,
    )


@dataclass
class DailyRowsetMaterializerService:
    dataset_identity: DatasetIdentity
    actuals_source: S2ActualsSourcePort
    forecast_provider: IncumbentDailyCurveProvider

    def __post_init__(self) -> None:
        self._validate_dataset_identity()

    def _validate_dataset_identity(self) -> None:
        identity = self.dataset_identity
        if (
            identity.dataset_id != EXPECTED_DATASET_ID
            or identity.dataset_version != EXPECTED_DATASET_VERSION
            or identity.materialized_dataset_identity_sha256
            != EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
        ):
            raise DatasetIdentityMismatchError(
                "S2 materialized dataset identity does not match bound authority"
            )

    def materialize_horizon_window(
        self,
        cell: EvaluationInstanceCell,
        request: HorizonWindowRequest,
    ) -> DailyRowsetResult:
        if is_cell_level_excluded(cell):
            return self._cell_excluded_result(WindowKind.HORIZON, request.evaluation_window_days)

        window_dates = horizon_window_dates(cell.forecast_cutoff_at, request.evaluation_window_days)
        if not window_within_default_month_scope(window_dates, cell.season):
            return self._cell_excluded_result(WindowKind.HORIZON, request.evaluation_window_days)

        if request.forecast_target_date is not None:
            required_target = expected_forecast_target_date(
                cell.forecast_cutoff_at,
                request.evaluation_window_days,
            )
            if request.forecast_target_date != required_target:
                return DailyRowsetResult(
                    outcome=MaterializationOutcome.NOT_COMPUTABLE,
                    reason_code=ReasonCode.TARGET_DATE_CUTOFF_HORIZON_MISMATCH,
                    window_kind=WindowKind.HORIZON,
                    evaluation_window_days=request.evaluation_window_days,
                )

        return self._materialize_window(
            cell=cell,
            window_kind=WindowKind.HORIZON,
            window_dates=window_dates,
            evaluation_window_days=request.evaluation_window_days,
        )

    def materialize_complete_season_window(
        self,
        cell: EvaluationInstanceCell,
    ) -> DailyRowsetResult:
        if is_cell_level_excluded(cell):
            return self._cell_excluded_result(WindowKind.COMPLETE_SEASON, None)

        if derive_season_year(cell.season) is None:
            return DailyRowsetResult(
                outcome=MaterializationOutcome.NOT_COMPUTABLE,
                reason_code=ReasonCode.SEASON_YEAR_DERIVATION_FAILURE,
                window_kind=WindowKind.COMPLETE_SEASON,
            )

        window_dates = complete_season_window_dates(cell.season)
        return self._materialize_window(
            cell=cell,
            window_kind=WindowKind.COMPLETE_SEASON,
            window_dates=window_dates,
            evaluation_window_days=None,
        )

    def _cell_excluded_result(
        self,
        window_kind: WindowKind,
        evaluation_window_days: int | None,
    ) -> DailyRowsetResult:
        return DailyRowsetResult(
            outcome=MaterializationOutcome.CELL_EXCLUDED,
            window_kind=window_kind,
            evaluation_window_days=evaluation_window_days,
        )

    def _materialize_window(
        self,
        *,
        cell: EvaluationInstanceCell,
        window_kind: WindowKind,
        window_dates: tuple[date, ...],
        evaluation_window_days: int | None,
    ) -> DailyRowsetResult:
        if window_contains_test_partition(window_dates):
            return DailyRowsetResult(
                outcome=MaterializationOutcome.REJECTED,
                reason_code=ReasonCode.TEST_PARTITION_NOT_ALLOWED,
                window_kind=window_kind,
                evaluation_window_days=evaluation_window_days,
                window_start_date=window_dates[0],
                window_end_date=window_dates[-1],
            )

        daily_rows: list[DailyRow] = []
        for business_date in window_dates:
            actual_lookup = self.actuals_source.lookup_actual(cell, business_date)
            forecast_lookup = self.forecast_provider.forecast_kg_for_day(
                cell,
                business_date=business_date,
            )
            daily_rows.append(
                DailyRow(
                    business_date=business_date,
                    daily_row_status=actual_lookup.daily_row_status,
                    actual_harvest_quantity_kg=actual_lookup.actual_harvest_quantity_kg,
                    forecast_harvest_quantity_kg=forecast_lookup.forecast_harvest_quantity_kg,
                )
            )

        if any(
            row.daily_row_status in {DailyRowStatus.UNKNOWN, DailyRowStatus.EXCLUDED}
            for row in daily_rows
        ):
            return DailyRowsetResult(
                outcome=MaterializationOutcome.REJECTED,
                reason_code=ReasonCode.WINDOW_REJECTED_UNKNOWN_OR_EXCLUDED_DAY,
                window_kind=window_kind,
                evaluation_window_days=evaluation_window_days,
                window_start_date=window_dates[0],
                window_end_date=window_dates[-1],
                daily_rows=tuple(daily_rows),
            )

        if any(
            self.forecast_provider.forecast_kg_for_day(
                cell,
                business_date=row.business_date,
            ).availability
            == ForecastAvailability.UNAVAILABLE
            for row in daily_rows
        ):
            return DailyRowsetResult(
                outcome=MaterializationOutcome.REJECTED,
                reason_code=ReasonCode.FORECAST_UNAVAILABLE,
                window_kind=window_kind,
                evaluation_window_days=evaluation_window_days,
                window_start_date=window_dates[0],
                window_end_date=window_dates[-1],
                daily_rows=tuple(daily_rows),
            )

        identity_hash = compute_rowset_identity_sha256(
            dataset_identity=self.dataset_identity,
            cell=cell,
            window_kind=window_kind,
            evaluation_window_days=evaluation_window_days,
            window_start_date=window_dates[0].isoformat(),
            window_end_date=window_dates[-1].isoformat(),
            daily_rows=tuple(daily_rows),
        )
        return DailyRowsetResult(
            outcome=MaterializationOutcome.SUCCESS,
            window_kind=window_kind,
            evaluation_window_days=evaluation_window_days,
            window_start_date=window_dates[0],
            window_end_date=window_dates[-1],
            daily_rows=tuple(daily_rows),
            rowset_identity_sha256=identity_hash,
            sustained_peak_pass_allowed=False,
            current_s3_daily_rowset_completeness_verified=False,
        )
