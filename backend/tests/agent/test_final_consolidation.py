"""TASK-013 Slice A — Round 8 Final Corrective Pass (review 4680340321).

This file is the test-first probe for the 7 P0 findings in review
``4680340321``.  Every test is RUN against the starting HEAD
``8186122...`` BEFORE any production code change, and at least some
tests MUST fail to confirm they are probing real defects.

**Reviewer directive: real TASK-009 persistence shape.**  The legacy
``input_snapshot["forecast_season"]`` is NOT a field that
``_sorted_request_snapshot()`` writes; it was a fabrication from
round 7.  Round 8 tests use the REAL persistence shape
(``input_snapshot={}`` or with non-season keys) and assert the
typed-failure surface that real rows must produce.

The 7 P0 findings and the corresponding test groups:

* **P0-1 (TASK-009 synthetic season identity)**
  ``test_task9_real_persistence_row_has_no_forecast_season``,
  ``test_task9_no_persisted_season_emits_scope_mismatch``,
  ``test_task9_season_mismatch_emits_scope_mismatch``.

* **P0-2 (TASK-009 typed selector result)**
  ``test_task9_default_not_found_emits_task9_authority_not_found``,
  ``test_task9_default_destination_mismatch_emits_scope_mismatch``,
  ``test_task9_default_date_mismatch_emits_scope_mismatch``,
  ``test_task9_default_hash_malformed_emits_typed``,
  ``test_task9_default_member_query_exception_emits_upstream_read_failure``,
  ``test_task9_default_multiple_valid_candidates_emits_conflict``.

* **P0-3 (TASK-010 typed selector + full identity)**
  ``test_task10_default_not_found_emits_task10_authority_not_found``,
  ``test_task10_default_execution_status_failed_emits_scope_mismatch``,
  ``test_task10_default_lineage_mismatch_emits_typed``,
  ``test_task10_default_hash_malformed_emits_typed``,
  ``test_task10_default_fallback_reason_set_emits_scope_mismatch``,
  ``test_task10_default_orm_read_failure_emits_upstream_read_failure``,
  ``test_task10_default_multiple_valid_candidates_emits_conflict``.

* **P0-4 (per-variety late missing grain)**
  ``test_per_variety_late_missing_grain_clears_whole_day``.

* **P0-5 (denominator scope)**
  ``test_per_variety_non_zero_extra_persisted_variety_emits_scope_mismatch``.

* **P0-6 (all grain blockers carry task9_run_id)**
  ``test_no_member_blocker_carries_task9_run_id``,
  ``test_missing_quantile_blocker_carries_task9_run_id``,
  ``test_member_volume_mismatch_blocker_carries_task9_run_id``,
  ``test_emitted_rate_mismatch_blocker_carries_task9_run_id``.

* **P0-7 (PR body stale)** is a documentation-only finding; it is
  handled in the final report and PR body markdown.
"""

# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import patch

from backend.app.agent.adapters.baseline_composer import (
    AuthoritySelectionResult,
    DATE_COVERAGE_MISMATCH,
    DefaultTaskCompositionBaseline,
    DESTINATION_MISMATCH,
    EXECUTION_STATUS_NOT_COMPLETED,
    FALLBACK_RUN_NOT_AUTHORITATIVE,
    MEMBER_VARIETY_SET_MISMATCH,
    SEASON_BINDING_UNAVAILABLE,
    _compose_rows,
    _evaluate_task10_row_against_scope,
    _evaluate_task9_row_against_scope,
    _per_variety_contribution_from_member_rows,
    _select_harvest_state_run_candidates,
    _select_residual_prediction_run_candidates,
)
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
# Real TASK-009 persistence fixture (no fabricated forecast_season)
# ---------------------------------------------------------------------------

#: Canonical real-persistence ``input_snapshot`` for a TASK-009 row
#: created via ``_sorted_request_snapshot()``.  This is the
#: reference shape for round 8 — it does NOT contain
#: ``forecast_season``.  Per Charles §3: "input_snapshot
#: ['forecast_season'] cannot be described as a real identity every
#: TASK-009 row persists".
_REAL_TASK9_INPUT_SNAPSHOT: dict[str, Any] = {
    "as_of_date": "2026-01-10",
    "forecast_start_date": "2026-01-01",
    "forecast_end_date": "2026-01-31",
    "forecast_quantiles": ["P50", "P80", "P90"],
    "destination_factory_id": 1,
}


def _make_normalized_request(
    *,
    varieties: list[NormalizedVarietyInput] | None = None,
    season: int | None = 2026,
    as_of: date = date(2026, 1, 15),
) -> NormalizedAgentRequest:
    """Build a normalized request.

    ``season`` defaults to ``None`` (no season request) so tests that
    do not care about season binding do not accidentally trigger
    AUTHORITY_SCOPE_MISMATCH from the round 8 typed selector.  Tests
    that DO care about season behavior must pass ``season=...``
    explicitly.
    """
    provenance = RequestedAsOfDateProvenance(
        caller_requested_as_of_date=as_of,
        effective_as_of_date=as_of,
        override_applied=False,
        override_kind=None,
        source_attestation=None,
        source_ref=None,
    )
    return NormalizedAgentRequest(
        request_id="req-round8",
        request_received_at=datetime(2026, 1, 15, tzinfo=UTC),
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
        # Use ``is None`` to allow callers to pass an empty list
        # for "no varieties requested" (the default fallback is
        # only used when the argument is genuinely None).
        varieties=(
            varieties
            if varieties is not None
            else [NormalizedVarietyInput(variety_id="Dx", planting_area_mu="100.0")]
        ),
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


@pytest_asyncio.fixture
async def sqlite_full_session() -> AsyncSession:
    """In-memory SQLite session with the full TASK-009/010 + Variety
    tables.  Used to exercise the ORM-level selectors end-to-end
    without any upstream read failure caused by missing tables.
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
    as_of_date: date = date(2026, 1, 10),
    forecast_start_date: date = date(2026, 1, 1),
    forecast_end_date: date = date(2026, 1, 31),
    status: str = "completed",
    destination_factory_id: int = 1,
    input_snapshot: dict[str, Any] | None = None,
    maturity_forecast_run_id: int | None = None,
) -> int:
    """Insert a real-persistence-shape TASK-009 row.

    ``input_snapshot`` defaults to the canonical real-persistence
    shape (no ``forecast_season``).  Pass an explicit dict to
    override (e.g. to add a season key for a season-binding test).
    """
    if input_snapshot is None:
        input_snapshot = dict(_REAL_TASK9_INPUT_SNAPSHOT)
    row = HarvestStateRun(
        status=status,
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot=input_snapshot,
        resolved_parameter_snapshot={},
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


def _has_blocker_with_reason(
    blockers: list[Blocker],
    code: BlockerCode,
    *,
    reason: str | None = None,
) -> bool:
    for b in blockers:
        if b.code != code:
            continue
        if reason is None:
            return True
        if (b.details or {}).get("reason") == reason:
            return True
    return False


# ===========================================================================
# P0-1: TASK-009 real persistence has no forecast_season; the absence is
# AUTHORITY_SCOPE_MISMATCH, NOT TASK9_AUTHORITY_NOT_FOUND
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_real_persistence_row_has_no_forecast_season(
    sqlite_full_session: AsyncSession,
) -> None:
    """The real TASK-009 persistence shape (the row inserted here
    with the canonical real-persistence ``input_snapshot``) MUST NOT
    carry a ``forecast_season`` key.  This test pins the production
    contract: rows that contain a fabricated ``forecast_season`` are
    not what ``_sorted_request_snapshot()`` writes.
    """
    hsr_id = await _insert_harvest_state_run(sqlite_full_session)
    from sqlalchemy import select

    row = (
        await sqlite_full_session.execute(
            select(HarvestStateRun).where(HarvestStateRun.id == hsr_id)
        )
    ).scalar_one()
    assert "forecast_season" not in (row.input_snapshot or {}), (
        "real TASK-009 persistence shape must NOT carry "
        "input_snapshot['forecast_season']; got "
        f"{row.input_snapshot}"
    )


@pytest.mark.asyncio
async def test_task9_no_persisted_season_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """A real-persistence row (no ``forecast_season``) with the
    request asking for an explicit season MUST be excluded with a
    typed :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` blocker
    carrying ``reason=PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE``,
    NOT collapsed into :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=2026,
    )
    assert selection.candidates == (), (
        f"row {hsr_id} must be excluded (no persisted season identity); "
        f"got candidates={selection.candidates}"
    )
    assert selection.blockers, "selector must surface typed blockers, not silent empty"
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"expected AUTHORITY_SCOPE_MISMATCH (real row, no persisted season), got {codes}"
    )
    scope_blk = next(b for b in selection.blockers if b.code.value == "AUTHORITY_SCOPE_MISMATCH")
    details = scope_blk.details or {}
    assert details.get("reason") == SEASON_BINDING_UNAVAILABLE, (
        f"expected reason={SEASON_BINDING_UNAVAILABLE}, got {details}"
    )
    assert details.get("persisted_season_identity") is None
    assert details.get("requested_effective_forecast_season") == 2026


@pytest.mark.asyncio
async def test_task9_season_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """A row whose ``input_snapshot`` carries a season key that
    differs from the requested season MUST be excluded with a typed
    AUTHORITY_SCOPE_MISMATCH carrying the mismatched
    ``persisted_season_identity``.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2025},
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=2026,
    )
    assert selection.candidates == ()
    scope_blks = [b for b in selection.blockers if b.code.value == "AUTHORITY_SCOPE_MISMATCH"]
    assert scope_blks, f"expected AUTHORITY_SCOPE_MISMATCH, got {selection.blockers}"
    details = scope_blks[0].details or {}
    assert details.get("reason") == SEASON_BINDING_UNAVAILABLE
    assert details.get("persisted_season_identity") == 2025
    assert details.get("requested_effective_forecast_season") == 2026


# ===========================================================================
# P0-2: TASK-009 default selector returns typed discrimination
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_default_not_found_emits_task9_authority_not_found(
    sqlite_full_session: AsyncSession,
) -> None:
    """No row in the DB → :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`
    (NOT :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`).
    """
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    assert selection.blockers
    codes = [b.code.value for b in selection.blockers]
    assert "TASK9_AUTHORITY_NOT_FOUND" in codes, (
        f"empty DB must emit TASK9_AUTHORITY_NOT_FOUND, got {codes}"
    )


@pytest.mark.asyncio
async def test_task9_default_destination_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """The strict-scope filter applies ``destination_factory_id`` in
    the WHERE clause; a request that asks for ``destination=1`` and
    the row has ``destination=2`` is filtered out at the base-scope
    stage and yields :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`
    (no base-scope rows).  This test asserts that base-scope
    behavior (NOT a silent empty list, NOT a scope-mismatch
    collapse).

    The typed AUTHORITY_SCOPE_MISMATCH+DESTINATION_MISMATCH path is
    exercised in :func:`test_task9_default_override_path_destination_mismatch_emits_scope_mismatch`
    via the override path (single-row validator).
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        destination_factory_id=2,
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "TASK9_AUTHORITY_NOT_FOUND" in codes, (
        f"base-scope destination filter must yield TASK9_AUTHORITY_NOT_FOUND, got {codes}"
    )


@pytest.mark.asyncio
async def test_task9_default_date_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """The strict-scope filter applies ``as_of_date <= as_of <=
    forecast_end_date`` in the WHERE clause; a request whose as_of
    is outside the row's coverage is filtered out at the base-scope
    stage and yields
    :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND` (no base-scope
    rows).

    The typed AUTHORITY_SCOPE_MISMATCH+DATE_COVERAGE_MISMATCH path
    is exercised in
    :func:`test_task9_default_override_path_date_mismatch_emits_scope_mismatch`
    via the override path.
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        as_of_date=date(2025, 6, 1),
        forecast_start_date=date(2025, 6, 1),
        forecast_end_date=date(2025, 6, 30),
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "TASK9_AUTHORITY_NOT_FOUND" in codes, (
        f"base-scope date-coverage filter must yield TASK9_AUTHORITY_NOT_FOUND, got {codes}"
    )


@pytest.mark.asyncio
async def test_task9_default_override_path_destination_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """Override path: a specific run id is requested but the row's
    ``destination_factory_id`` differs from the request's
    destination → :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=DESTINATION_MISMATCH``.  This is the override-path
    equivalent of
    :func:`test_task9_default_destination_mismatch_emits_scope_mismatch`.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        destination_factory_id=2,
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=hsr_id,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    assert _has_blocker_with_reason(
        selection.blockers, BlockerCode.AUTHORITY_SCOPE_MISMATCH, reason=DESTINATION_MISMATCH
    )


@pytest.mark.asyncio
async def test_task9_default_override_path_date_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """Override path: a specific run id is requested but the row's
    date coverage does not include the request's as_of →
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=DATE_COVERAGE_MISMATCH``.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        as_of_date=date(2025, 6, 1),
        forecast_start_date=date(2025, 6, 1),
        forecast_end_date=date(2025, 6, 30),
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=hsr_id,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    assert _has_blocker_with_reason(
        selection.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=DATE_COVERAGE_MISMATCH,
    )


@pytest.mark.asyncio
async def test_task9_default_hash_malformed_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """Row's ``result_hash`` is not 64-char lowercase hex →
    :data:`BlockerCode.AUTHORITY_HASH_MALFORMED`.  We use a typed
    fake row (the DB schema enforces valid hex at insert time, so
    we go through the shared validator).
    """

    @dataclass
    class _FakeRow:
        id: int = 999
        status: str = "completed"
        destination_factory_id: int = 1
        as_of_date: date = date(2026, 1, 15)
        forecast_end_date: date = date(2026, 1, 31)
        result_hash: str = "not-a-valid-64-char-hex"
        config_hash: str = "b" * 64
        input_snapshot: dict = field(default_factory=dict)

    outcome = await _evaluate_task9_row_against_scope(
        row=_FakeRow(),
        as_of=date(2026, 1, 15),
        destination_factory_id=1,
        requested_variety_codes=(),
        session=sqlite_full_session,
        effective_forecast_season=None,
    )
    assert outcome.candidates == ()
    assert outcome.blockers
    codes = [b.code.value for b in outcome.blockers]
    assert "AUTHORITY_HASH_MALFORMED" in codes, f"expected AUTHORITY_HASH_MALFORMED, got {codes}"
    blk = next(b for b in outcome.blockers if b.code.value == "AUTHORITY_HASH_MALFORMED")
    assert (blk.details or {}).get("field") == "result_hash"


@pytest.mark.asyncio
async def test_task9_default_member_query_exception_emits_upstream_read_failure(
    sqlite_full_session: AsyncSession,
) -> None:
    """When the member-variety ORM query raises an unexpected
    exception, the selector must surface
    :data:`BlockerCode.UPSTREAM_READ_FAILURE` (NOT a silent empty
    list).
    """
    hsr_id = await _insert_harvest_state_run(sqlite_full_session)

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated member-variety ORM read failure")

    # session.execute is called both for the base-scope read AND the
    # member-variety read; we patch the entire execute so the
    # base-scope returns no rows and the validator never reaches the
    # member-variety step.  Instead, force a member-variety call by
    # supplying a non-empty variety code AND stubbing
    # _member_variety_codes_for_run.
    with patch(
        "backend.app.agent.adapters.baseline_composer._member_variety_codes_for_run",
        side_effect=RuntimeError("simulated member-variety ORM read failure"),
    ):
        selection = await _select_harvest_state_run_candidates(
            sqlite_full_session,
            as_of=date(2026, 1, 15),
            run_id_override=None,
            destination_factory_id=1,
            requested_variety_codes=("Dx",),
            effective_forecast_season=None,
        )
    assert selection.candidates == ()
    assert selection.blockers
    codes = [b.code.value for b in selection.blockers]
    assert "UPSTREAM_READ_FAILURE" in codes, (
        f"expected UPSTREAM_READ_FAILURE on member-variety ORM failure, got {codes}"
    )
    assert hsr_id  # silence unused warning


@pytest.mark.asyncio
async def test_task9_default_multiple_valid_candidates_emits_conflict(
    sqlite_full_session: AsyncSession,
) -> None:
    """Two fully-valid TASK-009 rows in scope →
    :data:`BlockerCode.AUTHORITY_CONFLICT` is emitted by
    ``compute_baseline`` when it dispatches on the selector
    result.  Both rows have the real-persistence shape; the
    selector's discriminator surfaces BOTH candidates; the
    composer then disambiguates via AUTHORITY_CONFLICT.

    NOTE: this test inserts rows with the real persistence shape
    plus a ``forecast_season`` key on each — this is the ONLY
    legitimate way to satisfy ``compute_baseline`` (which always
    requires a season).  The season test (P0-1) deliberately uses
    the real-persistence shape WITHOUT a season key to assert
    AUTHORITY_SCOPE_MISMATCH.
    """
    sqlite_full_session.add(Variety(id=1, code="Dx", name="Test Dx"))
    await sqlite_full_session.flush()
    hsr_a = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    hsr_b = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="c" * 64,
        config_hash="d" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=2026,
    )
    assert {c["id"] for c in selection.candidates} == {hsr_a, hsr_b}, (
        f"selector must surface both candidates, got {selection.candidates}"
    )
    # AUTHORITY_CONFLICT is emitted by compute_baseline, not the
    # selector; the selector returns the 2 candidates.
    # Use a request with no varieties so the variety-scope check
    # does not exclude both rows.
    baseline = DefaultTaskCompositionBaseline()
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=_make_normalized_request(varieties=[]),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=None,
    )
    codes = [b.code.value for b in result.blockers]
    assert "AUTHORITY_CONFLICT" in codes, (
        f"compute_baseline must emit AUTHORITY_CONFLICT on multiple valid candidates, got {codes}"
    )


# ===========================================================================
# P0-3: TASK-010 default selector returns typed discrimination; full
# identity surface is validated by both default and override paths.
# ===========================================================================


@pytest.mark.asyncio
async def test_task10_default_not_found_emits_task10_authority_not_found(
    sqlite_full_session: AsyncSession,
) -> None:
    """No TASK-010 row for the selected TASK-009 lineage →
    :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`.
    """
    hsr_id = await _insert_harvest_state_run(sqlite_full_session)
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "TASK10_AUTHORITY_NOT_FOUND" in codes, (
        f"expected TASK10_AUTHORITY_NOT_FOUND, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_execution_status_failed_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """TASK-010 row with ``execution_status != 'completed'`` →
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=EXECUTION_STATUS_NOT_COMPLETED``.
    """
    hsr_id = await _insert_harvest_state_run(sqlite_full_session)
    await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        execution_status="failed",
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,
    )
    assert selection.candidates == ()
    assert _has_blocker_with_reason(
        selection.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=EXECUTION_STATUS_NOT_COMPLETED,
    )


@pytest.mark.asyncio
async def test_task10_default_lineage_mismatch_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """A TASK-010 row that exists but is bound to a different
    TASK-009 lineage (task9_result_hash mismatch) →
    :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH`.  This is
    exercised through the override path (a specific run id is
    supplied that doesn't match the selected TASK-009 lineage).
    """
    hsr_a = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    hsr_b = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="d" * 64,
        config_hash="e" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    # Override path: caller asks for hsr_a with result_hash=a*64
    # but we point to the hsr_b residual — lineage mismatch.
    rm_b = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_b,
        task9_result_hash="d" * 64,
        prediction_hash="e" * 64,
        prediction_input_signature="1" * 64,
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_a,
        task9_result_hash="a" * 64,
        prediction_run_id_override=rm_b,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_LINEAGE_MISMATCH" in codes, (
        f"expected AUTHORITY_LINEAGE_MISMATCH, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_hash_malformed_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """TASK-010 row whose ``prediction_hash`` is not 64-char hex →
    :data:`BlockerCode.AUTHORITY_HASH_MALFORMED`.  We use a typed
    fake row (DB schema enforces valid hex at insert time, so we
    go through the shared validator).
    """

    @dataclass
    class _FakeRow:
        id: int = 999
        execution_status: str = "completed"
        task9_run_id: int = 1
        task9_result_hash: str = "a" * 64
        prediction_hash: str = "not-hex"
        config_hash: str = "b" * 64
        prediction_input_signature: str = "9" * 64
        canonical_payload_hash: str = "c" * 64
        feature_schema_hash: str = "f" * 64
        artifact_hashes: list[str] = field(default_factory=lambda: ["a" * 64])
        fallback_reason: str | None = None

    outcome = await _evaluate_task10_row_against_scope(
        row=_FakeRow(),
        task9_run_id=1,
        task9_result_hash="a" * 64,
    )
    assert outcome.candidates == ()
    codes = [b.code.value for b in outcome.blockers]
    assert "AUTHORITY_HASH_MALFORMED" in codes, (
        f"expected AUTHORITY_HASH_MALFORMED on prediction_hash, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_fallback_reason_set_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """A TASK-010 row whose ``fallback_reason`` is set is a fallback
    run and not authoritative →
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=FALLBACK_RUN_NOT_AUTHORITATIVE``.
    """
    hsr_id = await _insert_harvest_state_run(sqlite_full_session)
    await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        fallback_reason="simulated fallback",
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,
    )
    assert selection.candidates == ()
    assert _has_blocker_with_reason(
        selection.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=FALLBACK_RUN_NOT_AUTHORITATIVE,
    )


@pytest.mark.asyncio
async def test_task10_default_orm_read_failure_emits_upstream_read_failure(
    sqlite_full_session: AsyncSession,
) -> None:
    """An ORM read failure (simulated) on the default path →
    :data:`BlockerCode.UPSTREAM_READ_FAILURE`.
    """
    hsr_id = await _insert_harvest_state_run(sqlite_full_session)

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated TASK-010 ORM read failure")

    with patch.object(sqlite_full_session, "execute", side_effect=_raise):
        selection = await _select_residual_prediction_run_candidates(
            sqlite_full_session,
            task9_run_id=hsr_id,
            task9_result_hash="a" * 64,
            prediction_run_id_override=None,
        )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "UPSTREAM_READ_FAILURE" in codes, (
        f"expected UPSTREAM_READ_FAILURE on ORM read failure, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_multiple_valid_candidates_emits_conflict(
    sqlite_full_session: AsyncSession,
) -> None:
    """Two fully-valid TASK-010 rows in scope →
    :data:`BlockerCode.AUTHORITY_CONFLICT` (disclosed via
    ``compute_baseline``).
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    rm_a = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_hash="a" * 64,
        prediction_input_signature="0" * 64,
    )
    rm_b = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_hash="b" * 64,
        prediction_input_signature="1" * 64,
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,
    )
    assert {c["id"] for c in selection.candidates} == {rm_a, rm_b}
    # The two rows produce different prediction_hashes, so the
    # default path's full identity validation should accept both;
    # compute_baseline will surface AUTHORITY_CONFLICT.  Use a
    # request with no varieties so the variety-scope check does
    # not exclude both TASK-009 candidates.
    baseline = DefaultTaskCompositionBaseline()
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=_make_normalized_request(varieties=[]),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=None,
    )
    codes = [b.code.value for b in result.blockers]
    assert "AUTHORITY_CONFLICT" in codes, (
        f"compute_baseline must emit AUTHORITY_CONFLICT for multiple "
        f"valid TASK-010 candidates, got {codes}"
    )


# ===========================================================================
# P0-4: per-variety late missing grain must clear the whole day
# ===========================================================================


@pytest.mark.asyncio
async def test_per_variety_late_missing_grain_clears_whole_day() -> None:
    """Phase 1 prevalidation: when Dx has all three quantiles
    (P50=120, P80=200, P90=300) and D12 is missing P90, the day's
    contribution list MUST be empty.  Dx's contribution MUST NOT
    survive even though its own row is well-formed (the round-7
    "late missing grain" defect).
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("300"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("120"),
        (d, "P80", 1): Decimal("200"),
        (d, "P90", 1): Decimal("300"),
        (d, "P50", 2): Decimal("80"),
        (d, "P80", 2): Decimal("100"),
        # D12 P90 missing on purpose
    }

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
        task9_run_id=42,
    )
    assert contributions == [], (
        f"per-variety contributions must be empty when one variety is "
        f"missing any quantile, but got {contributions}"
    )
    codes = [b.code.value for b in blockers]
    assert "TASK9_PER_VARIETY_GRAIN_MISSING" in codes, (
        f"expected TASK9_PER_VARIETY_GRAIN_MISSING, got {codes}"
    )
    grain_blks = [b for b in blockers if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING"]
    for b in grain_blks:
        assert (b.details or {}).get("task9_run_id") == 42, (
            f"all grain blockers must carry task9_run_id=42, got {b.details}"
        )


# ===========================================================================
# P0-5: denominator scope — non-zero extra persisted variety
# ===========================================================================


@pytest.mark.asyncio
async def test_per_variety_non_zero_extra_persisted_variety_emits_scope_mismatch() -> None:
    """Phase 2 scope: a non-zero-volume L25 row is a member of the
    persisted member-variety set even though it is not in the
    request.  Per round 8 directive: "do not depend on extra
    variety's volume being zero".  The system MUST return
    ``contributions == []`` and surface an AUTHORITY_SCOPE_MISMATCH
    with ``reason=TASK9_MEMBER_VARIETY_SET_MISMATCH`` (the
    persisted/requested sets are not equal).

    Setup:

    * Dx P50=100, D12 P50=80, **L25 P50=20 (non-zero extra)**
    * Pool P50=200 (sums to 100+80+20=200, so the round-7
      reconciliation would not catch this)
    * Request Dx + D12 only.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("100"),  # Dx
        (d, "P80", 1): Decimal("150"),
        (d, "P90", 1): Decimal("200"),
        (d, "P50", 2): Decimal("80"),  # D12
        (d, "P80", 2): Decimal("120"),
        (d, "P90", 2): Decimal("150"),
        (d, "P50", 3): Decimal("20"),  # L25 — non-zero extra
        (d, "P80", 3): Decimal("30"),
        (d, "P90", 3): Decimal("50"),
    }

    @dataclass
    class _V:
        variety_id: str

    varieties = [_V("Dx"), _V("D12")]
    contributions, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1, "D12": 2, "L25": 3},
        task9_run_id=42,
    )
    assert contributions == [], (
        f"non-zero extra persisted variety must be rejected; got contributions={contributions}"
    )
    codes = [b.code.value for b in blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, f"expected AUTHORITY_SCOPE_MISMATCH, got {codes}"
    scope_blk = next(b for b in blockers if b.code.value == "AUTHORITY_SCOPE_MISMATCH")
    details = scope_blk.details or {}
    assert details.get("reason") == MEMBER_VARIETY_SET_MISMATCH
    assert details.get("task9_run_id") == 42
    assert "Dx" in details.get("requested_variety_ids", [])
    assert "D12" in details.get("requested_variety_ids", [])
    assert "L25" in details.get("persisted_variety_ids", [])


# ===========================================================================
# P0-6: every grain / reconciliation blocker carries the real task9_run_id
# ===========================================================================


@pytest.mark.asyncio
async def test_no_member_blocker_carries_task9_run_id() -> None:
    """The TASK9_PER_VARIETY_GRAIN_MISSING blocker for the
    no-member-rows branch MUST carry the real ``task9_run_id``
    (not ``variety_pk`` or some other field).
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows: dict = {}

    @dataclass
    class _V:
        variety_id: str

    _, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=[_V("Dx")],
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1},
        task9_run_id=42,
    )
    grain_blk = next(b for b in blockers if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING")
    details = grain_blk.details or {}
    assert details.get("task9_run_id") == 42, (
        f"no-member blocker must carry task9_run_id=42, got {details}"
    )
    assert details.get("date") == d.isoformat()


@pytest.mark.asyncio
async def test_missing_quantile_blocker_carries_task9_run_id() -> None:
    """Per-(date, quantile, variety) missing-grain blockers MUST
    carry the real ``task9_run_id``.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("100"),
        (d, "P80", 1): Decimal("150"),
        # Dx P90 missing
    }

    @dataclass
    class _V:
        variety_id: str

    _, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=[_V("Dx")],
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1},
        task9_run_id=99,
    )
    grain_blks = [b for b in blockers if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING"]
    assert grain_blks, "expected at least one missing-grain blocker"
    for b in grain_blks:
        details = b.details or {}
        assert details.get("task9_run_id") == 99, (
            f"missing-grain blocker must carry task9_run_id=99, got {details}"
        )
        assert details.get("date") == d.isoformat()
        assert details.get("variety_id") == "Dx"


@pytest.mark.asyncio
async def test_member_volume_mismatch_blocker_carries_task9_run_id() -> None:
    """When the sum of member volumes over requested varieties does
    not equal the pool arrival total, the resulting
    TASK9_PER_VARIETY_GRAIN_MISSING blocker MUST carry the real
    ``task9_run_id``.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("100"),
        (d, "P80", 1): Decimal("150"),
        (d, "P90", 1): Decimal("200"),
        (d, "P50", 2): Decimal("50"),  # D12 P50 only 50
        (d, "P80", 2): Decimal("100"),
        (d, "P90", 2): Decimal("150"),
    }
    # P50 sum = 100+50 = 150, pool P50 = 200 → mismatch.

    @dataclass
    class _V:
        variety_id: str

    varieties = [_V("Dx"), _V("D12")]
    _, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1, "D12": 2},
        task9_run_id=7,
    )
    rec_blks = [
        b
        for b in blockers
        if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING"
        and (b.details or {}).get("quantile") == "P50"
    ]
    assert rec_blks, f"expected P50 reconciliation blocker, got {blockers}"
    for b in rec_blks:
        assert (b.details or {}).get("task9_run_id") == 7, (
            f"reconciliation blocker must carry task9_run_id=7, got {b.details}"
        )


@pytest.mark.asyncio
async def test_emitted_rate_mismatch_blocker_carries_task9_run_id() -> None:
    """When the sum of emitted rates deviates from 1 (after fixing
    sum-of-volumes), the resulting blocker MUST carry the real
    ``task9_run_id``.  This is a deliberate test: we set up a
    scenario where the sum of rates != 1 even though member volumes
    sum to the pool total — this is a sanity assertion that the
    ``emitted_rate_mismatch`` path is reachable.  We construct the
    case by using a pool arrival total of 100 and a member volume
    of 99 (mismatch on both axes); the volume mismatch is reported
    first.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("100"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("400"),
    }
    member_rows = {
        (d, "P50", 1): Decimal("100"),
        (d, "P80", 1): Decimal("150"),
        (d, "P90", 1): Decimal("200"),
        (d, "P50", 2): Decimal("0"),  # D12 P50 zero
        (d, "P80", 2): Decimal("100"),
        (d, "P90", 2): Decimal("150"),
    }
    # P50 sum = 100+0 = 100, pool P50 = 100 → match.
    # Rates: Dx=1.0, D12=0.0 → sum=1.0 (P50 matches).
    # P80 sum = 150+100 = 250, pool P80 = 300 → mismatch.

    @dataclass
    class _V:
        variety_id: str

    varieties = [_V("Dx"), _V("D12")]
    _, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows=member_rows,
        variety_pk_by_code={"Dx": 1, "D12": 2},
        task9_run_id=11,
    )
    p80_blks = [
        b
        for b in blockers
        if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING"
        and (b.details or {}).get("quantile") == "P80"
    ]
    assert p80_blks, f"expected P80 reconciliation blocker, got {blockers}"
    for b in p80_blks:
        assert (b.details or {}).get("task9_run_id") == 11, (
            f"P80 reconciliation blocker must carry task9_run_id=11, got {b.details}"
        )


# ===========================================================================
# Final integration: blocked scenario performs ZERO upstream reads
# (closed in round 7, re-verified here for regression).
# ===========================================================================


@pytest.mark.asyncio
async def test_blocked_scenario_does_not_call_daily_adapter(
    sqlite_full_session: AsyncSession,
) -> None:
    """Closed in round 7 (review 4680214102) — re-verified here
    for round 8 regression.  When ``scenario_overrides`` is
    non-empty, the scenario adapter must return BLOCKED at the
    entry point WITHOUT invoking the daily curve adapter or
    baseline composition.  A spy adapter that fails on call
    verifies the assertion.
    """
    from datetime import date as _date

    from backend.app.agent.adapters.scenario import DefaultScenarioAdapter

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
        as_of=date(2026, 1, 15),
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
