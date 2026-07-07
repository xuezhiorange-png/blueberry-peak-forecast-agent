# ruff: noqa: E501
"""Task 11 Phase 3.0 replay metadata schema gap.

Adds five typed, nullable, replay-marking columns to ``harvest_state_run`` and
creates ``harvest_state_replay_source_visibility_audit`` as a one-to-many
append-only audit table for cutoff-visible sources selected at replay time.

This migration is purely additive: every new column is nullable; no existing
row is rewritten. ``replay_executed_at`` deliberately has NO server-side
default — it is replay-only metadata and must be explicitly NULL on
historical_observed rows. A composite CHECK (``replay_metadata_coupling``)
enforces that ``is_replay IS NULL/FALSE`` rows carry no replay metadata and
``is_replay = TRUE`` rows carry ALL four replay metadata fields
(``forecast_effective_cutoff_at``, ``replay_executed_at``,
``replay_code_version``, ``replay_run_correlation_id``).

Historical_observed behavior is unchanged. The migration has a deterministic,
idempotent ``downgrade()``.

Revision ID: 0015_task11_phase3_schema_gap
Revises: 0014_task9_historical_authority
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_task11_phase3_schema_gap"
down_revision: str | None = "0014_task9_historical_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sha256_check_sql(column_name: str) -> str:
    stripped = column_name
    for char in "0123456789abcdef":
        stripped = f"replace({stripped}, '{char}', '')"
    return (
        f"length({column_name}) = 64 and lower({column_name}) = {column_name} and {stripped} = ''"
    )


def upgrade() -> None:
    # ── 1. harvest_state_run: replay discriminator + replay metadata ────────
    # All five columns are NULLABLE for existing rows.
    # NOTE: ``replay_executed_at`` MUST NOT have a server-side default. It is
    # replay-only metadata and must be explicitly NULL on historical_observed
    # rows; a server default would silently auto-populate non-replay rows.
    op.add_column(
        "harvest_state_run",
        sa.Column(
            "is_replay",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "harvest_state_run",
        sa.Column("forecast_effective_cutoff_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "harvest_state_run",
        sa.Column(
            "replay_executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "harvest_state_run",
        sa.Column("replay_code_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "harvest_state_run",
        sa.Column("replay_run_correlation_id", sa.Text(), nullable=True),
    )

    # ── 2. CHECK constraints on harvest_state_run ────────────────────────────
    # Each new column is nullable; the constraint is null-tolerant.
    op.create_check_constraint(
        "ck_harvest_state_run_replay_executed_at",
        "harvest_state_run",
        "replay_executed_at IS NULL OR replay_executed_at <= now() + interval '1 hour'",
    )
    op.create_check_constraint(
        "ck_harvest_state_run_replay_cutoff_past",
        "harvest_state_run",
        "forecast_effective_cutoff_at IS NULL "
        "OR forecast_effective_cutoff_at <= now() + interval '1 hour'",
    )
    op.create_check_constraint(
        "ck_harvest_state_run_replay_code_version_non_blank",
        "harvest_state_run",
        "replay_code_version IS NULL OR btrim(replay_code_version) <> ''",
    )
    op.create_check_constraint(
        "ck_harvest_state_run_replay_correlation_id_non_blank",
        "harvest_state_run",
        "replay_run_correlation_id IS NULL OR btrim(replay_run_correlation_id) <> ''",
    )
    # Composite coupling: ``is_replay`` is the discriminator.
    #
    # Historical_observed rows (``is_replay IS NULL`` / ``FALSE``) are NOT
    # replay rows and must carry NO replay metadata:
    #   - ``forecast_effective_cutoff_at IS NULL``
    #   - ``replay_executed_at IS NULL``
    #   - ``replay_code_version IS NULL``
    #   - ``replay_run_correlation_id IS NULL``
    #
    # Replay rows (``is_replay = TRUE``) MUST carry ALL four replay metadata
    # fields, explicitly written by the Phase 3 business writer:
    #   - ``forecast_effective_cutoff_at IS NOT NULL``
    #   - ``replay_executed_at IS NOT NULL``
    #   - ``replay_code_version IS NOT NULL``
    #   - ``replay_run_correlation_id IS NOT NULL``
    #
    # The two branches are mutually exclusive and exhaustive (via the ``OR``),
    # so any row satisfying neither branch is rejected.
    op.create_check_constraint(
        "ck_harvest_state_run_replay_metadata_coupling",
        "harvest_state_run",
        "((is_replay IS NULL OR is_replay = FALSE) "
        "AND forecast_effective_cutoff_at IS NULL "
        "AND replay_executed_at IS NULL "
        "AND replay_code_version IS NULL "
        "AND replay_run_correlation_id IS NULL) "
        "OR "
        "(is_replay = TRUE "
        "AND forecast_effective_cutoff_at IS NOT NULL "
        "AND replay_executed_at IS NOT NULL "
        "AND replay_code_version IS NOT NULL "
        "AND replay_run_correlation_id IS NOT NULL)",
    )

    # ── 3. Partial index: is_replay rows for fast replay-mode queries ───────
    op.create_index(
        "ix_harvest_state_run_is_replay",
        "harvest_state_run",
        ["is_replay"],
        postgresql_where=sa.text("is_replay = TRUE"),
    )

    # ── 4. harvest_state_replay_source_visibility_audit table ───────────────
    op.create_table(
        "harvest_state_replay_source_visibility_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "harvest_state_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column("source_role", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_visibility_source", sa.Text(), nullable=False),
        sa.Column(
            "forecast_cutoff_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "visibility_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("rejection_blocker_code", sa.Text(), nullable=True),
        sa.Column(
            "semantic_identity_hash",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "btrim(source_role) <> ''",
            name="ck_hsrpsva_role_non_blank",
        ),
        sa.CheckConstraint(
            "btrim(source_type) <> ''",
            name="ck_hsrpsva_type_non_blank",
        ),
        sa.CheckConstraint(
            "btrim(source_visibility_source) <> ''",
            name="ck_hsrpsva_visibility_source_non_blank",
        ),
        sa.CheckConstraint(
            "forecast_cutoff_at <= now() + interval '1 hour'",
            name="ck_hsrpsva_cutoff_past",
        ),
        sa.CheckConstraint(
            "rejection_blocker_code IS NULL OR btrim(rejection_blocker_code) <> ''",
            name="ck_hsrpsva_rejection_code_non_blank",
        ),
        sa.CheckConstraint(
            "semantic_identity_hash IS NULL OR " + _sha256_check_sql("semantic_identity_hash"),
            name="ck_hsrpsva_semantic_identity_hash_sha256",
        ),
        sa.CheckConstraint(
            "(visibility_passed = TRUE AND rejection_blocker_code IS NULL) "
            "OR "
            "(visibility_passed = FALSE AND rejection_blocker_code IS NOT NULL)",
            name="ck_hsrpsva_passed_blocker_coupling",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["harvest_state_run_id"],
            ["harvest_state_run.id"],
            name="fk_hsrpsva_harvest_state_run_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_hsrpsva_harvest_state_run_id",
        "harvest_state_replay_source_visibility_audit",
        ["harvest_state_run_id"],
    )
    op.create_index(
        "ix_hsrpsva_source_role",
        "harvest_state_replay_source_visibility_audit",
        ["source_role"],
    )


def downgrade() -> None:
    # Drop indexes / table first to release dependent objects.
    op.drop_index(
        "ix_hsrpsva_source_role",
        table_name="harvest_state_replay_source_visibility_audit",
    )
    op.drop_index(
        "ix_hsrpsva_harvest_state_run_id",
        table_name="harvest_state_replay_source_visibility_audit",
    )
    op.drop_table("harvest_state_replay_source_visibility_audit")

    op.drop_index(
        "ix_harvest_state_run_is_replay",
        table_name="harvest_state_run",
    )
    op.drop_constraint(
        "ck_harvest_state_run_replay_metadata_coupling",
        "harvest_state_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_harvest_state_run_replay_correlation_id_non_blank",
        "harvest_state_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_harvest_state_run_replay_code_version_non_blank",
        "harvest_state_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_harvest_state_run_replay_cutoff_past",
        "harvest_state_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_harvest_state_run_replay_executed_at",
        "harvest_state_run",
        type_="check",
    )

    op.drop_column("harvest_state_run", "replay_run_correlation_id")
    op.drop_column("harvest_state_run", "replay_code_version")
    op.drop_column("harvest_state_run", "replay_executed_at")
    op.drop_column("harvest_state_run", "forecast_effective_cutoff_at")
    op.drop_column("harvest_state_run", "is_replay")
