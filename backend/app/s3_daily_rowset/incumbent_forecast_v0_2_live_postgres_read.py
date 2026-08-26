"""S3-A2 incumbent forecast V0.2 live postgres read from frozen bindable table."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
    bindable_table_names,
)

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

SessionProvider = Callable[[], Session | None]

_session_provider: SessionProvider | None = None


def set_v0_2_live_postgres_session_provider(provider: SessionProvider | None) -> None:
    global _session_provider
    _session_provider = provider


def clear_v0_2_live_postgres_session_provider() -> None:
    set_v0_2_live_postgres_session_provider(None)


def read_bindable_replay_identity_rows() -> tuple[IncumbentForecastArtifactEntry, ...]:
    bindable_names = bindable_table_names()
    if bindable_names != (FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,):
        return ()
    if _session_provider is None:
        return ()
    try:
        session = _session_provider()
    except Exception:
        return ()
    if session is None:
        return ()
    try:
        return _read_rows_from_session(session)
    except Exception:
        return ()


def _read_rows_from_session(session: Session) -> tuple[IncumbentForecastArtifactEntry, ...]:
    bind = session.get_bind()
    if bind is None:
        return ()
    inspector = sa.inspect(bind)
    if FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME not in inspector.get_table_names():
        return ()
    column_names = {
        column["name"]
        for column in inspector.get_columns(FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME)
    }
    if not all(name in column_names for name in GRAIN_COLUMNS):
        return ()
    if any(
        any(forbidden in name for forbidden in FORBIDDEN_COLUMN_SUBSTRINGS) for name in column_names
    ):
        return ()

    metadata = sa.MetaData()
    table = sa.Table(
        FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
        metadata,
        autoload_with=bind,
    )
    statement = sa.select(
        table.c.forecast_cutoff_at,
        table.c.model_id,
        table.c.forecast_quantile,
    )
    rows = session.execute(statement).all()
    if not rows:
        return ()

    entries: list[IncumbentForecastArtifactEntry] = []
    dialect_name = bind.dialect.name
    for cutoff, model_id, forecast_quantile in rows:
        if not isinstance(cutoff, datetime):
            return ()
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            if dialect_name == "sqlite":
                cutoff = cutoff.replace(tzinfo=UTC)
            else:
                return ()
        if not model_id or not forecast_quantile:
            return ()
        entries.append(
            IncumbentForecastArtifactEntry(
                model_id=str(model_id),
                forecast_cutoff_at=cutoff,
                forecast_quantile=str(forecast_quantile),
            )
        )
    return tuple(entries)
