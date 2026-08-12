from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.schemas import Task9ACompletedOutput
from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.residual_model.analytics_authority import (
    ANALYTICS_FACTORY_RECEIPT_SOURCE_CLASS,
    bind_analytics_feature_authority,
)
from backend.app.residual_model.enums import ForecastInputSourceClass
from backend.app.residual_model.planning_authority import (
    PlanningFeatureAuthorityError,
    bind_planning_feature_authority,
)
from backend.app.residual_model.schemas import FeatureValue
from backend.app.residual_model.task9_mixed_authority import (
    Task9MixedAuthorityError,
    bind_task9_feature_provenance,
    validate_task9_mixed_authority,
)
from backend.app.residual_model.visibility import audit_feature_visibility
from backend.tests.residual_model.test_training_manifest import (
    _persist_task9_run,
    _seed_master_data,
)

pytestmark = pytest.mark.asyncio
pytest_plugins = ("backend.tests.residual_model.test_training_manifest",)


def _planning_feature(**updates: object) -> FeatureValue:
    source_ref: dict[str, object] = {
        "plan_id": 501,
        "plan_version": 1,
        "plan_row_hash": "f" * 64,
        "farm_id": 1,
        "subfarm_id": 11,
        "season_id": 1,
        "variety_id": 101,
    }
    source_ref.update(updates)
    return FeatureValue(
        feature_name="destination_factory_category",
        value="north",
        known_at=datetime(2026, 2, 28, 12, tzinfo=UTC),
        source_ref=source_ref,
        source_version="caller-value-must-be-replaced",
        source_available_at=datetime(2026, 2, 28, 12, tzinfo=UTC),
    )


def _analytics_feature(
    feature_name: str = "realized_cumulative_residual_to_as_of_kg",
) -> FeatureValue:
    return FeatureValue(
        feature_name=feature_name,
        value=Decimal("12"),
        known_at=datetime(2026, 2, 28, 12, tzinfo=UTC),
        source_ref={"caller": "must-not-be-authority"},
        source_version="caller-v1",
        source_available_at=datetime(2026, 2, 28, 12, tzinfo=UTC),
        observation_date=date(2026, 2, 27),
    )


def _analytics_build(*, finished_at: datetime) -> AnalyticsBuildRun:
    return AnalyticsBuildRun(
        id=7,
        season_id=1,
        aggregation_version="analytics-v1",
        source_max_raw_id=99,
        config_hash="a" * 64,
        config_snapshot={"analysis_months": [1, 2, 3]},
        status="completed",
        started_at=finished_at,
        finished_at=finished_at,
    )


def _with_task8_available_at(
    output: Task9ACompletedOutput,
    available_at: datetime,
) -> Task9ACompletedOutput:
    rows = deepcopy(output.source_ref_catalog)
    for entry in rows:
        if entry.source_ref_type.value == "TASK8_DAILY_PREDICTION":
            entry.source_ref_payload["maturity_daily_prediction_available_at"] = available_at
    return output.model_copy(update={"source_ref_catalog": rows})


async def test_planning_authority_reloads_effective_persisted_plan(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)

    bound = await bind_planning_feature_authority(
        sqlite_session,
        feature_values=(_planning_feature(),),
        as_of_date=date(2026, 2, 28),
    )

    assert (
        bound[0].source_ref["source_class"]
        == ForecastInputSourceClass.PRODUCTION_PLAN_EFFECTIVE_VERSION
    )
    assert bound[0].source_ref["plan_id"] == 501
    assert bound[0].source_ref["plan_row_hash"] == "f" * 64
    assert bound[0].source_version == "test-plan-v1"


@pytest.mark.parametrize(
    "updates",
    [
        {"plan_id": 999},
        {"plan_version": 99},
        {"plan_row_hash": "e" * 64},
    ],
)
async def test_planning_authority_rejects_identity_tampering(
    sqlite_session: AsyncSession,
    updates: dict[str, object],
) -> None:
    await _seed_master_data(sqlite_session)
    with pytest.raises(PlanningFeatureAuthorityError):
        await bind_planning_feature_authority(
            sqlite_session,
            feature_values=(_planning_feature(**updates),),
            as_of_date=date(2026, 2, 28),
        )


async def test_planning_authority_rejects_effective_plan_conflict(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    from backend.app.models.production_plan import FarmSeasonVarietyPlan

    sqlite_session.add(
        FarmSeasonVarietyPlan(
            id=502,
            farm_id=1,
            subfarm_id=11,
            season_id=1,
            variety_id=101,
            planted_area_mu=Decimal("100"),
            expected_yield_kg_per_mu=Decimal("1200"),
            marketable_rate=Decimal("0.8"),
            version=2,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            available_at=date(2026, 1, 1),
            source_type="test-plan",
            source_name="test",
            source_version="test-plan-v2",
            row_hash="e" * 64,
        )
    )
    await sqlite_session.flush()
    with pytest.raises(PlanningFeatureAuthorityError, match="multiple effective"):
        await bind_planning_feature_authority(
            sqlite_session,
            feature_values=(_planning_feature(),),
            as_of_date=date(2026, 2, 28),
        )


@pytest.mark.parametrize("field_name", ["available_at", "effective_from"])
async def test_planning_authority_rejects_later_or_not_effective_plan(
    sqlite_session: AsyncSession,
    field_name: str,
) -> None:
    await _seed_master_data(sqlite_session)
    from backend.app.models.production_plan import FarmSeasonVarietyPlan

    plan = await sqlite_session.get(FarmSeasonVarietyPlan, 501)
    assert plan is not None
    setattr(plan, field_name, date(2026, 3, 1))
    await sqlite_session.flush()
    with pytest.raises(PlanningFeatureAuthorityError, match="effective persisted"):
        await bind_planning_feature_authority(
            sqlite_session,
            feature_values=(_planning_feature(),),
            as_of_date=date(2026, 2, 28),
        )


@pytest.mark.parametrize(
    "finished_at, expected_allowed",
    [
        (datetime(2026, 2, 28, 11, tzinfo=UTC), True),
        (datetime(2026, 2, 28, 12, tzinfo=UTC), True),
        (datetime(2026, 2, 28, 13, tzinfo=UTC), False),
    ],
)
async def test_analytics_factory_receipt_source_cutoff_is_authoritative(
    finished_at: datetime,
    expected_allowed: bool,
) -> None:
    cutoff = datetime(2026, 2, 28, 12, tzinfo=UTC)
    bound = bind_analytics_feature_authority(
        feature_values=(_analytics_feature(),),
        build_run=_analytics_build(finished_at=finished_at),
        forecast_cutoff_at=cutoff,
    )
    assert bound[0].source_ref["source_class"] == ANALYTICS_FACTORY_RECEIPT_SOURCE_CLASS
    assert bound[0].source_ref["analytics_build_run_id"] == 7
    assert bound[0].source_available_at == finished_at
    audit = audit_feature_visibility(
        features=bound,
        as_of_date=date(2026, 2, 28),
        forecast_cutoff_at=cutoff,
        for_training=False,
    )
    assert (audit.status == "completed") is expected_allowed


async def test_task9_mixed_authority_classifies_refs_and_is_deterministic(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    output = _with_task8_available_at(
        output,
        datetime(2026, 2, 28, 12, tzinfo=UTC),
    )
    run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert run is not None
    run.is_replay = True
    run.forecast_effective_cutoff_at = datetime(2026, 3, 1, 4, tzinfo=UTC)
    await sqlite_session.commit()

    first = await validate_task9_mixed_authority(
        sqlite_session,
        task9_run_id=task9_run_id,
        output=output,
        forecast_cutoff_at=run.forecast_effective_cutoff_at,
    )
    second = await validate_task9_mixed_authority(
        sqlite_session,
        task9_run_id=task9_run_id,
        output=output,
        forecast_cutoff_at=run.forecast_effective_cutoff_at,
    )
    assert first.evidence_hash == second.evidence_hash
    feature = FeatureValue(
        feature_name="structural_arrival_p50_kg",
        value=Decimal("1"),
        known_at=first.forecast_cutoff_at,
        source_ref={"task9_run_id": task9_run_id},
        source_version="task9-completed-v1",
        source_available_at=first.forecast_cutoff_at,
    )
    bound = bind_task9_feature_provenance((feature,), evidence=first)
    assert bound[0].source_ref["task9_mixed_authority_validated"] is True
    assert bound[0].source_ref["task9_mixed_authority_evidence_hash"] == first.evidence_hash


async def test_task9_replay_missing_exact_task8_timestamp_is_blocked(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    output = _with_task8_available_at(
        output,
        datetime(2026, 2, 28, 12, tzinfo=UTC),
    )
    run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert run is not None
    run.is_replay = True
    await sqlite_session.commit()
    rows = deepcopy(output.source_ref_catalog)
    task8_entry = next(
        item for item in rows if item.source_ref_type.value == "TASK8_DAILY_PREDICTION"
    )
    task8_entry.source_ref_payload.pop("maturity_daily_prediction_available_at", None)
    mutated = output.model_copy(update={"source_ref_catalog": rows})

    with pytest.raises(Task9MixedAuthorityError, match="missing Task 8 exact availability"):
        await validate_task9_mixed_authority(
            sqlite_session,
            task9_run_id=task9_run_id,
            output=mutated,
            forecast_cutoff_at=datetime(2026, 3, 1, 4, tzinfo=UTC),
        )


async def test_task9_exact_timestamp_after_cutoff_is_blocked(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    cutoff = datetime(2026, 3, 1, 4, tzinfo=UTC)
    output = _with_task8_available_at(output, cutoff.replace(second=1))
    run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert run is not None
    run.is_replay = True
    await sqlite_session.commit()

    with pytest.raises(Task9MixedAuthorityError, match="after the forecast cutoff"):
        await validate_task9_mixed_authority(
            sqlite_session,
            task9_run_id=task9_run_id,
            output=output,
            forecast_cutoff_at=cutoff,
        )


async def test_task9_exact_timestamp_equal_cutoff_is_allowed(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    cutoff = datetime(2026, 3, 1, 4, tzinfo=UTC)
    output = _with_task8_available_at(output, cutoff)
    run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert run is not None
    run.is_replay = True
    await sqlite_session.commit()

    evidence = await validate_task9_mixed_authority(
        sqlite_session,
        task9_run_id=task9_run_id,
        output=output,
        forecast_cutoff_at=cutoff,
    )
    assert evidence.forecast_cutoff_at == cutoff


async def test_task9_local_date_after_as_of_is_blocked(
    sqlite_session: AsyncSession,
) -> None:
    await _seed_master_data(sqlite_session)
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    run = await sqlite_session.get(HarvestStateRun, task9_run_id)
    assert run is not None
    rows = deepcopy(output.source_ref_catalog)
    parameter_entry = next(
        item for item in rows if item.source_ref_type.value == "PARAMETER_SOURCE"
    )
    parameter_entry.source_ref_payload["available_at"] = "2026-03-01"
    mutated = output.model_copy(update={"source_ref_catalog": rows})

    with pytest.raises(Task9MixedAuthorityError, match="available_at is after"):
        await validate_task9_mixed_authority(
            sqlite_session,
            task9_run_id=task9_run_id,
            output=mutated,
            forecast_cutoff_at=datetime(2026, 3, 1, 4, tzinfo=UTC),
        )
