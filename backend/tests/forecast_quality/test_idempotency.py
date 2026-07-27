"""PostgreSQL replay and concurrency acceptance for Round B."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy import func, insert, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.persistence import (
    ForecastQualityConflictError,
    ForecastQualityContractError,
    ForecastQualityPartialResultError,
    _validate_evaluation_input,
)
from backend.app.forecast_quality.schemas import S3EvaluationInput
from backend.app.models.forecast_quality import (
    ModelBaselineComparisonModel,
    NaiveBaselineRunModel,
    QualityBreakdownResultModel,
    QualityEvaluationManifestModel,
    QualityEvaluationRunModel,
    QualityMetricResultModel,
)
from backend.tests.forecast_quality.test_persistence import (
    _fixture,
    _live_env,
    _persist,
)

pytestmark = [pytest.mark.postgres]


def _db_url(env: dict[str, str]) -> str:
    return (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )


async def _tamper_column(
    env: dict[str, str],
    *,
    table: str,
    column: str,
    trigger: str,
    value: object,
    row_id: int,
) -> None:
    conn = await asyncpg.connect(_db_url(env))
    try:
        await conn.execute("BEGIN")
        await conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        await conn.execute(
            f"UPDATE {table} SET {column} = $1 WHERE id = $2",
            value,
            row_id,
        )
        await conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")
        await conn.execute("COMMIT")
    except BaseException:
        await conn.execute("ROLLBACK")
        raise
    finally:
        await conn.close()


async def _seed_unsealed_run(env: dict[str, str], input_data: S3EvaluationInput) -> int:
    payload, request_hash, run_hash = _validate_evaluation_input(input_data)
    conn = await asyncpg.connect(_db_url(env))
    try:
        run_id = await conn.fetchval(
            """
            INSERT INTO quality_evaluation_run (
                schema_version, evaluation_request_hash, s2_run_identity,
                s2_manifest_identity, s2_binding_row_set_hash,
                metric_policy_version, baseline_policy_version, status,
                canonical_payload, canonical_hash, completed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'COMPLETE', $8::jsonb, $9, now())
            RETURNING id
            """,
            "v0.2-s3-quality-persistence-v1",
            request_hash,
            input_data.s2_run_identity,
            input_data.s2_manifest_identity,
            input_data.s2_binding_row_set_hash,
            input_data.metric_policy_version.value,
            input_data.baseline_policy_version.value,
            json.dumps(payload),
            run_hash,
        )
        assert run_id is not None
        return run_id
    finally:
        await conn.close()


async def _insert_race_child(conn: asyncpg.Connection, run_id: int) -> str:
    await conn.execute("BEGIN")
    try:
        await conn.execute(
            """
            INSERT INTO quality_metric_result (
                quality_evaluation_run_id, schema_version, metric_result_key_hash,
                metric_name, metric_status, reason_code, breakdown_identity,
                canonical_payload, canonical_hash, completed_at
            ) VALUES ($1, $2, $3, 'daily_mae', 'COMPUTED', 'NONE',
                      '{}'::jsonb, '{}'::jsonb, $4, now())
            """,
            run_id,
            "v0.2-s3-quality-persistence-v1",
            "e" * 64,
            hashlib.sha256(canonical_json_bytes({})).hexdigest(),
        )
        await conn.execute("COMMIT")
        return "committed"
    except asyncpg.PostgresError:
        await conn.execute("ROLLBACK")
        return "rejected"


@pytest.mark.asyncio
async def test_exact_replay_is_zero_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("exact-replay")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            first = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        async with session.begin():
            second = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        assert first.run_id == second.run_id
        assert first.manifest_id == second.manifest_id
        assert second.new_write_count == 0
        assert second.replayed is True
        assert await session.scalar(select(func.count(QualityEvaluationRunModel.id))) == 1
        assert await session.scalar(select(func.count(QualityMetricResultModel.id))) == 7
        assert await session.scalar(select(func.count(QualityEvaluationManifestModel.id))) == 1


@pytest.mark.asyncio
async def test_conflicting_replay_is_rejected_without_second_run() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("conflicting-replay")
    request_hash = _validate_evaluation_input(input_data)[1]
    changed_input, changed_metric, changed_breakdowns, changed_baseline = _fixture(
        "conflicting-replay", forecast_value=Decimal("99")
    )
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        async with session.begin():
            with pytest.raises(ForecastQualityConflictError, match="CONFLICTING_REPLAY_REJECTED"):
                await _persist(
                    session,
                    evaluation_input=changed_input,
                    metric_result=changed_metric,
                    breakdown_results=changed_breakdowns,
                    baseline_record=changed_baseline,
                )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_partial_existing_result_fails_closed() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("partial-result")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: sync_session.execute(
                    insert(QualityEvaluationRunModel).values(
                        schema_version="v0.2-s3-quality-persistence-v1",
                        evaluation_request_hash=_validate_evaluation_input(input_data)[1],
                        s2_run_identity=input_data.s2_run_identity,
                        s2_manifest_identity=input_data.s2_manifest_identity,
                        s2_binding_row_set_hash=input_data.s2_binding_row_set_hash,
                        metric_policy_version=input_data.metric_policy_version.value,
                        baseline_policy_version=input_data.baseline_policy_version.value,
                        status="COMPLETE",
                        canonical_payload={
                            "schema_version": "v0.2-s3-quality-persistence-v1",
                            "s2_run_identity": input_data.s2_run_identity,
                            "s2_manifest_identity": input_data.s2_manifest_identity,
                            "s2_binding_row_set_hash": input_data.s2_binding_row_set_hash,
                            "metric_policy_version": input_data.metric_policy_version.value,
                            "baseline_policy_version": input_data.baseline_policy_version.value,
                        },
                        canonical_hash=_validate_evaluation_input(input_data)[2],
                        completed_at=datetime.now(UTC),
                    )
                )
            )
        with pytest.raises(ForecastQualityPartialResultError, match="PARTIAL"):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )


@pytest.mark.asyncio
async def test_baseline_association_mismatch_fails_before_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("baseline-mismatch")
    request_hash = _validate_evaluation_input(input_data)[1]
    bad_result = replace(baseline.result, baseline_quantile="P80")
    bad_record = replace(baseline, result=bad_result)
    async with AsyncSessionMaker() as session:
        with pytest.raises(ForecastQualityContractError, match="quantile mismatch"):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=bad_record,
            )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_hash_invalid_existing_replay_is_forbidden() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("hash-invalid-replay")
    payload, request_hash, _ = _validate_evaluation_input(input_data)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: sync_session.execute(
                    insert(QualityEvaluationRunModel).values(
                        schema_version="v0.2-s3-quality-persistence-v1",
                        evaluation_request_hash=request_hash,
                        s2_run_identity=input_data.s2_run_identity,
                        s2_manifest_identity=input_data.s2_manifest_identity,
                        s2_binding_row_set_hash=input_data.s2_binding_row_set_hash,
                        metric_policy_version=input_data.metric_policy_version.value,
                        baseline_policy_version=input_data.baseline_policy_version.value,
                        status="COMPLETE",
                        canonical_payload=payload,
                        canonical_hash="f" * 64,
                        completed_at=datetime.now(UTC),
                    )
                )
            )
        with pytest.raises(
            ForecastQualityPartialResultError,
            match="PARTIAL_METRIC_PERSISTENCE_FORBIDDEN",
        ):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )


@pytest.mark.asyncio
async def test_caller_owned_rollback_after_flush_leaves_all_round_b_rows_zero() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("rollback-after-flush")
    request_hash = _validate_evaluation_input(input_data)[1]

    class ExpectedOuterRollback(RuntimeError):
        pass

    async with AsyncSessionMaker() as session:
        with pytest.raises(ExpectedOuterRollback):
            async with session.begin():
                persisted = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                )
                assert persisted.new_write_count == 11
                assert (
                    await session.scalar(
                        select(func.count(QualityEvaluationRunModel.id)).where(
                            QualityEvaluationRunModel.id == persisted.run_id
                        )
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(QualityMetricResultModel.id)).where(
                            QualityMetricResultModel.quality_evaluation_run_id == persisted.run_id
                        )
                    )
                    == 7
                )
                assert (
                    await session.scalar(
                        select(func.count(QualityBreakdownResultModel.id)).where(
                            QualityBreakdownResultModel.quality_evaluation_run_id
                            == persisted.run_id
                        )
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(NaiveBaselineRunModel.id)).where(
                            NaiveBaselineRunModel.quality_evaluation_run_id == persisted.run_id
                        )
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(QualityEvaluationManifestModel.id)).where(
                            QualityEvaluationManifestModel.quality_evaluation_run_id
                            == persisted.run_id
                        )
                    )
                    == 1
                )
                raise ExpectedOuterRollback

    async with AsyncSessionMaker() as verification_session:
        run_id = (
            select(QualityEvaluationRunModel.id)
            .where(QualityEvaluationRunModel.evaluation_request_hash == request_hash)
            .scalar_subquery()
        )
        assert (
            await verification_session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )
        for model in (
            QualityMetricResultModel,
            QualityBreakdownResultModel,
            NaiveBaselineRunModel,
            ModelBaselineComparisonModel,
            QualityEvaluationManifestModel,
        ):
            assert (
                await verification_session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.quality_evaluation_run_id == run_id)
                )
                == 0
            )


@pytest.mark.asyncio
async def test_identical_baseline_evidence_is_reusable_across_runs() -> None:
    _live_env()
    input_a, metric_a, breakdowns_a, baseline = _fixture("baseline-reuse-a")
    input_b, metric_b, breakdowns_b, _ = _fixture("baseline-reuse-b")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            first = await _persist(
                session,
                evaluation_input=input_a,
                metric_result=metric_a,
                breakdown_results=breakdowns_a,
                baseline_record=baseline,
            )
        async with session.begin():
            second = await _persist(
                session,
                evaluation_input=input_b,
                metric_result=metric_b,
                breakdown_results=breakdowns_b,
                baseline_record=baseline,
            )
        assert first.run_id != second.run_id
        baselines = (
            await session.scalars(
                select(NaiveBaselineRunModel)
                .where(
                    NaiveBaselineRunModel.quality_evaluation_run_id.in_(
                        (first.run_id, second.run_id)
                    )
                )
                .order_by(NaiveBaselineRunModel.id)
            )
        ).all()
        assert len(baselines) == 2
        assert baselines[0].canonical_hash == baselines[1].canonical_hash


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    ("metric_key", "baseline_key", "manifest_set_hash", "stored_payload_hash"),
)
async def test_corrupted_replay_projections_fail_closed(corruption: str) -> None:
    env = _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture(f"corruption-{corruption}")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            persisted = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        metric_id = await session.scalar(
            select(QualityMetricResultModel.id).where(
                QualityMetricResultModel.quality_evaluation_run_id == persisted.run_id
            )
        )
        baseline_id = await session.scalar(
            select(NaiveBaselineRunModel.id).where(
                NaiveBaselineRunModel.quality_evaluation_run_id == persisted.run_id
            )
        )
        assert metric_id is not None and baseline_id is not None
        if corruption == "metric_key":
            await _tamper_column(
                env,
                table="quality_metric_result",
                column="metric_result_key_hash",
                trigger="trg_quality_quality_metric_result_immutable",
                value="f" * 64,
                row_id=metric_id,
            )
        elif corruption == "baseline_key":
            await _tamper_column(
                env,
                table="naive_baseline_run",
                column="baseline_request_hash",
                trigger="trg_quality_naive_baseline_run_immutable",
                value="e" * 64,
                row_id=baseline_id,
            )
        elif corruption == "manifest_set_hash":
            await _tamper_column(
                env,
                table="quality_evaluation_manifest",
                column="metric_result_set_hash",
                trigger="trg_quality_quality_evaluation_manifest_immutable",
                value="f" * 64,
                row_id=persisted.manifest_id,
            )
        else:
            await _tamper_column(
                env,
                table="quality_metric_result",
                column="canonical_payload",
                trigger="trg_quality_quality_metric_result_immutable",
                value=json.dumps({"tampered": True}),
                row_id=metric_id,
            )

        with pytest.raises(
            ForecastQualityPartialResultError,
            match="PARTIAL_METRIC_PERSISTENCE_FORBIDDEN",
        ):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
@pytest.mark.concurrency
async def test_concurrent_identical_writes_converge_to_one_result() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("concurrent-identical")
    barrier = asyncio.Barrier(2)

    async def invoke() -> tuple[int, bool]:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await barrier.wait()
                result = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                )
                return result.run_id, result.replayed

    first, second = await asyncio.wait_for(asyncio.gather(invoke(), invoke()), timeout=60)
    assert first[0] == second[0]
    assert sorted((first[1], second[1])) == [False, True]
    async with AsyncSessionMaker() as session:
        assert await session.scalar(select(func.count(QualityEvaluationRunModel.id))) == 1
        assert await session.scalar(select(func.count(QualityEvaluationManifestModel.id))) == 1


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
@pytest.mark.concurrency
async def test_concurrent_conflicting_writes_have_one_conflict() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("concurrent-conflict")
    request_hash = _validate_evaluation_input(input_data)[1]
    changed_input, changed_metric, changed_breakdowns, changed_baseline = _fixture(
        "concurrent-conflict", forecast_value=Decimal("77")
    )
    barrier = asyncio.Barrier(2)

    async def invoke(current_input, current_metric, current_breakdowns, current_baseline) -> str:
        async with AsyncSessionMaker() as session:
            try:
                async with session.begin():
                    await barrier.wait()
                    result = await _persist(
                        session,
                        evaluation_input=current_input,
                        metric_result=current_metric,
                        breakdown_results=current_breakdowns,
                        baseline_record=current_baseline,
                    )
                    return "replayed" if result.replayed else "winner"
            except ForecastQualityConflictError:
                return "conflict"

    outcomes = await asyncio.wait_for(
        asyncio.gather(
            invoke(input_data, metric_result, breakdowns, baseline),
            invoke(changed_input, changed_metric, changed_breakdowns, changed_baseline),
        ),
        timeout=60,
    )
    assert sorted(outcomes) == ["conflict", "winner"]
    async with AsyncSessionMaker() as session:
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
@pytest.mark.concurrency
async def test_concurrent_manifest_seal_vs_child_insert_is_serialized() -> None:
    env = _live_env()
    input_data, _, _, _ = _fixture("manifest-child-race")
    run_id = await _seed_unsealed_run(env, input_data)
    manifest_conn = await asyncpg.connect(_db_url(env))
    child_conn = await asyncpg.connect(_db_url(env))
    child_task: asyncio.Task[str] | None = None
    try:
        await manifest_conn.execute("BEGIN")
        await manifest_conn.fetchrow(
            "SELECT id FROM quality_evaluation_run WHERE id = $1 FOR UPDATE", run_id
        )
        child_task = asyncio.create_task(_insert_race_child(child_conn, run_id))
        await asyncio.sleep(0.05)
        manifest_payload = {}
        await manifest_conn.execute(
            """
            INSERT INTO quality_evaluation_manifest (
                quality_evaluation_run_id, schema_version,
                evaluation_request_hash, evaluation_instance_hash,
                metric_result_set_hash, breakdown_result_set_hash,
                baseline_result_set_hash, comparison_result_set_hash,
                comparison_policy_version, comparison_result_schema_version,
                comparison_result_set_schema_version, comparison_cell_count,
                comparison_result_count,
                manifest_payload, manifest_hash, completed_at, sealed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL, NULL,
                      'v0.2-s3-comparison-result-set-v1', 0, 0,
                      $9::jsonb, $10, now(), now())
            """,
            run_id,
            "v0.2-s3-quality-persistence-v1",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            "e" * 64,
            "f" * 64,
            json.dumps(manifest_payload),
            hashlib.sha256(canonical_json_bytes(manifest_payload)).hexdigest(),
        )
        await manifest_conn.execute("COMMIT")
        assert await asyncio.wait_for(child_task, timeout=30) == "rejected"
        child_task = None
    finally:
        if child_task is not None:
            child_task.cancel()
            await child_task
        await manifest_conn.close()
        await child_conn.close()

    verify_conn = await asyncpg.connect(_db_url(env))
    try:
        assert (
            await verify_conn.fetchval(
                "SELECT count(*) FROM quality_evaluation_manifest "
                "WHERE quality_evaluation_run_id = $1",
                run_id,
            )
            == 1
        )
        assert (
            await verify_conn.fetchval(
                "SELECT count(*) FROM quality_metric_result WHERE quality_evaluation_run_id = $1",
                run_id,
            )
            == 0
        )
    finally:
        await verify_conn.close()
