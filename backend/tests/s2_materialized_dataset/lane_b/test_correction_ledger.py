from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.s2_materialized_dataset.lane_b.cleaning import build_cleaned_dataset
from backend.app.s2_materialized_dataset.lane_b.correction_ledger import (
    CorrectionLedgerConflictError,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CleaningBuildRequest,
    ManualCorrectionRequest,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import make_source_row_identity_hash

pytestmark = [pytest.mark.unit, pytest.mark.contract]


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
