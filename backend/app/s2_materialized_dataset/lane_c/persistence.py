"""In-memory persistence boundary for Lane C decisions (no Alembic in R1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.s2_materialized_dataset.lane_c.schemas import (
    PitVisibilityDecision,
    RevisionWinnerDecision,
)


@dataclass
class LaneCPersistenceStore:
    """Append-only in-memory store for deterministic replay during Draft R1."""

    pit_visibility_decisions: list[PitVisibilityDecision] = field(default_factory=list)
    revision_winner_decisions: list[RevisionWinnerDecision] = field(default_factory=list)

    def record_pit_visibility(self, decision: PitVisibilityDecision) -> None:
        self.pit_visibility_decisions.append(decision)

    def record_revision_winner(self, decision: RevisionWinnerDecision) -> None:
        self.revision_winner_decisions.append(decision)


__all__ = ["LaneCPersistenceStore"]
