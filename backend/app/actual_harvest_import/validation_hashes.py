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
RESOLVED_IDENTITY_HASH_POLICY_VERSION = "actual-harvest-resolved-identity-v1"
ACTUAL_HARVEST_SEASON_RESOLVER_VERSION = "actual-harvest-season-resolver-v1"


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
    *,
    registry_version: str,
    mapping_policy_version: str,
    entries: Iterable[dict[str, Any]],
    season_resolver_version: str = ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
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
            "season_resolver_version": season_resolver_version,
            "entries": ordered,
        }
    )


def compute_request_identity_hash(
    *,
    import_id: str,
    seal_manifest_hash: str,
    mapping_policy_version: str,
    validation_policy_version: str,
    season_resolver_version: str = ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
) -> str:
    return digest(
        {
            "policy_version": VALIDATION_REQUEST_HASH_POLICY_VERSION,
            "import_id": import_id,
            "seal_manifest_hash": seal_manifest_hash,
            "mapping_policy_version": mapping_policy_version,
            "validation_policy_version": validation_policy_version,
            "season_resolver_version": season_resolver_version,
        }
    )


def compute_instance_identity_hash(
    *,
    import_id: str,
    seal_manifest_hash: str,
    mapping_policy_version: str,
    validation_policy_version: str,
    committed_lineage_basis_hash: str,
    season_resolver_version: str = ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
) -> str:
    return digest(
        {
            "policy_version": VALIDATION_INSTANCE_HASH_POLICY_VERSION,
            "import_id": import_id,
            "seal_manifest_hash": seal_manifest_hash,
            "mapping_policy_version": mapping_policy_version,
            "validation_policy_version": validation_policy_version,
            "committed_lineage_basis_hash": committed_lineage_basis_hash,
            "season_resolver_version": season_resolver_version,
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


def compute_resolved_identity_snapshot_hash(
    outcomes: Iterable[dict[str, Any]],
    *,
    season_resolver_version: str = ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
) -> str:
    stable_outcomes = [
        {
            key: item[key]
            for key in (
                "source_system",
                "external_logical_record_id",
                "revision_number",
                "external_revision_id",
                "source_field",
                "source_code",
                "registry_version",
                "mapping_policy_version",
                "registry_entry_hash",
                "target_type",
                "target_business_key",
                "target_parent_business_key",
                "resolved_master_business_key",
                "resolved_master_parent_business_key",
                "resolved_master_record_hash",
                "resolution_mode",
                "resolver_version",
                "outcome",
            )
            if key in item
        }
        for item in outcomes
    ]
    ordered = sorted(
        stable_outcomes,
        key=lambda item: (
            item["source_system"],
            item["external_logical_record_id"],
            item["revision_number"],
            item["external_revision_id"],
            item["source_field"],
        ),
    )
    return digest(
        {
            "policy_version": RESOLVED_IDENTITY_HASH_POLICY_VERSION,
            "season_resolver_version": season_resolver_version,
            "outcomes": ordered,
        }
    )


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


def _lineage_node_hash_payload(node: dict[str, Any]) -> dict[str, Any]:
    """Return the lineage node payload that feeds ``node_hash``.

    The I7 contract excludes ``finalized_at`` from the persisted
    node model. The I7 contract requires that the digest over the
    PERSISTED columns (no ``finalized_at``) be stable, so the
    FINALIZED-time information lives in the basis-member row instead
    (migration 0022) and in ``canonical_record_hash`` (which binds
    it). This helper is also used at ``compute_lineage_node_hash``
    call sites.
    """
    return {key: value for key, value in node.items() if key != "finalized_at"}


def compute_lineage_node_hash(node: dict[str, Any]) -> str:
    return digest(
        {
            "policy_version": LINEAGE_GRAPH_HASH_POLICY_VERSION,
            "node": _lineage_node_hash_payload(node),
        }
    )


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
    record_hashes: Iterable[str | dict[str, Any]],
    mapping_outcomes: Iterable[dict[str, Any]],
    nodes: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
    errors: Iterable[dict[str, Any]],
    warnings: Iterable[dict[str, Any]],
    counts: dict[str, int],
    committed_lineage_basis_hash: str,
    lineage_graph_hash: str,
    resolved_identity_snapshot_hash: str = "0" * 64,
    season_resolver_version: str = ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
) -> str:
    stable_mapping_keys = (
        "source_system",
        "external_logical_record_id",
        "external_revision_id",
        "revision_number",
        "source_field",
        "source_code",
        "target_type",
        "target_business_key",
        "target_parent_business_key",
        "registry_version",
        "mapping_policy_version",
        "registry_entry_hash",
        "resolved_master_business_key",
        "resolved_master_parent_business_key",
        "resolved_master_record_hash",
        "resolution_mode",
        "resolver_version",
        "outcome",
    )
    mapping_outcome_items = [
        {key: item[key] for key in stable_mapping_keys if key in item} for item in mapping_outcomes
    ]
    ordered_record_hashes = []
    for item in record_hashes:
        if isinstance(item, str):
            ordered_record_hashes.append({"canonical_record_hash": item})
        else:
            ordered_record_hashes.append(
                {
                    "source_system": item["source_system"],
                    "external_logical_record_id": item["external_logical_record_id"],
                    "revision_number": item["revision_number"],
                    "external_revision_id": item["external_revision_id"],
                    "canonical_record_hash": item["canonical_record_hash"],
                }
            )
    ordered_record_hashes.sort(
        key=lambda item: (
            item.get("source_system", ""),
            item.get("external_logical_record_id", ""),
            item.get("revision_number", 0),
            item.get("external_revision_id", ""),
        )
    )

    return digest(
        {
            "policy_version": VALIDATION_RESULT_HASH_POLICY_VERSION,
            "seal_manifest_hash": seal_manifest_hash,
            "mapping_snapshot_hash": mapping_snapshot_hash,
            "resolved_identity_snapshot_hash": resolved_identity_snapshot_hash,
            "season_resolver_version": season_resolver_version,
            "mapping_policy_version": mapping_policy_version,
            "validation_policy_version": validation_policy_version,
            "ordered_record_hashes": ordered_record_hashes,
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
    "RESOLVED_IDENTITY_HASH_POLICY_VERSION",
    "ACTUAL_HARVEST_SEASON_RESOLVER_VERSION",
    "compute_committed_lineage_basis_hash",
    "compute_instance_identity_hash",
    "compute_lineage_graph_hash",
    "compute_lineage_node_hash",
    "compute_mapping_entry_hash",
    "compute_mapping_registry_hash",
    "compute_mapping_snapshot_hash",
    "compute_record_manifest_hash",
    "compute_resolved_identity_snapshot_hash",
    "compute_request_identity_hash",
    "compute_validation_result_hash",
    "digest",
]
