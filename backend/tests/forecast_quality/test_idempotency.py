"""PostgreSQL replay and concurrency acceptance for Round B."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, insert, select

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.persistence import (
    ForecastQualityConflictError,
    ForecastQualityContractError,
    ForecastQualityPartialResultError,
    _validate_evaluation_input,
)
from backend.app.models.forecast_quality import (
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
async def test_transaction_rollback_leaves_zero_round_b_rows() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("rollback")
    request_hash = _validate_evaluation_input(input_data)[1]
    async with AsyncSessionMaker() as session:
        try:
            async with session.begin():
                await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                    manifest_payload={"s2_run_identity": "wrong"},
                )
        except ForecastQualityContractError:
            pass
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationManifestModel.id))
                .join(
                    QualityEvaluationRunModel,
                    QualityEvaluationManifestModel.quality_evaluation_run_id
                    == QualityEvaluationRunModel.id,
                )
                .where(QualityEvaluationRunModel.evaluation_request_hash == request_hash)
            )
            == 0
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
