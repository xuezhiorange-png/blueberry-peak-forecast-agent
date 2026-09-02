"""S3-A2 incumbent forecast V0.2 replay-identity grain row presence tests."""

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
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    set_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_row_presence import (
    ReviewedGrainIdentity,
    clear_v0_2_grain_row_presence_session_provider,
    clear_v0_2_reviewed_grain_identity_set_provider,
    ensure_replay_identity_grain_rows,
    set_v0_2_grain_row_presence_session_provider,
    set_v0_2_reviewed_grain_identity_set_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    AUDIT_TABLE_COUNT,
    FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME,
    MATCH_TABLE_COUNT,
    MATCH_TABLE_NAMES,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

TABLE_NAME = "s3_incumbent_forecast_replay_identity"
TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"


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


@pytest.fixture(autouse=True)
def _clear_grain_row_presence_providers() -> None:
    clear_v0_2_reviewed_grain_identity_set_provider()
    clear_v0_2_grain_row_presence_session_provider()
    clear_v0_2_live_postgres_session_provider()
    yield
    clear_v0_2_reviewed_grain_identity_set_provider()
    clear_v0_2_grain_row_presence_session_provider()
    clear_v0_2_live_postgres_session_provider()


def test_without_reviewed_identity_set_table_remains_zero_rows() -> None:
    session = _empty_session()
    set_v0_2_grain_row_presence_session_provider(lambda: session)

    inserted = ensure_replay_identity_grain_rows()

    assert inserted == 0
    assert _count_grain_rows(session) == 0


def test_default_obtain_without_session_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_injected_session_with_empty_table_returns_empty_obtain() -> None:
    session = _empty_session()
    set_v0_2_live_postgres_session_provider(lambda: session)

    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_remains_no_versioned_without_session() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_injected_session_with_empty_table_catalog_remains_no_versioned() -> None:
    session = _empty_session()
    set_v0_2_live_postgres_session_provider(lambda: session)

    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_reviewed_set_without_session_still_inserts_zero_rows() -> None:
    session = _empty_session()
    reviewed = (
        ReviewedGrainIdentity(
            forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            model_id="reviewed-set-test-model",
            forecast_quantile="P80",
        ),
    )
    set_v0_2_reviewed_grain_identity_set_provider(lambda: reviewed)

    inserted = ensure_replay_identity_grain_rows()

    assert inserted == 0
    assert _count_grain_rows(session) == 0


def test_injected_reviewed_set_inserts_grain_rows_only() -> None:
    session = _empty_session()
    reviewed = (
        ReviewedGrainIdentity(
            forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            model_id="reviewed-set-test-model",
            forecast_quantile="P80",
        ),
    )
    set_v0_2_reviewed_grain_identity_set_provider(lambda: reviewed)
    set_v0_2_grain_row_presence_session_provider(lambda: session)

    inserted = ensure_replay_identity_grain_rows()

    assert inserted == 1
    assert _count_grain_rows(session) == 1
    bind = session.get_bind()
    assert bind is not None
    metadata = sa.MetaData()
    table = sa.Table(TABLE_NAME, metadata, autoload_with=bind)
    row = session.execute(sa.select(table)).one()
    cutoff = row.forecast_cutoff_at
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    assert cutoff == datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    assert row.model_id == "reviewed-set-test-model"
    assert row.forecast_quantile == "P80"
    assert not hasattr(row, "forecast_value")
    assert not hasattr(row, "tonnes")


def test_match_table_names_remain_empty() -> None:
    assert MATCH_TABLE_NAMES == ()
    assert MATCH_TABLE_COUNT == 0
    assert AUDIT_TABLE_COUNT == 106
    assert FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME not in MATCH_TABLE_NAMES


def test_grain_row_presence_module_contains_no_dsn() -> None:
    source = (
        Path(
            "backend/app/s3_daily_rowset/"
            "incumbent_forecast_v0_2_replay_identity_grain_row_presence.py"
        )
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
