from __future__ import annotations

from datetime import UTC, datetime

from backend.app.harvest_state.provenance import (
    build_source_ref_catalog,
    source_ref_hash,
    source_ref_payload,
)
from backend.app.harvest_state.schemas import ParameterSourceRef, Task9ARequest
from backend.tests.harvest_state.conftest import make_request, sha256_hex


def test_source_ref_catalog_blocks_unresolved_reference_hash() -> None:
    ref = ParameterSourceRef.model_validate(
        {
            "source_ref_type": "PARAMETER_SOURCE",
            "source_ref_schema_version": "task9a-source-ref-v1",
            "parameter_code": "DIRECT_NOMINAL_CAPACITY",
            "source_system": "test",
            "source_record_key": "direct-1",
            "source_version": "v1",
            "source_row_hash": sha256_hex({"row": 1}),
            "available_at": "2026-02-28",
            "as_of_date": "2026-02-28",
        }
    )

    _, blockers = build_source_ref_catalog(
        [ref],
        referenced_hashes={source_ref_hash(ref), "0" * 64},
    )

    assert any(item.startswith("UNRESOLVED_SOURCE_REF:") for item in blockers)


def test_source_ref_catalog_blocks_orphan_entry() -> None:
    ref = ParameterSourceRef.model_validate(
        {
            "source_ref_type": "PARAMETER_SOURCE",
            "source_ref_schema_version": "task9a-source-ref-v1",
            "parameter_code": "DIRECT_NOMINAL_CAPACITY",
            "source_system": "test",
            "source_record_key": "direct-1",
            "source_version": "v1",
            "source_row_hash": sha256_hex({"row": 1}),
            "available_at": "2026-02-28",
            "as_of_date": "2026-02-28",
        }
    )

    _, blockers = build_source_ref_catalog([ref], referenced_hashes=set())

    assert any(item.startswith("ORPHAN_SOURCE_REF:") for item in blockers)


def test_task8_datetime_in_catalog_payload_is_canonical_for_persistence() -> None:
    request = Task9ARequest.model_validate(make_request())
    available_at = datetime(2026, 2, 28, 3, 35, tzinfo=UTC)
    ref = request.task8_daily_predictions[0].source_ref.model_copy(
        update={"maturity_daily_prediction_available_at": available_at}
    )

    payload = source_ref_payload(ref)
    assert payload["maturity_daily_prediction_available_at"] == available_at.isoformat()

    catalog, blockers = build_source_ref_catalog(
        [ref],
        referenced_hashes={source_ref_hash(ref)},
    )
    assert blockers == []
    assert catalog[0].source_ref_payload["maturity_daily_prediction_available_at"] == (
        available_at.isoformat()
    )
