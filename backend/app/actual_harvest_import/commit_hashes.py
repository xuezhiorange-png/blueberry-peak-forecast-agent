"""S1 commit manifest hash computation.

Frozen contract (S1 §五):
- The commit_manifest_hash is computed over canonical JSON of:
  - commit_policy_version
  - import_id
  - validation_run_instance_identity_hash
  - 9 evidence hashes (seal / canonical_batch / record_manifest /
    validation_result / mapping_snapshot / resolved_identity_snapshot /
    lineage_graph / committed_lineage_basis / registry_content /
    source_semantics_attestation) — actually 10 hashes total
  - committed_record_count
  - ordered_revisions: list of dicts, each with
    ordinal, source_system, external_logical_record_id, external_revision_id,
    revision_number, record_content_hash

  The hash surface EXPLICITLY EXCLUDES:
  - database-generated ids
  - committed_at
  - committed_by_identity
  - host / process / transaction / filesystem / insertion order

- Sorted ordering: source_system, external_logical_record_id, revision_number,
  external_revision_id (matches I5's ordered_records()).

- Each record's record_content_hash comes from
  compute_canonical_record_hash() (reused from I5).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from backend.app.actual_harvest_import.canonical_hashes import (
    compute_canonical_record_hash,
)
from backend.app.actual_harvest_import.commit_models import COMMIT_POLICY_VERSION
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
)
from backend.app.actual_harvest_import.models import ActualHarvestImportRecordModel
from backend.app.rolling_backtest.canonical import canonical_json_dumps

COMMIT_MANIFEST_HASH_POLICY_VERSION = "actual-harvest-commit-manifest-hash-v1"
RECORD_MANIFEST_HASH_POLICY_VERSION = "actual-harvest-record-manifest-hash-v1"


@dataclass(frozen=True)
class OrderedRevision:
    """Deterministic identity tuple for one committed revision.

    Sorted by (source_system, external_logical_record_id, revision_number,
    external_revision_id) — see S1 §五.
    """

    ordinal: int
    source_system: str
    external_logical_record_id: str
    external_revision_id: str
    revision_number: int
    record_content_hash: str


def order_records_for_commit(
    records: Iterable[ActualHarvestImportRecordModel],
) -> tuple[OrderedRevision, ...]:
    """Return a deterministic ordering of records for commit-manifest hash.

    Sorting key (per S1 §五):
        (source_system ASC,
         external_logical_record_id ASC,
         revision_number ASC,
         external_revision_id ASC)
    """
    return tuple(
        OrderedRevision(
            ordinal=index,
            source_system=record.source_system,
            external_logical_record_id=record.external_logical_record_id,
            external_revision_id=record.external_revision_id,
            revision_number=record.revision_number,
            record_content_hash=compute_canonical_record_hash(_record_to_canonical(record)),
        )
        for index, record in enumerate(
            sorted(
                records,
                key=lambda record: (
                    record.source_system,
                    record.external_logical_record_id,
                    record.revision_number,
                    record.external_revision_id,
                ),
            )
        )
    )


def _record_to_canonical(
    record: ActualHarvestImportRecordModel,
) -> Any:
    """Build a minimal canonical record for compute_canonical_record_hash.

    We pass a plain object (not a pydantic model) with the same field shape
    I5's canonical_record_payload expects, since
    compute_canonical_record_hash accepts anything with .model_dump().
    """
    return _CanonicalRecord(
        external_logical_record_id=record.external_logical_record_id,
        external_revision_id=record.external_revision_id,
        source_system=record.source_system,
        external_batch_id=record.external_batch_id,
        harvest_business_date=record.harvest_business_date,
        farm_code=record.farm_code,
        subfarm_or_plot_code=record.subfarm_or_plot_code,
        variety_code=record.variety_code,
        actual_harvest_quantity_kg=record.actual_harvest_quantity_kg,
        source_recorded_at=record.source_recorded_at,
        source_recorded_at_authority_status=(record.source_recorded_at_authority_status),
        source_recorded_at_authority_reference_or_null=(
            record.source_recorded_at_authority_reference_or_null
        ),
        import_received_at=record.import_received_at,
        ingested_at=record.ingested_at,
        revision_number=record.revision_number,
        record_status=record.record_status,
        supersedes_external_revision_id=(record.supersedes_external_revision_id),
        season_code=record.season_code,
        farm_timezone=record.farm_timezone,
        revised_at=record.revised_at,
        finalized_at=record.finalized_at,
        source_note=record.source_note,
    )


class _CanonicalRecord:
    """Minimal duck-typed pydantic-compatible object for canonical hashing."""

    def __init__(self, **fields: Any) -> None:
        self._fields = fields

    def model_dump(
        self, *, mode: str = "python", exclude: set[str] | None = None
    ) -> dict[str, Any]:
        del mode
        excluded = exclude or set()
        return {key: value for key, value in self._fields.items() if key not in excluded}


@dataclass(frozen=True)
class CommitManifestInput:
    """All non-derivable inputs to compute_commit_manifest_hash.

    The hash MUST be deterministic over these fields and MUST NOT depend on
    committed_at, committed_by_identity, or any database id.
    """

    import_id: str
    validation_run_instance_identity_hash: str
    seal_manifest_hash: str
    canonical_batch_hash: str
    record_manifest_hash: str
    validation_result_hash: str
    mapping_snapshot_hash: str
    resolved_identity_snapshot_hash: str
    lineage_graph_hash: str
    committed_lineage_basis_hash: str
    registry_content_hash: str
    source_semantics_attestation_hash: str
    committed_record_count: int
    ordered_revisions: tuple[OrderedRevision, ...]


def compute_commit_manifest_hash(payload: CommitManifestInput) -> str:
    """Deterministic SHA-256 hex over canonical JSON of the commit inputs.

    Per S1 §五: hash surface EXCLUDES database-generated ids,
    committed_at, committed_by_identity, host, process, transaction,
    filesystem, insertion order.
    """
    body: dict[str, Any] = {
        "policy_version": COMMIT_MANIFEST_HASH_POLICY_VERSION,
        "commit_policy_version": COMMIT_POLICY_VERSION,
        "import_id": payload.import_id,
        "validation_run_instance_identity_hash": (payload.validation_run_instance_identity_hash),
        "seal_manifest_hash": payload.seal_manifest_hash,
        "canonical_batch_hash": payload.canonical_batch_hash,
        "record_manifest_hash": payload.record_manifest_hash,
        "validation_result_hash": payload.validation_result_hash,
        "mapping_snapshot_hash": payload.mapping_snapshot_hash,
        "resolved_identity_snapshot_hash": payload.resolved_identity_snapshot_hash,
        "lineage_graph_hash": payload.lineage_graph_hash,
        "committed_lineage_basis_hash": payload.committed_lineage_basis_hash,
        "registry_content_hash": payload.registry_content_hash,
        "source_semantics_attestation_hash": (payload.source_semantics_attestation_hash),
        "committed_record_count": payload.committed_record_count,
        "ordered_revisions": [
            {
                "ordinal": revision.ordinal,
                "source_system": revision.source_system,
                "external_logical_record_id": (revision.external_logical_record_id),
                "external_revision_id": revision.external_revision_id,
                "revision_number": revision.revision_number,
                "record_content_hash": revision.record_content_hash,
            }
            for revision in payload.ordered_revisions
        ],
    }
    encoded = canonical_json_dumps(body).encode("utf-8")
    return sha256(encoded).hexdigest()


def compute_record_manifest_hash(
    ordered_revisions: tuple[OrderedRevision, ...],
) -> str:
    """Deterministic SHA-256 hex over canonical JSON of the ordered
    revision set.

    The record_manifest_hash is the I5-side hash that the validation
    run stores at validation time. Re-deriving it inside the commit
    service lets us prove that the records the caller is about to
    commit are byte-identical to the records the validation run
    attested to. The hash surface EXCLUDES database-generated ids
    and any insertion / transaction metadata, matching S1 §五.
    """
    body: dict[str, Any] = {
        "policy_version": RECORD_MANIFEST_HASH_POLICY_VERSION,
        "ordered_revisions": [
            {
                "ordinal": revision.ordinal,
                "source_system": revision.source_system,
                "external_logical_record_id": (revision.external_logical_record_id),
                "external_revision_id": revision.external_revision_id,
                "revision_number": revision.revision_number,
                "record_content_hash": revision.record_content_hash,
            }
            for revision in ordered_revisions
        ],
    }
    encoded = canonical_json_dumps(body).encode("utf-8")
    return sha256(encoded).hexdigest()


def expected_committed_batch_status() -> str:
    return ActualHarvestImportBatchStatus.COMMITTED.value


__all__ = [
    "COMMIT_MANIFEST_HASH_POLICY_VERSION",
    "CommitManifestInput",
    "OrderedRevision",
    "RECORD_MANIFEST_HASH_POLICY_VERSION",
    "compute_commit_manifest_hash",
    "compute_record_manifest_hash",
    "expected_committed_batch_status",
    "order_records_for_commit",
]
