from __future__ import annotations

from datetime import UTC, datetime

from backend.app.s2_materialized_dataset.lane_c.revision_winner import (
    IDFL_REVISION_WINNER_REQUIRED,
    resolve_revision_winner,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    LogicalRecordKey,
    RevisionWinnerBlockReason,
    RevisionWinnerMode,
)
from backend.tests.s2_materialized_dataset.lane_c.conftest import (
    make_revision_candidate,
    make_timestamps,
)


def test_idfl_mode_returns_explicit_no_winner_without_manifest(
    cutoff_context: ForecastCutoffContext,
    revision_candidate_factory: object,
) -> None:
    candidate = make_revision_candidate(
        logical_record_id="LR-IDFL",
        revision_id="REV-1",
        revision_number=1,
        identity_hash="d" * 64,
        timestamps=make_timestamps(),
    )

    decision = resolve_revision_winner(
        logical_record_key=candidate.logical_record_key,
        candidates=(candidate,),
        cutoff_context=cutoff_context,
        mode=RevisionWinnerMode.IDFL_LABEL_SIDE,
    )

    assert IDFL_REVISION_WINNER_REQUIRED is False
    assert decision.revision_winner_required is False
    assert decision.winner_source_row_identity is None
    assert decision.no_winner_reason == RevisionWinnerBlockReason.NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
    assert decision.blocked is False
    assert decision.winner_manifest_required is False


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
