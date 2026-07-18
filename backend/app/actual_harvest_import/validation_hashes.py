from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import Any

from backend.app.actual_harvest_import.canonical_hashes import compute_canonical_record_hash
from backend.app.rolling_backtest.canonical import canonical_json_dumps

VALIDATION_REQUEST_HASH_POLICY_VERSION = "actual-harvest-validation-request-v1"
VALIDATION_INSTANCE_HASH_POLICY_VERSION = "actual-harvest-validation-instance-v1"
MAPPING_REGISTRY_HASH_POLICY_VERSION = "actual-harvest-mapping-registry-v1"
MAPPING_SNAPSHOT_HASH_POLICY_VERSION = "actual-harvest-mapping-snapshot-v1"
COMMITTED_LINEAGE_BASIS_HASH_POLICY_VERSION = "actual-harvest-committed-lineage-basis-v1"
LINEAGE_GRAPH_HASH_POLICY_VERSION = "actual-harvest-lineage-graph-v1"
VALIDATION_RESULT_HASH_POLICY_VERSION = "actual-harvest-validation-result-v1"


def digest(value: object) -> str:
    return sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def compute_mapping_entry_hash(entry: dict[str, Any]) -> str:
    return digest({"policy_version": MAPPING_REGISTRY_HASH_POLICY_VERSION, "entry": entry})


def compute_mapping_registry_hash(entries: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(
        entries,
        key=lambda item: (item["source_field"], item["source_code"], item["target_type"]),
    )
    return digest({"policy_version": MAPPING_REGISTRY_HASH_POLICY_VERSION, "entries": ordered})


def compute_mapping_snapshot_hash(
    *, registry_version: str, mapping_policy_version: str, entries: Iterable[dict[str, Any]]
) -> str:
    ordered = sorted(
        entries,
        key=lambda item: (item["source_field"], item["source_code"], item["target_type"]),
    )
    return digest(
        {
            "policy_version": MAPPING_SNAPSHOT_HASH_POLICY_VERSION,
            "registry_version": registry_version,
            "mapping_policy_version": mapping_policy_version,
            "entries": ordered,
        }
    )


def compute_request_identity_hash(
    *,
    import_id: str,
    seal_manifest_hash: str,
    mapping_policy_version: str,
    validation_policy_version: str,
) -> str:
    return digest(
        {
            "policy_version": VALIDATION_REQUEST_HASH_POLICY_VERSION,
            "import_id": import_id,
            "seal_manifest_hash": seal_manifest_hash,
            "mapping_policy_version": mapping_policy_version,
            "validation_policy_version": validation_policy_version,
        }
    )


def compute_instance_identity_hash(
    *,
    import_id: str,
    seal_manifest_hash: str,
    mapping_policy_version: str,
    validation_policy_version: str,
    committed_lineage_basis_hash: str,
) -> str:
    return digest(
        {
            "policy_version": VALIDATION_INSTANCE_HASH_POLICY_VERSION,
            "import_id": import_id,
            "seal_manifest_hash": seal_manifest_hash,
            "mapping_policy_version": mapping_policy_version,
            "validation_policy_version": validation_policy_version,
            "committed_lineage_basis_hash": committed_lineage_basis_hash,
        }
    )


def compute_record_manifest_hash(records: Iterable[Any]) -> str:
    ordered = sorted(
        records,
        key=lambda record: (
            record.source_system,
            record.external_logical_record_id,
            record.revision_number,
            record.external_revision_id,
        ),
    )
    return digest({"records": [compute_canonical_record_hash(record) for record in ordered]})


def compute_committed_lineage_basis_hash(members: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(
        members,
        key=lambda item: (
            item["source_system"],
            item["external_logical_record_id"],
            item["revision_number"],
            item["external_revision_id"],
            item["committed_batch_ref"],
        ),
    )
    return digest(
        {
            "policy_version": COMMITTED_LINEAGE_BASIS_HASH_POLICY_VERSION,
            "members": ordered,
        }
    )


def compute_lineage_node_hash(node: dict[str, Any]) -> str:
    return digest({"policy_version": LINEAGE_GRAPH_HASH_POLICY_VERSION, "node": node})


def compute_lineage_graph_hash(
    nodes: Iterable[dict[str, Any]], edges: Iterable[dict[str, Any]]
) -> str:
    ordered_nodes = sorted(
        nodes,
        key=lambda item: (
            item["source_system"],
            item["external_logical_record_id"],
            item["revision_number"],
            item["external_revision_id"],
            item["origin"],
        ),
    )
    ordered_edges = sorted(
        edges,
        key=lambda item: (
            item["source_system"],
            item["predecessor_revision_id"],
            item["successor_revision_id"],
            item["edge_type"],
        ),
    )
    return digest(
        {
            "policy_version": LINEAGE_GRAPH_HASH_POLICY_VERSION,
            "nodes": ordered_nodes,
            "edges": ordered_edges,
        }
    )


def compute_validation_result_hash(
    *,
    seal_manifest_hash: str,
    mapping_snapshot_hash: str,
    mapping_policy_version: str,
    validation_policy_version: str,
    record_hashes: Iterable[str],
    mapping_outcomes: Iterable[dict[str, Any]],
    nodes: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
    errors: Iterable[dict[str, Any]],
    warnings: Iterable[dict[str, Any]],
    counts: dict[str, int],
    committed_lineage_basis_hash: str,
    lineage_graph_hash: str,
) -> str:
    mapping_outcome_items: list[dict[str, Any]] = list(mapping_outcomes)

    return digest(
        {
            "policy_version": VALIDATION_RESULT_HASH_POLICY_VERSION,
            "seal_manifest_hash": seal_manifest_hash,
            "mapping_snapshot_hash": mapping_snapshot_hash,
            "mapping_policy_version": mapping_policy_version,
            "validation_policy_version": validation_policy_version,
            "record_hashes": sorted(record_hashes),
            "mapping_outcomes": sorted(
                mapping_outcome_items,
                key=lambda item: canonical_json_dumps(item),
            ),
            "lineage_nodes": sorted(nodes, key=lambda item: canonical_json_dumps(item)),
            "lineage_edges": sorted(edges, key=lambda item: canonical_json_dumps(item)),
            "errors": sorted(errors, key=lambda item: canonical_json_dumps(item)),
            "warnings": sorted(warnings, key=lambda item: canonical_json_dumps(item)),
            "counts": counts,
            "committed_lineage_basis_hash": committed_lineage_basis_hash,
            "lineage_graph_hash": lineage_graph_hash,
        }
    )


__all__ = [
    "COMMITTED_LINEAGE_BASIS_HASH_POLICY_VERSION",
    "LINEAGE_GRAPH_HASH_POLICY_VERSION",
    "MAPPING_REGISTRY_HASH_POLICY_VERSION",
    "MAPPING_SNAPSHOT_HASH_POLICY_VERSION",
    "VALIDATION_INSTANCE_HASH_POLICY_VERSION",
    "VALIDATION_REQUEST_HASH_POLICY_VERSION",
    "VALIDATION_RESULT_HASH_POLICY_VERSION",
    "compute_committed_lineage_basis_hash",
    "compute_instance_identity_hash",
    "compute_lineage_graph_hash",
    "compute_lineage_node_hash",
    "compute_mapping_entry_hash",
    "compute_mapping_registry_hash",
    "compute_mapping_snapshot_hash",
    "compute_record_manifest_hash",
    "compute_request_identity_hash",
    "compute_validation_result_hash",
    "digest",
]
