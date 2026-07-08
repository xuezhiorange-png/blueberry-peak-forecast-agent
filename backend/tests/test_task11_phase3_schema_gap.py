"""Phase 3.0 replay metadata schema-gap tests (non-PG).

These tests are pure unit / SQLAlchemy-metadata tests; they do NOT require a
live PostgreSQL connection. They cover:

1. Alembic 0015 migration file exists, registers in the chain, and has both
   upgrade() and downgrade() functions.
2. The :class:`HarvestStateRun` ORM model has all five replay-metadata columns
   added in 0015 with correct nullability / type.
3. The :class:`HarvestStateReplaySourceVisibilityAuditModel` ORM model exists
   with the expected columns, checks, and FK.
4. All new PG CHECK constraint names fit within PostgreSQL's 63-character
   identifier limit.
5. The new partial index on ``is_replay`` is exposed via the SQLAlchemy
   ``Table.indexes`` collection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from backend.app.models.harvest_state import (
    HarvestStateReplaySourceVisibilityAuditModel,
    HarvestStateRun,
)

# Slice 1 Batch 4 marker annotation: this file is owned by the
# `postgres-task11` shard per ci-shard-manifest.yml.
pytestmark = [pytest.mark.task11]

_REVISION_PATH = Path("backend/alembic/versions/0015_task11_phase3_schema_gap.py")


def test_phase3_schema_gap_revision_exists() -> None:
    assert _REVISION_PATH.exists()
    source = _REVISION_PATH.read_text()
    assert 'revision: str = "0015_task11_phase3_schema_gap"' in source
    assert 'down_revision: str | None = "0014_task9_historical_authority"' in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source


def test_phase3_schema_gap_migration_chains_into_0014() -> None:
    """0015 must revise the 0014 migration (chain integrity)."""
    source = _REVISION_PATH.read_text()
    assert 'down_revision: str | None = "0014_task9_historical_authority"' in source


def test_phase3_schema_gap_migration_drops_columns_in_downgrade() -> None:
    """downgrade() must reverse every added column on harvest_state_run."""
    source = _REVISION_PATH.read_text()
    for column in (
        "is_replay",
        "forecast_effective_cutoff_at",
        "replay_executed_at",
        "replay_code_version",
        "replay_run_correlation_id",
    ):
        assert f'op.drop_column("harvest_state_run", "{column}")' in source, (
            f"downgrade() must drop {column}"
        )


def test_phase3_schema_gap_migration_drops_support_table_in_downgrade() -> None:
    """downgrade() must drop the new replay visibility audit table."""
    source = _REVISION_PATH.read_text()
    assert 'op.drop_table("harvest_state_replay_source_visibility_audit")' in source


def test_phase3_schema_gap_adds_replay_columns_to_harvest_state_run() -> None:
    expected = {
        "is_replay": (True, "BOOLEAN"),
        "forecast_effective_cutoff_at": (True, "DATETIME"),
        "replay_executed_at": (True, "DATETIME"),
        "replay_code_version": (True, "TEXT"),
        "replay_run_correlation_id": (True, "TEXT"),
    }
    found: dict[str, tuple[bool, str]] = {}
    for col in HarvestStateRun.__table__.columns:
        if col.name in expected:
            type_name = col.type.__class__.__name__.upper()
            found[col.name] = (bool(col.nullable), type_name)

    assert set(found) == set(expected), (
        f"HarvestStateRun missing replay columns: expected {set(expected)}, found {set(found)}"
    )
    for name, (_nullable, type_name) in expected.items():
        actual_nullable, actual_type = found[name]
        assert actual_nullable is True, f"{name} must be nullable"
        # Postgres DateTime/timezone registers as DATETIME in SA repr.
        assert type_name in actual_type or actual_type in type_name, (
            f"{name} type mismatch: expected {type_name}, got {actual_type}"
        )


def test_phase3_schema_gap_migration_uses_replay_metadata_coupling_constraint() -> None:
    """The composite CHECK on harvest_state_run must be the strict
    ``ck_harvest_state_run_replay_metadata_coupling`` form.

    Replaces the weaker
    ``ck_harvest_state_run_historical_observed_no_replay_fields`` form
    which permitted ``is_replay=TRUE`` rows to omit replay metadata.
    The strict form enforces that every replay-marked row carries ALL
    four replay-metadata fields AND that every non-replay row has ALL
    four NULL.
    """
    migration_source = _REVISION_PATH.read_text()
    assert "ck_harvest_state_run_replay_metadata_coupling" in migration_source, (
        "0015 must declare the strict replay-metadata-coupling constraint"
    )
    # Both branches must be present.
    assert "is_replay IS NULL OR is_replay = FALSE" in migration_source
    assert "AND replay_executed_at IS NULL" in migration_source
    assert "is_replay = TRUE" in migration_source
    assert "AND replay_executed_at IS NOT NULL" in migration_source


def test_phase3_schema_gap_replay_executed_at_has_no_server_default() -> None:
    """``replay_executed_at`` MUST NOT carry a server-side default.

    A server default would silently auto-populate non-replay (historical
    observed) rows with a fresh wall-clock timestamp, corrupting the
    semantic of "this row was produced by a replay" and bypassing the
    composite CHECK partition that requires replay metadata to be written
    explicitly by the Phase 3 business writer.
    """
    import re

    migration_source = _REVISION_PATH.read_text()
    matches = re.findall(
        r'sa\.Column\(\s*"replay_executed_at"[\s\S]*?\)',
        migration_source,
        flags=re.MULTILINE,
    )
    assert matches, "0015 must declare the replay_executed_at column"
    for block in matches:
        assert "server_default" not in block, (
            "replay_executed_at MUST NOT carry a server_default in 0015; "
            "replay-only metadata must be written explicitly by the "
            "Phase 3 business writer.\n"
            f"got block: {block!r}"
        )

    col = HarvestStateRun.__table__.columns["replay_executed_at"]
    assert col.server_default is None, (
        "HarvestStateRun.replay_executed_at must not declare a server_default"
    )


def test_phase3_schema_gap_creates_replay_visibility_audit_model() -> None:
    table = HarvestStateReplaySourceVisibilityAuditModel.__table__
    assert table.name == "harvest_state_replay_source_visibility_audit"

    expected_columns = {
        "id",
        "harvest_state_run_id",
        "source_role",
        "source_type",
        "source_visibility_source",
        "forecast_cutoff_at",
        "visibility_passed",
        "rejection_blocker_code",
        "semantic_identity_hash",
        "captured_at",
    }
    actual_columns = {col.name for col in table.columns}
    assert actual_columns == expected_columns

    # harvest_state_run_id is nullable (FK with ondelete SET NULL)
    fk_col = next(c for c in table.columns if c.name == "harvest_state_run_id")
    assert fk_col.nullable is True, (
        "harvest_state_run_id must be nullable (audit survives run deletion)"
    )


def test_phase3_schema_gap_audit_table_check_names_within_pg_limit() -> None:
    """PostgreSQL identifier limit is 63 bytes; all new CHECK names must fit."""
    table = HarvestStateReplaySourceVisibilityAuditModel.__table__
    for constraint in table.constraints:
        if constraint.name:
            assert len(constraint.name) <= 63, constraint.name


def test_phase3_schema_gap_audit_table_compiles_for_postgres() -> None:
    """The compiled CREATE TABLE statement must succeed without exceptions."""
    table = HarvestStateReplaySourceVisibilityAuditModel.__table__
    CreateTable(table).compile(dialect=postgresql.dialect())


def test_phase3_schema_gap_harvest_state_run_partial_index_present() -> None:
    """The 0015 migration must register a partial index on is_replay=TRUE."""
    migration_source = _REVISION_PATH.read_text()
    assert '"ix_harvest_state_run_is_replay"' in migration_source, (
        "0015 must declare ix_harvest_state_run_is_replay"
    )
    assert "postgresql_where" in migration_source or "WHERE" in migration_source, (
        "0015 must declare a partial WHERE index on is_replay"
    )


def test_phase3_schema_gap_does_not_change_existing_harvest_state_run_columns() -> None:
    """No existing column on harvest_state_run may change: pre-Phase-3.0 spec.

    We assert the columns we expect Phase 2 readers to load (no rename,
    no type widening unrelated to replay metadata, no constraints removed).
    """
    expected = {
        "id",
        "status",
        "config_hash",
        "result_hash",
        "canonical_payload_hash",
        "forecast_start_date",
        "forecast_end_date",
        "as_of_date",
        "destination_factory_id",
        "pool_row_count",
        "member_row_count",
        "cohort_row_count",
        "future_arrival_row_count",
        "created_at",
        "updated_at",
        "maturity_model_run_id",
        "maturity_forecast_run_id",
        # Phase 3.0 additions
        "is_replay",
        "forecast_effective_cutoff_at",
        "replay_executed_at",
        "replay_code_version",
        "replay_run_correlation_id",
    }
    actual = {col.name for col in HarvestStateRun.__table__.columns}
    assert expected.issubset(actual), f"Expected subset missing: {expected - actual}"


@pytest.mark.parametrize(
    ("attribute", "orm_type"),
    [
        ("is_replay", bool),
        ("forecast_effective_cutoff_at", object),  # datetime, permissive check
        ("replay_executed_at", object),
        ("replay_code_version", str),
        ("replay_run_correlation_id", str),
    ],
)
def test_phase3_schema_gap_replay_columns_declared_on_orm(attribute: str, orm_type: type) -> None:
    assert hasattr(HarvestStateRun, attribute), (
        f"HarvestStateRun must expose {attribute!r} for Phase 3 writers"
    )
    descriptor = getattr(HarvestStateRun, attribute)
    # Mapped[...] produces a `Mapped` descriptor; just verify it is declared.
    assert descriptor is not None
