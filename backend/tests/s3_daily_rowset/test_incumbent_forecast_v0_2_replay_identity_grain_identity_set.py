"""S3-A2 incumbent forecast V0.2 replay-identity grain identity-set loader tests."""

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
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    clear_v0_2_reviewed_grain_identity_set_artifact_locator,
    clear_v0_2_reviewed_grain_identity_set_loader,
    grain_row_presence_reviewed_set_provider,
    load_reviewed_grain_identity_set,
    reviewed_grain_identity_set_artifact_available,
    set_v0_2_reviewed_grain_identity_set_artifact_locator,
    set_v0_2_reviewed_grain_identity_set_loader,
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


def _test_only_reviewed_member() -> ReviewedGrainIdentity:
    return ReviewedGrainIdentity(
        forecast_cutoff_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        model_id="loader-test-only-model",
        forecast_quantile="P80",
    )


@pytest.fixture(autouse=True)
def _clear_identity_set_loader_providers() -> None:
    clear_v0_2_reviewed_grain_identity_set_artifact_locator()
    clear_v0_2_reviewed_grain_identity_set_loader()
    clear_v0_2_reviewed_grain_identity_set_provider()
    clear_v0_2_grain_row_presence_session_provider()
    yield
    clear_v0_2_reviewed_grain_identity_set_artifact_locator()
    clear_v0_2_reviewed_grain_identity_set_loader()
    clear_v0_2_reviewed_grain_identity_set_provider()
    clear_v0_2_grain_row_presence_session_provider()


def test_without_reviewed_artifact_loader_returns_empty() -> None:
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()


def test_without_reviewed_artifact_grain_row_presence_remains_zero_rows() -> None:
    session = _empty_session()
    set_v0_2_grain_row_presence_session_provider(lambda: session)
    set_v0_2_reviewed_grain_identity_set_provider(grain_row_presence_reviewed_set_provider())

    inserted = ensure_replay_identity_grain_rows()

    assert inserted == 0
    assert _count_grain_rows(session) == 0


def test_default_obtain_without_session_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_remains_no_versioned_without_session() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_injected_test_only_loader_can_drive_grain_row_presence_without_repo_artifact() -> None:
    session = _empty_session()
    member = _test_only_reviewed_member()
    set_v0_2_reviewed_grain_identity_set_artifact_locator(lambda: True)
    set_v0_2_reviewed_grain_identity_set_loader(lambda: (member,))
    set_v0_2_grain_row_presence_session_provider(lambda: session)
    set_v0_2_reviewed_grain_identity_set_provider(grain_row_presence_reviewed_set_provider())

    assert load_reviewed_grain_identity_set() == (member,)
    inserted = ensure_replay_identity_grain_rows()

    assert inserted == 1
    assert _count_grain_rows(session) == 1


def test_match_table_names_remain_empty() -> None:
    assert MATCH_TABLE_NAMES == ()
    assert MATCH_TABLE_COUNT == 0
    assert AUDIT_TABLE_COUNT == 106
    assert FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME not in MATCH_TABLE_NAMES


def test_identity_set_loader_module_contains_no_dsn_or_sql_reads() -> None:
    source = (
        Path(
            "backend/app/s3_daily_rowset/"
            "incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
        )
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "postgresql://" not in source
    assert "dsn" not in source
    assert "create_engine(" not in source
    assert " select " not in source
    assert " from " not in source
    assert " join " not in source
    assert " where " not in source


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
