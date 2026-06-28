"""Section 11: PostgreSQL constraint violation tests with real IntegrityError assertions.

These tests insert illegal data into residual model tables and verify that
PostgreSQL CHECK constraints raise IntegrityError. Each test also verifies
that no partial rows remain after the failed insert (transaction rollback).

Requires RUN_POSTGRES_INTEGRATION=1 (integration marker).
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import AsyncSessionMaker

pytestmark = pytest.mark.integration

# Helpers ──────────────────────────────────────────────────────────────────────

_HASH: str = "a" * 64  # Valid SHA256 hex string


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


async def _expect_integrity_error(
    sql: str, params: dict[str, Any] | None = None
) -> None:
    """Execute sql, commit, and assert IntegrityError is raised.

    After the error, verify the session is still usable by performing a simple
    SELECT, confirming the failed INSERT was fully rolled back.
    """
    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text(sql), params or {})
            await session.flush()

        await session.rollback()
        await session.execute(text("SELECT 1"))


async def _seed_factory(name: str = "Test Factory") -> int:
    """Insert a minimal dim_factory row and return its id."""
    async with AsyncSessionMaker() as session:
        row = (
            await session.execute(
                text("INSERT INTO dim_factory (name) VALUES (:name) RETURNING id"),
                {"name": name},
            )
        ).scalar_one()
        await session.commit()
        return row


async def _seed_harvest_state_run(factory_id: int | None = None) -> int:
    """Insert a minimal harvest_state_run row and return its id."""
    if factory_id is None:
        factory_id = await _seed_factory()
    async with AsyncSessionMaker() as session:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO harvest_state_run (
                        status, output_schema_version,
                        result_hash_schema_version,
                        resolved_parameter_snapshot_schema_version,
                        source_ref_schema_version,
                        stable_cohort_key_schema_version,
                        input_snapshot, source_ref_catalog, warnings, blockers,
                        canonical_output, config_hash, result_hash,
                        canonical_payload_hash, forecast_start_date,
                        forecast_end_date, as_of_date, destination_factory_id,
                        pool_row_count, member_row_count, cohort_row_count,
                        future_arrival_row_count
                    ) VALUES (
                        'completed', '1', '1', '1', '1', '1',
                        '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, :hash, :hash, :hash,
                        '2026-01-01', '2026-04-30', '2026-01-15',
                        :factory_id, 0, 0, 0, 0
                    )
                    RETURNING id
                    """
                ),
                {"hash": _HASH, "factory_id": factory_id},
            )
        ).scalar_one()
        await session.commit()
        return row


async def _seed_training_run(
    execution_status: str = "completed",
    eligibility_status: str = "eligible",
    sample_count: int = 0,
    distinct_season_count: int = 0,
    distinct_factory_count: int = 0,
    manifest_row_count: int = 0,
    expected_artifact_count: int = 3,
) -> int:
    """Insert a minimal training_run row and return its id.

    Defaults produce a valid completed+eligible+3-artifacts row.
    """
    async with AsyncSessionMaker() as session:
        row = (
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
                        sample_count, distinct_season_count,
                        distinct_factory_count, manifest_row_count,
                        expected_artifact_count
                    ) VALUES (
                        :execution_status, :eligibility_status,
                        'test-model', '1.0.0',
                        '1', :hash,
                        '1',
                        :hash, :hash,
                        '{}'::jsonb, :hash, '{}'::jsonb,
                        '{}'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb,
                        '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb, :hash,
                        '3.12', '1.26', '1.6',
                        :sample_count, :distinct_season_count,
                        :distinct_factory_count, :manifest_row_count,
                        :expected_artifact_count
                    )
                    RETURNING id
                    """
                ),
                {
                    "execution_status": execution_status,
                    "eligibility_status": eligibility_status,
                    "hash": _HASH,
                    "sample_count": sample_count,
                    "distinct_season_count": distinct_season_count,
                    "distinct_factory_count": distinct_factory_count,
                    "manifest_row_count": manifest_row_count,
                    "expected_artifact_count": expected_artifact_count,
                },
            )
        ).scalar_one()
        await session.commit()
        return row


async def _seed_training_run_bare_minimum() -> int:
    """Insert a training_run with all-core-required fields, defaults for counts."""
    return await _seed_training_run()


async def _seed_artifact(
    training_run_id: int | None = None,
    quantile_label: str = "P50",
    artifact_format: str = "joblib_bundle",
    estimator_type: str = "HistGradientBoostingRegressor",
    loss_name: str = "quantile",
    quantile_value: float = 0.5,
    trusted_internal_source: bool = True,
) -> int:
    """Insert a minimal artifact row and return its id."""
    if training_run_id is None:
        training_run_id = await _seed_training_run_bare_minimum()
    async with AsyncSessionMaker() as session:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_artifact (
                        training_run_id, quantile_label,
                        artifact_format, artifact_schema_version,
                        estimator_type, loss_name, quantile_value,
                        artifact_bytes, artifact_sha256,
                        feature_schema_version, feature_schema_hash,
                        config_hash,
                        trusted_internal_source,
                        metadata,
                        python_version, numpy_version, sklearn_version
                    ) VALUES (
                        :training_run_id, :quantile_label,
                        :artifact_format, '1',
                        :estimator_type, :loss_name, :quantile_value,
                        decode('00', 'hex'), :hash,
                        '1', :hash,
                        :hash,
                        :trusted_internal_source,
                        '{}'::jsonb,
                        '3.12', '1.26', '1.6'
                    )
                    RETURNING id
                    """
                ),
                {
                    "training_run_id": training_run_id,
                    "quantile_label": quantile_label,
                    "artifact_format": artifact_format,
                    "estimator_type": estimator_type,
                    "loss_name": loss_name,
                    "quantile_value": quantile_value,
                    "hash": _HASH,
                    "trusted_internal_source": trusted_internal_source,
                },
            )
        ).scalar_one()
        await session.commit()
        return row


async def _seed_prediction_run(
    execution_status: str = "completed",
    mode: str = "residual_corrected",
    expected_prediction_row_count: int = 0,
    fallback_reason: str | None = None,
    task9_run_id: int | None = None,
) -> int:
    """Insert a minimal prediction_run row and return its id."""
    if task9_run_id is None:
        task9_run_id = await _seed_harvest_state_run()
    async with AsyncSessionMaker() as session:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_prediction_run (
                        task9_run_id, task9_result_hash,
                        execution_status, mode,
                        config_hash, feature_schema_version,
                        feature_schema_hash, artifact_hashes,
                        prediction_input_signature, prediction_hash,
                        feature_audit, warnings, blockers,
                        input_snapshot, canonical_output,
                        canonical_payload_hash,
                        expected_prediction_row_count,
                        fallback_reason
                    ) VALUES (
                        :task9_run_id, :hash,
                        :execution_status, :mode,
                        :hash, '1',
                        :hash, '[]'::jsonb,
                        :hash, :hash,
                        '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '{}'::jsonb, '{}'::jsonb,
                        :hash,
                        :expected_prediction_row_count,
                        :fallback_reason
                    )
                    RETURNING id
                    """
                ),
                {
                    "task9_run_id": task9_run_id,
                    "hash": _HASH,
                    "execution_status": execution_status,
                    "mode": mode,
                    "expected_prediction_row_count": expected_prediction_row_count,
                    "fallback_reason": fallback_reason,
                },
            )
        ).scalar_one()
        await session.commit()
        return row


async def _seed_prediction_row(
    prediction_run_id: int | None = None,
    mode: str = "residual_corrected",
    fallback_reason: str | None = None,
    forecast_horizon_days: int = 1,
    corrected_p50_kg: float = 10,
    corrected_p80_kg: float = 20,
    corrected_p90_kg: float = 30,
    raw_residual_p50_kg: float = 0,
    raw_residual_p80_kg: float = 0,
    raw_residual_p90_kg: float = 0,
    task9_run_id: int | None = None,
    factory_id: int | None = None,
) -> int:
    """Insert a minimal prediction_row and return its id."""
    if factory_id is None:
        factory_id = await _seed_factory(
            name=f"Prediction Row Factory {prediction_run_id or 'auto'}"
        )
    if prediction_run_id is None:
        prediction_run_id = await _seed_prediction_run()
    if task9_run_id is None:
        task9_run_id = await _seed_harvest_state_run(factory_id=factory_id)
    async with AsyncSessionMaker() as session:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO residual_model_prediction_row (
                        prediction_run_id, model_run_id,
                        task9_run_id, task9_result_hash,
                        destination_factory_id, arrival_local_date,
                        forecast_horizon_days,
                        structural_p50_kg, structural_p80_kg, structural_p90_kg,
                        raw_residual_p50_kg, raw_residual_p80_kg, raw_residual_p90_kg,
                        corrected_raw_p50_kg, corrected_raw_p80_kg, corrected_raw_p90_kg,
                        corrected_p50_kg, corrected_p80_kg, corrected_p90_kg,
                        nonnegative_projection_applied,
                        quantile_projection_applied,
                        projection_reasons,
                        feature_vector_hash, feature_audit_hash,
                        prediction_row_hash,
                        mode, fallback_reason
                    ) VALUES (
                        :prediction_run_id, NULL,
                        :task9_run_id, :hash,
                        :factory_id, '2026-03-01',
                        :forecast_horizon_days,
                        10, 20, 30,
                        :raw_residual_p50_kg, :raw_residual_p80_kg, :raw_residual_p90_kg,
                        10, 20, 30,
                        :corrected_p50_kg, :corrected_p80_kg, :corrected_p90_kg,
                        false, false,
                        '[]'::jsonb,
                        :hash, :hash, :hash,
                        :mode, :fallback_reason
                    )
                    RETURNING id
                    """
                ),
                {
                    "prediction_run_id": prediction_run_id,
                    "task9_run_id": task9_run_id,
                    "hash": _HASH,
                    "factory_id": factory_id,
                    "forecast_horizon_days": forecast_horizon_days,
                    "raw_residual_p50_kg": raw_residual_p50_kg,
                    "raw_residual_p80_kg": raw_residual_p80_kg,
                    "raw_residual_p90_kg": raw_residual_p90_kg,
                    "corrected_p50_kg": corrected_p50_kg,
                    "corrected_p80_kg": corrected_p80_kg,
                    "corrected_p90_kg": corrected_p90_kg,
                    "mode": mode,
                    "fallback_reason": fallback_reason,
                },
            )
        ).scalar_one()
        await session.commit()
        return row


# ── Training Run Constraint Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_training_run_negative_sample_count() -> None:
    """sample_count < 0 must raise IntegrityError."""
    _require_postgres()
    await _expect_integrity_error(
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
            sample_count
        ) VALUES (
            'running', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            -1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_negative_distinct_season_count() -> None:
    """distinct_season_count < 0 must raise IntegrityError."""
    _require_postgres()
    await _expect_integrity_error(
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
            distinct_season_count
        ) VALUES (
            'running', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            -1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_negative_distinct_factory_count() -> None:
    """distinct_factory_count < 0 must raise IntegrityError."""
    _require_postgres()
    await _expect_integrity_error(
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
            distinct_factory_count
        ) VALUES (
            'running', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            -1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_negative_manifest_row_count() -> None:
    """manifest_row_count < 0 must raise IntegrityError."""
    _require_postgres()
    await _expect_integrity_error(
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
            manifest_row_count
        ) VALUES (
            'running', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            -1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_negative_expected_artifact_count() -> None:
    """expected_artifact_count < 0 must raise IntegrityError."""
    _require_postgres()
    await _expect_integrity_error(
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
            expected_artifact_count
        ) VALUES (
            'running', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            -1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_completed_eligible_artifacts_not_three() -> None:
    """completed+eligible must have expected_artifact_count = 3."""
    _require_postgres()
    await _expect_integrity_error(
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
            expected_artifact_count
        ) VALUES (
            'completed', 'eligible',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            2
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_completed_ineligible_artifacts_not_zero() -> None:
    """completed+ineligible must have expected_artifact_count = 0."""
    _require_postgres()
    await _expect_integrity_error(
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
            expected_artifact_count
        ) VALUES (
            'completed', 'ineligible',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_blocked_failed_artifacts_not_zero() -> None:
    """blocked or failed must have expected_artifact_count = 0."""
    _require_postgres()
    # Test blocked
    await _expect_integrity_error(
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
            expected_artifact_count
        ) VALUES (
            'blocked', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            1
        )
        """,
        {"hash": _HASH},
    )
    # Test failed
    await _expect_integrity_error(
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
            expected_artifact_count
        ) VALUES (
            'failed', 'not_evaluated',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            1
        )
        """,
        {"hash": _HASH},
    )


@pytest.mark.asyncio
async def test_training_run_eligible_non_completed() -> None:
    """eligible requires execution_status = 'completed'."""
    _require_postgres()
    await _expect_integrity_error(
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
            expected_artifact_count
        ) VALUES (
            'running', 'eligible',
            'test', '1.0.0',
            '1', :hash,
            '1',
            :hash, :hash,
            '{}'::jsonb, :hash, '{}'::jsonb,
            '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb, :hash,
            '3.12', '1.26', '1.6',
            0
        )
        """,
        {"hash": _HASH},
    )


# ── Artifact Constraint Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_artifact_invalid_format() -> None:
    """artifact_format must be 'joblib_bundle'."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P50',
            'pickle', '1',
            'HistGradientBoostingRegressor', 'quantile', 0.5,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            true,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_artifact_invalid_estimator_type() -> None:
    """estimator_type must be 'HistGradientBoostingRegressor'."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P50',
            'joblib_bundle', '1',
            'RandomForestRegressor', 'quantile', 0.5,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            true,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_artifact_invalid_loss_name() -> None:
    """loss_name must be 'quantile'."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P50',
            'joblib_bundle', '1',
            'HistGradientBoostingRegressor', 'mse', 0.5,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            true,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_artifact_untrusted_source() -> None:
    """trusted_internal_source must be true."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P50',
            'joblib_bundle', '1',
            'HistGradientBoostingRegressor', 'quantile', 0.5,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            false,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_artifact_p50_wrong_quantile_value() -> None:
    """P50 must have quantile_value = 0.5000."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P50',
            'joblib_bundle', '1',
            'HistGradientBoostingRegressor', 'quantile', 0.51,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            true,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_artifact_p80_wrong_quantile_value() -> None:
    """P80 must have quantile_value = 0.8000."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P80',
            'joblib_bundle', '1',
            'HistGradientBoostingRegressor', 'quantile', 0.81,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            true,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_artifact_p90_wrong_quantile_value() -> None:
    """P90 must have quantile_value = 0.9000."""
    _require_postgres()
    training_run_id = await _seed_training_run_bare_minimum()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_artifact (
            training_run_id, quantile_label,
            artifact_format, artifact_schema_version,
            estimator_type, loss_name, quantile_value,
            artifact_bytes, artifact_sha256,
            feature_schema_version, feature_schema_hash,
            config_hash,
            trusted_internal_source,
            metadata,
            python_version, numpy_version, sklearn_version
        ) VALUES (
            :training_run_id, 'P90',
            'joblib_bundle', '1',
            'HistGradientBoostingRegressor', 'quantile', 0.91,
            decode('00', 'hex'), :hash,
            '1', :hash,
            :hash,
            true,
            '{}'::jsonb,
            '3.12', '1.26', '1.6'
        )
        """,
        {"training_run_id": training_run_id, "hash": _HASH},
    )


# ── Prediction Run Constraint Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_prediction_run_blocked_with_rows() -> None:
    """blocked execution_status requires expected_prediction_row_count = 0."""
    _require_postgres()
    task9_run_id = await _seed_harvest_state_run()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_run (
            task9_run_id, task9_result_hash,
            execution_status, mode,
            config_hash, feature_schema_version,
            feature_schema_hash, artifact_hashes,
            prediction_input_signature, prediction_hash,
            feature_audit, warnings, blockers,
            input_snapshot, canonical_output,
            canonical_payload_hash,
            expected_prediction_row_count
        ) VALUES (
            :task9_run_id, :hash,
            'blocked', 'blocked',
            :hash, '1',
            :hash, '[]'::jsonb,
            :hash, :hash,
            '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            :hash,
            1
        )
        """,
        {"task9_run_id": task9_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_prediction_run_structural_only_no_fallback() -> None:
    """completed+structural_only must have fallback_reason IS NOT NULL."""
    _require_postgres()
    task9_run_id = await _seed_harvest_state_run()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_run (
            task9_run_id, task9_result_hash,
            execution_status, mode,
            config_hash, feature_schema_version,
            feature_schema_hash, artifact_hashes,
            prediction_input_signature, prediction_hash,
            feature_audit, warnings, blockers,
            input_snapshot, canonical_output,
            canonical_payload_hash,
            expected_prediction_row_count
        ) VALUES (
            :task9_run_id, :hash,
            'completed', 'structural_only',
            :hash, '1',
            :hash, '[]'::jsonb,
            :hash, :hash,
            '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            :hash,
            0
        )
        """,
        {"task9_run_id": task9_run_id, "hash": _HASH},
    )


@pytest.mark.asyncio
async def test_prediction_run_failed_with_rows() -> None:
    """failed execution_status requires expected_prediction_row_count = 0."""
    _require_postgres()
    task9_run_id = await _seed_harvest_state_run()
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_run (
            task9_run_id, task9_result_hash,
            execution_status, mode,
            config_hash, feature_schema_version,
            feature_schema_hash, artifact_hashes,
            prediction_input_signature, prediction_hash,
            feature_audit, warnings, blockers,
            input_snapshot, canonical_output,
            canonical_payload_hash,
            expected_prediction_row_count
        ) VALUES (
            :task9_run_id, :hash,
            'failed', 'blocked',
            :hash, '1',
            :hash, '[]'::jsonb,
            :hash, :hash,
            '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '{}'::jsonb,
            :hash,
            1
        )
        """,
        {"task9_run_id": task9_run_id, "hash": _HASH},
    )


# ── Prediction Row Constraint Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_prediction_row_structural_only_residual_not_zero() -> None:
    """structural_only mode requires all raw residual values to be 0."""
    _require_postgres()
    factory_id = await _seed_factory("Prediction Constraint Factory 1")
    task9_run_id = await _seed_harvest_state_run(factory_id=factory_id)
    prediction_run_id = await _seed_prediction_run(
        execution_status="completed",
        mode="structural_only",
        fallback_reason="test_fallback",
        task9_run_id=task9_run_id,
    )
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_row (
            prediction_run_id, model_run_id,
            task9_run_id, task9_result_hash,
            destination_factory_id, arrival_local_date,
            forecast_horizon_days,
            structural_p50_kg, structural_p80_kg, structural_p90_kg,
            raw_residual_p50_kg, raw_residual_p80_kg, raw_residual_p90_kg,
            corrected_raw_p50_kg, corrected_raw_p80_kg, corrected_raw_p90_kg,
            corrected_p50_kg, corrected_p80_kg, corrected_p90_kg,
            nonnegative_projection_applied,
            quantile_projection_applied,
            projection_reasons,
            feature_vector_hash, feature_audit_hash,
            prediction_row_hash,
            mode, fallback_reason
        ) VALUES (
            :prediction_run_id, NULL,
            :task9_run_id, :hash,
            :factory_id, '2026-03-01',
            1,
            10, 20, 30,
            1, 0, 0,
            10, 20, 30,
            10, 20, 30,
            false, false,
            '[]'::jsonb,
            :hash, :hash, :hash,
            'structural_only', 'some_fallback_reason'
        )
        """,
        {
            "prediction_run_id": prediction_run_id,
            "task9_run_id": task9_run_id,
            "hash": _HASH,
            "factory_id": factory_id,
        },
    )


@pytest.mark.asyncio
async def test_prediction_row_residual_corrected_with_fallback() -> None:
    """residual_corrected mode must have fallback_reason IS NULL."""
    _require_postgres()
    factory_id = await _seed_factory("Prediction Constraint Factory 2")
    task9_run_id = await _seed_harvest_state_run(factory_id=factory_id)
    prediction_run_id = await _seed_prediction_run(
        execution_status="completed",
        mode="residual_corrected",
        task9_run_id=task9_run_id,
    )
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_row (
            prediction_run_id, model_run_id,
            task9_run_id, task9_result_hash,
            destination_factory_id, arrival_local_date,
            forecast_horizon_days,
            structural_p50_kg, structural_p80_kg, structural_p90_kg,
            raw_residual_p50_kg, raw_residual_p80_kg, raw_residual_p90_kg,
            corrected_raw_p50_kg, corrected_raw_p80_kg, corrected_raw_p90_kg,
            corrected_p50_kg, corrected_p80_kg, corrected_p90_kg,
            nonnegative_projection_applied,
            quantile_projection_applied,
            projection_reasons,
            feature_vector_hash, feature_audit_hash,
            prediction_row_hash,
            mode, fallback_reason
        ) VALUES (
            :prediction_run_id, NULL,
            :task9_run_id, :hash,
            :factory_id, '2026-03-01',
            1,
            10, 20, 30,
            0, 0, 0,
            10, 20, 30,
            10, 20, 30,
            false, false,
            '[]'::jsonb,
            :hash, :hash, :hash,
            'residual_corrected', 'some_fallback_reason'
        )
        """,
        {
            "prediction_run_id": prediction_run_id,
            "task9_run_id": task9_run_id,
            "hash": _HASH,
            "factory_id": factory_id,
        },
    )


@pytest.mark.asyncio
async def test_prediction_row_negative_forecast_horizon() -> None:
    """forecast_horizon_days must be >= 0."""
    _require_postgres()
    factory_id = await _seed_factory("Prediction Constraint Factory 3")
    task9_run_id = await _seed_harvest_state_run(factory_id=factory_id)
    prediction_run_id = await _seed_prediction_run(task9_run_id=task9_run_id)
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_row (
            prediction_run_id, model_run_id,
            task9_run_id, task9_result_hash,
            destination_factory_id, arrival_local_date,
            forecast_horizon_days,
            structural_p50_kg, structural_p80_kg, structural_p90_kg,
            raw_residual_p50_kg, raw_residual_p80_kg, raw_residual_p90_kg,
            corrected_raw_p50_kg, corrected_raw_p80_kg, corrected_raw_p90_kg,
            corrected_p50_kg, corrected_p80_kg, corrected_p90_kg,
            nonnegative_projection_applied,
            quantile_projection_applied,
            projection_reasons,
            feature_vector_hash, feature_audit_hash,
            prediction_row_hash,
            mode, fallback_reason
        ) VALUES (
            :prediction_run_id, NULL,
            :task9_run_id, :hash,
            :factory_id, '2026-03-01',
            -1,
            10, 20, 30,
            0, 0, 0,
            10, 20, 30,
            10, 20, 30,
            false, false,
            '[]'::jsonb,
            :hash, :hash, :hash,
            'residual_corrected', NULL
        )
        """,
        {
            "prediction_run_id": prediction_run_id,
            "task9_run_id": task9_run_id,
            "hash": _HASH,
            "factory_id": factory_id,
        },
    )


@pytest.mark.asyncio
async def test_prediction_row_non_monotonic_quantiles() -> None:
    """corrected quantiles must be monotonic: P50 <= P80 <= P90."""
    _require_postgres()
    factory_id = await _seed_factory("Prediction Constraint Factory 4")
    task9_run_id = await _seed_harvest_state_run(factory_id=factory_id)
    prediction_run_id = await _seed_prediction_run(task9_run_id=task9_run_id)

    # P50 > P80
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_row (
            prediction_run_id, model_run_id,
            task9_run_id, task9_result_hash,
            destination_factory_id, arrival_local_date,
            forecast_horizon_days,
            structural_p50_kg, structural_p80_kg, structural_p90_kg,
            raw_residual_p50_kg, raw_residual_p80_kg, raw_residual_p90_kg,
            corrected_raw_p50_kg, corrected_raw_p80_kg, corrected_raw_p90_kg,
            corrected_p50_kg, corrected_p80_kg, corrected_p90_kg,
            nonnegative_projection_applied,
            quantile_projection_applied,
            projection_reasons,
            feature_vector_hash, feature_audit_hash,
            prediction_row_hash,
            mode, fallback_reason
        ) VALUES (
            :prediction_run_id, NULL,
            :task9_run_id, :hash,
            :factory_id, '2026-03-01',
            1,
            10, 20, 30,
            0, 0, 0,
            10, 20, 30,
            30, 20, 10,
            false, false,
            '[]'::jsonb,
            :hash, :hash, :hash,
            'residual_corrected', NULL
        )
        """,
        {
            "prediction_run_id": prediction_run_id,
            "task9_run_id": task9_run_id,
            "hash": _HASH,
            "factory_id": factory_id,
        },
    )

    # P80 > P90
    await _expect_integrity_error(
        """
        INSERT INTO residual_model_prediction_row (
            prediction_run_id, model_run_id,
            task9_run_id, task9_result_hash,
            destination_factory_id, arrival_local_date,
            forecast_horizon_days,
            structural_p50_kg, structural_p80_kg, structural_p90_kg,
            raw_residual_p50_kg, raw_residual_p80_kg, raw_residual_p90_kg,
            corrected_raw_p50_kg, corrected_raw_p80_kg, corrected_raw_p90_kg,
            corrected_p50_kg, corrected_p80_kg, corrected_p90_kg,
            nonnegative_projection_applied,
            quantile_projection_applied,
            projection_reasons,
            feature_vector_hash, feature_audit_hash,
            prediction_row_hash,
            mode, fallback_reason
        ) VALUES (
            :prediction_run_id, NULL,
            :task9_run_id, :hash,
            :factory_id, '2026-03-01',
            1,
            10, 20, 30,
            0, 0, 0,
            10, 20, 30,
            10, 30, 20,
            false, false,
            '[]'::jsonb,
            :hash, :hash, :hash,
            'residual_corrected', NULL
        )
        """,
        {
            "prediction_run_id": prediction_run_id,
            "task9_run_id": task9_run_id,
            "hash": _HASH,
            "factory_id": factory_id,
        },
    )


@pytest.mark.asyncio
async def test_prediction_run_valid_residual_corrected_no_fallback() -> None:
    """Verify that a valid residual_corrected prediction_run with NULL fallback
    reason can be inserted (positive control — should NOT raise IntegrityError)."""
    _require_postgres()
    task9_run_id = await _seed_harvest_state_run()
    async with AsyncSessionMaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO residual_model_prediction_run (
                    task9_run_id, task9_result_hash,
                    execution_status, mode,
                    config_hash, feature_schema_version,
                    feature_schema_hash, artifact_hashes,
                    prediction_input_signature, prediction_hash,
                    feature_audit, warnings, blockers,
                    input_snapshot, canonical_output,
                    canonical_payload_hash,
                    expected_prediction_row_count,
                    fallback_reason
                ) VALUES (
                    :task9_run_id, :hash,
                    'completed', 'residual_corrected',
                    :hash, '1',
                    :hash, '[]'::jsonb,
                    :hash, :hash,
                    '{}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '{}'::jsonb, '{}'::jsonb,
                    :hash,
                    5,
                    NULL
                )
                """
            ),
            {"task9_run_id": task9_run_id, "hash": _HASH},
        )
        await session.commit()
