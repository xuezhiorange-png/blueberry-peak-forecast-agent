"""Revision-winner resolution for Lane C."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from backend.app.s2_materialized_dataset.lane_c.cutoff import validate_forecast_cutoff_context
from backend.app.s2_materialized_dataset.lane_c.hashes import (
    compute_idfl_revision_winner_content_hash,
    compute_revision_winner_content_hash,
    ordered_candidate_identity_hashes,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    IdflLabelSideContext,
    LogicalRecordKey,
    PitVisibilityBlockReason,
    RevisionCandidateRecord,
    RevisionWinnerBlockReason,
    RevisionWinnerDecision,
    RevisionWinnerMode,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)
from backend.app.s2_materialized_dataset.lane_c.visibility import evaluate_pit_visibility

IDFL_REVISION_WINNER_REQUIRED = False
LATEST_ROW_FALLBACK_ALLOWED = False
REVISION_WINNER_ALGORITHM = "NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE"

_WINNER_ELIGIBLE_STATUSES = frozenset({"ACTIVE", "FINALIZED"})


def idfl_null_timestamps() -> SourceRowLifecycleTimestamps:
    return SourceRowLifecycleTimestamps(
        source_recorded_at=None,
        source_available_at=None,
        source_revised_at=None,
        source_finalized_at=None,
        source_cancelled_at=None,
    )


def resolve_idfl_revision_winner_for_source_row(
    *,
    source_row_identity: SourceRowIdentity,
    idfl_label_side_context: IdflLabelSideContext | None = None,
) -> RevisionWinnerDecision:
    label_context = idfl_label_side_context or IdflLabelSideContext()
    timestamps = idfl_null_timestamps()
    logical_record_key = LogicalRecordKey(
        source_system=source_row_identity.source_system,
        external_logical_record_id=source_row_identity.external_logical_record_id,
    )
    ordered_identities = (source_row_identity.source_row_identity_hash,)
    content_sha256 = compute_idfl_revision_winner_content_hash(
        logical_record_key=logical_record_key,
        source_row_identity=source_row_identity,
        timestamps=timestamps,
        idfl_label_side_context=label_context,
        ordered_candidate_identities=ordered_identities,
        winner_source_row_identity_hash=None,
        blocked=False,
        no_winner_reason=RevisionWinnerBlockReason.NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE.value,
        mode=RevisionWinnerMode.IDFL_LABEL_SIDE.value,
    )
    return RevisionWinnerDecision(
        logical_record_key=logical_record_key,
        source_row_identity=source_row_identity,
        timestamps=timestamps,
        cutoff_context=None,
        idfl_label_side_context=label_context,
        mode=RevisionWinnerMode.IDFL_LABEL_SIDE,
        revision_winner_required=False,
        winner_manifest_required=False,
        winner_source_row_identity=None,
        blocked=False,
        no_winner_reason=RevisionWinnerBlockReason.NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE,
        ordered_candidate_identities=ordered_identities,
        content_sha256=content_sha256,
    )


def _duplicate_revision_ids(candidates: Sequence[RevisionCandidateRecord]) -> bool:
    seen: set[str] = set()
    for candidate in candidates:
        revision_id = candidate.source_row_identity.external_revision_id
        if revision_id in seen:
            return True
        seen.add(revision_id)
    return False


def resolve_revision_winner(
    *,
    logical_record_key: LogicalRecordKey,
    candidates: Sequence[RevisionCandidateRecord],
    mode: RevisionWinnerMode,
    cutoff_context: ForecastCutoffContext | None = None,
    idfl_label_side_context: IdflLabelSideContext | None = None,
) -> RevisionWinnerDecision:
    ordered_identities = ordered_candidate_identity_hashes(candidates)

    if mode is RevisionWinnerMode.IDFL_LABEL_SIDE:
        if len(candidates) != 1:
            raise ValueError("IDFL_LABEL_SIDE requires exactly one source row candidate")
        return resolve_idfl_revision_winner_for_source_row(
            source_row_identity=candidates[0].source_row_identity,
            idfl_label_side_context=idfl_label_side_context,
        )

    if cutoff_context is None:
        raise ValueError("replay revision-winner resolution requires cutoff_context")
    validated_context = validate_forecast_cutoff_context(cutoff_context)

    if _duplicate_revision_ids(candidates):
        return _blocked(
            logical_record_key=logical_record_key,
            cutoff_context=validated_context,
            mode=mode,
            ordered_candidate_identities=ordered_identities,
            reason=RevisionWinnerBlockReason.DUPLICATE_REVISION_CANDIDATE_IDENTITY,
        )

    for candidate in candidates:
        visibility = evaluate_pit_visibility(
            source_row_identity=candidate.source_row_identity,
            timestamps=candidate.timestamps,
            cutoff_context=validated_context,
        )
        if visibility.block_reason is PitVisibilityBlockReason.CONTRADICTORY_TIMESTAMPS:
            return _blocked(
                logical_record_key=logical_record_key,
                cutoff_context=validated_context,
                mode=mode,
                ordered_candidate_identities=ordered_identities,
                reason=RevisionWinnerBlockReason.CONTRADICTORY_EVIDENCE,
            )

    visible_candidates = [
        candidate
        for candidate in candidates
        if evaluate_pit_visibility(
            source_row_identity=candidate.source_row_identity,
            timestamps=candidate.timestamps,
            cutoff_context=validated_context,
        ).eligible
    ]

    if not visible_candidates:
        return _blocked(
            logical_record_key=logical_record_key,
            cutoff_context=validated_context,
            mode=mode,
            ordered_candidate_identities=ordered_identities,
            reason=RevisionWinnerBlockReason.NO_VISIBLE_CANDIDATE_AT_CUTOFF,
        )

    visible_by_revision_id: dict[str, RevisionCandidateRecord] = {}
    for candidate in visible_candidates:
        revision_id = candidate.source_row_identity.external_revision_id
        if revision_id in visible_by_revision_id:
            return _blocked(
                logical_record_key=logical_record_key,
                cutoff_context=validated_context,
                mode=mode,
                ordered_candidate_identities=ordered_identities,
                reason=RevisionWinnerBlockReason.DUPLICATE_REVISION_CANDIDATE_IDENTITY,
            )
        visible_by_revision_id[revision_id] = candidate

    visible_successors: dict[str, list[RevisionCandidateRecord]] = defaultdict(list)
    for candidate in visible_candidates:
        predecessor = candidate.supersedes_external_revision_id
        if predecessor is None:
            continue
        if predecessor not in visible_by_revision_id:
            continue
        visible_successors[predecessor].append(candidate)

    terminals: list[RevisionCandidateRecord] = []
    for candidate in visible_candidates:
        revision_id = candidate.source_row_identity.external_revision_id
        if visible_successors.get(revision_id):
            continue
        terminals.append(candidate)

    if len(terminals) != 1:
        return _blocked(
            logical_record_key=logical_record_key,
            cutoff_context=validated_context,
            mode=mode,
            ordered_candidate_identities=ordered_identities,
            reason=RevisionWinnerBlockReason.MULTIPLE_VISIBLE_TERMINALS
            if len(terminals) > 1
            else RevisionWinnerBlockReason.NO_VISIBLE_CANDIDATE_AT_CUTOFF,
        )

    terminal = terminals[0]
    if terminal.record_status not in _WINNER_ELIGIBLE_STATUSES:
        return _blocked(
            logical_record_key=logical_record_key,
            cutoff_context=validated_context,
            mode=mode,
            ordered_candidate_identities=ordered_identities,
            reason=RevisionWinnerBlockReason.NO_WINNER,
        )

    if terminal.record_status == "FINALIZED":
        finalized_at = terminal.finalized_at_or_null or terminal.timestamps.source_finalized_at
        if finalized_at is None:
            return _blocked(
                logical_record_key=logical_record_key,
                cutoff_context=validated_context,
                mode=mode,
                ordered_candidate_identities=ordered_identities,
                reason=RevisionWinnerBlockReason.CONTRADICTORY_EVIDENCE,
            )

    return _decision(
        logical_record_key=logical_record_key,
        cutoff_context=validated_context,
        mode=mode,
        revision_winner_required=True,
        winner_manifest_required=True,
        winner_source_row_identity=terminal.source_row_identity,
        blocked=False,
        no_winner_reason=None,
        ordered_candidate_identities=ordered_identities,
    )


def _blocked(
    *,
    logical_record_key: LogicalRecordKey,
    cutoff_context: ForecastCutoffContext,
    mode: RevisionWinnerMode,
    ordered_candidate_identities: tuple[str, ...],
    reason: RevisionWinnerBlockReason,
) -> RevisionWinnerDecision:
    return _decision(
        logical_record_key=logical_record_key,
        cutoff_context=cutoff_context,
        mode=mode,
        revision_winner_required=True,
        winner_manifest_required=True,
        winner_source_row_identity=None,
        blocked=True,
        no_winner_reason=reason,
        ordered_candidate_identities=ordered_candidate_identities,
    )


def _decision(
    *,
    logical_record_key: LogicalRecordKey,
    cutoff_context: ForecastCutoffContext,
    mode: RevisionWinnerMode,
    revision_winner_required: bool,
    winner_manifest_required: bool,
    winner_source_row_identity: SourceRowIdentity | None,
    blocked: bool,
    no_winner_reason: RevisionWinnerBlockReason | None,
    ordered_candidate_identities: tuple[str, ...],
) -> RevisionWinnerDecision:
    content_sha256 = compute_revision_winner_content_hash(
        logical_record_key=logical_record_key,
        cutoff_context=cutoff_context,
        ordered_candidate_identities=ordered_candidate_identities,
        winner_source_row_identity_hash=(
            None
            if winner_source_row_identity is None
            else winner_source_row_identity.source_row_identity_hash
        ),
        blocked=blocked,
        no_winner_reason=None if no_winner_reason is None else no_winner_reason.value,
        mode=mode.value,
    )
    return RevisionWinnerDecision(
        logical_record_key=logical_record_key,
        source_row_identity=None,
        timestamps=None,
        cutoff_context=cutoff_context,
        idfl_label_side_context=None,
        mode=mode,
        revision_winner_required=revision_winner_required,
        winner_manifest_required=winner_manifest_required,
        winner_source_row_identity=winner_source_row_identity,
        blocked=blocked,
        no_winner_reason=no_winner_reason,
        ordered_candidate_identities=ordered_candidate_identities,
        content_sha256=content_sha256,
    )


__all__ = [
    "IDFL_REVISION_WINNER_REQUIRED",
    "LATEST_ROW_FALLBACK_ALLOWED",
    "REVISION_WINNER_ALGORITHM",
    "idfl_null_timestamps",
    "resolve_idfl_revision_winner_for_source_row",
    "resolve_revision_winner",
]
