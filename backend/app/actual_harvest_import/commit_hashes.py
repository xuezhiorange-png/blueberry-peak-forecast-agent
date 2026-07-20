"""S1 commit manifest hash computation.

Frozen contract (S1 §五):
- The commit_manifest_hash is computed over canonical JSON of:
  - commit_policy_version
  - import_id
  - validation_run_instance_identity_hash
  - 10 evidence hashes (seal / canonical_batch / record_manifest /
    validation_result / mapping_snapshot / resolved_identity_snapshot /
    lineage_graph / committed_lineage_basis / registry_content /
    source_semantics_attestation)
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

- The record_manifest_hash is NOT computed here. It is the single I5
  authority ``validation_hashes.compute_record_manifest_hash`` and is
  reused as-is to guarantee that the commit-time attestation equals
  the validation-time attestation.
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
from backend.app.actual_harvest_import.schemas import (
    CanonicalActualHarvestImportRecord,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

COMMIT_MANIFEST_HASH_POLICY_VERSION = "actual-harvest-commit-manifest-hash-v1"


@dataclass(frozen=True)
class OrderedRevision:
    """Deterministic identity tuple for one committed revision.

    Sorted by (source_system, external_logical_record_id, revision_number,
    external_revision_id) — see S1 §五.

    This type is part of the commit_manifest_hash surface ONLY. It is
    NOT used to re-derive the validation-side record_manifest_hash,
    which is the single authority computed by
    ``validation_hashes.compute_record_manifest_hash`` over canonical
    records.
    """

    ordinal: int
    source_system: str
    external_logical_record_id: str
    external_revision_id: str
    revision_number: int
    record_content_hash: str


def canonical_records_for_commit(
    records: Iterable[ActualHarvestImportRecordModel],
) -> tuple[CanonicalActualHarvestImportRecord, ...]:
    """Convert ORM records into the canonical-record schema.

    Sorted by the I5 record-manifest key
    (source_system, external_logical_record_id, revision_number,
    external_revision_id) and validated against
    :class:`CanonicalActualHarvestImportRecord`.

    The schema deliberately excludes database-generated columns
    (id, batch_id, created_at, ...) so the resulting tuple is
    hash-stable across SQL backends and across re-loads that may
    assign different surrogate ids.

    This is the single bridge between the persisted ORM row and the
    validation-side canonical hash computation. The commit service
    uses it to (a) call the validation-side record_manifest_hash
    authority and (b) build OrderedRevision tuples for the
    commit_manifest_hash surface.
    """
    ordered_models = sorted(
        records,
        key=lambda record: (
            record.source_system,
            record.external_logical_record_id,
            record.revision_number,
            record.external_revision_id,
        ),
    )
    return tuple(
        CanonicalActualHarvestImportRecord.model_validate(
            {
                field_name: getattr(record, field_name)
                for field_name in CanonicalActualHarvestImportRecord.model_fields
            }
        )
        for record in ordered_models
    )


def order_records_for_commit(
    canonical_records: Iterable[CanonicalActualHarvestImportRecord],
) -> tuple[OrderedRevision, ...]:
    """Return a deterministic ordering of canonical records for
    commit-manifest hash.

    Sorting key (per S1 §五):
        (source_system ASC,
         external_logical_record_id ASC,
         revision_number ASC,
         external_revision_id ASC)

    The input MUST be canonical records (i.e. produced by
    :func:`canonical_records_for_commit`) so that the per-record
    content hash is byte-stable across the validation-run attestation
    and the commit-time recomputation.
    """
    return tuple(
        OrderedRevision(
            ordinal=index,
            source_system=record.source_system,
            external_logical_record_id=record.external_logical_record_id,
            external_revision_id=record.external_revision_id,
            revision_number=record.revision_number,
            record_content_hash=compute_canonical_record_hash(record),
        )
        for index, record in enumerate(
            sorted(
                canonical_records,
                key=lambda record: (
                    record.source_system,
                    record.external_logical_record_id,
                    record.revision_number,
                    record.external_revision_id,
                ),
            )
        )
    )


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


def expected_committed_batch_status() -> str:
    return ActualHarvestImportBatchStatus.COMMITTED.value


__all__ = [
    "COMMIT_MANIFEST_HASH_POLICY_VERSION",
    "CanonicalActualHarvestImportRecord",  # re-exported for typing
    "CommitManifestInput",
    "OrderedRevision",
    "canonical_records_for_commit",
    "compute_commit_manifest_hash",
    "expected_committed_batch_status",
    "order_records_for_commit",
]
