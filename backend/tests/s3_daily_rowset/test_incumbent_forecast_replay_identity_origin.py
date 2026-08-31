"""S3-A2 incumbent forecast replay-identity origin from frozen calendar policy."""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.app.s2_materialized_dataset.lane_d.partitions import TEST_START, VALIDATION_END
from backend.app.s3_daily_rowset.actuals import (
    is_evaluation_partition_allowed,
    window_contains_test_partition,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    ORIGIN_MODEL_ID,
    ORIGIN_QUANTILES,
    ReplayIdentityOriginLandingReasonCode,
    cutoff_is_legal_for_accepted_s2_window,
    default_calendar_cutoff_instants,
    land_replay_identity_origin_into_sync_session,
    last_legal_cutoff_before_test,
    legal_policy_cutoff_instants,
    replay_identity_origin_entries,
    shanghai_midnight,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.registry import V0_3_S3_FORECASTS_AUTHORITY
from backend.app.s3_daily_rowset.schemas import HORIZON_DAYS
from backend.app.s3_daily_rowset.window import cutoff_business_date, horizon_window_dates
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

TABLE_NAME = "s3_incumbent_forecast_replay_identity"
TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
ORIGIN_MODULE = Path("backend/app/s3_daily_rowset/incumbent_forecast_replay_identity_origin.py")


class _UtcAwareDateTime(sa.TypeDecorator[datetime]):
    impl = sa.DateTime(timezone=True)
    cache_ok = True

    def process_result_value(
        self,
        value: datetime | None,
        dialect: sa.Dialect,
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def _create_bindable_table(engine: sa.Engine) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        TABLE_NAME,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("forecast_cutoff_at", _UtcAwareDateTime(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "forecast_cutoff_at",
            "model_id",
            "forecast_quantile",
            name="uq_s3_replay_identity_grain",
        ),
    )
    metadata.create_all(engine)
    return table


def _empty_session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    _create_bindable_table(engine)
    return sessionmaker(bind=engine)()


def _count_grain_rows(session: Session) -> int:
    bind = session.get_bind()
    assert bind is not None
    metadata = sa.MetaData()
    table = sa.Table(TABLE_NAME, metadata, autoload_with=bind)
    return session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()


def test_2026_default_calendar_nodes_are_all_illegal() -> None:
    calendar = default_calendar_cutoff_instants()
    assert calendar
    assert all(not cutoff_is_legal_for_accepted_s2_window(cutoff) for cutoff in calendar)


def test_last_legal_cutoff_keeps_max_horizon_inside_validation() -> None:
    cutoff = last_legal_cutoff_before_test()
    assert cutoff.tzinfo is not None
    assert cutoff_business_date(cutoff) == date(2026, 2, 16)
    assert cutoff_is_legal_for_accepted_s2_window(cutoff)
    max_horizon = max(HORIZON_DAYS)
    window = horizon_window_dates(cutoff, max_horizon)
    assert window[-1] == VALIDATION_END
    assert not window_contains_test_partition(window)
    assert all(is_evaluation_partition_allowed(day) for day in window)
    assert TEST_START not in window


def test_legal_policy_cutoffs_fallback_when_calendar_empty() -> None:
    legal = legal_policy_cutoff_instants()
    assert legal == (last_legal_cutoff_before_test(),)


def test_origin_entries_are_authority_model_times_supported_quantiles() -> None:
    entries = replay_identity_origin_entries()
    assert len(entries) == 3
    assert ORIGIN_MODEL_ID == V0_3_S3_FORECASTS_AUTHORITY
    assert ORIGIN_QUANTILES == ("P50", "P80", "P90")
    assert {entry.model_id for entry in entries} == {V0_3_S3_FORECASTS_AUTHORITY}
    assert tuple(entry.forecast_quantile for entry in entries) == ORIGIN_QUANTILES
    assert all(entry.forecast_cutoff_at == last_legal_cutoff_before_test() for entry in entries)
    assert "incumbent-v0.2" not in {entry.model_id for entry in entries}


def test_origin_does_not_use_harvest_dates_or_handwritten_cutoff_list() -> None:
    source = ORIGIN_MODULE.read_text(encoding="utf-8")
    assert "harvest_rows" not in source
    assert "HANDWRITTEN_CUTOFF_LIST" not in source
    assert "incumbent-v0.2" not in source
    entries = replay_identity_origin_entries()
    harvest_probe = date(2026, 2, 1)
    assert all(cutoff_business_date(entry.forecast_cutoff_at) != harvest_probe for entry in entries)


def test_shanghai_midnight_is_timezone_aware() -> None:
    instant = shanghai_midnight(date(2026, 2, 16))
    assert instant.tzinfo is not None
    assert instant.utcoffset() is not None
    assert instant.astimezone(UTC) == datetime(2026, 2, 15, 16, 0, tzinfo=UTC)


def test_land_origin_is_idempotent_and_does_not_set_session_provider() -> None:
    session = _empty_session()
    entries = replay_identity_origin_entries()

    first = land_replay_identity_origin_into_sync_session(session, entries)
    second = land_replay_identity_origin_into_sync_session(session, entries)

    assert first.reason_code is ReplayIdentityOriginLandingReasonCode.LANDED
    assert first.inserted == 3
    assert first.table_row_count == 3
    assert second.reason_code is ReplayIdentityOriginLandingReasonCode.ALREADY_PRESENT
    assert second.inserted == 0
    assert second.skipped == 3
    assert _count_grain_rows(session) == 3
    assert read_bindable_replay_identity_rows() == ()
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_remains_no_versioned_after_landing_without_provider() -> None:
    session = _empty_session()
    land_replay_identity_origin_into_sync_session(session)

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    clear_v0_2_live_postgres_session_provider()


def test_origin_module_contains_no_dsn() -> None:
    source = ORIGIN_MODULE.read_text(encoding="utf-8").lower()
    assert "postgresql://" not in source
    assert "dsn" not in source
    assert "create_engine(" not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
