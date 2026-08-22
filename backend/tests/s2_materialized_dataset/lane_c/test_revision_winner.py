from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa

from backend.app.s2_materialized_dataset.lane_c.cutoff import (
    ForecastCutoffValidationError,
    validate_forecast_cutoff_context,
)
from backend.app.s2_materialized_dataset.lane_c.persistence import (
    LaneCPersistenceStore,
    idfl_null_timestamps,
    persist_idfl_revision_winner_decision,
    pit_sql_persist_blocked_without_forecast_cutoff,
    revision_winner_sql_persist_blocked_without_forecast_cutoff,
)
from backend.app.s2_materialized_dataset.lane_c.revision_winner import (
    IDFL_REVISION_WINNER_REQUIRED,
    resolve_idfl_revision_winner_for_source_row,
    resolve_revision_winner,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    IdflLabelSideContext,
    LogicalRecordKey,
    RevisionWinnerBlockReason,
    RevisionWinnerMode,
    SourceRowIdentity,
)
from backend.tests.s2_materialized_dataset.lane_c.conftest import (
    make_revision_candidate,
    make_timestamps,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.mark.migration
def test_lane_c_revision_winner_table_enforces_mode_and_immutability(
    lane_c_migrated_session,
    cutoff_context,
) -> None:
    candidate = make_revision_candidate(
        logical_record_id="LR-MIG",
        revision_id="REV-MIG",
        revision_number=1,
        identity_hash="c" * 64,
        timestamps=make_timestamps(),
    )
    decision = resolve_revision_winner(
        logical_record_key=candidate.logical_record_key,
        candidates=(candidate,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )
    from backend.app.s2_materialized_dataset.lane_c.persistence import (
        persist_revision_winner_decision,
    )

    row = persist_revision_winner_decision(lane_c_migrated_session, decision)
    lane_c_migrated_session.commit()
    inspector = sa.inspect(lane_c_migrated_session.bind)
    checks = {
        check["name"] for check in inspector.get_check_constraints("s2_revision_winner_decision")
    }
    assert "ck_s2_revision_winner_mode" in checks
    assert "ck_s2_revision_winner_no_winner_reason" in checks
    with pytest.raises(sa.exc.IntegrityError):
        lane_c_migrated_session.execute(
            sa.text(
                """
                UPDATE s2_revision_winner_decision
                SET blocked = 1
                WHERE id = :row_id
                """
            ),
            {"row_id": row.id},
        )
        lane_c_migrated_session.commit()


def test_idfl_mode_returns_explicit_no_winner_without_manifest(
    synthetic_source_row_identity: SourceRowIdentity,
) -> None:
    decision = resolve_idfl_revision_winner_for_source_row(
        source_row_identity=synthetic_source_row_identity,
    )

    assert IDFL_REVISION_WINNER_REQUIRED is False
    assert decision.revision_winner_required is False
    assert decision.winner_source_row_identity is None
    assert decision.no_winner_reason == RevisionWinnerBlockReason.NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
    assert decision.blocked is False
    assert decision.winner_manifest_required is False
    assert decision.cutoff_context is None
    assert decision.idfl_label_side_context is not None


def test_idfl_revision_winner_timestamps_are_explicit_nulls(
    synthetic_source_row_identity: SourceRowIdentity,
) -> None:
    decision = resolve_idfl_revision_winner_for_source_row(
        source_row_identity=synthetic_source_row_identity,
    )

    assert decision.timestamps == idfl_null_timestamps()
    assert decision.timestamps.source_recorded_at is None
    assert decision.timestamps.source_available_at is None
    assert decision.timestamps.source_revised_at is None
    assert decision.timestamps.source_finalized_at is None
    assert decision.timestamps.source_cancelled_at is None


def test_idfl_revision_winner_hash_is_stable_across_replays(
    synthetic_source_row_identity: SourceRowIdentity,
) -> None:
    first = resolve_idfl_revision_winner_for_source_row(
        source_row_identity=synthetic_source_row_identity,
    )
    second = resolve_idfl_revision_winner_for_source_row(
        source_row_identity=synthetic_source_row_identity,
    )

    assert first.content_sha256 == second.content_sha256


def test_idfl_revision_winner_can_persist_without_fabricated_cutoff(
    lane_c_migrated_session,
    synthetic_source_row_identity: SourceRowIdentity,
) -> None:
    assert pit_sql_persist_blocked_without_forecast_cutoff(lane_c_migrated_session)
    assert revision_winner_sql_persist_blocked_without_forecast_cutoff(lane_c_migrated_session)

    decision = resolve_idfl_revision_winner_for_source_row(
        source_row_identity=synthetic_source_row_identity,
    )
    store = LaneCPersistenceStore()
    first = persist_idfl_revision_winner_decision(
        lane_c_migrated_session,
        decision,
        store=store,
    )
    second = persist_idfl_revision_winner_decision(
        lane_c_migrated_session,
        decision,
        store=store,
    )

    assert first is None
    assert second is None
    assert len(store.revision_winner_decisions) == 1
    assert store.revision_winner_decisions[0].content_sha256 == decision.content_sha256


def test_idfl_revision_winner_does_not_require_source_available_at(
    synthetic_source_row_identity: SourceRowIdentity,
) -> None:
    decision = resolve_idfl_revision_winner_for_source_row(
        source_row_identity=synthetic_source_row_identity,
    )

    assert decision.blocked is False
    assert decision.no_winner_reason == RevisionWinnerBlockReason.NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
    assert decision.no_winner_reason != RevisionWinnerBlockReason.NO_VISIBLE_CANDIDATE_AT_CUTOFF


def test_harvest_business_date_cannot_be_used_as_idfl_forecast_cutoff() -> None:
    harvest_date = date(2026, 2, 10)
    with pytest.raises((TypeError, ValueError)):
        IdflLabelSideContext(forecast_cutoff_at=harvest_date)  # type: ignore[call-arg]
    naive_harvest_cutoff = datetime.combine(harvest_date, datetime.min.time())
    with pytest.raises(ForecastCutoffValidationError, match="timezone-aware"):
        validate_forecast_cutoff_context(
            ForecastCutoffContext(forecast_cutoff_at=naive_harvest_cutoff),
        )


def test_unique_visible_terminal_wins_for_replay_mode(
    cutoff_context: ForecastCutoffContext,
) -> None:
    logical = LogicalRecordKey(
        source_system="synthetic-scan-weight",
        external_logical_record_id="LR-REPLAY",
    )
    root = make_revision_candidate(
        logical_record_id="LR-REPLAY",
        revision_id="REV-1",
        revision_number=1,
        identity_hash="1" * 64,
        timestamps=make_timestamps(source_available_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC)),
        record_status="CORRECTED",
        supersedes_external_revision_id=None,
    )
    winner = make_revision_candidate(
        logical_record_id="LR-REPLAY",
        revision_id="REV-2",
        revision_number=2,
        identity_hash="2" * 64,
        timestamps=make_timestamps(source_available_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC)),
        record_status="ACTIVE",
        supersedes_external_revision_id="REV-1",
    )

    decision = resolve_revision_winner(
        logical_record_key=logical,
        candidates=(winner, root),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert decision.blocked is False
    assert decision.winner_source_row_identity == winner.source_row_identity
    assert decision.no_winner_reason is None


def test_no_visible_candidate_returns_explicit_no_winner_and_blocks_row(
    cutoff_context: ForecastCutoffContext,
) -> None:
    candidate = make_revision_candidate(
        logical_record_id="LR-NONE",
        revision_id="REV-LATE",
        revision_number=1,
        identity_hash="3" * 64,
        timestamps=make_timestamps(
            source_available_at=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
        ),
    )

    decision = resolve_revision_winner(
        logical_record_key=candidate.logical_record_key,
        candidates=(candidate,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert decision.winner_source_row_identity is None
    assert decision.blocked is True
    assert decision.no_winner_reason == RevisionWinnerBlockReason.NO_VISIBLE_CANDIDATE_AT_CUTOFF


def test_multiple_visible_terminals_block_with_no_winner(
    cutoff_context: ForecastCutoffContext,
) -> None:
    logical = LogicalRecordKey(
        source_system="synthetic-scan-weight",
        external_logical_record_id="LR-TIE",
    )
    first = make_revision_candidate(
        logical_record_id="LR-TIE",
        revision_id="REV-A",
        revision_number=1,
        identity_hash="4" * 64,
        timestamps=make_timestamps(source_available_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC)),
        record_status="ACTIVE",
    )
    second = make_revision_candidate(
        logical_record_id="LR-TIE",
        revision_id="REV-B",
        revision_number=1,
        identity_hash="5" * 64,
        timestamps=make_timestamps(source_available_at=datetime(2026, 2, 27, 9, 30, tzinfo=UTC)),
        record_status="ACTIVE",
    )

    decision = resolve_revision_winner(
        logical_record_key=logical,
        candidates=(first, second),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert decision.winner_source_row_identity is None
    assert decision.blocked is True
    assert decision.no_winner_reason == RevisionWinnerBlockReason.MULTIPLE_VISIBLE_TERMINALS


def test_contradictory_finalization_and_cancellation_blocks_row(
    cutoff_context: ForecastCutoffContext,
) -> None:
    candidate = make_revision_candidate(
        logical_record_id="LR-CONFLICT",
        revision_id="REV-X",
        revision_number=1,
        identity_hash="6" * 64,
        timestamps=make_timestamps(
            source_finalized_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            source_cancelled_at=datetime(2026, 2, 27, 11, 0, tzinfo=UTC),
        ),
        record_status="FINALIZED",
        finalized_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
    )

    decision = resolve_revision_winner(
        logical_record_key=candidate.logical_record_key,
        candidates=(candidate,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert decision.blocked is True
    assert decision.no_winner_reason == RevisionWinnerBlockReason.CONTRADICTORY_EVIDENCE


def test_latest_row_fallback_is_not_used_when_only_late_candidate_exists(
    cutoff_context: ForecastCutoffContext,
) -> None:
    late = make_revision_candidate(
        logical_record_id="LR-LATE",
        revision_id="REV-LATE",
        revision_number=99,
        identity_hash="7" * 64,
        timestamps=make_timestamps(
            source_available_at=datetime(2026, 3, 2, 0, 0, tzinfo=UTC),
        ),
        record_status="ACTIVE",
    )

    decision = resolve_revision_winner(
        logical_record_key=late.logical_record_key,
        candidates=(late,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert decision.winner_source_row_identity is None
    assert decision.blocked is True


def test_revision_winner_hash_is_deterministic_for_same_inputs(
    cutoff_context: ForecastCutoffContext,
) -> None:
    candidate = make_revision_candidate(
        logical_record_id="LR-HASH",
        revision_id="REV-H",
        revision_number=1,
        identity_hash="8" * 64,
        timestamps=make_timestamps(),
    )
    first = resolve_revision_winner(
        logical_record_key=candidate.logical_record_key,
        candidates=(candidate,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )
    second = resolve_revision_winner(
        logical_record_key=candidate.logical_record_key,
        candidates=(candidate,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert first.content_sha256 == second.content_sha256


def test_duplicate_external_revision_id_fails_closed(
    cutoff_context: ForecastCutoffContext,
) -> None:
    logical = LogicalRecordKey(
        source_system="synthetic-scan-weight",
        external_logical_record_id="LR-DUP",
    )
    first = make_revision_candidate(
        logical_record_id="LR-DUP",
        revision_id="REV-DUP",
        revision_number=1,
        identity_hash="9" * 64,
        timestamps=make_timestamps(),
    )
    second = make_revision_candidate(
        logical_record_id="LR-DUP",
        revision_id="REV-DUP",
        revision_number=2,
        identity_hash="a" * 64,
        timestamps=make_timestamps(),
    )

    decision = resolve_revision_winner(
        logical_record_key=logical,
        candidates=(first, second),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.REPLAY_REVISION_GRAPH,
    )

    assert decision.blocked is True
    assert (
        decision.no_winner_reason == RevisionWinnerBlockReason.DUPLICATE_REVISION_CANDIDATE_IDENTITY
    )
