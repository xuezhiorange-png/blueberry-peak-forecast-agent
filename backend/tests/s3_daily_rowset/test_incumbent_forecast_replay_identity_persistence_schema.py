"""S3-A2 incumbent forecast replay-identity persistence schema tests."""

from __future__ import annotations

import importlib.util
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    MATCH_TABLE_NAMES,
    is_bindable,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    _BACKEND_ROOT / "alembic" / "versions" / "e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py"
)
NEW_ALEMBIC_HEAD = "e8b2c4d6f1a3"
PARENT_ALEMBIC_REVISION = "a7c3e9f1b2d4"
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


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "s3_incumbent_forecast_replay_identity_migration",
        _MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_has_single_head_at_new_revision() -> None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()

    assert heads == [NEW_ALEMBIC_HEAD]


def test_migration_revision_metadata() -> None:
    module = _migration_module()

    assert module.revision == NEW_ALEMBIC_HEAD
    assert module.down_revision == PARENT_ALEMBIC_REVISION


def test_table_exists_with_zero_rows_after_upgrade() -> None:
    module = _migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        cast(Any, module).op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        inspector = sa.inspect(connection)
        assert TABLE_NAME in inspector.get_table_names()
        row_count = connection.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()
        assert row_count == 0
        module.downgrade()
        assert TABLE_NAME not in sa.inspect(connection).get_table_names()


def test_grain_unique_constraint_rejects_duplicate_triple() -> None:
    module = _migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    cutoff = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)
    with engine.begin() as connection:
        cast(Any, module).op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {TABLE_NAME} (forecast_cutoff_at, model_id, forecast_quantile)
                VALUES (:cutoff, :model_id, :forecast_quantile)
                """
            ),
            {
                "cutoff": cutoff,
                "model_id": "schema-uniqueness-probe",
                "forecast_quantile": "P50",
            },
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    f"""
                    INSERT INTO {TABLE_NAME} (forecast_cutoff_at, model_id, forecast_quantile)
                    VALUES (:cutoff, :model_id, :forecast_quantile)
                    """
                ),
                {
                    "cutoff": cutoff,
                    "model_id": "schema-uniqueness-probe",
                    "forecast_quantile": "P50",
                },
            )
        connection.rollback()


def test_table_has_only_frozen_grain_columns() -> None:
    module = _migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        cast(Any, module).op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        column_names = {column["name"] for column in sa.inspect(connection).get_columns(TABLE_NAME)}
        assert column_names == {
            "id",
            "forecast_cutoff_at",
            "model_id",
            "forecast_quantile",
        }
        assert column_names.isdisjoint(FORBIDDEN_COLUMN_NAMES)


def test_default_replay_source_obtain_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_first_blocker_is_no_versioned_forecast() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_match_table_names_remain_empty_and_table_not_bindable() -> None:
    assert MATCH_TABLE_NAMES == ()
    assert is_bindable("s3_incumbent_forecast_replay_identity") is False
    assert is_bindable("core_forecast_daily_row") is False


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
