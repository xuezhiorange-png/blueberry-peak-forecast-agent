from __future__ import annotations

from backend.app.harvest_state.provenance import build_source_ref_catalog, source_ref_hash
from backend.app.harvest_state.schemas import ParameterSourceRef


def test_source_ref_catalog_blocks_unresolved_reference_hash() -> None:
    ref = ParameterSourceRef.model_validate(
        {
            "source_ref_type": "PARAMETER_SOURCE",
            "source_ref_schema_version": "task9a-source-ref-v1",
            "parameter_code": "DIRECT_NOMINAL_CAPACITY",
            "source_system": "test",
            "source_record_key": "direct-1",
            "source_version": "v1",
            "source_row_hash": "row-hash-1",
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
            "source_row_hash": "row-hash-1",
            "available_at": "2026-02-28",
            "as_of_date": "2026-02-28",
        }
    )

    _, blockers = build_source_ref_catalog([ref], referenced_hashes=set())

    assert any(item.startswith("ORPHAN_SOURCE_REF:") for item in blockers)
