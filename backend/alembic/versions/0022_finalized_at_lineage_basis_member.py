"""Persist finalized_at on the I5 lineage basis member for V0.2-S2 / Q2A-I7.

Frozen contract:
- docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md §10
- Revision: 0022_finalized_at_lineage_basis_member
- Down revision: 0021_actual_harvest_label_snapshot
- Adds a single nullable column finalized_at
  (TIMESTAMP WITH TIME ZONE on PostgreSQL, DateTime(timezone=True) on
  SQLite) to the existing table
  actual_harvest_validation_lineage_basis_member.
- This column makes the committed FINALIZED predecessor's finalized_at
  a piece of immutable committed lineage basis evidence so:
    1. I5 hardening check FINALIZED_AT_REQUIRED can read it back on
       subsequent validation runs;
    2. I7 AS_OF_FINALIZED_AFTER_CUTOFF can read it back when computing
       effective_status = finalized_after_cutoff -> STATUS_NOT_VISIBLE_AT_CUTOFF;
    3. AS_OF_FINALIZED_HARDENING_AFTER_CUTOFF_DOWNGRADE_TO_ACTIVE = false
       (the AS_OF rule never silently rewrites a FINALIZED record to
       ACTIVE; the original committed record_status stays authoritative).
- The I7 four child tables (actual_harvest_label_snapshot / _winner /
  _label / _exclusion) are created without a finalized_at column on
  purpose: the I7 snapshot hash is bound to the winner's lineage node
  hash (which already carries the in-memory finalized_at when present)
  and to the lineage basis member row hash (which now persists
  finalized_at). No additional I7 schema change is required.
- Downgrade order:
  drop I7 child tables (0021) -> drop I7 header (0021) ->
  drop finalized_at column from lineage basis member.
  (alembic will call 0021's downgrade first when running
  ``alembic downgrade 0020``, which is the safe FK-aware order.)

No new immutability trigger is required: finalized_at is a leaf
timestamp column on a non-I7 evidence table that the application
already treats as append-only via the lineage basis creation flow
(actual_harvest_validation_lineage_basis_member rows are inserted
once per validation run and never updated by the production code
path).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_finalized_at_lineage_basis_member"
down_revision = "0021_actual_harvest_label_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    with op.batch_alter_table(
        "actual_harvest_validation_lineage_basis_member",
        recreate="always" if is_sqlite else "auto",
    ) as batch_op:
        if is_sqlite:
            batch_op.add_column(
                sa.Column(
                    "finalized_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                )
            )
        else:
            batch_op.add_column(
                sa.Column(
                    "finalized_at",
                    sa.TIMESTAMP(timezone=True),
                    nullable=True,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    with op.batch_alter_table(
        "actual_harvest_validation_lineage_basis_member",
        recreate="always" if is_sqlite else "auto",
    ) as batch_op:
        batch_op.drop_column("finalized_at")
