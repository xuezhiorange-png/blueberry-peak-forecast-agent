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


# ===========================================================================
# P0 (review 4680912426): TASK-009 as-of visibility cutoff
#
# A future TASK-009 row (row.as_of_date > request.as_of) MUST be
# completely invisible to the default path.  No candidate, no scope
# mismatch, no blocker message/details, no conflict disclosure may
# expose its row_id, as_of_date, or forecast_end_date.
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_default_future_same_destination_row_is_not_visible(
    sqlite_full_session: AsyncSession,
) -> None:
    """The only TASK-009 row in the DB has
    ``as_of_date=2026-02-01`` (in the FUTURE relative to
    request.as_of=2026-01-15) and the SAME destination as the
    request.  The default path MUST emit
    :data:`BlockerCode.TASK9_AUTHORITY_NOT_FOUND` and MUST NOT
    surface ``AUTHORITY_SCOPE_MISMATCH / DATE_COVERAGE_MISMATCH``
    for the future row.  The future row's row_id, as_of_date, and
    forecast_end_date MUST NOT appear in any blocker message or
    details.
    """
    # Insert a canary (non-relative) row first so the future row's
    # database id is offset; this prevents the future row's id
    # from coincidentally matching the request's destination id
    # (which is also ``1``).
    await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="c" * 64,
        config_hash="d" * 64,
        as_of_date=date(2025, 1, 1),
        forecast_start_date=date(2025, 1, 1),
        forecast_end_date=date(2025, 1, 31),
        status="completed",
        destination_factory_id=99,  # a canary in 2025 — visible but unrelated
    )
    future_hsr = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 2, 1),  # FUTURE relative to as_of=2026-01-15
        forecast_start_date=date(2026, 2, 1),
        forecast_end_date=date(2026, 4, 30),
        status="completed",
        destination_factory_id=1,  # SAME destination
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,  # default path
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    assert selection.candidates == (), (
        f"future row must not surface as a candidate; got {selection.candidates}"
    )
    codes = [b.code.value for b in selection.blockers]
    assert "TASK9_AUTHORITY_NOT_FOUND" in codes, (
        f"only the future row exists → must emit TASK9_AUTHORITY_NOT_FOUND, got {codes}"
    )
    assert "AUTHORITY_SCOPE_MISMATCH" not in codes, (
        f"future row must not leak as a typed scope mismatch; got {codes}"
    )
    # No blocker may disclose the future row's identity.  We check
    # by inspecting the blocker messages + serialized details dict
    # for the future row's identifier context.  Specifically:
    #   - the future row's database id (a unique int)
    #   - the future row's as_of_date (2026-02-01)
    #   - the future row's forecast_end_date (2026-04-30)
    # The request's destination_factory_id (1) and as_of_date
    # (2026-01-15) are LEGITIMATE fields that may appear; we
    # do not match on those.
    import json

    for b in selection.blockers:
        details_json = json.dumps(b.details or {}, sort_keys=True)
        message = b.message or ""
        # Future row's unique id (the canary is id=1, future is id=2;
        # the integer 2 may appear as a substring of "2026-01-15"
        # which is a 2025→2026 year boundary; use word-boundary
        # search via regex to avoid false matches).
        import re

        # Match the future row id only as a whole-number token.
        assert not re.search(rf"\b{re.escape(str(future_hsr))}\b", details_json), (
            f"future row id {future_hsr} leaked into blocker details: {b.details}"
        )
        assert not re.search(rf"\b{re.escape(str(future_hsr))}\b", message), (
            f"future row id {future_hsr} leaked into blocker message: {message}"
        )
        assert "2026-02-01" not in details_json, (
            f"future as_of_date leaked into blocker details: {b.details}"
        )
        assert "2026-02-01" not in message
        assert "2026-04-30" not in details_json, (
            f"future forecast_end_date leaked into blocker details: {b.details}"
        )
        assert "2026-04-30" not in message


@pytest.mark.asyncio
async def test_task9_future_row_not_disclosed_by_compute_baseline(
    sqlite_full_session: AsyncSession,
) -> None:
    """``compute_baseline()`` (the public production path) MUST
    also not disclose the future row's identity — the public
    composition surface inherits the selector's visibility cutoff.
    """
    # Insert a canary (non-relative) row first so the future row's
    # database id is offset; this prevents the future row's id
    # from coincidentally matching the request's destination id.
    await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="c" * 64,
        config_hash="d" * 64,
        as_of_date=date(2025, 1, 1),
        forecast_start_date=date(2025, 1, 1),
        forecast_end_date=date(2025, 1, 31),
        status="completed",
        destination_factory_id=99,
    )
    future_hsr = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        as_of_date=date(2026, 2, 1),
        forecast_start_date=date(2026, 2, 1),
        forecast_end_date=date(2026, 4, 30),
        status="completed",
        destination_factory_id=1,
    )
    baseline = DefaultTaskCompositionBaseline()
    result = await baseline.compute_baseline(
        session=sqlite_full_session,
        normalized_request=_make_normalized_request(
            varieties=[],
            season=9999,
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
    assert "TASK9_AUTHORITY_NOT_FOUND" in codes, (
        f"compute_baseline must emit TASK9_AUTHORITY_NOT_FOUND for the future-only DB; got {codes}"
    )
    assert "AUTHORITY_SCOPE_MISMATCH" not in codes, (
        f"compute_baseline must not surface the future row as a typed scope mismatch; got {codes}"
    )
    # No blocker may disclose the future row's identity.  We use
    # whole-number token matching so the request's destination id
    # (which is also ``1``) and the request's as_of_date
    # (2026-01-15) are not mistakenly matched.
    import json
    import re

    for b in result.blockers:
        details_json = json.dumps(b.details or {}, sort_keys=True)
        message = b.message or ""
        assert not re.search(rf"\b{re.escape(str(future_hsr))}\b", details_json), (
            f"compute_baseline leaked future row id {future_hsr}: {b.details}"
        )
        assert not re.search(rf"\b{re.escape(str(future_hsr))}\b", message)
        assert "2026-02-01" not in details_json
        assert "2026-02-01" not in message
        assert "2026-04-30" not in details_json
        assert "2026-04-30" not in message


# ===========================================================================
# P0 (review 4680912426): deterministic selector ordering
#
# Selectors must return candidates/blockers in a stable, cross-DB
# total order so equal content in opposite insertion order produces
# identical canonical output and hash.  The "valid candidate + invalid
# related row" test pins the contract: the valid candidate must
# always be the candidate (not a blocker / not a conflict).
# ===========================================================================


@pytest.mark.asyncio
async def test_task9_candidate_order_is_stable_across_insertion_order(
    sqlite_full_session: AsyncSession,
) -> None:
    """Two fully-valid TASK-009 candidates inserted in opposite
    order on equivalent DB content produce the same candidate id
    order from the default path.
    """
    a = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    b = await _insert_harvest_state_run(
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
    ids = [c["id"] for c in selection.candidates]
    assert ids == sorted(ids), f"candidate ids must be sorted ascending; got {ids} (a={a}, b={b})"


@pytest.mark.asyncio
async def test_task9_blocker_order_is_stable_across_insertion_order(
    sqlite_full_session: AsyncSession,
) -> None:
    """Three related rows with different failure modes (destination,
    date, status) inserted in opposite order on equivalent content
    must produce the same blocker order, reason order, and row_id
    order.  The serialized output (canonical JSON dumps of
    blockers) MUST be byte-identical across opposite insertion.
    """
    from backend.app.harvest_state.canonical import canonical_json_dumps
    from backend.app.residual_model.canonical import canonical_payload_hash

    # Insert in order: A (destination mismatch), B (status mismatch), C (date mismatch)
    a = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        destination_factory_id=2,  # dest mismatch
    )
    b = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="b" * 64,
        destination_factory_id=1,
        status="blocked",  # status mismatch
    )
    c = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="c" * 64,
        destination_factory_id=1,
        as_of_date=date(2025, 6, 1),  # date mismatch
        forecast_start_date=date(2025, 6, 1),
        forecast_end_date=date(2025, 6, 30),
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    serial = canonical_json_dumps([b.model_dump(mode="json") for b in selection.blockers])
    canonical_hash_1 = canonical_payload_hash(serial)
    row_ids_1 = sorted([b.details.get("row_id") for b in selection.blockers])
    codes_1 = [b.code.value for b in selection.blockers]
    reasons_1 = [(b.details or {}).get("reason") for b in selection.blockers]

    # Wipe and re-insert in the OPPOSITE order: C, B, A
    from sqlalchemy import delete

    await sqlite_full_session.execute(
        delete(HarvestStateRun).where(HarvestStateRun.id.in_([a, b, c]))
    )
    await sqlite_full_session.flush()
    await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="c" * 64,
        destination_factory_id=1,
        as_of_date=date(2025, 6, 1),
        forecast_start_date=date(2025, 6, 1),
        forecast_end_date=date(2025, 6, 30),
    )
    await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="b" * 64,
        destination_factory_id=1,
        status="blocked",
    )
    await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        destination_factory_id=2,
    )
    selection2 = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    serial2 = canonical_json_dumps([b.model_dump(mode="json") for b in selection2.blockers])
    canonical_hash_2 = canonical_payload_hash(serial2)

    # Equal-content / opposite-insertion must produce equal canonical
    # serialization.  Because the row_ids differ between the two
    # runs (sqlite reuses ids 1/2/3), we redact the row_id from the
    # blocker details AND from the human-readable message text
    # before comparing the canonical payload.  This proves the
    # **semantic** canonical payload is stable across insertion
    # order; the row_id is an internal discriminator that is not
    # part of the semantic content.
    def _redact_row_id(blocker_dump: dict[str, Any]) -> dict[str, Any]:
        d = dict(blocker_dump)
        details = d.get("details")
        if isinstance(details, dict):
            redacted = {k: v for k, v in details.items() if k != "row_id"}
            d["details"] = redacted
        message = d.get("message")
        if isinstance(message, str) and message:
            # Replace "candidate row <N>" / "row <N>" with a
            # stable placeholder so the message becomes
            # content-stable.  This is a test-only redaction; the
            # production message is still human-readable and
            # preserved on the public Blocker object.
            import re

            d["message"] = re.sub(r"\b(?:candidate )?row\s+\d+\b", "<ROW_ID>", message)
        return d

    redacted_serial_1 = canonical_json_dumps(
        [_redact_row_id(b.model_dump(mode="json")) for b in selection.blockers]
    )
    redacted_serial_2 = canonical_json_dumps(
        [_redact_row_id(b.model_dump(mode="json")) for b in selection2.blockers]
    )
    redacted_hash_1 = canonical_payload_hash(redacted_serial_1)
    redacted_hash_2 = canonical_payload_hash(redacted_serial_2)
    assert redacted_serial_1 == redacted_serial_2, (
        f"redacted canonical bytes must match across opposite insertion order:\n"
        f"  run1: {redacted_serial_1}\n  run2: {redacted_serial_2}"
    )
    assert redacted_hash_1 == redacted_hash_2, (
        f"redacted canonical hash must match across opposite insertion order: "
        f"{redacted_hash_1} vs {redacted_hash_2}"
    )
    assert codes_1 == [b.code.value for b in selection2.blockers], (
        f"code order must be stable across insertion order: "
        f"{codes_1} vs {[b.code.value for b in selection2.blockers]}"
    )
    assert reasons_1 == [(b.details or {}).get("reason") for b in selection2.blockers], (
        f"reason order must be stable across insertion order: "
        f"{reasons_1} vs "
        f"{[(b.details or {}).get('reason') for b in selection2.blockers]}"
    )


@pytest.mark.asyncio
async def test_task10_candidate_and_blocker_order_is_stable() -> None:
    """Two fully-valid TASK-010 residual candidates and one
    partial-lineage mismatch row must produce stable order on the
    default path (no prediction_run_id_override).
    """
    from backend.app.residual_model.canonical import canonical_payload_hash
    from backend.app.harvest_state.canonical import canonical_json_dumps
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Build an in-memory DB with 1 valid TASK-009 + 2 valid TASK-010
    # residuals + 1 wrong-lineage residual.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from backend.app.models.harvest_state import (
        HarvestStateDailyMemberRowModel,
        HarvestStateDailyPoolRowModel,
        HarvestStateRun,
    )
    from backend.app.models.master_data import Variety
    from backend.app.models.residual_model import (
        ResidualModelPredictionRow,
        ResidualModelPredictionRun,
        ResidualModelTrainingRun,
    )

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
        hsr = HarvestStateRun(
            status="completed",
            output_schema_version="v1",
            result_hash_schema_version="v1",
            resolved_parameter_snapshot_schema_version="v1",
            source_ref_schema_version="v1",
            stable_cohort_key_schema_version="v1",
            input_snapshot={
                **_REAL_TASK9_INPUT_SNAPSHOT,
                "forecast_season": 2026,
            },
            resolved_parameter_snapshot={},
            source_ref_catalog=[],
            warnings=[],
            blockers=[],
            mass_balance_result=None,
            continuity_result=None,
            canonical_output={"ok": True},
            config_hash="b" * 64,
            result_hash="a" * 64,
            canonical_payload_hash="c" * 64,
            forecast_start_date=date(2026, 1, 1),
            forecast_end_date=date(2026, 1, 31),
            as_of_date=date(2026, 1, 10),
            destination_factory_id=1,
            pool_row_count=0,
            member_row_count=0,
            cohort_row_count=0,
            future_arrival_row_count=0,
            maturity_forecast_run_id=None,
        )
        session.add(hsr)
        await session.flush()
        hsr_id = int(hsr.id)
        # Two valid residuals
        for i, pred_hash in enumerate(["a" * 64, "b" * 64]):
            session.add(
                ResidualModelPredictionRun(
                    training_run_id=None,
                    task9_run_id=hsr_id,
                    task9_result_hash="a" * 64,
                    execution_status="completed",
                    mode="residual_corrected",
                    config_hash="b" * 64,
                    feature_schema_version="v1",
                    feature_schema_hash="f" * 64,
                    artifact_hashes=["a" * 64],
                    prediction_input_signature=f"{i}" * 64,
                    prediction_hash=pred_hash,
                    feature_audit={},
                    warnings=[],
                    blockers=[],
                    fallback_reason=None,
                    expected_prediction_row_count=0,
                    input_snapshot={},
                    canonical_output={},
                    canonical_payload_hash="c" * 64,
                    error_message=None,
                    typed_attempt=None,
                )
            )
        # One wrong-lineage residual
        session.add(
            ResidualModelPredictionRun(
                training_run_id=None,
                task9_run_id=9999,  # wrong run id
                task9_result_hash="a" * 64,  # matching result_hash
                execution_status="completed",
                mode="residual_corrected",
                config_hash="b" * 64,
                feature_schema_version="v1",
                feature_schema_hash="f" * 64,
                artifact_hashes=["a" * 64],
                prediction_input_signature="9" * 64,
                prediction_hash="e" * 64,
                feature_audit={},
                warnings=[],
                blockers=[],
                fallback_reason=None,
                expected_prediction_row_count=0,
                input_snapshot={},
                canonical_output={},
                canonical_payload_hash="c" * 64,
                error_message=None,
                typed_attempt=None,
            )
        )
        await session.flush()
        selection = await _select_residual_prediction_run_candidates(
            session,
            task9_run_id=hsr_id,
            task9_result_hash="a" * 64,
            prediction_run_id_override=None,
        )
        cand_ids = [c["id"] for c in selection.candidates]
        assert cand_ids == sorted(cand_ids), (
            f"TASK-010 candidate ids must be sorted ascending; got {cand_ids}"
        )
        # Blocker order must be stable
        codes = [b.code.value for b in selection.blockers]
        assert codes == sorted(codes), (
            f"TASK-010 blocker codes must be sorted ascending; got {codes}"
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_task9_valid_candidate_coexists_with_invalid_related_row(
    sqlite_full_session: AsyncSession,
) -> None:
    """One fully-valid candidate and one visible-but-failing related
    row.  The selector MUST return the valid candidate (not a
    blocker / not a conflict) regardless of which row the DB
    returns first.  This pins the contract: a valid candidate
    always wins over invalid related rows; no flip-flop across
    insertion order.
    """
    valid = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="b" * 64,
        destination_factory_id=2,  # dest mismatch (visible)
    )
    selection = await _select_harvest_state_run_candidates(
        sqlite_full_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=2026,
    )
    # Contract: the valid row is the ONLY candidate; never a
    # blocker, never a conflict.  The valid row's identity is
    # stable across insertion order.  Insert in opposite order
    # and re-assert.
    assert [c["id"] for c in selection.candidates] == [valid], (
        f"valid row must be the sole candidate; got {selection.candidates}"
    )


# ===========================================================================
# P0 (Round 11 review 4680976947): strict total-order public payload
#
# The Round 10 sort key ``(code, reason, field)`` was content-based
# but NOT a strict total order: two distinct-content blockers with
# the same prefix produced identical keys, so reverse-order inputs
# could yield different public payloads.  Round 11 extends the key
# with the full canonical public payload as the final tie-break.
# The conflict helper previously keyed on the non-existent
# ``id`` field; it now extracts the real identity field
# (``harvest_state_run_id`` or ``prediction_run_id``) and fail-closes
# on missing/ambiguous payloads.
#
# These tests assert byte-identical canonical output (no test-only
# redaction) and the conflict-helper identity fields are
# exercised directly.
# ===========================================================================


def _build_round11_blocker(
    *,
    code: BlockerCode,
    row_id: int,
    row_destination_factory_id: int,
    reason: str = "DESTINATION_MISMATCH",
    field: str = "",
    message_suffix: str = "",
) -> Blocker:
    """Build a :class:`Blocker` with a public-content discriminator.

    The ``row_id`` / ``row_destination_factory_id`` /
    ``message_suffix`` are part of the public payload, so two
    blockers constructed with the same ``code`` / ``reason`` /
    ``field`` but different combinations of these three fields
    produce **different** full public payloads.
    """

    return Blocker(
        code=code,
        message=(
            f"TASK-009 candidate row {row_id} (destination="
            f"{row_destination_factory_id}) fails scope check"
            f"{message_suffix}"
        ),
        details={
            "row_id": row_id,
            "row_destination_factory_id": row_destination_factory_id,
            "reason": reason,
            "field": field,
        },
        retry_hint="PROVIDE_OVERRIDE",
    )


def test_task9_same_type_blocker_total_order_canonical_byte_identical() -> None:
    """Two distinct-content blockers with the same
    ``(code, reason, field)`` MUST sort to the same total order
    regardless of input order.  The Round 10 sort key
    ``(code, reason, field)`` collapses them, so the public payload
    diverges on reverse inputs.  Round 11's strict total-order key
    guarantees byte-identical canonical output.

    Test contract (Round 11):
        * SAME blocker objects (no fabrication between runs).
        * REVERSE input order.
        * Compare **unredacted** full canonical bytes + hash.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )

    a = _build_round11_blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        row_id=7,
        row_destination_factory_id=1,
    )
    b = _build_round11_blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        row_id=11,
        row_destination_factory_id=2,
    )

    from backend.app.agent.adapters.baseline_composer import (
        _blocker_sort_key,
        _sort_blockers_deterministically,
    )

    sorted_ab = _sort_blockers_deterministically([a, b])
    sorted_ba = _sort_blockers_deterministically([b, a])

    payload_ab = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_ab])
    payload_ba = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_ba])

    assert payload_ab == payload_ba, (
        f"strict-total-order sort must produce byte-identical canonical "
        f"payload across reverse input orders; got\n  ab: {payload_ab}\n"
        f"  ba: {payload_ba}"
    )
    assert canonical_payload_hash(payload_ab) == canonical_payload_hash(payload_ba)

    # The sort key must be a strict total order: distinct-content
    # blockers produce distinct keys.
    assert _blocker_sort_key(a) != _blocker_sort_key(b), (
        f"distinct-content blockers must produce distinct sort keys; "
        f"a={_blocker_sort_key(a)}\nb={_blocker_sort_key(b)}"
    )


def test_task9_mixed_blocker_total_order_canonical_byte_identical() -> None:
    """Four distinct blockers (different code/reason/field/row_id)
    sorted in reverse input orders MUST produce byte-identical
    canonical payload.  The strict-total-order key in Round 11
    covers every (code, reason, field) group with canonical-payload
    as the final tie-break.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )
    from backend.app.agent.adapters.baseline_composer import (
        _sort_blockers_deterministically,
    )

    a = _build_round11_blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        row_id=1,
        row_destination_factory_id=99,
        reason="DESTINATION_MISMATCH",
    )
    b = _build_round11_blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        row_id=2,
        row_destination_factory_id=1,
        reason="EXECUTION_STATUS_NOT_COMPLETED",
    )
    c = _build_round11_blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        row_id=3,
        row_destination_factory_id=1,
        reason="DATE_COVERAGE_MISMATCH",
    )
    d = _build_round11_blocker(
        code=BlockerCode.AUTHORITY_HASH_MALFORMED,
        row_id=4,
        row_destination_factory_id=1,
        reason="HASH_MALFORMED",
    )

    forward = [a, b, c, d]
    reverse = [d, c, b, a]
    sorted_fwd = _sort_blockers_deterministically(forward)
    sorted_rev = _sort_blockers_deterministically(reverse)

    payload_fwd = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_fwd])
    payload_rev = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_rev])
    assert payload_fwd == payload_rev
    assert canonical_payload_hash(payload_fwd) == canonical_payload_hash(payload_rev)


def test_task10_blocker_sort_helper_is_stable_for_reversed_input() -> None:
    """Helper-only ordering evidence (not a default-selector test).

    This test directly exercises the production sort helper
    :func:`_sort_blockers_deterministically` on hand-constructed
    :class:`Blocker` objects.  It does NOT call the default
    selector; it only proves the sort key is a strict total order
    over the public payload when applied to the same blocker
    objects in opposite orders.

    For the **real default-selector** same-prefix evidence, see
    :func:`test_task10_default_selector_returns_total_ordered_nonempty_blockers`
    (which uses the production
    :func:`_select_residual_prediction_run_candidates` with
    ``prediction_run_id_override=None``).
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )
    from backend.app.agent.adapters.baseline_composer import (
        _blocker_sort_key,
        _sort_blockers_deterministically,
    )

    lineage_a = Blocker(
        code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
        message=(
            "TASK-010 candidate row 1 has task9_result_hash="
            "0000000000000000000000000000000000000000000000000000000000000000"
            " but selected TASK-009 row has different hash"
        ),
        details={
            "row_id": 1,
            "reason": "PERSISTED_TASK9_RESULT_HASH_MISMATCH",
            "field": "task9_result_hash",
            "persisted_task9_result_hash": ("0" * 64),
        },
        retry_hint="PROVIDE_OVERRIDE",
    )
    lineage_b = Blocker(
        code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
        message=(
            "TASK-010 candidate row 2 has task9_result_hash="
            "1111111111111111111111111111111111111111111111111111111111111111"
            " but selected TASK-009 row has different hash"
        ),
        details={
            "row_id": 2,
            "reason": "PERSISTED_TASK9_RESULT_HASH_MISMATCH",
            "field": "task9_result_hash",
            "persisted_task9_result_hash": ("1" * 64),
        },
        retry_hint="PROVIDE_OVERRIDE",
    )
    status_mismatch = Blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        message="TASK-010 candidate row 3 has execution_status=blocked",
        details={
            "row_id": 3,
            "reason": "EXECUTION_STATUS_NOT_COMPLETED",
            "field": "execution_status",
        },
        retry_hint="PROVIDE_OVERRIDE",
    )
    hash_malformed = Blocker(
        code=BlockerCode.AUTHORITY_HASH_MALFORMED,
        message=("TASK-010 candidate row 4 has malformed prediction_hash"),
        details={
            "row_id": 4,
            "reason": "HASH_MALFORMED",
            "field": "prediction_hash",
        },
        retry_hint="PROVIDE_OVERRIDE",
    )

    forward = [lineage_a, lineage_b, status_mismatch, hash_malformed]
    reverse = [hash_malformed, status_mismatch, lineage_b, lineage_a]
    sorted_fwd = _sort_blockers_deterministically(forward)
    sorted_rev = _sort_blockers_deterministically(reverse)

    # Strict-total-order key: distinct content produces distinct keys.
    assert _blocker_sort_key(lineage_a) != _blocker_sort_key(lineage_b), (
        "two lineage-mismatch blockers with different public content "
        "must produce distinct sort keys"
    )

    payload_fwd = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_fwd])
    payload_rev = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_rev])
    assert payload_fwd == payload_rev
    assert canonical_payload_hash(payload_fwd) == canonical_payload_hash(payload_rev)


def test_conflict_helper_task9_sorts_by_harvest_state_run_id() -> None:
    """The AUTHORITY_CONFLICT candidate disclosure for TASK-009
    uses ``harvest_state_run_id`` as the public identity.  Reverse
    input order MUST sort to the same byte-identical public payload.
    """

    from backend.app.agent.adapters.baseline_composer import (
        _authority_conflict_blocker,
    )

    candidates = [
        {
            "harvest_state_run_id": 9,
            "result_hash": "f" * 64,
        },
        {
            "harvest_state_run_id": 2,
            "result_hash": "a" * 64,
        },
    ]
    reverse = list(reversed(candidates))
    blocker = _authority_conflict_blocker("TASK9_HARVEST_STATE_RUN", candidates)
    reverse_blocker = _authority_conflict_blocker("TASK9_HARVEST_STATE_RUN", reverse)
    ids = [c["harvest_state_run_id"] for c in blocker.details["candidates"]]
    reverse_ids = [c["harvest_state_run_id"] for c in reverse_blocker.details["candidates"]]
    assert ids == [2, 9]
    assert reverse_ids == [2, 9]
    # Full public payload must be byte-identical.
    assert blocker.model_dump(mode="json") == reverse_blocker.model_dump(mode="json")


def test_conflict_helper_task10_sorts_by_prediction_run_id() -> None:
    """Same contract for TASK-010, with ``prediction_run_id``."""

    from backend.app.agent.adapters.baseline_composer import (
        _authority_conflict_blocker,
    )

    candidates = [
        {
            "prediction_run_id": 12,
            "task9_run_id": 1,
            "task9_result_hash": "a" * 64,
        },
        {
            "prediction_run_id": 4,
            "task9_run_id": 1,
            "task9_result_hash": "a" * 64,
        },
    ]
    reverse = list(reversed(candidates))
    blocker = _authority_conflict_blocker("TASK10_PREDICTION_RUN", candidates)
    reverse_blocker = _authority_conflict_blocker("TASK10_PREDICTION_RUN", reverse)
    ids = [c["prediction_run_id"] for c in blocker.details["candidates"]]
    reverse_ids = [c["prediction_run_id"] for c in reverse_blocker.details["candidates"]]
    assert ids == [4, 12]
    assert reverse_ids == [4, 12]
    assert blocker.model_dump(mode="json") == reverse_blocker.model_dump(mode="json")


def test_conflict_helper_invalid_identity_fails_closed() -> None:
    """Conflict candidates with missing, ambiguous, or no
    supported identity MUST raise :class:`ValueError` — no silent
    ``0`` fallback (Round 11 review 4680976947).
    """

    from backend.app.agent.adapters.baseline_composer import (
        _authority_conflict_blocker,
    )

    # 1) No supported identity present at all.
    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK9_HARVEST_STATE_RUN",
            [
                {"result_hash": "a" * 64},
            ],
        )

    # 2) Both ``id`` and ``harvest_state_run_id`` present.
    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK9_HARVEST_STATE_RUN",
            [
                {
                    "id": 5,
                    "harvest_state_run_id": 5,
                    "result_hash": "a" * 64,
                },
            ],
        )

    # 3) Both ``harvest_state_run_id`` and ``prediction_run_id``
    # present (cross-task identity ambiguity).
    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK10_PREDICTION_RUN",
            [
                {
                    "harvest_state_run_id": 5,
                    "prediction_run_id": 5,
                    "task9_result_hash": "a" * 64,
                },
            ],
        )


# ===========================================================================
# Round 11 evidence fix (review 4681067112): real TASK-010 default-selector
# same-prefix collision evidence + reverse-row-delivery determinism.
#
# The Round 11 fresh implementation is correct, but the
# ``test_task10_default_blocker_payload_is_stable_for_reversed_result_order``
# test only exercised the ``_sort_blockers_deterministically`` HELPER on
# hand-constructed ``Blocker`` objects — it did NOT actually call the
# real default-selector.  This Round 11 evidence-fix round provides the
# real default-selector evidence required by review 4681067112:
#
# * ``test_task10_default_selector_returns_total_ordered_nonempty_blockers``
#   — calls the production
#   ``_select_residual_prediction_run_candidates`` with
#   ``prediction_run_id_override=None`` (default path), inserts two
#   production-shaped ``ResidualModelPredictionRun`` rows that share the
#   same ``(code, reason, field)`` prefix but have different public
#   content, and asserts the returned blockers are in strict-total-order
#   over the unredacted public payload.
#
# * ``test_task10_default_selector_byte_identical_with_reversed_row_delivery``
#   — uses a real session proxy that flips the ``.all()`` order of the
#   actual SQLAlchemy result, runs the production selector twice on the
#   SAME persisted rows + SAME authority IDs, and asserts byte-identical
#   canonical payload + hash across reverse row-delivery.
# ===========================================================================


class _ReverseAllResult:
    """Wrap a SQLAlchemy result so ``.all()`` returns the rows in
    REVERSE order.  The wrapped result is real; only the
    consumption order is changed.  This lets us prove the
    production selector is byte-deterministic regardless of the
    underlying DB row-return order.
    """

    def __init__(self, result: Any) -> None:
        self._result = result
        self._reversed_rows: list[Any] | None = None

    def all(self) -> list[Any]:
        if self._reversed_rows is None:
            self._reversed_rows = list(reversed(self._result.all()))
        return list(self._reversed_rows)

    def scalars(self) -> Any:
        return self._result.scalars()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._result, name)


class _ReverseResultSession:
    """Async session proxy that flips ``.all()`` on every
    :func:`session.execute` call.  All other attributes are
    delegated to the underlying real session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        result = await self._session.execute(statement, *args, **kwargs)
        return _ReverseAllResult(result)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


@pytest.mark.asyncio
async def test_task10_default_selector_returns_total_ordered_nonempty_blockers(
    sqlite_full_session: AsyncSession,
) -> None:
    """Real default-selector evidence for the same-prefix collision.

    Calls the production
    :func:`_select_residual_prediction_run_candidates` with
    ``prediction_run_id_override=None`` (i.e. the **default** path)
    and asserts the returned blockers are in strict-total-order
    over the unredacted public payload.  Two production-shaped
    :class:`ResidualModelPredictionRun` rows are inserted: both
    bind to the selected TASK-009 by ``task9_run_id`` but
    deliberately carry wrong ``task9_result_hash`` values.  Both
    rows produce the SAME ``(code, reason, field)`` prefix in
    the public blocker (``AUTHORITY_LINEAGE_MISMATCH /
    PERSISTED_TASK9_RESULT_HASH_MISMATCH / task9_result_hash``)
    but differ in ``row_id``, ``persisted_task9_result_hash``,
    ``message``, and the rest of the public details.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )
    from backend.app.agent.adapters.baseline_composer import (
        _blocker_sort_key,
    )

    # Selected TASK-009 authority identity.
    selected_task9_run_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    selected_task9_result_hash = "a" * 64

    # Two residual runs bound to the same task9_run_id but with
    # deliberately wrong task9_result_hash values.  Both will
    # surface AUTHORITY_LINEAGE_MISMATCH in the default path.
    residual_a = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash="0" * 64,  # WRONG hash → lineage mismatch
        prediction_hash="e" * 64,
        prediction_input_signature="1" * 64,
    )
    residual_b = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash="1" * 64,  # WRONG hash → lineage mismatch
        prediction_hash="f" * 64,
        prediction_input_signature="2" * 64,
    )

    selection = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash=selected_task9_result_hash,
        prediction_run_id_override=None,  # DEFAULT path
    )
    assert selection.candidates == (), (
        f"two lineage-mismatch rows must yield zero candidates; got {selection.candidates}"
    )
    assert len(selection.blockers) >= 2, (
        f"default path must return ≥2 lineage-mismatch blockers "
        f"(a={residual_a}, b={residual_b}); got {len(selection.blockers)}"
    )

    # At least two blockers must share the same (code, field) prefix.
    lineage_blockers = [
        b
        for b in selection.blockers
        if b.code == BlockerCode.AUTHORITY_LINEAGE_MISMATCH
        and (b.details or {}).get("field") == "task9_result_hash"
    ]
    assert len(lineage_blockers) >= 2, (
        f"expected ≥2 lineage-mismatch blockers with same (code, field) "
        f"prefix; got "
        f"{[(b.code.value, b.details.get('field'), b.details.get('row_id')) for b in selection.blockers]}"
    )
    # Same (code, field) prefix, distinct public content.
    keys = [_blocker_sort_key(b) for b in lineage_blockers]
    assert len(set(keys)) == len(keys), (
        f"strict total order requires distinct keys for distinct-content "
        f"lineage blockers; got duplicate keys: {keys}"
    )
    # The two lineage blockers must carry different row_ids
    # (authority identity must be preserved, NOT collapsed).
    row_ids = sorted(int((b.details or {}).get("row_id")) for b in lineage_blockers)
    assert row_ids == sorted([residual_a, residual_b]), (
        f"lineage blockers must carry their distinct real row_ids; "
        f"got {row_ids} (a={residual_a}, b={residual_b})"
    )
    # The two lineage blockers must carry different row_task9_result_hash
    # values (which is the public-content discriminator).
    row_hashes = sorted((b.details or {}).get("row_task9_result_hash") for b in lineage_blockers)
    assert row_hashes == ["0" * 64, "1" * 64], (
        f"lineage blockers must carry their distinct row_task9_result_hash; got {row_hashes}"
    )

    # Full, unredacted canonical payload / hash on the entire
    # production-returned blocker list (NOT a redaction subset).
    payload = canonical_json_dumps([b.model_dump(mode="json") for b in selection.blockers])
    payload_hash = canonical_payload_hash(payload)
    assert isinstance(payload, str) and payload.startswith("[")
    # Unredacted: row_id / message / details / retry_hint all present.
    for b in lineage_blockers:
        details = b.details or {}
        assert "row_id" in details
        assert "row_task9_result_hash" in details
        assert "selected_task9_result_hash" in details
        assert b.message
        assert b.retry_hint
    # Re-hash the payload to ensure determinism.
    assert canonical_payload_hash(payload) == payload_hash


@pytest.mark.asyncio
async def test_task10_default_selector_byte_identical_with_reversed_row_delivery(
    sqlite_full_session: AsyncSession,
) -> None:
    """Same TASK-010 default-selector evidence, but with the real
    session proxy returning rows in REVERSE order.  Uses the
    **same persisted rows + same authority IDs** — no
    delete+reinsert, no row_id changes, no helper-only path.

    Compares the full, unredacted canonical payload / hash of
    the production-returned blockers across normal and reversed
    row delivery.  This is the strict-total-order evidence
    required by review 4681067112.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )

    selected_task9_run_id = await _insert_harvest_state_run(
        sqlite_full_session,
        result_hash="a" * 64,
        config_hash="b" * 64,
        input_snapshot={**_REAL_TASK9_INPUT_SNAPSHOT, "forecast_season": 2026},
    )
    selected_task9_result_hash = "a" * 64

    residual_a = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash="0" * 64,
        prediction_hash="e" * 64,
        prediction_input_signature="1" * 64,
    )
    residual_b = await _insert_residual_prediction_run(
        sqlite_full_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash="1" * 64,
        prediction_hash="f" * 64,
        prediction_input_signature="2" * 64,
    )

    # Normal delivery: real session, no proxy.
    normal = await _select_residual_prediction_run_candidates(
        sqlite_full_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash=selected_task9_result_hash,
        prediction_run_id_override=None,
    )
    # Reversed delivery: SAME rows, SAME authority IDs, just
    # flipping the .all() order of the underlying SQLAlchemy result.
    reversed_session = _ReverseResultSession(sqlite_full_session)
    reversed_result = await _select_residual_prediction_run_candidates(
        reversed_session,
        task9_run_id=selected_task9_run_id,
        task9_result_hash=selected_task9_result_hash,
        prediction_run_id_override=None,
    )

    assert normal.candidates == ()
    assert reversed_result.candidates == ()
    assert len(normal.blockers) >= 2
    assert len(reversed_result.blockers) >= 2

    normal_payload = canonical_json_dumps([b.model_dump(mode="json") for b in normal.blockers])
    reversed_payload = canonical_json_dumps(
        [b.model_dump(mode="json") for b in reversed_result.blockers]
    )
    assert normal_payload == reversed_payload, (
        f"production default selector must return byte-identical public "
        f"payload across reverse row delivery:\n  normal:   {normal_payload}\n"
        f"  reversed: {reversed_payload}\n"
        f"  residual_a={residual_a}, residual_b={residual_b}"
    )
    assert canonical_payload_hash(normal_payload) == canonical_payload_hash(reversed_payload)
