"""PostgreSQL migration tests for S3-B final-target quantile prediction lane."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = [pytest.mark.postgres, pytest.mark.migration]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    _BACKEND_ROOT
    / "alembic"
    / "versions"
    / "f3a9b2c8d1e4_s3_b_final_target_quantile_prediction_lane.py"
)
NEW_HEAD = "f3a9b2c8d1e4"
PARENT_REVISION = "e8b2c4d6f1a3"
_HASH = "a" * 64


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "s3_b_final_target_quantile_prediction_lane_migration",
        _MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_single_head_is_new_revision() -> None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == [NEW_HEAD]


def test_migration_revision_metadata() -> None:
    module = _migration_module()
    assert module.revision == NEW_HEAD
    assert module.down_revision == PARENT_REVISION


def test_migration_source_contains_lane_and_grain_semantics() -> None:
    source = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "prediction_target_kind" in source
    assert "distinct_grain_count" in source
    assert "final_target_quantile" in source
    assert "ck_residual_model_prediction_run_lane_consistency" in source
    assert "FINAL_TARGET_QUANTILE prediction rows exist" in source


def test_downgrade_fails_closed_when_final_target_rows_exist() -> None:
    module = _migration_module()
    bind = MagicMock()
    bind.execute.return_value.scalar_one.return_value = 1
    cast(Any, module).op = MagicMock(get_bind=lambda: bind)
    with pytest.raises(RuntimeError, match="FINAL_TARGET_QUANTILE"):
        module.downgrade()


@pytest.mark.asyncio
async def test_postgres_lane_constraints() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")
    from backend.app.db.session import AsyncSessionMaker

    try:
        async with AsyncSessionMaker() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL integration database is not available")

    async with AsyncSessionMaker() as session:
        training_id = (
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_training_run (
                        execution_status, eligibility_status,
                        model_family, model_version,
                        feature_schema_version, feature_schema_hash,
                        artifact_schema_version,
                        training_signature, config_hash,
                        config_snapshot, manifest_hash, manifest_snapshot,
                        feature_audit_summary, category_encoding_snapshot,
                        training_metrics, validation_metrics,
                        eligibility_reasons, warnings, blockers,
                        input_snapshot, canonical_output, canonical_payload_hash,
                        python_version, numpy_version, sklearn_version,
                        distinct_grain_count
                    ) VALUES (
                        'completed', 'eligible', 'test', '1', '1', :hash, '1',
                        :hash, :hash, '{}'::jsonb, :hash, '{}'::jsonb,
                        '{}'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb,
                        '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb, :hash,
                        '3.12', '1.26', '1.6', 2
                    )
                    RETURNING id
                    """
                ),
                {"hash": _HASH},
            )
        ).scalar_one()
        await session.commit()

    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO residual_model_prediction_run (
                    training_run_id, task9_run_id, task9_result_hash,
                    prediction_target_kind, execution_status, mode,
                    config_hash, feature_schema_version, feature_schema_hash,
                    artifact_hashes, prediction_input_signature, prediction_hash,
                    feature_audit, warnings, blockers, input_snapshot,
                    canonical_output, canonical_payload_hash,
                    expected_prediction_row_count
                ) VALUES (
                    :training_id, NULL, NULL, 'FINAL_TARGET_QUANTILE',
                    'completed', 'final_target_quantile',
                    :hash, '1', :hash, '[]'::jsonb, :hash, :hash,
                    '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '{}'::jsonb, '{}'::jsonb, :hash, 0
                )
                """
            ),
            {"training_id": training_id, "hash": _HASH},
        )
        await session.commit()

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_prediction_run (
                        training_run_id, task9_run_id, task9_result_hash,
                        prediction_target_kind, execution_status, mode,
                        config_hash, feature_schema_version, feature_schema_hash,
                        artifact_hashes, prediction_input_signature, prediction_hash,
                        feature_audit, warnings, blockers, input_snapshot,
                        canonical_output, canonical_payload_hash,
                        expected_prediction_row_count
                    ) VALUES (
                        :training_id, NULL, NULL, 'FINAL_TARGET_QUANTILE',
                        'completed', 'residual_corrected',
                        :hash, '1', :hash, '[]'::jsonb, :hash, :hash,
                        '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb, :hash, 0
                    )
                    """
                ),
                {"training_id": training_id, "hash": _HASH},
            )
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_prediction_run (
                        training_run_id, task9_run_id, task9_result_hash,
                        prediction_target_kind, execution_status, mode,
                        config_hash, feature_schema_version, feature_schema_hash,
                        artifact_hashes, prediction_input_signature, prediction_hash,
                        feature_audit, warnings, blockers, input_snapshot,
                        canonical_output, canonical_payload_hash,
                        expected_prediction_row_count
                    ) VALUES (
                        :training_id, 0, :hash, 'FINAL_TARGET_QUANTILE',
                        'completed', 'final_target_quantile',
                        :hash, '1', :hash, '[]'::jsonb, :hash, :hash,
                        '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb, :hash, 0
                    )
                    """
                ),
                {"training_id": training_id, "hash": _HASH},
            )
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_prediction_run (
                        training_run_id, task9_run_id, task9_result_hash,
                        prediction_target_kind, execution_status, mode,
                        config_hash, feature_schema_version, feature_schema_hash,
                        artifact_hashes, prediction_input_signature, prediction_hash,
                        feature_audit, warnings, blockers, input_snapshot,
                        canonical_output, canonical_payload_hash,
                        expected_prediction_row_count
                    ) VALUES (
                        NULL, NULL, NULL, 'LEGACY_RESIDUAL_CORRECTION',
                        'completed', 'residual_corrected',
                        :hash, '1', :hash, '[]'::jsonb, :hash, :hash,
                        '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb, :hash, 0
                    )
                    """
                ),
                {"hash": _HASH},
            )
            await session.flush()
        await session.rollback()
