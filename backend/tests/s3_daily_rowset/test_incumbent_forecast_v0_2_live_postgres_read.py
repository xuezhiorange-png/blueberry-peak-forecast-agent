"""S3-A2 incumbent forecast V0.2 live postgres read tests."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
    set_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    AUDIT_TABLE_COUNT,
    FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
    MATCH_TABLE_COUNT,
    MATCH_TABLE_NAMES,
    bindable_table_names,
    is_bindable,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

TABLE_NAME = "s3_incumbent_forecast_replay_identity"
TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
FORBIDDEN_COLUMN_NAMES = frozenset(
    {
        "actual_harvest_quantity_kg",
        "forecast_value",
        "harvest_business_date",
        "quantity",
        "tonnes",
        "weight",
    }
)


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


def _replay_entry(
    *,
    cutoff: datetime | None = None,
    model_id: str = "live-read-probe",
    quantile: str = "P50",
) -> IncumbentForecastArtifactEntry:
    if cutoff is None:
        cutoff = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)
    return IncumbentForecastArtifactEntry(
        model_id=model_id,
        forecast_cutoff_at=cutoff,
        forecast_quantile=quantile,
    )


def _create_bindable_table(
    engine: sa.Engine,
    *,
    extra_columns: tuple[sa.Column[object], ...] = (),
) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        TABLE_NAME,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("forecast_cutoff_at", _UtcAwareDateTime(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("forecast_quantile", sa.Text(), nullable=False),
        *extra_columns,
    )
    metadata.create_all(engine)
    return table


def _session_with_rows(
    rows: tuple[tuple[datetime, str, str], ...] = (),
    *,
    extra_columns: tuple[sa.Column[object], ...] = (),
    create_table: bool = True,
) -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    if create_table:
        table = _create_bindable_table(engine, extra_columns=extra_columns)
        session = sessionmaker(bind=engine)()
        for cutoff, model_id, forecast_quantile in rows:
            session.execute(
                table.insert().values(
                    forecast_cutoff_at=cutoff,
                    model_id=model_id,
                    forecast_quantile=forecast_quantile,
                )
            )
        session.commit()
        return session
    return sessionmaker(bind=engine)()


@pytest.fixture(autouse=True)
def _clear_live_postgres_session_provider() -> None:
    clear_v0_2_live_postgres_session_provider()
    yield
    clear_v0_2_live_postgres_session_provider()


def test_default_obtain_without_session_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_remains_no_versioned_without_session() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_injected_session_with_empty_frozen_table_returns_empty_obtain() -> None:
    session = _session_with_rows()
    set_v0_2_live_postgres_session_provider(lambda: session)

    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_injected_session_with_empty_table_catalog_remains_no_versioned() -> None:
    session = _session_with_rows()
    set_v0_2_live_postgres_session_provider(lambda: session)

    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_injected_session_projects_grain_rows_without_forbidden_columns() -> None:
    row = (
        datetime(2026, 2, 15, 16, 0, tzinfo=UTC),
        "live-read-probe",
        "P50",
    )
    session = _session_with_rows((row,))
    set_v0_2_live_postgres_session_provider(lambda: session)

    rows = IncumbentForecastReplaySource().obtain()

    assert rows == (_replay_entry(),)
    assert all(
        not any(forbidden in field_name for forbidden in FORBIDDEN_COLUMN_NAMES)
        for field_name in IncumbentForecastArtifactEntry.__dataclass_fields__
    )


def test_harvest_as_cutoff_returns_empty_even_with_session_rows() -> None:
    session = _session_with_rows(
        ((datetime(2026, 2, 15, 16, 0, tzinfo=UTC), "live-read-probe", "P50"),)
    )
    set_v0_2_live_postgres_session_provider(lambda: session)
    source = IncumbentForecastReplaySource(uses_harvest_date_as_forecast_cutoff=True)

    assert source.obtain() == ()


def test_explicit_replay_rows_win_over_live_read() -> None:
    session = _session_with_rows(
        ((datetime(2026, 2, 15, 16, 0, tzinfo=UTC), "postgres-model", "P50"),)
    )
    set_v0_2_live_postgres_session_provider(lambda: session)
    source = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(model_id="explicit-model"),),
    )

    assert source.obtain() == (_replay_entry(model_id="explicit-model"),)


def test_missing_session_provider_returns_empty() -> None:
    assert read_bindable_replay_identity_rows() == ()


def test_unreadable_session_provider_returns_empty() -> None:
    def _raise() -> Session:
        raise RuntimeError("session unavailable")

    set_v0_2_live_postgres_session_provider(_raise)

    assert IncumbentForecastReplaySource().obtain() == ()


def test_missing_table_returns_empty() -> None:
    session = _session_with_rows(create_table=False)
    set_v0_2_live_postgres_session_provider(lambda: session)

    assert IncumbentForecastReplaySource().obtain() == ()


def test_ambiguous_forbidden_column_returns_empty() -> None:
    session = _session_with_rows(
        extra_columns=(sa.Column("forecast_value", sa.Numeric()),),
    )
    set_v0_2_live_postgres_session_provider(lambda: session)

    assert IncumbentForecastReplaySource().obtain() == ()


def test_match_table_names_remain_empty_and_frozen_name_not_in_match() -> None:
    assert MATCH_TABLE_NAMES == ()
    assert MATCH_TABLE_COUNT == 0
    assert AUDIT_TABLE_COUNT == 106
    assert bindable_table_names() == (FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,)
    assert is_bindable(FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME) is True
    assert FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME not in MATCH_TABLE_NAMES


def test_live_read_module_contains_no_dsn() -> None:
    source = (
        Path("backend/app/s3_daily_rowset/incumbent_forecast_v0_2_live_postgres_read.py")
        .read_text(encoding="utf-8")
        .lower()
    )
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
