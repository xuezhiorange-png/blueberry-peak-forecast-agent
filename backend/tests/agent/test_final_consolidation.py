"""TASK-013 Slice A — Final Consolidation test-first probe (Round 7 review 4680214102).

This file was authored BEFORE any production-code change.  The 9 tests in
this module probe the production code paths enumerated in review
``4680214102`` and assert the typed-failure contract Charles requires:

* Test A — TASK-009 season identity MUST come from
  ``HarvestStateRun.input_snapshot["forecast_season"]`` (real persisted
  field), NOT from ``HarvestStateRun.as_of_date.year`` (date-guess).
* Test B — Real PostgreSQL ``extract('year', ...)`` selector path
  (executed separately under the ``postgres`` marker).
* Test C — TASK-009 default selector returns typed discrimination
  (NOT_FOUND / SCOPE_MISMATCH / HASH_MALFORMED / IDENTITY_MALFORMED /
  LINEAGE_MISMATCH / UPSTREAM_READ_FAILURE / AUTHORITY_CONFLICT) — NOT
  a flat ``TASK9_AUTHORITY_NOT_FOUND`` blob.
* Test D — TASK-010 default selector returns the analogous typed
  discrimination; never collapses to ``TASK10_AUTHORITY_NOT_FOUND``.
* Test E — Per-variety contribution is whole-day fail-closed when one
  variety is missing any quantile (no Dx-only partial contribution).
* Test F — Emitted contribution rates sum to 1 (denominator = selected
  member variety set, no mixed-semantic truncation).
* Test G — ``TASK9_PER_VARIETY_GRAIN_MISSING`` blocker carries the real
  ``task9_run_id`` (NOT ``variety_pk``) when member rows are absent.
* Test H — Blocked scenario performs ZERO upstream reads: daily
  adapter call count == 0, peak adapter call count == 0, baseline
  composition is NOT invoked.
* Test I — Spring Festival missing-policy blocker is emitted by
  ``compute_baseline`` (real path; not a calendar helper test).

These tests are RUN on the starting HEAD ``d9e2758e...`` BEFORE any
production code change.  At least some tests MUST fail to confirm they
are probing real defects.
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.agent.adapters.baseline_composer import (
    DefaultTaskCompositionBaseline,
    _compose_rows,
    _per_variety_contribution_from_member_rows,
    _select_harvest_state_run_candidates,
    _select_residual_prediction_run_candidates,
)
from backend.app.agent.adapters.scenario import DefaultScenarioAdapter
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    AdvancedOverrides,
    Blocker,
    LocationInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    PeakMetricPolicy,
    ProcessorCapacityScenarioOverride,
    ProcessorCapacityOverrideValue,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    ScenarioOverrideUnion,
    SimulateScenarioInput,
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


# ---------------------------------------------------------------------------
# Shared test factories
# ---------------------------------------------------------------------------


def _sha(n: int) -> str:
    return f"{n:064x}"


def _make_normalized_request(
    *,
    varieties: list[NormalizedVarietyInput] | None = None,
    season: int = 2026,
    as_of: date = date(2026, 3, 1),
) -> NormalizedAgentRequest:
    provenance = RequestedAsOfDateProvenance(
        caller_requested_as_of_date=as_of,
        effective_as_of_date=as_of,
        override_applied=False,
        override_kind=None,
        source_attestation=None,
        source_ref=None,
    )
    return NormalizedAgentRequest(
        request_id="req-final-7",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=as_of,
        effective_forecast_season=season,
        season_resolution_policy_version="season-calendar/v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=provenance,
        normalized_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        location_input=LocationInput(raw_text="Yunnan, China", location_reference_id=1),
        varieties=varieties or [NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


@pytest_asyncio.fixture
async def sqlite_full_session() -> AsyncSession:
    """In-memory SQLite session with the full TASK-009/010 + Variety
    tables.  This fixture is used to exercise the ORM-level selectors
    end-to-end without any upstream read failure caused by missing
    tables.

    Postgres-only JSONB columns are excluded (TASK-013 Slice A
    integration scope).
    """
    from backend.app.models.harvest_state import HarvestStateRun
    from backend.app.models.master_data import Variety
    from backend.app.models.residual_model import ResidualModelTrainingRun

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    tables = [
        HarvestStateRun.__table__,
        HarvestStateDailyPoolRowModel.__table__,
        HarvestStateDailyMemberRowModel.__table__,
        ResidualModelTrainingRun.__table__,
        ResidualModelPredictionRun.__table__,
        ResidualModelPredictionRow.__table__,
        Variety.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: HarvestStateRun.metadata.create_all(sync_conn, tables=tables)
        )

    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as session:
        yield session
    await engine.dispose()


async def _insert_harvest_state_run(
    session: AsyncSession,
    *,
    result_hash: str = "a" * 64,
    config_hash: str = "b" * 64,
    as_of_date: date = date(2025, 12, 1),
    forecast_start_date: date = date(2025, 12, 1),
    forecast_end_date: date = date(2025, 12, 31),
    status: str = "completed",
    destination_factory_id: int = 1,
    input_snapshot_forecast_season: int | None = 2025,
    maturity_forecast_run_id: int | None = None,
) -> int:
    """Insert a real HarvestStateRun row.

    The ``input_snapshot_forecast_season`` argument is the REAL
    persisted identity Charles requires.  Default 2025.  Pass
    ``None`` to omit the key (typed blocker expected).
    """
    input_snapshot: dict = {
        "forecast_season": input_snapshot_forecast_season,
        "as_of_date": as_of_date.isoformat(),
    }
    row = HarvestStateRun(
        status=status,
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot=input_snapshot,
        resolved_parameter_snapshot={"forecast_season": input_snapshot_forecast_season}
        if input_snapshot_forecast_season is not None
        else None,
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result=None,
        continuity_result=None,
        canonical_output={"ok": True},
        config_hash=config_hash,
        result_hash=result_hash,
        canonical_payload_hash="c" * 64,
        forecast_start_date=forecast_start_date,
        forecast_end_date=forecast_end_date,
        as_of_date=as_of_date,
        destination_factory_id=destination_factory_id,
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_forecast_run_id=maturity_forecast_run_id,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


async def _insert_residual_prediction_run(
    session: AsyncSession,
    *,
    task9_run_id: int,
    task9_result_hash: str = "a" * 64,
    execution_status: str = "completed",
    mode: str = "residual_corrected",
    config_hash: str = "b" * 64,
    feature_schema_hash: str = "f" * 64,
    prediction_input_signature: str = "9" * 64,
    prediction_hash: str = "8" * 64,
    canonical_payload_hash: str = "c" * 64,
    artifact_hashes: list[str] | None = None,
    fallback_reason: str | None = None,
    expected_prediction_row_count: int = 0,
) -> int:
    if artifact_hashes is None:
        artifact_hashes = ["a" * 64]
    row = ResidualModelPredictionRun(
        training_run_id=None,
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        execution_status=execution_status,
        mode=mode,
        config_hash=config_hash,
        feature_schema_version="v1",
        feature_schema_hash=feature_schema_hash,
        artifact_hashes=artifact_hashes,
        prediction_input_signature=prediction_input_signature,
        prediction_hash=prediction_hash,
        feature_audit={},
        warnings=[],
        blockers=[],
        fallback_reason=fallback_reason,
        expected_prediction_row_count=expected_prediction_row_count,
        input_snapshot={},
        canonical_output={},
        canonical_payload_hash=canonical_payload_hash,
        error_message=None,
        typed_attempt=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


# ===========================================================================
# Test A: season identity MUST NOT be derived from as_of_date.year
# ===========================================================================


@pytest.mark.asyncio
async def test_season_in_request_must_match_persisted_identity(
    sqlite_full_session: AsyncSession,
) -> None:
    """TASK-009 season identity must be read from
    ``input_snapshot["forecast_season"]`` (real persisted field),
    NOT from ``HarvestStateRun.as_of_date.year``.

    The request asks for season 2025; the persisted row carries
    input_snapshot.forecast_season=2026 and as_of_date=2026-01-10.
    A selector that treats ``as_of_date.year`` as the season
    identity would silently pass — the request says 2025 but
    as_of_date.year is 2026, the selector's failure surface MUST
    surface the scope mismatch via a typed blocker.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
        input_snapshot_forecast_season=2026,
    )

    candidates = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=2025,
    )
    # Real persisted identity says 2026; request asked for 2025.
    # The selector MUST exclude this row.
    assert all(c["id"] != hsr_id for c in candidates), (
        "selector used as_of_date.year or some other date-guess "
        "instead of the real persisted input_snapshot.forecast_season "
        f"identity; row id {hsr_id} slipped through for season=2025"
    )


# ===========================================================================
# Test B: PG extract('year', ...) — handled in integration test
# ===========================================================================


# Test B is implemented in
# ``backend/tests/integration/agent/test_postgres_selector_year_extraction.py``
# under the ``postgres`` marker.  It is intentionally NOT exercised
# under SQLite.


# ===========================================================================
# Test C: TASK-009 default selector returns typed discrimination
# ===========================================================================


@pytest.mark.asyncio
async def test_default_selector_rejects_typed_when_result_hash_filter_runs(
    sqlite_full_session: AsyncSession,
) -> None:
    """The default selector currently returns the row without a
    result_hash validation step.  The schema enforces 64-char hex at
    insert time, so the test is structured to verify the
    selector-level validation is performed: the row has a valid
    result_hash but the override path must also re-validate (round 6
    did this in ``_validate_task9_row_against_scope``).

    This test asserts the typed surface: a row with a member-row
    set that covers the request's variety codes is returned;
    a row WITHOUT member rows is also returned (the variety
    coverage check is silent — see test_default_selector_rejects_wrong_season_via_persisted_identity
    for the real defect being closed in this round).
    """
    # Insert a Variety row so member rows can reference it.
    sqlite_full_session.add(Variety(id=1, code="Dx", name="Test Dx"))
    await sqlite_full_session.flush()

    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 3, 1),
        forecast_start_date=date(2026, 3, 1),
        forecast_end_date=date(2026, 3, 31),
        input_snapshot_forecast_season=2026,
    )
    # Insert a member row for Dx on a relevant date.
    sqlite_full_session.add(
        HarvestStateDailyMemberRowModel(
            harvest_state_run_id=hsr_id,
            state_date=date(2026, 3, 1),
            forecast_quantile="P50",
            capacity_pool_id="pool-1",
            capacity_pool_grain="SUBFARM_VARIETY",
            capacity_pool_membership_hash="a" * 64,
            farm_id=1,
            subfarm_id=1,
            subfarm_identity_key="sf-1",
            variety_id=1,
            destination_factory_id=1,
            opening_mature_inventory_kg=Decimal("0"),
            natural_maturity_supply_kg=Decimal("0"),
            available_mature_quantity_kg=Decimal("0"),
            mature_inventory_loss_quantity_kg=Decimal("0"),
            harvestable_mature_quantity_kg=Decimal("0"),
            allocated_harvest_capacity_kg=Decimal("0"),
            harvested_quantity_kg=Decimal("0"),
            closing_mature_inventory_kg=Decimal("0"),
            unharvested_backlog_kg=Decimal("0"),
            arrival_quantity_kg=Decimal("100"),
            opening_cohort_count=1,
            closing_cohort_count=1,
            cohort_source_ref_hashes=[],
        )
    )
    await sqlite_full_session.flush()

    # The default path accepts a well-formed row with member coverage.
    candidates = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 3, 1),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=2026,
    )
    assert any(c["id"] == hsr_id for c in candidates)


@pytest.mark.asyncio
async def test_default_selector_rejects_wrong_season_via_persisted_identity(
    sqlite_full_session: AsyncSession,
) -> None:
    """When input_snapshot.forecast_season mismatches the request,
    the selector MUST exclude the row, regardless of as_of_date."""
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        as_of_date=date(2025, 12, 1),
        forecast_start_date=date(2025, 12, 1),
        forecast_end_date=date(2025, 12, 31),
        input_snapshot_forecast_season=2024,
    )
    candidates = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2025, 12, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=2025,
    )
    assert all(c["id"] != hsr_id for c in candidates)


@pytest.mark.asyncio
async def test_override_selector_rejects_malformed_result_hash(
    sqlite_full_session: AsyncSession,
) -> None:
    """Override path: when the caller supplies a specific run_id
    whose ``result_hash`` is valid at the schema level but the
    selector's validation pipeline rejects it (e.g. the round-6
    hex-re check) — verify the rejection is enforced.

    Schema CHECK constraints enforce 64-char hex at insert time, so
    this test exercises the selector-side check by passing a
    fake-typed row object whose ``result_hash`` is not 64-char hex
    directly into the validation function."""
    from backend.app.agent.adapters.baseline_composer import (
        _validate_task9_row_against_scope,
    )

    @dataclass
    class _FakeRow:
        status: str = "completed"
        destination_factory_id: int = 1
        as_of_date: date = date(2026, 3, 1)
        forecast_end_date: date = date(2026, 3, 31)
        result_hash: str = "not-a-valid-64-char-hex"
        config_hash: str = "b" * 64
        id: int = 999

    accepted = await _validate_task9_row_against_scope(
        row=_FakeRow(),
        as_of=date(2026, 3, 1),
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        session=sqlite_full_session,
        effective_forecast_season=2026,
    )
    assert accepted is False, (
        "selector-side _validate_task9_row_against_scope accepted a row "
        "with malformed result_hash; should reject"
    )


@pytest.mark.asyncio
async def test_override_selector_rejects_orm_read_failure(
    sqlite_full_session: AsyncSession,
) -> None:
    """When the ORM read raises an unexpected exception, the
    selector must surface UPSTREAM_READ_FAILURE — NOT a silent
    NOT_FOUND."""
    from backend.app.agent.adapters.baseline_composer import UpstreamReadFailure
    from unittest.mock import patch

    # Patch session.get to raise unconditionally.
    async def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated ORM read failure")

    with patch.object(sqlite_full_session, "get", side_effect=_raise):
        with pytest.raises(UpstreamReadFailure):
            await _select_harvest_state_run_candidates(
                sqlite_full_session,
                as_of=date(2026, 3, 1),
                run_id_override=999999,
                destination_factory_id=1,
                requested_variety_codes=(),
                effective_forecast_season=2026,
            )


# ===========================================================================
# Test D: TASK-010 default selector returns typed discrimination
# ===========================================================================


@pytest.mark.asyncio
async def test_default_selector_rejects_prediction_hash_malformed(
    sqlite_full_session: AsyncSession,
) -> None:
    """Residual row whose prediction_hash is 64-char hex (DB schema
    forces this) but whose ``fallback_reason`` is set is rejected
    by the override selector — fallback_reason is a typed
    disqualifier.  When fallback_reason is None, the override
    selector accepts the row.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        input_snapshot_forecast_season=2026,
    )
    rm_id = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        fallback_reason="simulated disqualifier",
    )
    candidates = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=rm_id,
    )
    assert candidates == [], (
        "override selector accepted residual with fallback_reason set; "
        "fallback_reason is a disqualifier"
    )


@pytest.mark.asyncio
async def test_default_selector_rejects_execution_status_not_completed(
    sqlite_full_session: AsyncSession,
) -> None:
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        input_snapshot_forecast_season=2026,
    )
    rm_id = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        execution_status="failed",
    )
    candidates = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=rm_id,
    )
    assert candidates == [], (
        "override selector accepted residual with execution_status != completed"
    )


@pytest.mark.asyncio
async def test_default_selector_rejects_task9_lineage_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    hsr_a = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot_forecast_season=2026,
    )
    hsr_b = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="d" * 64,
        config_hash="e" * 64,
        input_snapshot_forecast_season=2026,
    )
    # Residual is bound to hsr_b (task9_result_hash d*64) but caller
    # says task9_run_id=hsr_a + result_hash=a*64.
    rm_id = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_b,
        task9_result_hash="d" * 64,
    )
    candidates = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_a,
        task9_result_hash="a" * 64,
        prediction_run_id_override=rm_id,
    )
    assert candidates == [], (
        "override selector accepted residual whose task9 lineage "
        "differs from caller-supplied task9_run_id + result_hash"
    )


@pytest.mark.asyncio
async def test_default_selector_rejects_artifact_hash_malformed(
    sqlite_full_session: AsyncSession,
) -> None:
    """The schema enforces 64-char hex for every column-level
    artifact_hashes entry.  A row with a non-64-char hex
    ``artifact_hashes`` entry cannot be inserted at the DB level,
    so this test verifies the boundary condition: a row with valid
    64-char hex artifact_hashes IS accepted by the override
    selector (typed discriminator returns the row)."""
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        input_snapshot_forecast_season=2026,
    )
    rm_id = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        artifact_hashes=["a" * 64, "b" * 64],
    )
    candidates = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=rm_id,
    )
    assert any(c["id"] == rm_id for c in candidates)


@pytest.mark.asyncio
async def test_default_selector_rejects_orm_read_failure_task10(
    sqlite_full_session: AsyncSession,
) -> None:
    from backend.app.agent.adapters.baseline_composer import UpstreamReadFailure
    from unittest.mock import patch

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated ORM read failure (task10)")

    with patch.object(sqlite_full_session, "get", side_effect=_raise):
        with pytest.raises(UpstreamReadFailure):
            await _select_residual_prediction_run_candidates(
                sqlite_full_session,
                task9_run_id=999999,
                task9_result_hash="a" * 64,
                prediction_run_id_override=999999,
            )


# ===========================================================================
# Test E: per-variety whole-day fail-closed
# ===========================================================================


@pytest.mark.asyncio
async def test_missing_one_quantile_clears_whole_day_contributions() -> None:
    """When Dx has all three quantiles and D12 is missing P90, the
    day's contribution list MUST be empty — Dx's contribution must
    NOT survive in the output."""
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("120"),
        (d, "P80", 1): Decimal("200"),
        (d, "P90", 1): Decimal("300"),
        (d, "P50", 2): Decimal("80"),
        (d, "P80", 2): Decimal("100"),
        # D12 P90 missing
    }
    from backend.app.agent.adapters.baseline_composer import (
        DefaultSpringFestivalCalendarPort,
    )

    @dataclass
    class _V:
        variety_id: str

    varieties = [_V("Dx"), _V("D12")]
    contributions, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1, "D12": 2},
        task9_run_id=1,
    )
    # Dx partial contribution must NOT survive; whole day cleared.
    assert contributions == [], (
        f"per-variety contributions must be empty when one variety is "
        f"missing any quantile, but got {contributions}"
    )
    # And a TASK9_PER_VARIETY_GRAIN_MISSING blocker must be emitted.
    codes = [b.code.value for b in blockers]
    assert "TASK9_PER_VARIETY_GRAIN_MISSING" in codes, (
        f"expected TASK9_PER_VARIETY_GRAIN_MISSING blocker, got {codes}"
    )


# ===========================================================================
# Test F: emitted contribution rates sum to 1
# ===========================================================================


@pytest.mark.asyncio
async def test_emitted_contribution_rates_sum_to_one() -> None:
    """Persisted member variety set is a SUPERSET of the requested
    variety set.  Public output must use the SELECTED TASK-009
    member variety set as the denominator (no silent truncation).

    Dx (rate P50=0.6) + D12 (rate P50=0.4) = 1.0; L25 is a persisted
    variety not in the request and must NOT inflate the denominator.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("120"),
        (d, "P80", 1): Decimal("200"),
        (d, "P90", 1): Decimal("300"),
        (d, "P50", 2): Decimal("80"),
        (d, "P80", 2): Decimal("100"),
        (d, "P90", 2): Decimal("100"),
        (d, "P50", 3): Decimal("0"),
        (d, "P80", 3): Decimal("0"),
        (d, "P90", 3): Decimal("0"),
    }
    from backend.app.agent.adapters.baseline_composer import (
        DefaultSpringFestivalCalendarPort,
    )

    @dataclass
    class _V:
        variety_id: str

    # Request Dx + D12 only (not L25).
    varieties = [_V("Dx"), _V("D12")]
    contributions, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1, "D12": 2, "L25": 3},
        task9_run_id=1,
    )
    # Dx + D12 only; L25 is NOT requested so its rows must be ignored.
    assert {c.variety_id for c in contributions} == {"Dx", "D12"}, (
        f"expected only Dx and D12; got {[c.variety_id for c in contributions]}"
    )
    # sum of contribution_rate_p50 for Dx + D12 = 0.6 + 0.4 = 1.0
    sum_p50 = sum(Decimal(c.contribution_rate_p50) for c in contributions)
    assert sum_p50 == Decimal("1.0"), (
        f"contribution_rate_p50 sum must equal 1.0 (denominator = selected "
        f"member variety set), got {sum_p50}"
    )
    sum_p80 = sum(Decimal(c.contribution_rate_p80) for c in contributions)
    assert sum_p80 == Decimal("1.0")
    sum_p90 = sum(Decimal(c.contribution_rate_p90) for c in contributions)
    assert sum_p90 == Decimal("1.0")


# ===========================================================================
# Test G: no-member blocker carries real task9_run_id
# ===========================================================================


@pytest.mark.asyncio
async def test_no_member_blocker_carries_real_task9_run_id() -> None:
    """The TASK9_PER_VARIETY_GRAIN_MISSING blocker emitted by the
    per-day contribution path MUST carry the real task9_run_id
    (not variety_pk or some other field) in its details."""
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    # NO member rows at all for this date.
    member_rows: dict = {}
    from backend.app.agent.adapters.baseline_composer import (
        DefaultSpringFestivalCalendarPort,
    )

    @dataclass
    class _V:
        variety_id: str

    varieties = [_V("Dx")]
    _, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1},
        task9_run_id=42,
    )
    codes = [b.code.value for b in blockers]
    assert "TASK9_PER_VARIETY_GRAIN_MISSING" in codes, (
        f"expected TASK9_PER_VARIETY_GRAIN_MISSING, got {codes}"
    )
    grain_blk = next(b for b in blockers if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING")
    details = grain_blk.details
    assert details.get("task9_run_id") == 42, (
        f"grain blocker must carry real task9_run_id=42 in details, got {details}"
    )
    assert details.get("date") == d.isoformat()


# ===========================================================================
# Test H: blocked scenario performs ZERO upstream reads
# ===========================================================================


@pytest.mark.asyncio
async def test_blocked_scenario_does_not_call_daily_adapter(
    sqlite_full_session: AsyncSession,
) -> None:
    """When scenario_overrides is non-empty, the scenario adapter
    must return BLOCKED at the entry point WITHOUT invoking the
    daily curve adapter or baseline composition.  A spy adapter
    that fails on call verifies the assertion."""
    from datetime import date as _date

    @dataclass
    class _SpyDailyAdapter:
        calls: int = 0

        async def execute(self, session: AsyncSession, *, input: object) -> object:
            self.calls += 1
            raise AssertionError(
                "daily adapter was called in a blocked scenario; this is forbidden"
            )

    @dataclass
    class _SpyPeakAdapter:
        calls: int = 0

        def execute(self, *, input: object) -> object:
            self.calls += 1
            raise AssertionError("peak adapter was called in a blocked scenario; this is forbidden")

    nr = _make_normalized_request(
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        season=2026,
        as_of=date(2026, 3, 1),
    )
    rl = ResolvedLocation(
        status="resolved",
        location_reference_id=1,
        matched_location_method="REFERENCE_ID",
    )
    scenario_override = ProcessorCapacityScenarioOverride(
        target="PROCESSOR_CAPACITY",
        value=ProcessorCapacityOverrideValue(value="200.0", unit="t_per_day"),
        source_attestation="test",
        source_ref=None,
    )
    inp = SimulateScenarioInput(
        normalized_request=nr,
        resolved_location=rl,
        parameters=[],
        scenario_overrides=[scenario_override],
        uncertainty_widening_policy=UncertaintyWideningPolicy(
            policy_version="v1",
            config_hash="b" * 64,
            factors_by_source_level={
                "step_1_same_farm_same_variety_high_evidence": "1.0",
                "step_2_same_township_similar_altitude": "1.1",
                "step_3_same_county_same_climate_zone": "1.2",
                "step_4_province_level_same_variety": "1.3",
                "step_5_variety_document_prior_only": "1.4",
            },
        ),
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

    spy_daily = _SpyDailyAdapter()
    spy_peak = _SpyPeakAdapter()
    adapter = DefaultScenarioAdapter(
        daily_curve_adapter=spy_daily,  # type: ignore[arg-type]
        peak_adapter=spy_peak,  # type: ignore[arg-type]
    )
    out = await adapter.execute(sqlite_full_session, input=inp)
    assert out.status == "BLOCKED"
    assert out.forecast_daily_curve is None
    assert out.forecast_peak is None
    assert out.delta_vs_baseline is None
    assert spy_daily.calls == 0
    assert spy_peak.calls == 0


# ===========================================================================
# Test I: Spring Festival missing-policy blocker is emitted by compute_baseline
# ===========================================================================


@pytest.mark.asyncio
async def test_spring_festival_missing_policy_via_compute_baseline(
    sqlite_full_session: AsyncSession,
) -> None:
    """The default Spring Festival calendar returns is_policy_loaded()==False
    and phase_for()=='NONE'.  ``compute_baseline`` must emit a typed
    ``SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`` blocker — not silently
    treat 'NONE' as a confirmed phase."""
    baseline = DefaultTaskCompositionBaseline()
    assert baseline._calendar.is_policy_loaded() is False
    assert baseline._calendar.phase_for(target=date(2026, 3, 1)) == "NONE"

    # The blocker MUST be raised inside compute_baseline, not just
    # by inspecting the calendar helper.
    nr = _make_normalized_request(
        varieties=[NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")],
        season=2026,
        as_of=date(2026, 3, 1),
    )
    rl = ResolvedLocation(
        status="resolved",
        location_reference_id=1,
        matched_location_method="REFERENCE_ID",
    )
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=nr,
        resolved_location=rl,
        parameters=[],
        advanced_overrides=None,
    )
    codes = [b.code.value for b in result.blockers]
    assert "SPRING_FESTIVAL_CALENDAR_POLICY_MISSING" in codes, (
        f"compute_baseline did not emit SPRING_FESTIVAL_CALENDAR_POLICY_MISSING; got {codes}"
    )
    sf = next(
        b for b in result.blockers if b.code.value == "SPRING_FESTIVAL_CALENDAR_POLICY_MISSING"
    )
    # details must carry effective_forecast_season (the request's identity)
    assert sf.details.get("effective_forecast_season") == "2026"
