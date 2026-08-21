from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.app.s2_materialized_dataset.lane_b.cleaning import build_cleaned_dataset
from backend.app.s2_materialized_dataset.lane_b.correction_ledger import (
    CorrectionLedgerConflictError,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import compute_value_digest
from backend.app.s2_materialized_dataset.lane_b.persistence import persist_cleaning_build_result
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CleaningBuildRequest,
    ManualCorrectionRequest,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import make_source_row_identity_hash

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_value_digest_uses_canonical_decimal_encoding() -> None:
    left = compute_value_digest(field_name="actual_harvest_quantity_kg", value=Decimal("12.5"))
    right = compute_value_digest(
        field_name="actual_harvest_quantity_kg", value=Decimal("12.500000")
    )
    assert left == right
    assert left != compute_value_digest(
        field_name="actual_harvest_quantity_kg",
        value=Decimal("12.500001"),
    )


def test_correction_ledger_is_append_only_audit_trail(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    request = cleaning_build_request.model_copy(
        update={
            "manual_corrections": (
                ManualCorrectionRequest(
                    correction_event_id="corr-ledger-1",
                    source_row_identity_hash=source_hash,
                    field_name="actual_harvest_quantity_kg",
                    corrected_value=Decimal("20.000000"),
                    reason="ledgered correction",
                    manual_actor_or_authority_reference="auditor-1",
                ),
            )
        }
    )
    result = build_cleaned_dataset(request)
    entry = result.correction_ledger_entries[0]

    assert entry.correction_event_id == "corr-ledger-1"
    assert entry.original_value_digest != entry.corrected_value_digest
    assert result.cleaned_rows[0].source_actual_harvest_quantity_kg == Decimal("12.500000")


def test_duplicate_correction_event_with_different_digest_fails(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    first = ManualCorrectionRequest(
        correction_event_id="corr-dup",
        source_row_identity_hash=source_hash,
        field_name="actual_harvest_quantity_kg",
        corrected_value=Decimal("18.000000"),
        reason="first reason",
        manual_actor_or_authority_reference="auditor-1",
    )
    second = first.model_copy(update={"corrected_value": Decimal("19.000000")})
    request = cleaning_build_request.model_copy(update={"manual_corrections": (first, second)})

    with pytest.raises(CorrectionLedgerConflictError):
        build_cleaned_dataset(request)


def test_duplicate_correction_event_id_is_deduped_in_memory(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    correction = ManualCorrectionRequest(
        correction_event_id="corr-dedup",
        source_row_identity_hash=source_hash,
        field_name="actual_harvest_quantity_kg",
        corrected_value=Decimal("18.000000"),
        reason="same correction submitted twice",
        manual_actor_or_authority_reference="auditor-1",
    )
    request = cleaning_build_request.model_copy(
        update={"manual_corrections": (correction, correction)}
    )
    result = build_cleaned_dataset(request)

    assert len(result.correction_ledger_entries) == 1
    assert result.correction_ledger_entries[0].correction_event_id == "corr-dedup"


@pytest.mark.migration
def test_lane_b_correction_ledger_rejects_update_and_duplicate_event_id(
    lane_b_migrated_session,
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row,
) -> None:
    source_hash = make_source_row_identity_hash(known_quantity_row)
    request = cleaning_build_request.model_copy(
        update={
            "manual_corrections": (
                ManualCorrectionRequest(
                    correction_event_id="corr-migration-1",
                    source_row_identity_hash=source_hash,
                    field_name="actual_harvest_quantity_kg",
                    corrected_value=Decimal("18.000000"),
                    reason="migration correction",
                    manual_actor_or_authority_reference="auditor-1",
                ),
            )
        }
    )
    result = build_cleaned_dataset(request)
    version_row = persist_cleaning_build_result(lane_b_migrated_session, result)
    lane_b_migrated_session.commit()
    entry_id = lane_b_migrated_session.execute(
        sa.text(
            """
            SELECT id FROM s2_correction_ledger_entry
            WHERE cleaned_dataset_version_id = :version_id
            """
        ),
        {"version_id": version_row.id},
    ).scalar_one()
    with pytest.raises(sa.exc.IntegrityError):
        lane_b_migrated_session.execute(
            sa.text(
                """
                UPDATE s2_correction_ledger_entry
                SET reason = 'mutated'
                WHERE id = :entry_id
                """
            ),
            {"entry_id": entry_id},
        )
        lane_b_migrated_session.commit()
    lane_b_migrated_session.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        lane_b_migrated_session.execute(
            sa.text(
                """
                INSERT INTO s2_correction_ledger_entry (
                    cleaned_dataset_version_id,
                    correction_ledger_entry_identity_hash,
                    source_row_identity_hash,
                    correction_event_id,
                    field_name,
                    correction_policy_version,
                    correction_schema_version,
                    original_value_digest,
                    corrected_value_digest,
                    reason,
                    manual_actor_or_authority_reference
                ) VALUES (
                    :version_id,
                    :identity_hash,
                    :source_hash,
                    'corr-migration-1',
                    'actual_harvest_quantity_kg',
                    'policy',
                    'schema',
                    :original_digest,
                    :corrected_digest,
                    'duplicate event',
                    'auditor-2'
                )
                """
            ),
            {
                "version_id": version_row.id,
                "identity_hash": "c" * 64,
                "source_hash": source_hash,
                "original_digest": "d" * 64,
                "corrected_digest": "e" * 64,
            },
        )
        lane_b_migrated_session.commit()
