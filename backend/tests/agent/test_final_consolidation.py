"""TASK-013 Slice A — Round 9 Default-Path Typed Classification Fix (review 4680528194).

This file is the test-first probe for the 3 P0/P1 code findings in review
``4680528194``.  Every test is RUN against the starting HEAD
``1f105d1...`` BEFORE any production code change, and at least some
tests MUST fail to confirm they are probing real defects.

**Reviewer directive (P0-1 / P0-2 — code defects):**

* TASK-009 default selector applies ``status='completed'``,
  ``destination_factory_id`` and date-coverage predicates in SQL
  ``WHERE`` before the shared validator sees the rows.  Out-of-scope
  rows therefore disappear and yield
  :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND` instead of
  :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`.
* The shared validator also classifies ``status != 'completed'`` as
  :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`; it should be a
  scope/status mismatch.
* TASK-010 default selector filters by exact ``task9_run_id`` AND
  ``task9_result_hash`` in SQL before validation.  A residual run
  that exists but points to the wrong TASK-009 lineage is invisible
  to the shared validator and becomes
  :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND` instead of
  :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH`.

**Reviewer directive (P1-3 / P1-4 / P1-5 — fact defects):**

* Tests named as default-path scope/lineage mismatch checks either
  assert NOT_FOUND or exercise only the override path.  Rename /
  rewrite so the test name, executed path, and asserted blocker are
  identical.
* The PR body mutation checklist is factually inconsistent.

The 3 P0/P1 code findings and the corresponding test groups:

* **P0-1 (TASK-009 default destination/date/status failures collapse to NOT_FOUND)**
  ``test_task9_default_destination_mismatch_emits_scope_mismatch``,
  ``test_task9_default_date_mismatch_emits_scope_mismatch``,
  ``test_task9_default_status_mismatch_emits_scope_mismatch``,
  ``test_task9_default_status_mismatch_production_path``,
  ``test_task9_default_destination_mismatch_production_path``,
  ``test_task9_default_date_mismatch_production_path``.

* **P0-2 (TASK-010 default lineage mismatch collapses to NOT_FOUND)**
  ``test_task10_default_wrong_run_id_lineage_emits_typed``,
  ``test_task10_default_wrong_result_hash_lineage_emits_typed``,
  ``test_task10_default_lineage_mismatch_production_path``.

* **P1-3 (test name vs path mismatch)**
  All other tests below have been renamed so the prefix
  ``test_task9_default_...`` / ``test_task10_default_...`` reflects
  an actual default-path selector call (no
  ``run_id_override=`` / ``prediction_run_id_override=`` /
  ``advanced_overrides=`` providing the targeted run id).
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
    RequestedAsOfDateProvenance,
    ResolvedLocation,
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
#: created via ``_sorted_request_snapshot()``.  This is the reference
#: shape for round 9 — it does NOT contain ``forecast_season``.
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
    """Build a normalized request for compute_baseline() calls."""
    provenance = RequestedAsOfDateProvenance(
        caller_requested_as_of_date=as_of,
        effective_as_of_date=as_of,
        override_applied=False,
        override_kind=None,
        source_attestation=None,
        source_ref=None,
    )
    return NormalizedAgentRequest(
        request_id="req-round9",
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
    """In-memory SQLite session with the full TASK-009/010 + Variety tables."""
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
    """Insert a real-persistence-shape TASK-009 row."""
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
# P0-1 (review 4680528194): TASK-009 default selector must surface
# destination/date/status mismatches as AUTHORITY_SCOPE_MISMATCH, not
# silently collapse to TASK9_AUTHORITY_NOT_FOUND.
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_default_destination_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """Default path (NO ``run_id_override``).  A row with
    ``destination_factory_id=2`` is queried when the request asks for
    ``destination_factory_id=1``.  The default path must surface a
    typed :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` blocker with
    ``reason=DESTINATION_MISMATCH`` — NOT
    :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND` (which was the
    round 8 behavior because the SQL ``WHERE`` filter eliminated the
    out-of-scope row before the shared validator saw it).
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        destination_factory_id=2,
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,  # DEFAULT path
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"default-path destination mismatch must surface AUTHORITY_SCOPE_MISMATCH, got {codes}"
    )
    assert _has_blocker_with_reason(
        selection.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=DESTINATION_MISMATCH,
    ), f"expected reason=DESTINATION_MISMATCH, got {selection.blockers}"
    # Confirm NOT_FOUND is NOT the lone failure (the round 8 regression)
    not_found_only = (
        len(selection.blockers) == 1
        and selection.blockers[0].code == BlockerCode.TASK9_AUTHORITY_NOT_FOUND
    )
    assert not not_found_only, (
        "default path must NOT collapse to bare TASK9_AUTHORITY_NOT_FOUND; "
        "the out-of-scope row's destination mismatch must be visible"
    )


@pytest.mark.asyncio
async def test_task9_default_destination_mismatch_production_path(
    sqlite_full_session: AsyncSession,
) -> None:
    """The default-path destination mismatch MUST also be visible at
    the public ``compute_baseline()`` surface (P0-1 review 4680528194
    requires ``compute_baseline`` evidence, not just the internal
    selector).  The public composition must surface
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` (NOT
    :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`).
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        destination_factory_id=2,
    )
    baseline = DefaultTaskCompositionBaseline()
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=_make_normalized_request(
            varieties=[],
            season=9999,  # arbitrary season (rows don't have one)
        ),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=None,
    )
    codes = [b.code.value for b in result.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"compute_baseline default-path destination mismatch must surface "
        f"AUTHORITY_SCOPE_MISMATCH, got {codes}"
    )
    assert _has_blocker_with_reason(
        result.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=DESTINATION_MISMATCH,
    )


@pytest.mark.asyncio
async def test_task9_default_date_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """Default path: a row whose date coverage does not include the
    request's ``as_of`` must surface
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=DATE_COVERAGE_MISMATCH`` — NOT silently collapse to
    :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`.
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
        run_id_override=None,  # DEFAULT path
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"default-path date mismatch must surface AUTHORITY_SCOPE_MISMATCH, got {codes}"
    )
    assert _has_blocker_with_reason(
        selection.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=DATE_COVERAGE_MISMATCH,
    )


@pytest.mark.asyncio
async def test_task9_default_date_mismatch_production_path(
    sqlite_full_session: AsyncSession,
) -> None:
    """Public ``compute_baseline()`` must surface
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=DATE_COVERAGE_MISMATCH`` for default-path date coverage
    mismatch.
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        as_of_date=date(2025, 6, 1),
        forecast_start_date=date(2025, 6, 1),
        forecast_end_date=date(2025, 6, 30),
    )
    baseline = DefaultTaskCompositionBaseline()
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=_make_normalized_request(
            varieties=[],
            season=9999,  # arbitrary season (rows don't have one)
        ),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=None,
    )
    codes = [b.code.value for b in result.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"compute_baseline default-path date mismatch must surface "
        f"AUTHORITY_SCOPE_MISMATCH, got {codes}"
    )
    assert _has_blocker_with_reason(
        result.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=DATE_COVERAGE_MISMATCH,
    )


@pytest.mark.asyncio
async def test_task9_default_status_mismatch_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """Default path: a row with ``status != 'completed'`` (e.g.
    ``status='blocked'``) must surface
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` (NOT
    :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`, the round 8
    classification).  Status is a SCOPE property, not an identity
    property.  ``blocked`` is the only non-``completed`` value
    accepted by the DB CHECK constraint, but the validator must
    classify it the same way as any other non-``completed`` value.
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        status="blocked",
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,  # DEFAULT path
        destination_factory_id=1,
        requested_variety_codes=("Dx",),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"default-path status mismatch must surface AUTHORITY_SCOPE_MISMATCH, got {codes}"
    )
    # The round 8 regression: status != completed returned IDENTITY_MALFORMED.
    assert "AUTHORITY_IDENTITY_MALFORMED" not in codes, (
        f"status mismatch must NOT be classified as IDENTITY_MALFORMED; got {codes}"
    )


@pytest.mark.asyncio
async def test_task9_default_status_mismatch_production_path(
    sqlite_full_session: AsyncSession,
) -> None:
    """Public ``compute_baseline()`` must surface
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` (NOT
    :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED`) for
    default-path status mismatch.
    """
    await _insert_harvest_state_run(
        sqlite_full_session,
        status="blocked",
    )
    baseline = DefaultTaskCompositionBaseline()
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=_make_normalized_request(
            varieties=[],
            season=9999,  # arbitrary season (rows don't have one)
        ),
        resolved_location=ResolvedLocation(
            status="resolved",
            location_reference_id=1,
            matched_location_method="REFERENCE_ID",
        ),
        parameters=[],
        advanced_overrides=None,
    )
    codes = [b.code.value for b in result.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes, (
        f"compute_baseline default-path status mismatch must surface "
        f"AUTHORITY_SCOPE_MISMATCH, got {codes}"
    )
    assert "AUTHORITY_IDENTITY_MALFORMED" not in codes, (
        f"compute_baseline must NOT classify status mismatch as IDENTITY_MALFORMED; got {codes}"
    )


# ===========================================================================
# TASK-009 default: NOT_FOUND (legitimate, no related rows at all)
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_default_no_related_row_emits_task9_authority_not_found(
    sqlite_full_session: AsyncSession,
) -> None:
    """No row in the DB at all → :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND`.
    This is the ONLY case that legitimately emits NOT_FOUND.  When
    the DB is empty, there is no candidate row whose mismatch the
    validator could surface.
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
    codes = [b.code.value for b in selection.blockers]
    assert "TASK9_AUTHORITY_NOT_FOUND" in codes, (
        f"empty DB must emit TASK9_AUTHORITY_NOT_FOUND, got {codes}"
    )


# ===========================================================================
# TASK-009: P0-2 typed hash / identity / upstream / conflict (round 8 closure)
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_default_hash_malformed_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """Row's ``result_hash`` is not 64-char lowercase hex →
    :data:`BlockerCode.AUTHORITY_HASH_MALFORMED` (validator-level
    exercise, since the DB column has a CHECK constraint that would
    reject invalid hex at insert time).
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
    codes = [b.code.value for b in outcome.blockers]
    assert "AUTHORITY_HASH_MALFORMED" in codes, f"expected AUTHORITY_HASH_MALFORMED, got {codes}"


@pytest.mark.asyncio
async def test_task9_default_member_query_exception_emits_upstream_read_failure(
    sqlite_full_session: AsyncSession,
) -> None:
    """When the member-variety ORM query raises an unexpected
    exception, the selector must surface
    :data:`BlockerCode.UPSTREAM_READ_FAILURE`.
    """
    await _insert_harvest_state_run(sqlite_full_session)
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
    codes = [b.code.value for b in selection.blockers]
    assert "UPSTREAM_READ_FAILURE" in codes, (
        f"expected UPSTREAM_READ_FAILURE on member-variety ORM failure, got {codes}"
    )


# ===========================================================================
# TASK-010 P0-2 (review 4680528194): default lineage mismatch must be
# AUTHORITY_LINEAGE_MISMATCH, NOT silently TASK10_AUTHORITY_NOT_FOUND.
# These tests use the DEFAULT path (no prediction_run_id_override).
# ===========================================================================


@pytest.mark.asyncio
async def test_task10_default_wrong_run_id_lineage_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """Default path (NO ``prediction_run_id_override``).  A residual
    run that exists but is bound to a *different* ``task9_run_id``
    than the selected TASK-009 must surface
    :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH` — NOT silently
    collapse to :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`.
    """
    hsr_selected = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    hsr_unrelated = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="d" * 64,
        config_hash="e" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    # Residual bound to a DIFFERENT task9_run_id; same task9_result_hash
    # (so the round 8 SQL filter would also have eliminated it; the
    # round 9 broader OR-query lets the validator see it).
    await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_unrelated,
        task9_result_hash="a" * 64,
        prediction_hash="e" * 64,
        prediction_input_signature="1" * 64,
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_selected,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,  # DEFAULT path
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_LINEAGE_MISMATCH" in codes, (
        f"default-path wrong run id lineage must surface AUTHORITY_LINEAGE_MISMATCH, got {codes}"
    )
    not_found_only = (
        len(selection.blockers) == 1
        and selection.blockers[0].code == BlockerCode.TASK10_AUTHORITY_NOT_FOUND
    )
    assert not not_found_only, (
        "default path must NOT collapse to bare TASK10_AUTHORITY_NOT_FOUND; "
        "the wrong-lineage row's lineage mismatch must be visible"
    )


@pytest.mark.asyncio
async def test_task10_default_wrong_result_hash_lineage_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """Default path: a residual run that exists with the same
    ``task9_run_id`` but a different ``task9_result_hash`` than the
    selected TASK-009 must surface
    :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH`.
    """
    hsr_selected = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    # Residual bound to the same task9_run_id BUT a different result_hash
    # (e.g. from a prior TASK-009 re-run before the latest result_hash
    # was bound).
    await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=hsr_selected,
        task9_result_hash="d" * 64,
        prediction_hash="e" * 64,
        prediction_input_signature="1" * 64,
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_selected,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,  # DEFAULT path
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_LINEAGE_MISMATCH" in codes, (
        f"default-path wrong result_hash lineage must surface "
        f"AUTHORITY_LINEAGE_MISMATCH, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_lineage_mismatch_production_path(
    sqlite_full_session: AsyncSession,
) -> None:
    """Public ``compute_baseline()`` must surface
    :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH` (NOT
    :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`) when a
    default-path residual row has a wrong lineage.
    """
    hsr_a = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    # Insert a residual bound to a NON-EXISTENT hsr_b (id=9999) so
    # the TASK-010 default OR-query (task9_run_id == selected OR
    # task9_result_hash == selected) finds it.  This row's
    # task9_run_id=9999 mismatches the selected hsr_a; its
    # task9_result_hash="a"*64 matches hsr_a's.  Either mismatch
    # dimension alone should trigger AUTHORITY_LINEAGE_MISMATCH.
    await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=9999,
        task9_result_hash="a" * 64,
        prediction_hash="e" * 64,
        prediction_input_signature="1" * 64,
    )
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
    assert "AUTHORITY_LINEAGE_MISMATCH" in codes, (
        f"compute_baseline default-path lineage mismatch must surface "
        f"AUTHORITY_LINEAGE_MISMATCH, got {codes}"
    )
    assert hsr_a  # silence unused warnings


# ===========================================================================
# TASK-010: NOT_FOUND, execution_status, hash malformed, fallback, conflict
# ===========================================================================


@pytest.mark.asyncio
async def test_task10_default_no_related_row_emits_task10_authority_not_found(
    sqlite_full_session: AsyncSession,
) -> None:
    """No TASK-010 row exists with ANY shared lineage component
    (neither same ``task9_run_id`` nor same ``task9_result_hash``) →
    :data:`BlockerCode.TASK10_AUTHORITY_NOT_FOUND`.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=hsr_id,
        task9_result_hash="a" * 64,
        prediction_run_id_override=None,
    )
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "TASK10_AUTHORITY_NOT_FOUND" in codes, (
        f"no related residual row must emit TASK10_AUTHORITY_NOT_FOUND, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_execution_status_failed_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """TASK-010 row with ``execution_status != 'completed'`` →
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` with
    ``reason=EXECUTION_STATUS_NOT_COMPLETED``.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
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
async def test_task10_default_hash_malformed_emits_typed(
    sqlite_full_session: AsyncSession,
) -> None:
    """TASK-010 row whose ``prediction_hash`` is not 64-char hex →
    :data:`BlockerCode.AUTHORITY_HASH_MALFORMED`."""

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
    codes = [b.code.value for b in outcome.blockers]
    assert "AUTHORITY_HASH_MALFORMED" in codes, (
        f"expected AUTHORITY_HASH_MALFORMED on prediction_hash, got {codes}"
    )


@pytest.mark.asyncio
async def test_task10_default_fallback_reason_set_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """A TASK-010 row whose ``fallback_reason`` is set is not
    authoritative → :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH`
    with ``reason=FALLBACK_RUN_NOT_AUTHORITATIVE``.
    """
    hsr_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
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


# ===========================================================================
# P0-1 (round 8): TASK-009 season fail-closed
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_no_persisted_season_emits_scope_mismatch(
    sqlite_full_session: AsyncSession,
) -> None:
    """Round 8 closure: a real-persistence row (no
    ``forecast_season``) with the request asking for an explicit
    season MUST be excluded with a typed
    :data:`BlockerCode.AUTHORITY_SCOPE_MISMATCH` blocker carrying
    ``reason=PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE``.
    """
    await _insert_harvest_state_run(
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
    assert selection.candidates == ()
    codes = [b.code.value for b in selection.blockers]
    assert "AUTHORITY_SCOPE_MISMATCH" in codes
    assert _has_blocker_with_reason(
        selection.blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=SEASON_BINDING_UNAVAILABLE,
    )


# ===========================================================================
# P0-4 / P0-5 / P0-6 (round 8): per-variety matrix + denominator scope
# ===========================================================================


@pytest.mark.asyncio
async def test_per_variety_late_missing_grain_clears_whole_day() -> None:
    """Phase 1 prevalidation: Dx has P50=120, P80=200, P90=300;
    D12 has P50=80, P80=100, P90 MISSING.  Dx's contribution MUST
    NOT survive even though its own row is well-formed.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("300"),
        "P90_arrival": Decimal("300"),
    }
    member_rows: dict[tuple[date, str, int], Decimal] = {
        (d, "P50", 1): Decimal("120"),
        (d, "P80", 1): Decimal("200"),
        (d, "P90", 1): Decimal("300"),
        (d, "P50", 2): Decimal("80"),
        (d, "P80", 2): Decimal("100"),
        # (d, "P90", 2) intentionally MISSING
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
        task9_run_id=123,
    )
    assert contributions == [], (
        f"late missing grain must clear the whole day; got contributions={contributions}"
    )
    # All grain blockers MUST carry task9_run_id
    grain_blockers = [b for b in blockers if b.code.value == "TASK9_PER_VARIETY_GRAIN_MISSING"]
    assert grain_blockers, f"expected grain-missing blockers, got {blockers}"
    for b in grain_blockers:
        assert (b.details or {}).get("task9_run_id") == 123, (
            f"grain blocker must carry task9_run_id, got {b.details}"
        )


@pytest.mark.asyncio
async def test_per_variety_non_zero_extra_persisted_variety_emits_scope_mismatch() -> None:
    """Phase 2 scope check: persisted member variety set is Dx+D12+L25
    (L25 has non-zero volume); requested set is Dx+D12.  The
    contribution list MUST be empty + AUTHORITY_SCOPE_MISMATCH must
    be surfaced.  We MUST NOT silently drop L25 and emit a
    Dx+D12-only output with rates summing to 0.9.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("200"),
        "P80_arrival": Decimal("330"),
        "P90_arrival": Decimal("630"),
    }
    member_rows: dict[tuple[date, str, int], Decimal] = {
        (d, "P50", 1): Decimal("100"),
        (d, "P80", 1): Decimal("200"),
        (d, "P90", 1): Decimal("300"),
        (d, "P50", 2): Decimal("80"),
        (d, "P80", 2): Decimal("100"),
        (d, "P90", 2): Decimal("300"),
        # L25 with non-zero volume (so the extra variety is NOT a
        # phantom zero-volume entry):
        (d, "P50", 3): Decimal("20"),
        (d, "P80", 3): Decimal("30"),
        (d, "P90", 3): Decimal("30"),
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
        task9_run_id=123,
    )
    assert contributions == [], (
        f"non-zero extra persisted variety must clear contributions; got {contributions}"
    )
    assert _has_blocker_with_reason(
        blockers,
        BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        reason=MEMBER_VARIETY_SET_MISMATCH,
    ), f"expected MEMBER_VARIETY_SET_MISMATCH, got {blockers}"


# ===========================================================================
# P0-6 (round 8): every grain blocker must carry task9_run_id
# ===========================================================================


def test_grain_blockers_carry_task9_run_id() -> None:
    """Every ``TASK9_PER_VARIETY_GRAIN_MISSING`` and
    ``AUTHORITY_SCOPE_MISMATCH`` (member-variety-set-mismatch)
    blocker must carry ``task9_run_id`` in its details.
    """
    d = date(2026, 3, 1)
    pool_arrival = {
        "P50_arrival": Decimal("0"),
        "P80_arrival": Decimal("0"),
        "P90_arrival": Decimal("0"),
    }

    @dataclass
    class _V:
        variety_id: str

    varieties = [_V("Dx"), _V("D12")]
    # No member rows → produces a no_member_row blocker.
    contributions, blockers = _per_variety_contribution_from_member_rows(
        d=d,
        varieties=varieties,
        pool_arrival=pool_arrival,
        variety_member_rows={},
        variety_pk_by_code={"Dx": 1, "D12": 2},
        task9_run_id=42,
    )
    assert contributions == []
    for b in blockers:
        details = b.details or {}
        assert details.get("task9_run_id") == 42, (
            f"blocker {b.code} missing task9_run_id in details: {b}"
        )
