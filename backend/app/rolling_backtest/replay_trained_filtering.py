"""TASK-012 Slice C — replay_trained_model training-row cutoff filtering.

Per ``docs/task-012-replay-trained-model-design.md`` §12 Slice C (verbatim):

    Allowed: deterministic training invocation under replay only, behind explicit
             policy gate.
    Forbidden: changing Task 8 / Task 9 semantics, using current-data fallback, or
               changing historical model behavior.

Per §14 stop conditions, this module MUST NOT introduce any ``current_data``,
``latest``, or ``most_recent`` fallback semantics. All filtering is deterministic
and content-driven via explicit cutoff timestamps carried in the identity
projection (see ``replay_trained_identity.TrainingManifestPayload``).

This module provides three pure-function helpers:

1. ``filter_training_rows_by_cutoff`` — §11 #3 execution portion.
   Drops rows whose ``observation_date`` is strictly after
   ``training_cutoff_at``. Deterministic, no implicit fallback.
2. ``filter_labels_by_availability_cutoff`` — §11 #4.
   Drops rows whose label ``availability_date`` is strictly after
   ``label_availability_cutoff_at``. Same determinism contract.
3. ``require_non_empty_training_rows`` — §11 #5.
   Raises :class:`TrainingRowsEmptyError` (a structured blocker mapped to
   ``OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY``) when the filtered
   training set is empty. The blocker is the same canonical blocker used by
   Slice B §9, ensuring no ad-hoc blocker strings are introduced.

These helpers are pure functions — they do not invoke any live training
algorithm, do not mutate inputs, and do not touch Task 8 / Task 9 / Task 10
semantics. They are intended to be invoked from the explicit policy gate
``validate_replay_task10_model_policy`` only when the runtime gate is flipped.
Until the runtime gate is flipped, replay_trained_model continues to refuse all
execution attempts (per §13) — these helpers are inert at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .canonical import canonical_json_dumps
from .orchestration import OrchestrationBlocker


@dataclass(frozen=True)
class FilteredTrainingRow:
    """Single training row after cutoff filtering.

    Mirrors the shape of a Task 8 task8 curve row's subset that
    ``filter_training_rows_by_cutoff`` keeps — observation_date + value.
    We intentionally keep this dataclass minimal (no Task 8 / Task 9
    integration). The execution layer is responsible for projecting
    full rows; this helper operates on the canonical cutoff-filter
    contract only.
    """

    observation_date: date
    value: float


@dataclass(frozen=True)
class FilteredLabelRow:
    """Single label row after label-availability cutoff filtering (§11 #4)."""

    observation_date: date
    label_availability_date: date
    value: float


class TrainingRowsEmptyError(ValueError):
    """§11 #5 — structured blocker when filtered training set is empty.

    Maps to :class:`OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY` so
    callers can rely on the canonical blocker enum rather than ad-hoc
    error strings. The accompanying :attr:`blocker_code` carries the
    enum's ``.value`` string, matching the existing
    :class:`replay_metadata.ReplayMetadataInputError` /
    :class:`replay_metadata.ReplayMetadataConflictError` module-local
    pattern.

    The :attr:`payload` is a deterministic canonical-JSON string
    (per ``canonical.canonical_json_dumps``) — load-bearing for §7 hash
    traceability into training reports.
    """

    def __init__(
        self,
        message: str,
        *,
        blocker_code: str = OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY.value,
        training_cutoff_at: date | None = None,
        candidate_row_count: int = 0,
        kept_row_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.blocker_code = blocker_code
        self.training_cutoff_at = training_cutoff_at
        self.candidate_row_count = candidate_row_count
        self.kept_row_count = kept_row_count
        self.payload = canonical_json_dumps(
            {
                "blocker": blocker_code,
                "training_cutoff_at": (
                    training_cutoff_at.isoformat() if training_cutoff_at is not None else None
                ),
                "candidate_row_count": candidate_row_count,
                "kept_row_count": kept_row_count,
            }
        )


def filter_training_rows_by_cutoff(
    rows: tuple[FilteredTrainingRow, ...],
    *,
    training_cutoff_at: date,
) -> tuple[FilteredTrainingRow, ...]:
    """§11 #3 execution portion — deterministic cutoff filter.

    Drops rows whose ``observation_date`` is strictly greater than
    ``training_cutoff_at``. Rows whose ``observation_date`` equals
    ``training_cutoff_at`` are KEPT (inclusive cutoff, matches §3 binding
    gate convention).

    The function is pure: it does not mutate ``rows``, does not introduce
    any fallback (no current_data / latest / most_recent semantics), and
    returns a tuple ordered identically to the input (deterministic order
    preservation — load-bearing for §7 deterministic hash contract).

    Parameters
    ----------
    rows : tuple[FilteredTrainingRow, ...]
        Candidate training rows. Expected to be sorted by ``observation_date``
        in ascending order (the canonical ordering used by Task 8 curves).
        Order is preserved exactly — no re-sorting, no implicit re-ordering.
    training_cutoff_at : date
        Inclusive cutoff. Rows with ``observation_date > training_cutoff_at``
        are dropped. Rows with ``observation_date <= training_cutoff_at`` are
        kept.

    Returns
    -------
    tuple[FilteredTrainingRow, ...]
        Filtered rows in original order.
    """
    return tuple(row for row in rows if row.observation_date <= training_cutoff_at)


def filter_labels_by_availability_cutoff(
    rows: tuple[FilteredLabelRow, ...],
    *,
    label_availability_cutoff_at: date,
) -> tuple[FilteredLabelRow, ...]:
    """§11 #4 — deterministic label-availability cutoff filter.

    Drops rows whose ``label_availability_date`` is strictly greater than
    ``label_availability_cutoff_at``. Rows whose ``label_availability_date``
    equals the cutoff are KEPT (inclusive cutoff).

    Same pure-function / no-fallback contract as
    :func:`filter_training_rows_by_cutoff`.
    """
    return tuple(row for row in rows if row.label_availability_date <= label_availability_cutoff_at)


def require_non_empty_training_rows(
    rows: tuple[FilteredTrainingRow, ...],
    *,
    training_cutoff_at: date,
    candidate_row_count: int | None = None,
) -> tuple[FilteredTrainingRow, ...]:
    """§11 #5 — structured blocker when filtered training set is empty.

    Returns ``rows`` unchanged if non-empty. Otherwise raises
    :class:`TrainingRowsEmptyError` carrying the canonical blocker enum +
    deterministic JSON payload (so the error can be hashed into training
    reports without re-serialization drift).

    Parameters
    ----------
    rows : tuple[FilteredTrainingRow, ...]
        Already-cutoff-filtered training rows (output of
        :func:`filter_training_rows_by_cutoff`).
    training_cutoff_at : date
        The cutoff used during filtering — recorded in the error payload
        for reproducibility / §7 hash traceability.
    candidate_row_count : int | None
        Optional pre-filter row count (for diagnostic clarity). Defaults
        to ``len(rows)``.
    """
    if rows:
        return rows
    raise TrainingRowsEmptyError(
        "filtered training row set is empty after cutoff filter",
        training_cutoff_at=training_cutoff_at,
        candidate_row_count=(candidate_row_count if candidate_row_count is not None else 0),
        kept_row_count=0,
    )
