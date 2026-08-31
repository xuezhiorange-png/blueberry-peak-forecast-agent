"""Lawful incumbent forecast replay-identity origin from frozen calendar policy.

Forecast cutoffs are not derived from SOURCE_002 harvest dates. Grains are the
bound rolling-backtest default nodes (or the last legal fallback before TEST)
crossed with the V0.2 incumbent authority model id and P50/P80/P90. No tonnes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.forecast_quality.enums import SupportedQuantile
from backend.app.rolling_backtest.calendar import resolve_default_node_dates
from backend.app.s2_materialized_dataset.lane_d.partitions import VALIDATION_END
from backend.app.s3_daily_rowset.actuals import (
    is_evaluation_partition_allowed,
    window_contains_test_partition,
)
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
    bindable_table_names,
)
from backend.app.s3_daily_rowset.registry import V0_3_S3_FORECASTS_AUTHORITY
from backend.app.s3_daily_rowset.schemas import HORIZON_DAYS
from backend.app.s3_daily_rowset.window import (
    DEFAULT_IN_SEASON_MONTHS,
    SHANGHAI,
    cutoff_business_date,
    horizon_window_dates,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True
ORIGIN_MODEL_ID = V0_3_S3_FORECASTS_AUTHORITY
ORIGIN_QUANTILES: tuple[str, ...] = tuple(quantile.value for quantile in SupportedQuantile)
GRAIN_COLUMNS = ("forecast_cutoff_at", "model_id", "forecast_quantile")
FORBIDDEN_COLUMN_SUBSTRINGS = (
    "kg",
    "tonnes",
    "weight",
    "quantity",
    "forecast_value",
    "daily_curve",
    "harvest_business_date",
    "catalog_cell",
    "alignment_identity",
)


class ReplayIdentityOriginLandingReasonCode(StrEnum):
    LANDED = "LANDED"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    NO_ORIGIN_ENTRIES = "NO_ORIGIN_ENTRIES"
    TABLE_MISSING = "TABLE_MISSING"
    NOT_BINDABLE_TABLE = "NOT_BINDABLE_TABLE"
    FORBIDDEN_COLUMNS = "FORBIDDEN_COLUMNS"
    INSERT_FAILED = "INSERT_FAILED"


@dataclass(frozen=True, slots=True)
class ReplayIdentityOriginLandingResult:
    reason_code: ReplayIdentityOriginLandingReasonCode
    attempted: int
    inserted: int
    skipped: int
    table_row_count: int | None
    landed: bool


def shanghai_midnight(day: date) -> datetime:
    if isinstance(day, datetime):
        day = day.astimezone(SHANGHAI).date()
    return datetime.combine(day, time.min, tzinfo=SHANGHAI)


def last_legal_cutoff_before_test() -> datetime:
    return shanghai_midnight(VALIDATION_END - timedelta(days=max(HORIZON_DAYS)))


def cutoff_is_legal_for_accepted_s2_window(forecast_cutoff_at: datetime) -> bool:
    cutoff_date = cutoff_business_date(forecast_cutoff_at)
    if cutoff_date.month not in DEFAULT_IN_SEASON_MONTHS:
        return False
    if not is_evaluation_partition_allowed(cutoff_date):
        return False
    for horizon_days in sorted(HORIZON_DAYS):
        window_dates = horizon_window_dates(forecast_cutoff_at, horizon_days)
        if window_contains_test_partition(window_dates):
            return False
        if any(day.month not in DEFAULT_IN_SEASON_MONTHS for day in window_dates):
            return False
    return True


def default_calendar_cutoff_instants() -> tuple[datetime, ...]:
    season_year = VALIDATION_END.year
    return tuple(
        shanghai_midnight(node.as_of_local_date) for node in resolve_default_node_dates(season_year)
    )


def legal_policy_cutoff_instants() -> tuple[datetime, ...]:
    legal = tuple(
        cutoff
        for cutoff in default_calendar_cutoff_instants()
        if cutoff_is_legal_for_accepted_s2_window(cutoff)
    )
    if legal:
        return legal
    fallback = last_legal_cutoff_before_test()
    if cutoff_is_legal_for_accepted_s2_window(fallback):
        return (fallback,)
    return ()


def replay_identity_origin_entries() -> tuple[IncumbentForecastArtifactEntry, ...]:
    entries = [
        IncumbentForecastArtifactEntry(
            model_id=ORIGIN_MODEL_ID,
            forecast_cutoff_at=cutoff,
            forecast_quantile=quantile,
        )
        for cutoff in legal_policy_cutoff_instants()
        for quantile in ORIGIN_QUANTILES
    ]
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                entry.model_id,
                entry.forecast_cutoff_at.isoformat(),
                entry.forecast_quantile,
            ),
        )
    )


def land_replay_identity_origin_into_sync_session(
    session: Session,
    entries: tuple[IncumbentForecastArtifactEntry, ...] | None = None,
) -> ReplayIdentityOriginLandingResult:
    origin_entries = entries if entries is not None else replay_identity_origin_entries()
    if not origin_entries:
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.NO_ORIGIN_ENTRIES,
            attempted=0,
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )
    if bindable_table_names() != (FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,):
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.NOT_BINDABLE_TABLE,
            attempted=len(origin_entries),
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )
    try:
        return _land_into_session(session, origin_entries)
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.INSERT_FAILED,
            attempted=len(origin_entries),
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )


def _land_into_session(
    session: Session,
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...],
) -> ReplayIdentityOriginLandingResult:
    bind = session.get_bind()
    if bind is None:
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.INSERT_FAILED,
            attempted=len(origin_entries),
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )
    inspector = sa.inspect(bind)
    if FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME not in inspector.get_table_names():
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.TABLE_MISSING,
            attempted=len(origin_entries),
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )
    column_names = {
        column["name"]
        for column in inspector.get_columns(FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME)
    }
    if not all(name in column_names for name in GRAIN_COLUMNS):
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.FORBIDDEN_COLUMNS,
            attempted=len(origin_entries),
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )
    if any(
        any(forbidden in name for forbidden in FORBIDDEN_COLUMN_SUBSTRINGS) for name in column_names
    ):
        return ReplayIdentityOriginLandingResult(
            reason_code=ReplayIdentityOriginLandingReasonCode.FORBIDDEN_COLUMNS,
            attempted=len(origin_entries),
            inserted=0,
            skipped=0,
            table_row_count=None,
            landed=False,
        )

    metadata = sa.MetaData()
    table = sa.Table(
        FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
        metadata,
        autoload_with=bind,
    )
    before = session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
    values = [
        {
            "forecast_cutoff_at": entry.forecast_cutoff_at,
            "model_id": entry.model_id,
            "forecast_quantile": entry.forecast_quantile,
        }
        for entry in origin_entries
    ]
    statement = _insert_do_nothing(table, bind.dialect.name, values)
    session.execute(statement)
    session.commit()
    after = session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
    inserted = int(after) - int(before)
    skipped = len(origin_entries) - inserted
    if inserted > 0:
        reason = ReplayIdentityOriginLandingReasonCode.LANDED
    else:
        reason = ReplayIdentityOriginLandingReasonCode.ALREADY_PRESENT
    return ReplayIdentityOriginLandingResult(
        reason_code=reason,
        attempted=len(origin_entries),
        inserted=inserted,
        skipped=skipped,
        table_row_count=int(after),
        landed=int(after) > 0,
    )


def _insert_do_nothing(
    table: sa.Table,
    dialect_name: str,
    values: list[dict[str, object]],
) -> sa.Insert:
    index_elements = list(GRAIN_COLUMNS)
    if dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return (
            sqlite_insert(table)
            .values(values)
            .on_conflict_do_nothing(index_elements=index_elements)
        )
    from sqlalchemy.dialects.postgresql import insert as postgres_insert

    return (
        postgres_insert(table).values(values).on_conflict_do_nothing(index_elements=index_elements)
    )
