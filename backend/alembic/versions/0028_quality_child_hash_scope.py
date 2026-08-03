"""Scope Quality child canonical hashes to their owning evaluation run."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_quality_child_hash_scope"
down_revision = "0027_s5_a2_forecast_evidence_persistence"
branch_labels = None
depends_on = None

_CONSTRAINTS = (
    (
        "quality_metric_result",
        "uq_quality_metric_result_canonical_hash",
        "uq_quality_metric_result_run_canonical_hash",
    ),
    (
        "quality_breakdown_result",
        "uq_quality_breakdown_result_canonical_hash",
        "uq_quality_breakdown_result_run_canonical_hash",
    ),
)


def _cross_run_duplicate_exists(table_name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            f"""
            SELECT canonical_hash
            FROM {table_name}
            GROUP BY canonical_hash
            HAVING COUNT(DISTINCT quality_evaluation_run_id) > 1
            LIMIT 1
            """
        )
    ).first()
    return row is not None


def upgrade() -> None:
    for table_name, old_name, new_name in _CONSTRAINTS:
        op.drop_constraint(old_name, table_name, type_="unique")
        op.create_unique_constraint(
            new_name,
            table_name,
            ["quality_evaluation_run_id", "canonical_hash"],
        )


def downgrade() -> None:
    # Both preconditions are checked before any DDL so a blocked downgrade
    # leaves constraints and data untouched.
    duplicate_tables = [
        table_name for table_name, _, _ in _CONSTRAINTS if _cross_run_duplicate_exists(table_name)
    ]
    if duplicate_tables:
        raise RuntimeError(
            "QUALITY_CHILD_HASH_SCOPE_DOWNGRADE_BLOCKED: cross-run canonical hash duplicates exist"
        )

    for table_name, old_name, new_name in _CONSTRAINTS:
        op.drop_constraint(new_name, table_name, type_="unique")
        op.create_unique_constraint(old_name, table_name, ["canonical_hash"])
