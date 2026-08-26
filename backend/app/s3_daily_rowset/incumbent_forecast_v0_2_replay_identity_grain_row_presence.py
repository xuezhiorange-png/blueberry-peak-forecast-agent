"""S3-A2 incumbent forecast V0.2 replay-identity grain row presence fail-closed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

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


@dataclass(frozen=True, slots=True)
class ReviewedGrainIdentity:
    forecast_cutoff_at: datetime
    model_id: str
    forecast_quantile: str


ReviewedGrainIdentitySetProvider = Callable[[], tuple[ReviewedGrainIdentity, ...] | None]
SessionProvider = Callable[[], Session | None]

_reviewed_set_provider: ReviewedGrainIdentitySetProvider | None = None
_session_provider: SessionProvider | None = None


def set_v0_2_reviewed_grain_identity_set_provider(
    provider: ReviewedGrainIdentitySetProvider | None,
) -> None:
    global _reviewed_set_provider
    _reviewed_set_provider = provider


def clear_v0_2_reviewed_grain_identity_set_provider() -> None:
    set_v0_2_reviewed_grain_identity_set_provider(None)


def set_v0_2_grain_row_presence_session_provider(provider: SessionProvider | None) -> None:
    global _session_provider
    _session_provider = provider


def clear_v0_2_grain_row_presence_session_provider() -> None:
    set_v0_2_grain_row_presence_session_provider(None)


def ensure_replay_identity_grain_rows() -> int:
    """Fail-closed: INSERT grain rows only when a reviewed identity-set exists."""
    if bindable_table_names() != (FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,):
        return 0
    if _reviewed_set_provider is None:
        return 0
    try:
        reviewed_set = _reviewed_set_provider()
    except Exception:
        return 0
    if not reviewed_set:
        return 0
    if _session_provider is None:
        return 0
    try:
        session = _session_provider()
    except Exception:
        return 0
    if session is None:
        return 0
    try:
        return _insert_reviewed_grain_rows(session, reviewed_set)
    except Exception:
        return 0


def _insert_reviewed_grain_rows(
    session: Session,
    reviewed_set: tuple[ReviewedGrainIdentity, ...],
) -> int:
    bind = session.get_bind()
    if bind is None:
        return 0
    inspector = sa.inspect(bind)
    if FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME not in inspector.get_table_names():
        return 0
    column_names = {
        column["name"]
        for column in inspector.get_columns(FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME)
    }
    if not all(name in column_names for name in GRAIN_COLUMNS):
        return 0
    if any(
        any(forbidden in name for forbidden in FORBIDDEN_COLUMN_SUBSTRINGS)
        for name in column_names
    ):
        return 0

    metadata = sa.MetaData()
    table = sa.Table(
        FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
        metadata,
        autoload_with=bind,
    )

    inserted = 0
    for identity in reviewed_set:
        normalized = _normalize_reviewed_identity(identity, bind.dialect.name)
        if normalized is None:
            return inserted
        session.execute(
            table.insert().values(
                forecast_cutoff_at=normalized.forecast_cutoff_at,
                model_id=normalized.model_id,
                forecast_quantile=normalized.forecast_quantile,
            )
        )
        inserted += 1
    if inserted:
        session.commit()
    return inserted


def _normalize_reviewed_identity(
    identity: ReviewedGrainIdentity,
    dialect_name: str,
) -> ReviewedGrainIdentity | None:
    cutoff = identity.forecast_cutoff_at
    if not isinstance(cutoff, datetime):
        return None
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        if dialect_name == "sqlite":
            cutoff = cutoff.replace(tzinfo=UTC)
        else:
            return None
    if not identity.model_id or not identity.forecast_quantile:
        return None
    if cutoff is identity.forecast_cutoff_at:
        return identity
    return ReviewedGrainIdentity(
        forecast_cutoff_at=cutoff,
        model_id=identity.model_id,
        forecast_quantile=identity.forecast_quantile,
    )
