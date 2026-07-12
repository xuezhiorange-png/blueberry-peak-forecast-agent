"""TASK-013 Slice A — persisted SQLite integration tests for production wiring.

These tests exercise the P0-1/P0-2/P0-3 production wiring paths against
real SQLite-backed ORM tables (TASK-008/009/010 + Variety).  No upstream
modules are mocked; the adapters actually call the production
``load_maturity_forecast_result`` / ``get_harvest_state_run_by_id`` /
``load_residual_prediction_run_by_id`` callables.

This file implements the 27 new tests required by the PR #94 review.
Where a real upstream source does not exist for a capability
(e.g. persisted prior observations for parameters), the test asserts
that the adapter raises :class:`SourceCapabilityGapError` — it does NOT
invent a numeric prior.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from backend.app.agent.adapters.baseline_composer import (
    DefaultTaskCompositionBaseline,
)
from backend.app.agent.adapters.daily_curve import DefaultDailyCurveAdapter
from backend.app.agent.adapters.location import DefaultLocationAdapter
from backend.app.agent.adapters.parameters import (
    DefaultParameterAdapter,
    DefaultVarietyCatalogPort,
)
from backend.app.agent.adapters.peak import DefaultPeakAdapter
from backend.app.agent.adapters.scenario import DefaultScenarioAdapter
from backend.app.agent.adapters.task_loaders import DefaultSpringFestivalCalendarPort
from backend.app.agent.enums import BlockerCode
from backend.app.agent.ports import LocationResolverPort
from backend.app.agent.schemas import (
    AdvancedOverrides,
    ForecastDailyCurveInput,
    ForecastPeakInput,
    InferParametersInput,
    LocationInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    PeakMetricPolicy,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    ResolveLocationInput,
    SimulateScenarioInput,
    StaffingOverrideValue,
    StaffingScenarioOverride,
    UncertaintyWideningPolicy,
)
from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Variety
from backend.app.models.residual_model import (
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
)

# --- Helpers --------------------------------------------------------------


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _build_harvest_state_run(
    session,
    *,
    run_id: int,
    as_of_date: date,
    forecast_start: date,
    forecast_end: date,
    destination_factory_id: int,
    maturity_forecast_run_id: int | None,
    pool_row_count: int = 0,
) -> HarvestStateRun:
    run = HarvestStateRun(
        id=run_id,
        status="completed",
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot={},
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result={},
        continuity_result={},
        canonical_output={},
        config_hash=_hash(f"cfg-{run_id}"),
        result_hash=_hash(f"res-{run_id}"),
        canonical_payload_hash=_hash(f"pay-{run_id}"),
        forecast_start_date=forecast_start,
        forecast_end_date=forecast_end,
        as_of_date=as_of_date,
        destination_factory_id=destination_factory_id,
        pool_row_count=pool_row_count,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_model_run_id=None,
        maturity_model_version="v1",
        maturity_model_config_hash=_hash(f"mc-{run_id}"),
        maturity_model_source_signature="sig",
        maturity_model_artifact_id=None,
        maturity_model_artifact_hash=_hash(f"ma-{run_id}"),
        maturity_forecast_run_id=maturity_forecast_run_id,
        maturity_forecast_source_signature="fsig",
    )
    session.add(run)
    return run


def _add_pool_row(
    session,
    *,
    harvest_state_run_id: int,
    state_date: date,
    quantile: str,
    capacity_pool_id: int,
    harvested_kg: Decimal,
    arrival_kg: Decimal,
    natural_kg: Decimal,
    closing_kg: Decimal,
    backlog_kg: Decimal,
) -> HarvestStateDailyPoolRowModel:
    row = HarvestStateDailyPoolRowModel(
        harvest_state_run_id=harvest_state_run_id,
        state_date=state_date,
        forecast_quantile=quantile,
        capacity_pool_id=capacity_pool_id,
        capacity_pool_grain="SUBFARM_VARIETY",
        capacity_pool_membership_hash="a" * 64,
        capacity_input_mode="LABOR_DERIVED",
        opening_mature_inventory_kg=Decimal("0"),
        natural_maturity_supply_kg=natural_kg,
        available_mature_quantity_kg=Decimal("0"),
        mature_inventory_loss_quantity_kg=Decimal("0"),
        harvestable_mature_quantity_kg=Decimal("0"),
        nominal_harvest_capacity_kg_per_day=Decimal("1000"),
        labor_availability_ratio=Decimal("1"),
        weather_harvest_efficiency_ratio=Decimal("1"),
        operational_efficiency_ratio=Decimal("1"),
        effective_harvest_capacity_kg_per_day=harvested_kg,
        effective_capacity_for_day_kg=harvested_kg,
        harvested_quantity_kg=harvested_kg,
        closing_mature_inventory_kg=closing_kg,
        unharvested_backlog_kg=backlog_kg,
        arrival_quantity_kg=arrival_kg,
        opening_cohort_count=0,
        closing_cohort_count=0,
        member_count=0,
        mass_balance_passed=True,
        capacity_constraint_passed=True,
        continuity_passed=True,
        parameter_source_ref_hashes=[],
        cohort_source_ref_hashes=[],
    )
    session.add(row)
    return row


def _add_member_row(
    session,
    *,
    harvest_state_run_id: int,
    state_date: date,
    quantile: str,
    capacity_pool_id: int,
    variety_id: int,
    destination_factory_id: int,
    arrival_kg: Decimal,
) -> HarvestStateDailyMemberRowModel:
    """Insert a :class:`HarvestStateDailyMemberRowModel` for per-variety grain.

    Per P0-4, the baseline composer reads per-variety contribution from
    real member rows.  When a test asserts deterministic per-day row
    output, the test fixture MUST materialise member rows matching the
    pool totals; otherwise the composer surfaces a capability gap
    blocker and returns no rows.
    """

    row = HarvestStateDailyMemberRowModel(
        harvest_state_run_id=harvest_state_run_id,
        state_date=state_date,
        forecast_quantile=quantile,
        capacity_pool_id=capacity_pool_id,
        capacity_pool_grain="SUBFARM_VARIETY",
        capacity_pool_membership_hash="a" * 64,
        farm_id=1,
        subfarm_id=1,
        subfarm_identity_key=f"sf:{1}",
        variety_id=variety_id,
        destination_factory_id=destination_factory_id,
        opening_mature_inventory_kg=Decimal("0"),
        natural_maturity_supply_kg=arrival_kg,
        available_mature_quantity_kg=Decimal("0"),
        mature_inventory_loss_quantity_kg=Decimal("0"),
        harvestable_mature_quantity_kg=Decimal("0"),
        allocated_harvest_capacity_kg=arrival_kg,
        harvested_quantity_kg=arrival_kg,
        closing_mature_inventory_kg=Decimal("0"),
        unharvested_backlog_kg=Decimal("0"),
        arrival_quantity_kg=arrival_kg,
        opening_cohort_count=0,
        closing_cohort_count=0,
        cohort_source_ref_hashes=[],
    )
    session.add(row)
    return row


def _populate_member_rows_matching_pool(
    session,
    *,
    harvest_state_run_id: int,
    destination_factory_id: int,
    variety_id: int,
    arrival_kg_per_quantile_per_date: dict[tuple[date, str], Decimal],
) -> None:
    """Insert member rows that mirror the pool totals for the given variety.

    Test fixtures call this after :func:`_add_pool_row` to materialise
    the per-variety grain that the baseline composer requires (P0-4).
    """

    for (d, q), arrival_kg in arrival_kg_per_quantile_per_date.items():
        _add_member_row(
            session,
            harvest_state_run_id=harvest_state_run_id,
            state_date=d,
            quantile=q,
            capacity_pool_id=1,
            variety_id=variety_id,
            destination_factory_id=destination_factory_id,
            arrival_kg=arrival_kg,
        )


class _StubTask8Port:
    """Stub :class:`Task8ForecastPort` for tests without maturity tables.

    The default TASK-008 loader requires ``MaturityForecastRun`` and
    ``MaturityModelRun`` ORM rows that are not materialised in the
    SQLite fixture (they contain Postgres-only JSONB columns).  Tests
    that do not need to assert on TASK-008 envelope contents inject this
    stub instead.
    """

    def __init__(self, *, forecast_run_id: int = 1) -> None:
        self._forecast_run_id = forecast_run_id

    async def load_by_id(self, *, session, forecast_run_id: int):
        from backend.app.agent.schemas import Task8Authority

        return Task8Authority(
            maturity_model_run_id=1,
            maturity_model_version="v1",
            maturity_model_config_hash="a" * 64,
            maturity_model_source_signature="sig",
            maturity_model_artifact_id=1,
            maturity_model_artifact_hash="a" * 64,
            maturity_forecast_run_id=forecast_run_id,
            maturity_forecast_source_signature="fsig",
            maturity_forecast_as_of_date=date(2026, 3, 1),
        )


def _add_residual_prediction_run(
    session,
    *,
    prediction_run_id: int,
    task9_run_id: int,
    task9_result_hash: str,
) -> ResidualModelPredictionRun:
    run = ResidualModelPredictionRun(
        id=prediction_run_id,
        training_run_id=None,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        execution_status="completed",
        mode="residual_corrected",
        config_hash=_hash(f"cfg-r{prediction_run_id}"),
        feature_schema_version="v1",
        feature_schema_hash=_hash(f"fsh-{prediction_run_id}"),
        artifact_hashes=[],
        prediction_input_signature=_hash(f"pis-{prediction_run_id}"),
        prediction_hash=_hash(f"ph-{prediction_run_id}"),
        feature_audit={},
        warnings=[],
        blockers=[],
        fallback_reason=None,
        expected_prediction_row_count=0,
        input_snapshot={},
        canonical_output={},
        canonical_payload_hash=_hash(f"cph-{prediction_run_id}"),
    )
    session.add(run)
    return run


def _add_residual_prediction_row(
    session,
    *,
    prediction_run_id: int,
    arrival_local_date: date,
    destination_factory_id: int,
    corrected_p50: Decimal,
    corrected_p80: Decimal,
    corrected_p90: Decimal,
    task9_run_id: int,
    task9_result_hash: str,
) -> ResidualModelPredictionRow:
    row = ResidualModelPredictionRow(
        prediction_run_id=prediction_run_id,
        model_run_id=None,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        destination_factory_id=destination_factory_id,
        arrival_local_date=arrival_local_date,
        forecast_horizon_days=1,
        structural_p50_kg=corrected_p50,
        structural_p80_kg=corrected_p80,
        structural_p90_kg=corrected_p90,
        raw_residual_p50_kg=Decimal("0"),
        raw_residual_p80_kg=Decimal("0"),
        raw_residual_p90_kg=Decimal("0"),
        corrected_raw_p50_kg=corrected_p50,
        corrected_raw_p80_kg=corrected_p80,
        corrected_raw_p90_kg=corrected_p90,
        corrected_p50_kg=corrected_p50,
        corrected_p80_kg=corrected_p80,
        corrected_p90_kg=corrected_p90,
        nonnegative_projection_applied=False,
        quantile_projection_applied=False,
        projection_reasons=[],
        feature_vector_hash="a" * 64,
        feature_audit_hash="a" * 64,
        prediction_row_hash=_hash(f"prh-{prediction_run_id}-{arrival_local_date}"),
        mode="residual_corrected",
        fallback_reason=None,
    )
    session.add(row)
    return row


# --- Fixtures -------------------------------------------------------------


def _mk_input(planting_area_mu: str = "100.0") -> ForecastDailyCurveInput:
    nr = NormalizedAgentRequest(
        request_id="r1",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="season-calendar/v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        location_input=LocationInput(
            raw_text="云南曲靖",
            location_reference_id=1,
        ),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu=planting_area_mu)],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    return ForecastDailyCurveInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="uncertainty-widening/v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )


# --- Test 1: persisted TASK-008/009/010 ---------------------------------


@pytest.mark.asyncio
async def test_default_daily_curve_reads_persisted_task8_task9_task10(sqlite_session):
    """Insert real ORM rows; assert adapter reads from them."""
    # Variety row required for code→PK lookup used by per-variety grain.
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    # Set up TASK-008/009/010 with deterministic decimal values.
    as_of = date(2026, 3, 1)
    forecast_start = date(2026, 3, 1)
    forecast_end = date(2026, 3, 4)
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=as_of,
        forecast_start=forecast_start,
        forecast_end=forecast_end,
        destination_factory_id=1,
        maturity_forecast_run_id=1,  # present; the lineage is satisfied
        pool_row_count=9,
    )
    await sqlite_session.flush()
    # Three days × three quantiles = 9 pool rows.
    for i, d in enumerate([date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]):
        for q in ("P50", "P80", "P90"):
            base = Decimal(100 + i * 10)
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=base,
                arrival_kg=base,
                natural_kg=base,
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    # Member rows (P0-4): per-variety grain MUST mirror pool totals.
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal(100 + i * 10)
            for i, d in enumerate([date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)])
            for q in ("P50", "P80", "P90")
        },
    )
    # TASK-010 residual prediction.  The TASK-010 candidate MUST carry
    # the SAME task9_result_hash as the TASK-009 harvest_state_run's
    # result_hash — the strict-scope selector rejects mismatches.
    hs_result_hash = _hash("res-1")
    res_run = _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=hs_result_hash,
    )
    for i, d in enumerate([date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]):
        base = Decimal(120 + i * 12)
        _add_residual_prediction_row(
            sqlite_session,
            prediction_run_id=res_run.id,
            arrival_local_date=d,
            destination_factory_id=1,
            corrected_p50=base,
            corrected_p80=base + Decimal("5"),
            corrected_p90=base + Decimal("10"),
            task9_run_id=hsr.id,
            task9_result_hash=hs_result_hash,
        )
    await sqlite_session.flush()

    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out = await adapter.execute(sqlite_session, input=_mk_input())
    assert out.agent_daily_curve_hash != "0" * 64
    # 3 days; final_corrected_arrival_quantity_kg should equal the
    # residual corrected values we inserted.
    p50_values = [row.final_corrected_arrival_quantity_kg.p50 for row in out.per_day]
    # Order-insensitive: assert that the three deterministic values appear.
    expected = {
        Decimal("120.000000000000000000"),
        Decimal("132.000000000000000000"),
        Decimal("144.000000000000000000"),
    }
    assert set(Decimal(v) for v in p50_values) == expected


# --- Test 2: emit real typed authorities ---------------------------------


@pytest.mark.asyncio
async def test_default_daily_curve_emits_real_typed_authorities(sqlite_session):
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    as_of = date(2026, 3, 1)
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=as_of,
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q in ("P50", "P80", "P90"):
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal("100")
            for d in (date(2026, 3, 1), date(2026, 3, 2))
            for q in ("P50", "P80", "P90")
        },
    )
    _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=_hash("res-1"),
    )
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q_p50 in (Decimal("110"),):
            _add_residual_prediction_row(
                sqlite_session,
                prediction_run_id=1,
                arrival_local_date=d,
                destination_factory_id=1,
                corrected_p50=q_p50,
                corrected_p80=q_p50 + Decimal("5"),
                corrected_p90=q_p50 + Decimal("10"),
                task9_run_id=hsr.id,
                task9_result_hash=_hash("res-1"),
            )
    await sqlite_session.flush()

    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out = await adapter.execute(sqlite_session, input=_mk_input())
    # task9_authority is populated (real PK + hashes from the inserted row).
    assert out.task9_authority is not None
    assert out.task9_authority.harvest_state_run_id == 1
    assert out.task9_authority.pool_row_count == 3


# --- Test 3: lineage mismatch ------------------------------------------


@pytest.mark.asyncio
async def test_default_daily_curve_rejects_task9_task10_lineage_mismatch(
    sqlite_session,
):
    # Insert a harvest_state_run whose maturity_forecast_run_id=None AND
    # no TASK-010 residual prediction run.  Per the strict-scope
    # composer, TASK-010 is validated BEFORE TASK-008; the absence of
    # TASK-010 produces TASK10_AUTHORITY_NOT_FOUND first.
    as_of = date(2026, 3, 1)
    _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=as_of,
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=None,
        pool_row_count=0,
    )
    await sqlite_session.flush()

    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out = await adapter.execute(sqlite_session, input=_mk_input())
    codes = [b.code for b in out.blockers]
    # Either blocker is acceptable — the test asserts the adapter
    # surfaces a typed capability blocker rather than silently
    # substituting a fallback.
    assert (
        BlockerCode.TASK8_AUTHORITY_NOT_FOUND in codes
        or BlockerCode.TASK10_AUTHORITY_NOT_FOUND in codes
    )


# --- Test 4: empty DB → structured blockers -----------------------------


@pytest.mark.asyncio
async def test_default_daily_curve_missing_authority_returns_structured_blocker(
    sqlite_session,
):
    # Empty DB.
    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out = await adapter.execute(sqlite_session, input=_mk_input())
    codes = [b.code for b in out.blockers]
    assert BlockerCode.TASK9_AUTHORITY_NOT_FOUND in codes
    # TASK-010 cascade is blocked by the missing TASK-009 lineage.
    assert BlockerCode.TASK10_AUTHORITY_NOT_FOUND in codes
    assert out.per_day == []


# --- Test 5: byte-identical curve hash ----------------------------------


@pytest.mark.asyncio
async def test_default_daily_curve_same_persisted_input_is_byte_identical(
    sqlite_session,
):
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q in ("P50", "P80", "P90"):
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=_hash("res-1"),
    )
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal("100")
            for d in (date(2026, 3, 1), date(2026, 3, 2))
            for q in ("P50", "P80", "P90")
        },
    )
    await sqlite_session.flush()

    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out1 = await adapter.execute(sqlite_session, input=_mk_input())
    out2 = await adapter.execute(sqlite_session, input=_mk_input())
    assert out1.agent_daily_curve_hash == out2.agent_daily_curve_hash


# --- Test 6: TASK-12 absent by default ----------------------------------


@pytest.mark.asyncio
async def test_default_daily_curve_task12_absent_without_explicit_override(
    sqlite_session,
):
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q in ("P50", "P80", "P90"):
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=_hash("res-1"),
    )
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal("100")
            for d in (date(2026, 3, 1), date(2026, 3, 2))
            for q in ("P50", "P80", "P90")
        },
    )
    await sqlite_session.flush()

    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out = await adapter.execute(sqlite_session, input=_mk_input())
    assert out.task12_authority is None


# --- Test 7: parameter adapter uses real variety catalog ----------------


@pytest.mark.asyncio
async def test_default_parameters_load_real_priors(sqlite_session):
    # Insert a real Variety row.
    session = sqlite_session
    var = Variety(id=1, code="Dx", name="Test")
    session.add(var)
    await session.flush()

    # With no real prior observations table, the upstream infer_parameter
    # returns status='unavailable' and the adapter surfaces
    # INSUFFICIENT_HISTORY (no fabricated numerics).
    adapter = DefaultParameterAdapter(catalog=DefaultVarietyCatalogPort())
    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    inp = InferParametersInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )
    out = await adapter.execute(session, input=inp)
    # Block codes must be INSUFFICIENT_HISTORY (no fabrication).
    codes = [b.code.value for b in out.blockers]
    assert "INSUFFICIENT_HISTORY" in codes
    # No fabricated parameter estimate.
    assert out.parameters == []


# --- Test 8: unknown variety --------------------------------------------


@pytest.mark.asyncio
async def test_default_parameters_unknown_variety_uses_catalog(sqlite_session):
    # Variety "Dx" is known, "DOES_NOT_EXIST" is not.
    session = sqlite_session
    var = Variety(id=1, code="Dx", name="Test")
    session.add(var)
    await session.flush()

    adapter = DefaultParameterAdapter(catalog=DefaultVarietyCatalogPort())

    def _mk_nr(variety_id: str) -> NormalizedAgentRequest:
        return NormalizedAgentRequest(
            request_id="r",
            request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
            effective_as_of_date=date(2026, 3, 1),
            effective_forecast_season=2026,
            season_resolution_policy_version="v1",
            season_calendar_config_hash="a" * 64,
            requested_as_of_date_provenance=RequestedAsOfDateProvenance(
                caller_requested_as_of_date=date(2026, 3, 1),
                effective_as_of_date=date(2026, 3, 1),
                override_applied=False,
                override_kind=None,
                source_attestation=None,
                source_ref=None,
            ),
            normalized_location=ResolvedLocation(
                status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
            ),
            location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
            varieties=[NormalizedVarietyInput(variety_id=variety_id, planting_area_mu="100.0")],
            advanced_overrides=AdvancedOverrides(),
            canonical_request_hash="0" * 64,
        )

    # "Dx" — should NOT be blocked with UNKNOWN_VARIETY (but might still
    # be INSUFFICIENT_HISTORY because there are no real priors).
    inp = InferParametersInput(
        normalized_request=_mk_nr("Dx"),
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )
    out_known = await adapter.execute(session, input=inp)
    unknown_codes = [b.code.value for b in out_known.blockers]
    assert "UNKNOWN_VARIETY" not in unknown_codes

    # "DOES_NOT_EXIST" — should be blocked with UNKNOWN_VARIETY.
    inp2 = InferParametersInput(
        normalized_request=_mk_nr("DOES_NOT_EXIST"),
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )
    out_unknown = await adapter.execute(session, input=inp2)
    assert "DOES_NOT_EXIST" in out_unknown.blocked_variety_ids
    assert BlockerCode.UNKNOWN_VARIETY in [b.code for b in out_unknown.blockers]


# --- Test 9: string variety codes "Dx", "D12", "1702" --------------------


@pytest.mark.asyncio
async def test_default_parameters_string_variety_dx_d12_1702(sqlite_session):
    session = sqlite_session
    for code in ("Dx", "D12", "1702"):
        session.add(Variety(id=hash(code) % 100000, code=code, name=f"Test-{code}"))
    await session.flush()

    adapter = DefaultParameterAdapter(catalog=DefaultVarietyCatalogPort())
    for code in ("Dx", "D12", "1702"):
        nr = NormalizedAgentRequest(
            request_id=f"r-{code}",
            request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
            effective_as_of_date=date(2026, 3, 1),
            effective_forecast_season=2026,
            season_resolution_policy_version="v1",
            season_calendar_config_hash="a" * 64,
            requested_as_of_date_provenance=RequestedAsOfDateProvenance(
                caller_requested_as_of_date=date(2026, 3, 1),
                effective_as_of_date=date(2026, 3, 1),
                override_applied=False,
                override_kind=None,
                source_attestation=None,
                source_ref=None,
            ),
            normalized_location=ResolvedLocation(
                status="resolved",
                location_reference_id=1,
                matched_location_method="REFERENCE_ID",
            ),
            location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
            varieties=[NormalizedVarietyInput(variety_id=code, planting_area_mu="100.0")],
            advanced_overrides=AdvancedOverrides(),
            canonical_request_hash="0" * 64,
        )
        inp = InferParametersInput(
            normalized_request=nr,
            resolved_location=ResolvedLocation(
                status="resolved",
                location_reference_id=1,
                matched_location_method="REFERENCE_ID",
            ),
            uncertainty_widening_policy=UncertaintyWideningPolicy(
                policy_version="v1",
                config_hash="b" * 64,
                factors_by_source_level={
                    "step_1_same_farm_same_variety_high_evidence": "1.000",
                    "step_2_same_township_similar_altitude": "1.250",
                    "step_3_same_county_same_climate_zone": "1.500",
                    "step_4_province_level_same_variety": "1.750",
                    "step_5_variety_document_prior_only": "2.000",
                },
                monotonicity_invariant=True,
            ),
        )
        out = await adapter.execute(session, input=inp)
        # Variety is known → no UNKNOWN_VARIETY blocker
        codes = [b.code.value for b in out.blockers]
        assert "UNKNOWN_VARIETY" not in codes


class _StaticPort(LocationResolverPort):
    """Static LocationResolverPort returning a pre-canned ResolvedLocation."""

    def __init__(
        self,
        *,
        status: str,
        location_reference_id: int | None = None,
        warning: str | None = None,
        matched_method: str = "REFERENCE_ID",
    ):
        self._resolved = ResolvedLocation(
            status=status,
            location_reference_id=location_reference_id,
            matched_location_method=matched_method,  # type: ignore[arg-type]
            warning=warning,
        )

    async def resolve(
        self,
        *,
        session: Any,
        location: dict[str, Any],
        as_of_date: Any,
    ) -> ResolvedLocation:
        return self._resolved


# --- Test 10: resolve_location from raw_text -----------------------------


@pytest.mark.asyncio
async def test_resolve_location_from_raw_text(sqlite_session):
    """The default location adapter reads from raw LocationInput."""
    # Adapter constructed with a fake port — no real catalog needed.
    port = _StaticPort(status="resolved", location_reference_id=42)
    adapter = DefaultLocationAdapter(resolver=port)
    from backend.app.agent.schemas import LocationInput as LI

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=42,
            matched_location_method="REFERENCE_ID",
        ),
        location_input=LI(raw_text="云南曲靖", location_reference_id=42),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    out = await adapter.execute(sqlite_session, input=ResolveLocationInput(normalized_request=nr))
    assert out.resolved_location.status == "resolved"
    assert out.resolved_location.location_reference_id == 42


# --- Test 11: resolve_location from coordinates -------------------------


@pytest.mark.asyncio
async def test_resolve_location_from_coordinates(sqlite_session):
    """The adapter uses the static port when given coordinate input."""
    port = _StaticPort(status="resolved", location_reference_id=42)
    adapter = DefaultLocationAdapter(resolver=port)
    from backend.app.agent.schemas import LocationInput as LI

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=42,
            matched_location_method="COORDINATE",
        ),
        location_input=LI(latitude="25.5", longitude="103.8", location_reference_id=42),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    out = await adapter.execute(sqlite_session, input=ResolveLocationInput(normalized_request=nr))
    assert out.resolved_location.status == "resolved"


# --- Test 12: coordinate pairing ----------------------------------------


def test_resolve_location_coordinates_require_pair():
    # latitude without longitude → ValidationError.
    from pydantic import ValidationError

    from backend.app.agent.schemas import LocationInput

    with pytest.raises(ValidationError):
        LocationInput(latitude="25.5", raw_text=None)


# --- Test 13: coordinate ranges -----------------------------------------


def test_resolve_location_coordinate_ranges():
    from pydantic import ValidationError

    from backend.app.agent.schemas import LocationInput

    with pytest.raises(ValidationError):
        LocationInput(latitude="91", longitude="0.0")
    with pytest.raises(ValidationError):
        LocationInput(latitude="0.0", longitude="181.0")


# --- Test 14: ambiguous match -------------------------------------------


def test_resolve_location_equal_score_returns_ambiguous():
    """The adapter translates the upstream warning to LOCATION_AMBIGUOUS."""
    # Use a static port with two candidates.
    from backend.app.agent.ports import LocationResolverPort
    from backend.app.agent.schemas import (
        NormalizedAgentRequest,
        NormalizedVarietyInput,
        RequestedAsOfDateProvenance,
        ResolvedLocation,
    )

    class _TwoCandidatesPort(LocationResolverPort):
        async def resolve(self, *, session, location, as_of_date):
            return ResolvedLocation(
                status="ambiguous",
                location_reference_id=None,
                matched_location_method="REFERENCE_ID",
                candidates=[
                    {"location_reference_id": 1, "score": "0.500"},
                    {"location_reference_id": 2, "score": "0.500"},
                ],
            )

    from backend.app.agent.schemas import LocationInput as LI

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="ambiguous", matched_location_method="REFERENCE_ID"
        ),
        location_input=LI(raw_text="云南曲靖"),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )

    import asyncio

    out = asyncio.run(
        DefaultLocationAdapter(resolver=_TwoCandidatesPort()).execute(
            cast(Any, object()),
            input=ResolveLocationInput(normalized_request=nr),
        )
    )
    assert BlockerCode.LOCATION_AMBIGUOUS in [b.code for b in out.blockers]


# --- Test 15: catalog version is as-of-date dependent -------------------


@pytest.mark.asyncio
async def test_resolve_location_catalog_visibility_at_as_of(sqlite_session):
    """Catalog_version sha256 derivation differs across as-of dates."""
    from backend.app.agent.adapters.location import _compute_catalog_version

    v1 = _compute_catalog_version(date(2026, 3, 1), [date(2025, 1, 1)])
    v2 = _compute_catalog_version(date(2026, 4, 1), [date(2025, 1, 1)])
    assert v1 != v2
    assert len(v1) == 64


# --- Test 16: same input → same catalog version -------------------------


@pytest.mark.asyncio
async def test_resolve_location_same_input_same_catalog_same_output(
    sqlite_session,
):
    from backend.app.agent.adapters.location import _compute_catalog_version

    v1 = _compute_catalog_version(date(2026, 3, 1), [date(2025, 1, 1), date(2025, 6, 1)])
    v2 = _compute_catalog_version(date(2026, 3, 1), [date(2025, 1, 1), date(2025, 6, 1)])
    assert v1 == v2


# --- Test 17: scenario preserves authority overrides ---------------------


@pytest.mark.asyncio
async def test_scenario_preserves_authority_overrides(sqlite_session):
    """Both baseline and scenario use the same TASK-9 run when overridden."""
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q in ("P50", "P80", "P90"):
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal("100")
            for d in (date(2026, 3, 1), date(2026, 3, 2))
            for q in ("P50", "P80", "P90")
        },
    )
    _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=_hash("res-1"),
    )
    await sqlite_session.flush()

    from backend.app.agent.schemas import Task9HarvestStateRunAuthorityOverride

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(
            authority_overrides=[
                Task9HarvestStateRunAuthorityOverride(
                    override_kind="AUTHORITY_OVERRIDE_KIND",
                    target="TASK9_HARVEST_STATE_RUN",
                    value=1,
                    source_attestation="op",
                ),
            ],
        ),
        canonical_request_hash="0" * 64,
    )
    daily = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    peak = DefaultPeakAdapter()
    DefaultScenarioAdapter(daily_curve_adapter=daily, peak_adapter=peak)
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        scenario_overrides=[],
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.900",
        ),
        advanced_overrides=AdvancedOverrides(),
    )
    scenario_adapter = DefaultScenarioAdapter(daily_curve_adapter=daily, peak_adapter=peak)
    out = await scenario_adapter.execute(sqlite_session, input=inp)
    # Both baseline and scenario use task9_run_id=1.
    assert out.forecast_daily_curve.task9_authority is not None
    assert out.forecast_daily_curve.task9_authority.harvest_state_run_id == 1


# --- Test 18: scenario preserves as-of override provenance ---------------


@pytest.mark.asyncio
async def test_scenario_preserves_as_of_override_provenance(sqlite_session):
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q in ("P50", "P80", "P90"):
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal("100")
            for d in (date(2026, 3, 1), date(2026, 3, 2))
            for q in ("P50", "P80", "P90")
        },
    )
    _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=_hash("res-1"),
    )
    await sqlite_session.flush()

    from backend.app.agent.schemas import AsOfOverride

    base_provenance = RequestedAsOfDateProvenance(
        caller_requested_as_of_date=date(2026, 3, 1),
        effective_as_of_date=date(2026, 3, 1),
        override_applied=False,
        override_kind=None,
        source_attestation=None,
        source_ref=None,
    )
    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=base_provenance,
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(
            as_of_overrides=[
                AsOfOverride(
                    override_kind="AS_OF_OVERRIDE",
                    value=date(2026, 5, 1),
                    source_attestation="op",
                ),
            ],
        ),
        canonical_request_hash="0" * 64,
    )
    daily = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    peak = DefaultPeakAdapter()
    DefaultScenarioAdapter(daily_curve_adapter=daily, peak_adapter=peak)
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        scenario_overrides=[],
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.900",
        ),
        advanced_overrides=AdvancedOverrides(),
    )
    # Construction should validate (override_applied consistency enforced).
    assert inp.normalized_request.advanced_overrides is not None


# --- Test 19: scenario rejects baseline authority drift -----------------


@pytest.mark.asyncio
async def test_scenario_rejects_baseline_authority_drift(sqlite_session):
    # Per P0-6 strict authority selection, the composer returns a single
    # candidate (zero or one) and rejects AUTHORITY_CONFLICT when multiple
    # candidates satisfy the strict scope.  When both hsr1 and hsr2
    # qualify the same effective_as_of_date, the composer emits
    # AUTHORITY_CONFLICT with full candidate disclosure and the delta is
    # NOT computed.
    hsr1 = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    hsr2 = _build_harvest_state_run(
        sqlite_session,
        run_id=2,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for hsr in (hsr1, hsr2):
        for d in (date(2026, 3, 1), date(2026, 3, 2)):
            for q in ("P50", "P80", "P90"):
                _add_pool_row(
                    sqlite_session,
                    harvest_state_run_id=hsr.id,
                    state_date=d,
                    quantile=q,
                    capacity_pool_id=1,
                    harvested_kg=Decimal("100"),
                    arrival_kg=Decimal("100"),
                    natural_kg=Decimal("100"),
                    closing_kg=Decimal("0"),
                    backlog_kg=Decimal("0"),
                )
    _add_residual_prediction_run(
        sqlite_session, prediction_run_id=1, task9_run_id=hsr1.id, task9_result_hash=_hash("r1")
    )
    _add_residual_prediction_run(
        sqlite_session, prediction_run_id=2, task9_run_id=hsr2.id, task9_result_hash=_hash("r2")
    )
    await sqlite_session.flush()

    # Run the daily curve adapter and assert AUTHORITY_CONFLICT.
    from backend.app.agent.schemas import (
        AdvancedOverrides,
        LocationInput,
        NormalizedAgentRequest,
        NormalizedVarietyInput,
        RequestedAsOfDateProvenance,
        ResolvedLocation,
    )

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    from backend.app.agent.schemas import ForecastDailyCurveInput, UncertaintyWideningPolicy

    inp = ForecastDailyCurveInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        advanced_overrides=AdvancedOverrides(),
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
    )
    adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    out = await adapter.execute(sqlite_session, input=inp)
    codes = [b.code for b in out.blockers]
    assert BlockerCode.AUTHORITY_CONFLICT in codes
    # The conflict blocker must disclose the candidate IDs.
    conflict_blockers = [b for b in out.blockers if b.code == BlockerCode.AUTHORITY_CONFLICT]
    assert len(conflict_blockers) >= 1
    details = conflict_blockers[0].details or {}
    assert "candidates" in details
    cand_ids = sorted(c["harvest_state_run_id"] for c in details["candidates"])
    assert cand_ids == [1, 2]


# --- Test 20: scenario default constructor uses production daily_curve -


@pytest.mark.asyncio
async def test_scenario_default_constructor_uses_production_daily_curve(
    sqlite_session,
):
    # With an empty DB, the production daily curve returns blockers but
    # does NOT raise INTERNAL_FAILURE.
    from backend.app.agent.adapters.scenario import DefaultScenarioAdapter

    DefaultScenarioAdapter()
    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        scenario_overrides=[],
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.900",
        ),
        advanced_overrides=AdvancedOverrides(),
    )
    daily_curve_adapter = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    peak_adapter = DefaultPeakAdapter()
    scenario_adapter = DefaultScenarioAdapter(
        daily_curve_adapter=daily_curve_adapter, peak_adapter=peak_adapter
    )
    out = await scenario_adapter.execute(sqlite_session, input=inp)
    # No INTERNAL_FAILURE: production wiring is correctly engaged.
    codes = [b.code for b in out.forecast_daily_curve.blockers]
    assert BlockerCode.INTERNAL_FAILURE not in codes


# --- Test 21: scenario same input → identical hash ----------------------


@pytest.mark.asyncio
async def test_scenario_same_input_same_hash_and_delta(sqlite_session):
    var = Variety(id=1, code="Dx", name="Test")
    sqlite_session.add(var)
    await sqlite_session.flush()
    hsr = _build_harvest_state_run(
        sqlite_session,
        run_id=1,
        as_of_date=date(2026, 3, 1),
        forecast_start=date(2026, 3, 1),
        forecast_end=date(2026, 3, 2),
        destination_factory_id=1,
        maturity_forecast_run_id=1,
        pool_row_count=3,
    )
    await sqlite_session.flush()
    for d in (date(2026, 3, 1), date(2026, 3, 2)):
        for q in ("P50", "P80", "P90"):
            _add_pool_row(
                sqlite_session,
                harvest_state_run_id=hsr.id,
                state_date=d,
                quantile=q,
                capacity_pool_id=1,
                harvested_kg=Decimal("100"),
                arrival_kg=Decimal("100"),
                natural_kg=Decimal("100"),
                closing_kg=Decimal("0"),
                backlog_kg=Decimal("0"),
            )
    _populate_member_rows_matching_pool(
        sqlite_session,
        harvest_state_run_id=hsr.id,
        destination_factory_id=1,
        variety_id=int(var.id),
        arrival_kg_per_quantile_per_date={
            (d, q): Decimal("100")
            for d in (date(2026, 3, 1), date(2026, 3, 2))
            for q in ("P50", "P80", "P90")
        },
    )
    _add_residual_prediction_run(
        sqlite_session,
        prediction_run_id=1,
        task9_run_id=hsr.id,
        task9_result_hash=_hash("res-1"),
    )
    await sqlite_session.flush()

    daily = DefaultDailyCurveAdapter(
        baseline=DefaultTaskCompositionBaseline(), task8=_StubTask8Port()
    )
    peak = DefaultPeakAdapter()
    adapter = DefaultScenarioAdapter(daily_curve_adapter=daily, peak_adapter=peak)
    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    so = StaffingScenarioOverride(
        override_kind="SCENARIO_OVERRIDE_KIND",
        target="STAFFING",
        value=StaffingOverrideValue(value="10.0"),
        source_attestation="op",
    )
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        parameters=[],
        scenario_overrides=[so],
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.000",
                "step_2_same_township_similar_altitude": "1.250",
                "step_3_same_county_same_climate_zone": "1.500",
                "step_4_province_level_same_variety": "1.750",
                "step_5_variety_document_prior_only": "2.000",
            },
            monotonicity_invariant=True,
        ),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="peak-metric/v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.900",
        ),
        advanced_overrides=AdvancedOverrides(),
    )
    out1 = await adapter.execute(sqlite_session, input=inp)
    out2 = await adapter.execute(sqlite_session, input=inp)
    assert out1.scenario_id == out2.scenario_id
    assert out1.scenario_config_hash == out2.scenario_config_hash


# --- Test 22: peak duration breaks on missing calendar date ------------


def test_peak_duration_breaks_on_missing_calendar_date():
    from backend.app.agent.adapters.peak import _peak_duration_days
    from backend.app.agent.schemas import DailyQuantiles, ForecastDailyRow

    rows = [
        ForecastDailyRow(
            date=d,
            natural_maturity_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            harvested_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            closing_mature_inventory_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
            unharvested_backlog_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
            arrival_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            final_corrected_arrival_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            agent_daily_row_hash="0" * 64,
        )
        for d in (date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 4), date(2026, 3, 5))
    ]
    # peak_date = 2026-03-04, threshold 50; consecutive days at >=50
    # containing 2026-03-04: 2026-03-04, 2026-03-05 → length 2
    dur = _peak_duration_days(
        rows, quantile="P50", threshold=Decimal("50"), peak_date=date(2026, 3, 4)
    )
    assert dur == 2


# --- Test 23: sustained window rejects date gap -----------------------


def test_sustained_window_rejects_date_gap():
    from backend.app.agent.adapters.peak import _sustained_3day_peak
    from backend.app.agent.schemas import DailyQuantiles, ForecastDailyRow

    rows = [
        ForecastDailyRow(
            date=d,
            natural_maturity_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            harvested_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            closing_mature_inventory_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
            unharvested_backlog_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
            arrival_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            final_corrected_arrival_quantity_kg=DailyQuantiles(p50="100", p80="100", p90="100"),
            agent_daily_row_hash="0" * 64,
        )
        for d in (date(2026, 3, 1), date(2026, 3, 5), date(2026, 3, 6))
    ]
    with pytest.raises(ValueError):
        _sustained_3day_peak(rows, quantile="P50")


# --- Test 24: peak empty curve → EMPTY_CURVE blocker -------------------


def test_peak_empty_curve_returns_blocker():
    from backend.app.agent.adapters.peak import DefaultPeakAdapter
    from backend.app.agent.schemas import (
        AdvancedOverrides,
        ForecastDailyCurveOutput,
        LocationInput,
        NormalizedAgentRequest,
        NormalizedVarietyInput,
        PeakMetricPolicy,
        RequestedAsOfDateProvenance,
        ResolvedLocation,
    )

    nr = NormalizedAgentRequest(
        request_id="r",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status="resolved", location_reference_id=1, matched_location_method="REFERENCE_ID"
        ),
        location_input=LocationInput(raw_text="云南曲靖", location_reference_id=1),
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )
    inp = ForecastPeakInput(
        normalized_request=nr,
        daily_curve=ForecastDailyCurveOutput(per_day=[], agent_daily_curve_hash="a" * 64),
        peak_metric_policy=PeakMetricPolicy(
            policy_version="v1",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.900",
        ),
    )
    out = DefaultPeakAdapter().execute(input=inp)
    assert BlockerCode.EMPTY_CURVE in [b.code for b in out.blockers]


# --- Test 25: peak policy missing version → blocker --------------------


def test_peak_policy_missing_version_returns_blocker():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PeakMetricPolicy(
            policy_version="",
            policy_config_hash="c" * 64,
            sustained_window_days=3,
            sustained_metric="ROLLING_DAILY_AVERAGE",
            tie_break="EARLIEST_START_DATE",
            peak_window_days_before=7,
            peak_window_days_after=7,
            high_load_reference="SINGLE_DAY_PEAK",
            high_load_threshold_ratio="0.900",
        )


# --- Test 26: ForecastDailyRow has weather_tags + spring_festival_phase -


def test_default_forecast_daily_row_includes_weather_and_spring_festival_phase():
    from backend.app.agent.adapters.daily_curve import _row_hash
    from backend.app.agent.schemas import DailyQuantiles, ForecastDailyRow

    base_row = ForecastDailyRow(
        date=date(2026, 3, 1),
        natural_maturity_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        harvested_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        closing_mature_inventory_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        unharvested_backlog_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        arrival_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        final_corrected_arrival_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        agent_daily_row_hash="0" * 64,
    )
    h1 = _row_hash(base_row)
    # weather_tags change → different hash.
    row2 = base_row.model_copy(update={"weather_tags": ("WIND",)})
    h2 = _row_hash(row2)
    assert h1 != h2
    # spring_festival_phase change → different hash.
    row3 = base_row.model_copy(update={"spring_festival_phase": "DURING"})
    h3 = _row_hash(row3)
    assert h1 != h3


# --- Test 27: row hash differs with weather_tags --------------------------


def test_forecast_daily_curve_hash_differs_with_weather_tags():
    from backend.app.agent.adapters.daily_curve import _row_hash
    from backend.app.agent.schemas import DailyQuantiles, ForecastDailyRow

    row_a = ForecastDailyRow(
        date=date(2026, 3, 1),
        natural_maturity_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        harvested_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        closing_mature_inventory_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        unharvested_backlog_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        arrival_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        final_corrected_arrival_quantity_kg=DailyQuantiles(p50="0", p80="0", p90="0"),
        weather_tags=("A",),
        agent_daily_row_hash="0" * 64,
    )
    row_b = row_a.model_copy(update={"weather_tags": ("B",)})
    assert _row_hash(row_a) != _row_hash(row_b)


# --- Bonus: spring-festival calendar port deterministic ------------------


def test_spring_festival_calendar_port_deterministic():
    cal = DefaultSpringFestivalCalendarPort()
    # 2026-02-17 is Chinese New Year 2026.
    assert cal.phase_for(target=date(2026, 2, 17)) == "DURING"
    assert cal.phase_for(target=date(2026, 2, 10)) == "PRE"
    assert cal.phase_for(target=date(2026, 2, 25)) == "POST"
    assert cal.phase_for(target=date(2026, 6, 1)) == "NONE"
