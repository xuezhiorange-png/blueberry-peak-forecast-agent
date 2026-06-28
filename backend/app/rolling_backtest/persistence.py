"""Rolling backtest persistence: typed commands, atomic repository, and integrity loader."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestDagSnapshot,
    RollingBacktestNode,
    RollingBacktestOrchestrationSnapshot,
    RollingBacktestResolvedInput,
    RollingBacktestRun,
    RollingBacktestStageEvent,
)
from backend.app.rolling_backtest.availability import (
    availability_snapshot_audit_hash,
    availability_snapshot_audit_payload,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.rolling_backtest.config import (
    rolling_backtest_config_hash,
    rolling_backtest_config_payload,
)
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestAuthorityBindingError,
    RollingBacktestCanonicalParityError,
    RollingBacktestChildCountMismatchError,
    RollingBacktestCommandMismatchError,
    RollingBacktestDagIntegrityError,
    RollingBacktestIdentityConflictError,
    RollingBacktestIntegrityError,
    RollingBacktestPersistenceError,
    RollingBacktestStageIntegrityError,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilitySnapshot,
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
)
from backend.app.rolling_backtest.signatures import (
    node_signature_hash,
    node_signature_payload,
    run_signature_hash,
)

# ── Typed persistence commands ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResolvedInputPersistenceCommand:
    identity: ResolvedUpstreamSemanticIdentity
    persistent_reference: PersistentUpstreamReference | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityAuditPersistenceCommand:
    source_role: str
    snapshot: AvailabilitySnapshot
    forecast_cutoff_at: datetime
    resolved_identity: ResolvedUpstreamSemanticIdentity | None = None


@dataclass(frozen=True, slots=True)
class DagPersistenceCommand:
    dag_schema_version: str
    dag_policy_version: str
    dag_dict: dict[str, Any]
    expected_node_count: int
    expected_edge_count: int


@dataclass(frozen=True, slots=True)
class RollingNodePersistenceCommand:
    node: RollingNodeDefinition
    resolved_inputs: tuple[ResolvedInputPersistenceCommand, ...] = ()
    availability_audits: tuple[AvailabilityAuditPersistenceCommand, ...] = ()
    dag: DagPersistenceCommand | None = None


@dataclass(frozen=True, slots=True)
class RollingBacktestPersistenceCommand:
    config: RollingBacktestConfig
    nodes: tuple[RollingNodePersistenceCommand, ...]


_CreateOrLoadHook = Callable[[str], Awaitable[None] | None]
_CREATE_OR_LOAD_SYNC_HOOK: _CreateOrLoadHook | None = None
_ATTEMPT_ALLOCATION_SYNC_HOOK: _CreateOrLoadHook | None = None
_PersistenceWriteTestHook = Callable[
    [str, AsyncSession, RollingBacktestNode], Awaitable[None] | None
]
_PERSISTENCE_WRITE_TEST_HOOK: _PersistenceWriteTestHook | None = None

_RESOLVED_IDENTITY_ADAPTER: TypeAdapter[ResolvedUpstreamSemanticIdentity] = TypeAdapter(
    ResolvedUpstreamSemanticIdentity
)
_AVAILABILITY_SNAPSHOT_ADAPTER: TypeAdapter[Any] = TypeAdapter(AvailabilitySnapshot)


async def _run_sync_hook(hook: _CreateOrLoadHook | None, phase: str) -> None:
    if hook is None:
        return
    result = hook(phase)
    if isinstance(result, Awaitable):
        await result


async def _run_persistence_write_test_hook(
    phase: str,
    session: AsyncSession,
    node: RollingBacktestNode,
) -> None:
    if _PERSISTENCE_WRITE_TEST_HOOK is None:
        return
    result = _PERSISTENCE_WRITE_TEST_HOOK(phase, session, node)
    if isinstance(result, Awaitable):
        await result


def _json_value(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(canonical_json_dumps(value)))


def _resolved_input_canonical_payload(
    identity: ResolvedUpstreamSemanticIdentity,
) -> dict[str, object]:
    return _json_value(
        {
            "source_type": identity.source_type,
            "source_role": identity.source_role,
            "role_qualifier": identity.role_qualifier,
            "semantic": identity.semantic.model_dump(mode="python", exclude={"display_label"}),
        }
    )


def _resolved_input_identity_from_payload(
    payload: Mapping[str, Any],
) -> ResolvedUpstreamSemanticIdentity:
    normalized = deepcopy(dict(payload))
    semantic = normalized.get("semantic")
    if isinstance(semantic, dict) and "display_label" not in semantic:
        semantic["display_label"] = "__canonical__"
    return _RESOLVED_IDENTITY_ADAPTER.validate_python(normalized)


def _config_from_canonical_payload(payload: Mapping[str, Any]) -> RollingBacktestConfig:
    normalized = deepcopy(dict(payload))
    raw_nodes = normalized.get("nodes")
    if isinstance(raw_nodes, list):
        for node in raw_nodes:
            if not isinstance(node, dict):
                continue
            identities = node.get("resolved_upstream_semantic_identities")
            if not isinstance(identities, list):
                continue
            for identity in identities:
                if not isinstance(identity, dict):
                    continue
                semantic = identity.get("semantic")
                if isinstance(semantic, dict) and "display_label" not in semantic:
                    semantic["display_label"] = "__canonical__"
    return RollingBacktestConfig.model_validate(normalized)


def _resolved_input_audit_hash(identity: ResolvedUpstreamSemanticIdentity) -> str:
    return sha256_payload(_resolved_input_canonical_payload(identity))


def _dag_canonical_payload(
    *,
    owner_node_signature: str,
    dag: DagPersistenceCommand,
) -> dict[str, object]:
    return _json_value(
        {
            "owner_node_signature": owner_node_signature,
            "dag_schema_version": dag.dag_schema_version,
            "dag_policy_version": dag.dag_policy_version,
            "nodes": dag.dag_dict.get("nodes", []),
            "edges": dag.dag_dict.get("edges", []),
        }
    )


def _assert_no_persistent_reference_fields(value: object, *, path: str = "$") -> None:
    forbidden = {"persistent_reference", "database_id", "uuid", "orm_id"}
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                raise RollingBacktestIntegrityError(
                    f"forbidden persistent identity field at {path}.{key}"
                )
            _assert_no_persistent_reference_fields(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_persistent_reference_fields(child, path=f"{path}[{index}]")


def _validate_dag_payload(
    payload: Mapping[str, Any],
    *,
    owner_node_signature: str,
    dag_schema_version: str,
    dag_policy_version: str,
    expected_node_count: int,
    expected_edge_count: int,
) -> None:
    if payload.get("owner_node_signature") != owner_node_signature:
        raise RollingBacktestDagIntegrityError("DAG owner_node_signature mismatch")
    if payload.get("dag_schema_version") != dag_schema_version:
        raise RollingBacktestDagIntegrityError("DAG schema version mismatch")
    if payload.get("dag_policy_version") != dag_policy_version:
        raise RollingBacktestDagIntegrityError("DAG policy version mismatch")

    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise RollingBacktestDagIntegrityError("DAG payload must contain nodes and edges lists")

    node_names: list[str] = []
    for item in raw_nodes:
        if not isinstance(item, str) or not item:
            raise RollingBacktestDagIntegrityError("DAG node identifiers must be non-empty strings")
        node_names.append(item)
    if len(set(node_names)) != len(node_names):
        raise RollingBacktestDagIntegrityError("DAG contains duplicate node identifiers")

    edge_pairs: list[tuple[str, str]] = []
    for item in raw_edges:
        if not isinstance(item, list | tuple) or len(item) != 2:
            raise RollingBacktestDagIntegrityError("DAG edges must be 2-item lists")
        left, right = item
        if not isinstance(left, str) or not isinstance(right, str):
            raise RollingBacktestDagIntegrityError("DAG edge endpoints must be strings")
        if left == right:
            raise RollingBacktestDagIntegrityError("DAG self-loops are not allowed")
        if left not in node_names or right not in node_names:
            raise RollingBacktestDagIntegrityError("DAG edge endpoint is missing from node set")
        edge_pairs.append((left, right))
    if len(set(edge_pairs)) != len(edge_pairs):
        raise RollingBacktestDagIntegrityError("DAG contains duplicate edges")
    if len(node_names) != expected_node_count:
        raise RollingBacktestChildCountMismatchError(
            f"DAG node count mismatch: expected={expected_node_count} actual={len(node_names)}"
        )
    if len(edge_pairs) != expected_edge_count:
        raise RollingBacktestChildCountMismatchError(
            f"DAG edge count mismatch: expected={expected_edge_count} actual={len(edge_pairs)}"
        )


def validate_persistence_command(command: RollingBacktestPersistenceCommand) -> None:
    config = command.config
    if len(config.nodes) != len(command.nodes):
        raise RollingBacktestCommandMismatchError(
            "command node count does not match config node count"
        )

    for index, (expected_node, node_cmd) in enumerate(
        zip(config.nodes, command.nodes, strict=True)
    ):
        if node_cmd.node != expected_node:
            raise RollingBacktestCommandMismatchError(
                f"command node at index {index} does not match config node"
            )
        if node_cmd.dag is None:
            raise RollingBacktestCommandMismatchError(
                f"node {expected_node.node_key.value} is missing required DAG payload"
            )

        command_resolved_identities = tuple(item.identity for item in node_cmd.resolved_inputs)
        if node_cmd.node.resolved_upstream_semantic_identities != command_resolved_identities:
            raise RollingBacktestCommandMismatchError(
                f"node {expected_node.node_key.value} resolved identities do not match "
                "resolved input commands"
            )

        resolved_by_role = {
            item.identity.source_role: item.identity for item in node_cmd.resolved_inputs
        }
        audit_roles: set[str] = set()

        for audit_cmd in node_cmd.availability_audits:
            if not audit_cmd.source_role or audit_cmd.source_role == "unknown":
                raise RollingBacktestAuthorityBindingError(
                    "availability audit source_role is invalid"
                )
            if audit_cmd.source_role in audit_roles:
                raise RollingBacktestAuthorityBindingError(
                    f"duplicate availability audit source_role '{audit_cmd.source_role}'"
                )
            audit_roles.add(audit_cmd.source_role)

            if audit_cmd.resolved_identity is None:
                raise RollingBacktestAuthorityBindingError(
                    f"availability audit '{audit_cmd.source_role}' is missing resolved identity"
                )

            resolved = resolved_by_role.get(audit_cmd.source_role)
            if resolved is None:
                raise RollingBacktestAuthorityBindingError(
                    f"availability audit '{audit_cmd.source_role}' does not match a resolved input"
                )

            if audit_cmd.resolved_identity != resolved:
                raise RollingBacktestAuthorityBindingError(
                    f"availability audit '{audit_cmd.source_role}' resolved identity mismatch"
                )

            if audit_cmd.snapshot.source_type != resolved.source_type:
                raise RollingBacktestAuthorityBindingError(
                    f"availability audit '{audit_cmd.source_role}' source_type mismatch"
                )


# ── Public API ──────────────────────────────────────────────────────────────


async def create_or_load_logical_run(
    command: RollingBacktestPersistenceCommand,
) -> RollingBacktestRun:
    """Create a new logical run or load an existing one with full integrity check.

    All children (nodes, resolved inputs, audits, DAG snapshots) are created
    in a single atomic transaction. If any child fails, the entire transaction
    is rolled back.
    """
    validate_persistence_command(command)
    config = command.config
    signature = run_signature_hash(config)
    config_payload = rolling_backtest_config_payload(config)
    config_hash_val = rolling_backtest_config_hash(config)
    payload_hash = sha256_payload(canonical_json_dumps(config_payload))

    async with AsyncSessionMaker() as session:
        existing = await _find_run_by_signature(session, signature)
        if existing is not None:
            await _verify_or_conflict(existing, config_hash_val, payload_hash, signature)
            return await load_logical_run_with_integrity(session, existing)

        await _run_sync_hook(_CREATE_OR_LOAD_SYNC_HOOK, "after_lookup")

        try:
            run = RollingBacktestRun(
                run_signature=signature,
                config_hash=config_hash_val,
                execution_mode=config.execution_mode.value,
                rolling_schema_version=config.rolling_schema_version,
                canonical_serialization_version=config.canonical_serialization_version,
                availability_registry_version=config.availability_registry_version,
                node_calendar_version=config.node_calendar_version,
                forecast_horizon_policy_version=config.forecast_horizon_policy_version,
                upstream_selection_policy_version=config.upstream_selection_policy_version,
                metric_policy_version=config.metric_policy_version,
                calendar_phase_policy_version=config.calendar_phase_policy_version,
                cutoff_policy_version=config.cutoff_policy_version,
                cutoff_timezone=config.cutoff_timezone,
                cutoff_local_time=config.cutoff_local_time,
                status="pending",
                expected_node_count=len(command.nodes),
                canonical_payload=_json_value(config_payload),
                canonical_payload_hash=payload_hash,
            )
            session.add(run)
            await session.flush()

            for node_cmd in command.nodes:
                node_def = node_cmd.node
                full_payload = node_signature_payload(config, node_def)
                node_sig = node_signature_hash(config, node_def)
                node_payload_hash = sha256_payload(canonical_json_dumps(full_payload))

                db_node = RollingBacktestNode(
                    rolling_run_id=run.id,
                    season_id=node_def.season_id,
                    node_key=node_def.node_key.value,
                    node_signature=node_sig,
                    as_of_local_date=node_def.as_of_local_date,
                    forecast_cutoff_at=node_def.forecast_cutoff_at,
                    forecast_start_local_date=node_def.forecast_start_local_date,
                    forecast_end_local_date=node_def.forecast_end_local_date,
                    execution_mode=config.execution_mode.value,
                    upstream_selection_mode=node_def.upstream_selection_mode.value,
                    scope=_json_value(node_def.scope),
                    forecast_horizon_policy_version=node_def.forecast_horizon_policy_version,
                    task10_model_policy=_json_value(node_def.task10_model_policy),
                    cutoff_policy_version=config.cutoff_policy_version,
                    timezone=node_def.timezone,
                    canonical_payload=_json_value(full_payload),
                    canonical_payload_hash=node_payload_hash,
                    expected_resolved_input_count=len(node_cmd.resolved_inputs),
                    expected_availability_audit_count=len(node_cmd.availability_audits),
                )
                session.add(db_node)
                await session.flush()

                for ri_cmd in node_cmd.resolved_inputs:
                    ident = ri_cmd.identity
                    db_input = RollingBacktestResolvedInput(
                        rolling_node_id=db_node.id,
                        source_role=ident.source_role,
                        source_type=ident.source_type.value,
                        role_qualifier=ident.role_qualifier,
                        semantic_input_signature=ident.semantic.input_signature,
                        result_hash=ident.semantic.result_hash,
                        canonical_payload_hash=ident.semantic.canonical_payload_hash,
                        schema_version=ident.semantic.schema_version,
                        policy_version=ident.semantic.policy_version,
                        persistent_reference_type=(
                            ri_cmd.persistent_reference.reference_type
                            if ri_cmd.persistent_reference
                            else None
                        ),
                        persistent_reference_value=(
                            str(ri_cmd.persistent_reference.reference_value)
                            if ri_cmd.persistent_reference
                            else None
                        ),
                        canonical_payload=_resolved_input_canonical_payload(ident),
                        audit_hash=_resolved_input_audit_hash(ident),
                    )
                    session.add(db_input)

                from backend.app.rolling_backtest.availability import (
                    evaluate_authority_visibility,
                )

                for audit_cmd in node_cmd.availability_audits:
                    snapshot = audit_cmd.snapshot
                    eval_result = evaluate_authority_visibility(
                        snapshot=snapshot,
                        execution_mode=config.execution_mode,
                        forecast_cutoff_at=audit_cmd.forecast_cutoff_at,
                        as_of_local_date=node_def.as_of_local_date,
                        business_timezone=config.cutoff_timezone,
                    )
                    db_audit = RollingBacktestAvailabilityAudit(
                        rolling_node_id=db_node.id,
                        source_role=audit_cmd.source_role,
                        source_type=snapshot.source_type.value,
                        allowed=eval_result.allowed,
                        blocker_code=eval_result.blocker_code,
                        canonical_payload=_json_value(
                            availability_snapshot_audit_payload(snapshot)
                        ),
                        audit_hash=availability_snapshot_audit_hash(snapshot),
                    )
                    session.add(db_audit)

                await session.flush()
                await _run_persistence_write_test_hook(
                    "after_first_node_children_flush",
                    session,
                    db_node,
                )

                dag_cmd = node_cmd.dag
                if dag_cmd is None:
                    raise RollingBacktestDagIntegrityError(
                        f"node {node_def.node_key.value} is missing required DAG payload"
                    )
                dag_payload = _dag_canonical_payload(
                    owner_node_signature=node_sig,
                    dag=dag_cmd,
                )
                _validate_dag_payload(
                    dag_payload,
                    owner_node_signature=node_sig,
                    dag_schema_version=dag_cmd.dag_schema_version,
                    dag_policy_version=dag_cmd.dag_policy_version,
                    expected_node_count=dag_cmd.expected_node_count,
                    expected_edge_count=dag_cmd.expected_edge_count,
                )
                db_dag = RollingBacktestDagSnapshot(
                    rolling_node_id=db_node.id,
                    dag_schema_version=dag_cmd.dag_schema_version,
                    dag_policy_version=dag_cmd.dag_policy_version,
                    canonical_payload=dag_payload,
                    canonical_payload_hash=sha256_payload(canonical_json_dumps(dag_payload)),
                    expected_node_count=dag_cmd.expected_node_count,
                    expected_edge_count=dag_cmd.expected_edge_count,
                )
                session.add(db_dag)

            await session.commit()
            return await load_logical_run_with_integrity(session, run)
        except SAIntegrityError as exc:
            await session.rollback()
            existing = await _find_run_by_signature(session, signature)
            if existing is not None:
                await _verify_or_conflict(existing, config_hash_val, payload_hash, signature)
                return await load_logical_run_with_integrity(session, existing)
            raise RollingBacktestPersistenceError(
                "logical run persistence failed before aggregate completion"
            ) from exc


async def _find_run_by_signature(
    session: AsyncSession, signature: str
) -> RollingBacktestRun | None:
    result = await session.execute(
        select(RollingBacktestRun).where(RollingBacktestRun.run_signature == signature)
    )
    return result.scalar_one_or_none()


async def _verify_or_conflict(
    run: RollingBacktestRun,
    config_hash_val: str,
    payload_hash: str,
    signature: str,
) -> None:
    if run.config_hash != config_hash_val:
        raise RollingBacktestIdentityConflictError(
            f"config_hash mismatch for run_signature={signature[:16]}...: "
            f"existing={run.config_hash[:16]}... new={config_hash_val[:16]}..."
        )
    if run.canonical_payload_hash != payload_hash:
        raise RollingBacktestIdentityConflictError(
            f"canonical_payload_hash mismatch for run_signature={signature[:16]}..."
        )


# ── Integrity loader ────────────────────────────────────────────────────────


async def load_logical_run_with_integrity(
    session: AsyncSession,
    run: RollingBacktestRun,
) -> RollingBacktestRun:
    """Full integrity verification of a loaded logical run."""

    try:
        config = _config_from_canonical_payload(run.canonical_payload)
    except ValidationError as exc:
        raise RollingBacktestCanonicalParityError(
            "run canonical_payload is not a valid config"
        ) from exc

    expected_run_payload = _json_value(rolling_backtest_config_payload(config))
    expected_payload_hash = sha256_payload(canonical_json_dumps(expected_run_payload))
    expected_config_hash = rolling_backtest_config_hash(config)
    expected_run_signature = run_signature_hash(config)

    if run.canonical_payload != expected_run_payload:
        raise RollingBacktestCanonicalParityError("run canonical payload does not round-trip")
    if run.canonical_payload_hash != expected_payload_hash:
        raise RollingBacktestCanonicalParityError("run canonical_payload_hash mismatch")
    if run.config_hash != expected_config_hash:
        raise RollingBacktestCanonicalParityError("run config_hash mismatch")
    if run.run_signature != expected_run_signature:
        raise RollingBacktestCanonicalParityError("run run_signature mismatch")

    normalized_run_fields = {
        "execution_mode": config.execution_mode.value,
        "rolling_schema_version": config.rolling_schema_version,
        "canonical_serialization_version": config.canonical_serialization_version,
        "availability_registry_version": config.availability_registry_version,
        "node_calendar_version": config.node_calendar_version,
        "forecast_horizon_policy_version": config.forecast_horizon_policy_version,
        "upstream_selection_policy_version": config.upstream_selection_policy_version,
        "metric_policy_version": config.metric_policy_version,
        "calendar_phase_policy_version": config.calendar_phase_policy_version,
        "cutoff_policy_version": config.cutoff_policy_version,
        "cutoff_timezone": config.cutoff_timezone,
        "cutoff_local_time": config.cutoff_local_time,
        "expected_node_count": len(config.nodes),
    }
    for field_name, expected_value in normalized_run_fields.items():
        if getattr(run, field_name) != expected_value:
            raise RollingBacktestCanonicalParityError(
                f"run normalized field mismatch for {field_name}"
            )

    nodes_result = await session.execute(
        select(RollingBacktestNode)
        .where(RollingBacktestNode.rolling_run_id == run.id)
        .order_by(
            RollingBacktestNode.season_id,
            RollingBacktestNode.as_of_local_date,
            RollingBacktestNode.node_key,
        )
    )
    nodes = nodes_result.scalars().all()
    if len(nodes) != run.expected_node_count:
        raise RollingBacktestChildCountMismatchError(
            f"node count mismatch: expected={run.expected_node_count} actual={len(nodes)}"
        )

    actual_nodes_by_key = {(node.season_id, node.node_key): node for node in nodes}
    if len(actual_nodes_by_key) != len(nodes):
        raise RollingBacktestIntegrityError("duplicate node business key detected during reload")

    for expected_node in config.nodes:
        actual_node = actual_nodes_by_key.pop(
            (expected_node.season_id, expected_node.node_key.value), None
        )
        if actual_node is None:
            raise RollingBacktestChildCountMismatchError(
                "missing node for "
                f"season={expected_node.season_id} "
                f"key={expected_node.node_key.value}"
            )
        await _verify_node_with_integrity(session, config, expected_node, actual_node)

    if actual_nodes_by_key:
        raise RollingBacktestChildCountMismatchError("unexpected extra node rows detected")

    await _verify_attempt_chain(session, run.id)
    return run


async def _verify_node_with_integrity(
    session: AsyncSession,
    config: RollingBacktestConfig,
    expected_node: RollingNodeDefinition,
    node: RollingBacktestNode,
) -> None:
    expected_payload = _json_value(node_signature_payload(config, expected_node))
    expected_hash = sha256_payload(canonical_json_dumps(expected_payload))
    expected_signature = node_signature_hash(config, expected_node)

    normalized_node_fields = {
        "season_id": expected_node.season_id,
        "node_key": expected_node.node_key.value,
        "as_of_local_date": expected_node.as_of_local_date,
        "forecast_cutoff_at": expected_node.forecast_cutoff_at,
        "forecast_start_local_date": expected_node.forecast_start_local_date,
        "forecast_end_local_date": expected_node.forecast_end_local_date,
        "execution_mode": config.execution_mode.value,
        "upstream_selection_mode": expected_node.upstream_selection_mode.value,
        "scope": _json_value(expected_node.scope),
        "forecast_horizon_policy_version": expected_node.forecast_horizon_policy_version,
        "task10_model_policy": _json_value(expected_node.task10_model_policy),
        "cutoff_policy_version": config.cutoff_policy_version,
        "timezone": expected_node.timezone,
        "expected_resolved_input_count": len(expected_node.resolved_upstream_semantic_identities),
    }
    for field_name, expected_value in normalized_node_fields.items():
        if getattr(node, field_name) != expected_value:
            raise RollingBacktestCanonicalParityError(
                f"node normalized field mismatch for {field_name}"
            )

    if node.canonical_payload != expected_payload:
        raise RollingBacktestCanonicalParityError("node canonical payload mismatch")
    if node.canonical_payload_hash != expected_hash:
        raise RollingBacktestCanonicalParityError("node canonical_payload_hash mismatch")
    if node.node_signature != expected_signature:
        raise RollingBacktestCanonicalParityError("node_signature mismatch")

    resolved_result = await session.execute(
        select(RollingBacktestResolvedInput)
        .where(RollingBacktestResolvedInput.rolling_node_id == node.id)
        .order_by(RollingBacktestResolvedInput.source_role)
    )
    resolved_rows = resolved_result.scalars().all()
    if len(resolved_rows) != node.expected_resolved_input_count:
        raise RollingBacktestChildCountMismatchError(
            "resolved_input count mismatch for "
            f"node {node.id}: expected={node.expected_resolved_input_count} "
            f"actual={len(resolved_rows)}"
        )

    expected_resolved = {
        item.source_role: item for item in expected_node.resolved_upstream_semantic_identities
    }
    resolved_rows_by_role: dict[str, ResolvedUpstreamSemanticIdentity] = {}
    for row in resolved_rows:
        _assert_no_persistent_reference_fields(row.canonical_payload)
        try:
            reconstructed = _resolved_input_identity_from_payload(row.canonical_payload)
        except ValidationError as exc:
            raise RollingBacktestCanonicalParityError("resolved input payload is invalid") from exc
        expected_identity = expected_resolved.get(row.source_role)
        if expected_identity is None:
            raise RollingBacktestIntegrityError(
                f"unexpected resolved input role '{row.source_role}' for node {node.id}"
            )
        if _resolved_input_canonical_payload(reconstructed) != _resolved_input_canonical_payload(
            expected_identity
        ):
            raise RollingBacktestCanonicalParityError(
                f"resolved input semantic mismatch for role '{row.source_role}'"
            )
        if row.source_type != reconstructed.source_type.value:
            raise RollingBacktestCanonicalParityError("resolved input source_type mismatch")
        if row.role_qualifier != reconstructed.role_qualifier:
            raise RollingBacktestCanonicalParityError("resolved input role_qualifier mismatch")
        if row.semantic_input_signature != reconstructed.semantic.input_signature:
            raise RollingBacktestCanonicalParityError(
                "resolved input semantic_input_signature mismatch"
            )
        if row.result_hash != reconstructed.semantic.result_hash:
            raise RollingBacktestCanonicalParityError("resolved input result_hash mismatch")
        if row.canonical_payload_hash != reconstructed.semantic.canonical_payload_hash:
            raise RollingBacktestCanonicalParityError(
                "resolved input canonical_payload_hash mismatch"
            )
        if row.schema_version != reconstructed.semantic.schema_version:
            raise RollingBacktestCanonicalParityError("resolved input schema_version mismatch")
        if row.policy_version != reconstructed.semantic.policy_version:
            raise RollingBacktestCanonicalParityError("resolved input policy_version mismatch")
        if row.canonical_payload != _resolved_input_canonical_payload(reconstructed):
            raise RollingBacktestCanonicalParityError("resolved input canonical payload mismatch")
        if row.audit_hash != _resolved_input_audit_hash(reconstructed):
            raise RollingBacktestCanonicalParityError("resolved input audit hash mismatch")
        resolved_rows_by_role[row.source_role] = reconstructed

    audit_result = await session.execute(
        select(RollingBacktestAvailabilityAudit)
        .where(RollingBacktestAvailabilityAudit.rolling_node_id == node.id)
        .order_by(RollingBacktestAvailabilityAudit.source_role)
    )
    audits = audit_result.scalars().all()
    if len(audits) != node.expected_availability_audit_count:
        raise RollingBacktestChildCountMismatchError(
            "availability_audit count mismatch for "
            f"node {node.id}: expected={node.expected_availability_audit_count} "
            f"actual={len(audits)}"
        )

    from backend.app.rolling_backtest.availability import evaluate_authority_visibility

    for audit in audits:
        if audit.source_role not in resolved_rows_by_role:
            raise RollingBacktestAuthorityBindingError(
                f"availability audit '{audit.source_role}' is missing matching resolved input"
            )
        _assert_no_persistent_reference_fields(audit.canonical_payload)
        try:
            snapshot = _AVAILABILITY_SNAPSHOT_ADAPTER.validate_python(audit.canonical_payload)
        except ValidationError as exc:
            raise RollingBacktestCanonicalParityError(
                "availability audit payload is invalid"
            ) from exc
        if snapshot.source_type.value != audit.source_type:
            raise RollingBacktestAuthorityBindingError(
                f"availability audit '{audit.source_role}' source_type mismatch"
            )
        matching_input = resolved_rows_by_role[audit.source_role]
        if matching_input.source_type != snapshot.source_type:
            raise RollingBacktestAuthorityBindingError(
                f"availability audit '{audit.source_role}' does not bind to matching resolved input"
            )
        expected_audit_payload = _json_value(availability_snapshot_audit_payload(snapshot))
        if audit.canonical_payload != expected_audit_payload:
            raise RollingBacktestCanonicalParityError("availability audit payload mismatch")
        if audit.audit_hash != availability_snapshot_audit_hash(snapshot):
            raise RollingBacktestCanonicalParityError("availability audit hash mismatch")
        eval_result = evaluate_authority_visibility(
            snapshot=snapshot,
            execution_mode=config.execution_mode,
            forecast_cutoff_at=expected_node.forecast_cutoff_at,
            as_of_local_date=expected_node.as_of_local_date,
            business_timezone=config.cutoff_timezone,
        )
        if audit.allowed != eval_result.allowed or audit.blocker_code != eval_result.blocker_code:
            raise RollingBacktestCanonicalParityError(
                f"availability audit '{audit.source_role}' evaluation mismatch"
            )

    dag_result = await session.execute(
        select(RollingBacktestDagSnapshot).where(
            RollingBacktestDagSnapshot.rolling_node_id == node.id
        )
    )
    dags = dag_result.scalars().all()
    if len(dags) != 1:
        raise RollingBacktestDagIntegrityError(
            f"node {node.id} has {len(dags)} DAG snapshots, expected exactly one"
        )
    dag = dags[0]
    _validate_dag_payload(
        dag.canonical_payload,
        owner_node_signature=node.node_signature,
        dag_schema_version=dag.dag_schema_version,
        dag_policy_version=dag.dag_policy_version,
        expected_node_count=dag.expected_node_count,
        expected_edge_count=dag.expected_edge_count,
    )
    if dag.canonical_payload_hash != sha256_payload(canonical_json_dumps(dag.canonical_payload)):
        raise RollingBacktestCanonicalParityError("DAG canonical_payload_hash mismatch")


async def _verify_attempt_chain(session: AsyncSession, run_id: int) -> None:
    result = await session.execute(
        select(RollingBacktestAttempt)
        .where(RollingBacktestAttempt.rolling_run_id == run_id)
        .order_by(RollingBacktestAttempt.rolling_node_id, RollingBacktestAttempt.attempt_number)
    )
    attempts = result.scalars().all()
    if not attempts:
        return

    attempts_by_id = {attempt.id: attempt for attempt in attempts}
    attempts_by_node: dict[int, list[RollingBacktestAttempt]] = {}
    for attempt in attempts:
        if attempt.rolling_run_id != run_id:
            raise RollingBacktestAttemptConflictError(
                f"attempt {attempt.id} belongs to wrong run {attempt.rolling_run_id}"
            )
        if attempt.rolling_node_id is None:
            raise RollingBacktestAttemptConflictError(
                f"attempt {attempt.id} is missing required rolling_node_id"
            )
        attempts_by_node.setdefault(attempt.rolling_node_id, []).append(attempt)

    for node_id, node_attempts in attempts_by_node.items():
        for index, attempt in enumerate(node_attempts, start=1):
            if attempt.attempt_number != index:
                raise RollingBacktestAttemptConflictError(
                    "attempt numbering gap at "
                    f"run {run_id} node {node_id}: expected {index} "
                    f"found {attempt.attempt_number}"
                )
            if attempt.rolling_node_id != node_id:
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} belongs to wrong node {attempt.rolling_node_id}"
                )
            if (attempt.status in ("pending", "running")) != (attempt.finished_at is None):
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} status/finished_at mismatch"
                )

            snapshot_terminal_stage = await validate_orchestration_snapshot_consistency(
                session, attempt.id
            )
            expected_terminal_stage = snapshot_terminal_stage
            if expected_terminal_stage is None and attempt.current_stage in _STAGE_ORDINAL:
                expected_terminal_stage = attempt.current_stage
            await validate_stage_continuity(
                session,
                attempt.id,
                terminal_stage=expected_terminal_stage,
            )

            if index == 1:
                if attempt.prior_attempt_id is not None:
                    raise RollingBacktestAttemptConflictError(
                        f"attempt {attempt.id} is first in node chain but has prior_attempt_id"
                    )
                continue

            previous = node_attempts[index - 2]
            if attempt.prior_attempt_id != previous.id:
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} does not point to direct predecessor {previous.id}"
                )
            prior = attempts_by_id.get(attempt.prior_attempt_id)
            if prior is None:
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} prior attempt {attempt.prior_attempt_id} not found"
                )
            if prior.rolling_node_id != attempt.rolling_node_id:
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} prior attempt crosses node boundary"
                )
            if prior.rolling_run_id != attempt.rolling_run_id:
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} prior attempt crosses run boundary"
                )
            if previous.status not in ("failed", "blocked"):
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} cannot retry from previous status {previous.status}"
                )


# ── Attempt management ──────────────────────────────────────────────────────


async def create_execution_attempt(
    run_id: int,
    node_id: int,
    *,
    status: str = "pending",
    current_stage: str = "initialized",
    prior_attempt_id: int | None = None,
) -> RollingBacktestAttempt:
    """Create a new execution attempt with per-node attempt_number.

    Uses SELECT ... FOR UPDATE on rolling_backtest_node to serialize
    concurrent attempt creation for the same node. Different nodes
    can create attempts in parallel.

    Repository gate: validates that rolling_run_id on the attempt
    equals the node's rolling_run_id at insert time.
    """
    async with AsyncSessionMaker() as session:
        # Lock the node row to serialize attempt creation for this node
        node_result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.id == node_id).with_for_update()
        )
        node_row = node_result.scalar_one_or_none()
        if node_row is None:
            raise RollingBacktestIntegrityError(f"node {node_id} not found")

        # Repository gate: ensure run_id matches node's run_id
        if node_row.rolling_run_id != run_id:
            raise RollingBacktestAuthorityBindingError(
                f"attempt run_id {run_id} does not match node {node_id} "
                f"run_id {node_row.rolling_run_id}"
            )

        await _run_sync_hook(_ATTEMPT_ALLOCATION_SYNC_HOOK, "after_node_lock")

        # Query existing attempts for THIS NODE only
        existing_attempts = await session.execute(
            select(RollingBacktestAttempt)
            .where(RollingBacktestAttempt.rolling_node_id == node_id)
            .order_by(RollingBacktestAttempt.attempt_number)
        )
        attempts = existing_attempts.scalars().all()

        for index, attempt in enumerate(attempts, start=1):
            if attempt.attempt_number != index:
                raise RollingBacktestAttemptConflictError(
                    f"attempt chain has gap: expected {index} found {attempt.attempt_number}"
                )
            if index == 1 and attempt.prior_attempt_id is not None:
                raise RollingBacktestAttemptConflictError(
                    "attempt 1 must not point to a prior attempt"
                )
            if index > 1 and attempt.prior_attempt_id != attempts[index - 2].id:
                raise RollingBacktestAttemptConflictError(
                    f"attempt {attempt.id} does not point to direct predecessor"
                )
            if attempt.prior_attempt_id is not None:
                prior_in_chain = await session.get(RollingBacktestAttempt, attempt.prior_attempt_id)
                if prior_in_chain is None or prior_in_chain.rolling_node_id != node_id:
                    raise RollingBacktestAttemptConflictError(
                        f"attempt {attempt.id} prior link crosses node boundary"
                    )
                if prior_in_chain.rolling_run_id != run_id:
                    raise RollingBacktestAttemptConflictError(
                        f"attempt {attempt.id} prior link crosses run boundary"
                    )

        next_number = len(attempts) + 1
        resolved_prior_id = prior_attempt_id
        if attempts:
            previous = attempts[-1]
            if previous.status not in ("failed", "blocked"):
                raise RollingBacktestAttemptConflictError(
                    f"cannot create retry after previous status {previous.status}"
                )
            if resolved_prior_id is None:
                resolved_prior_id = previous.id
            elif resolved_prior_id != previous.id:
                raise RollingBacktestAttemptConflictError(
                    f"prior_attempt must be direct predecessor {previous.id}"
                )
        elif resolved_prior_id is not None:
            raise RollingBacktestAttemptConflictError("attempt 1 must not provide prior_attempt_id")

        finished_at_val = None
        if status not in ("pending", "running"):
            finished_at_val = datetime.now(UTC)

        attempt = RollingBacktestAttempt(
            rolling_run_id=run_id,
            rolling_node_id=node_id,
            attempt_number=next_number,
            prior_attempt_id=resolved_prior_id,
            status=status,
            current_stage=current_stage,
            started_at=datetime.now(UTC),
            finished_at=finished_at_val,
        )
        session.add(attempt)
        try:
            await session.commit()
        except SAIntegrityError as exc:
            await session.rollback()
            raise RollingBacktestAttemptConflictError(
                f"attempt_number {next_number} already exists for node {node_id}"
            ) from exc
        return attempt


async def _finalize_attempt_status_in_session(
    session: AsyncSession,
    attempt_id: int,
    *,
    status: str,
    current_stage: str,
    structured_error_code: str | None = None,
    sanitized_diagnostics: dict[str, object] | None = None,
) -> RollingBacktestAttempt:
    result = await session.execute(
        select(RollingBacktestAttempt).where(RollingBacktestAttempt.id == attempt_id)
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise RollingBacktestAttemptConflictError(f"attempt {attempt_id} not found")
    if attempt.status == "completed":
        raise RollingBacktestAttemptConflictError(f"cannot modify completed attempt {attempt_id}")

    attempt.status = status
    attempt.current_stage = current_stage
    attempt.structured_error_code = structured_error_code
    attempt.sanitized_diagnostics = sanitized_diagnostics
    attempt.finished_at = None if status in ("pending", "running") else datetime.now(UTC)
    await session.flush()
    return attempt


async def finalize_attempt_status(
    attempt_id: int,
    *,
    status: str,
    current_stage: str,
    structured_error_code: str | None = None,
    sanitized_diagnostics: dict[str, object] | None = None,
    session: AsyncSession | None = None,
) -> RollingBacktestAttempt:
    """Finalize an attempt's status (cannot modify a completed attempt)."""
    if session is not None:
        return await _finalize_attempt_status_in_session(
            session,
            attempt_id,
            status=status,
            current_stage=current_stage,
            structured_error_code=structured_error_code,
            sanitized_diagnostics=sanitized_diagnostics,
        )

    async with AsyncSessionMaker() as owned_session:
        attempt = await _finalize_attempt_status_in_session(
            owned_session,
            attempt_id,
            status=status,
            current_stage=current_stage,
            structured_error_code=structured_error_code,
            sanitized_diagnostics=sanitized_diagnostics,
        )
        await owned_session.commit()
        return attempt


# ── Stage ordinal mapping (fixed ordinals, no MAX()+1) ──────────────────────

_STAGE_ORDINAL: dict[str, int] = {
    "resolve_historical_inputs": 1,
    "validate_visibility": 2,
    "validate_authority_chain": 3,
    "resolve_or_replay_task8": 4,
    "resolve_or_replay_task9": 5,
    "resolve_or_train_task10": 6,
    "execute_task10_prediction": 7,
    "finalize_orchestration_snapshot": 8,
}


# ── Stage event persistence ──────────────────────────────────────────────────


async def persist_stage_event(
    attempt_id: int,
    node_id: int,
    *,
    stage: str,
    status: str,
    structured_error_code: str | None = None,
    sanitized_diagnostics: dict[str, object] | None = None,
    entered_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> RollingBacktestStageEvent:
    """Insert or update a stage event for a given attempt and stage.

    Fixed ordinal: sequence_number = _STAGE_ORDINAL[stage] (no MAX()+1).
    Uses INSERT ... ON CONFLICT (attempt_id, stage) DO NOTHING for idempotency.
    On entering: status='running', finished_at=NULL.
    On completion/failure: UPDATE status, finished_at.
    """
    ordinal = _STAGE_ORDINAL.get(stage)
    if ordinal is None:
        raise RollingBacktestStageIntegrityError(f"unknown stage: {stage}")

    now = datetime.now(UTC)
    if entered_at is None:
        entered_at = now

    async with AsyncSessionMaker() as session:
        # Try insert (idempotent for initial entry)
        event = RollingBacktestStageEvent(
            attempt_id=attempt_id,
            rolling_node_id=node_id,
            sequence_number=ordinal,
            stage=stage,
            status=status,
            structured_error_code=structured_error_code,
            sanitized_diagnostics=sanitized_diagnostics,
            entered_at=entered_at,
            finished_at=None if status == "running" else (finished_at or now),
        )
        session.add(event)
        try:
            await session.commit()
            return event
        except SAIntegrityError:
            await session.rollback()
            # ── Close this session; open a fresh one for SELECT+UPDATE ──
            await session.close()

        # Already exists — update it in a fresh session
        async with AsyncSessionMaker() as update_session:
            result = await update_session.execute(
                select(RollingBacktestStageEvent).where(
                    RollingBacktestStageEvent.attempt_id == attempt_id,
                    RollingBacktestStageEvent.stage == stage,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise RollingBacktestStageIntegrityError(
                    f"stage event for attempt {attempt_id} stage {stage} disappeared"
                ) from None
            existing.status = status
            existing.structured_error_code = structured_error_code
            existing.sanitized_diagnostics = sanitized_diagnostics
            if status != "running":
                existing.finished_at = finished_at or now
            await update_session.commit()
            return existing


# ── Orchestration snapshot persistence ───────────────────────────────────────


async def _persist_orchestration_snapshot_in_session(
    session: AsyncSession,
    attempt_id: int,
    node_id: int,
    *,
    status: str,
    terminal_stage: str,
    fallback_mode: str | None = None,
    blocker_code: str | None = None,
    canonical_payload: dict[str, Any] | None = None,
) -> RollingBacktestOrchestrationSnapshot:
    result = await session.execute(
        select(RollingBacktestStageEvent)
        .where(RollingBacktestStageEvent.attempt_id == attempt_id)
        .order_by(RollingBacktestStageEvent.sequence_number.desc())
        .limit(1)
    )
    last_event = result.scalar_one_or_none()

    if last_event is not None:
        derived_terminal = last_event.stage
        if derived_terminal != terminal_stage:
            raise RollingBacktestStageIntegrityError(
                f"terminal_stage drift: snapshot says {terminal_stage}, "
                f"stage_event says {derived_terminal}"
            )
    else:
        derived_terminal = terminal_stage

    payload = canonical_payload or {}
    payload_hash = sha256_payload(payload)

    snapshot = RollingBacktestOrchestrationSnapshot(
        attempt_id=attempt_id,
        rolling_node_id=node_id,
        status=status,
        terminal_stage=derived_terminal,
        fallback_mode=fallback_mode,
        blocker_code=blocker_code,
        canonical_payload=payload,
        canonical_payload_hash=payload_hash,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def persist_orchestration_snapshot(
    attempt_id: int,
    node_id: int,
    *,
    status: str,
    terminal_stage: str,
    fallback_mode: str | None = None,
    blocker_code: str | None = None,
    canonical_payload: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> RollingBacktestOrchestrationSnapshot:
    """Persist the terminal orchestration outcome for an attempt.

    terminal_stage is derived from the last stage_event for this attempt
    and validated for consistency in the same transaction.
    """
    if session is not None:
        return await _persist_orchestration_snapshot_in_session(
            session,
            attempt_id,
            node_id,
            status=status,
            terminal_stage=terminal_stage,
            fallback_mode=fallback_mode,
            blocker_code=blocker_code,
            canonical_payload=canonical_payload,
        )

    async with AsyncSessionMaker() as owned_session:
        try:
            snapshot = await _persist_orchestration_snapshot_in_session(
                owned_session,
                attempt_id,
                node_id,
                status=status,
                terminal_stage=terminal_stage,
                fallback_mode=fallback_mode,
                blocker_code=blocker_code,
                canonical_payload=canonical_payload,
            )
            await owned_session.commit()
        except SAIntegrityError as exc:
            await owned_session.rollback()
            raise RollingBacktestAttemptConflictError(
                f"snapshot already exists for attempt {attempt_id}"
            ) from exc

        return snapshot


async def finalize_attempt_with_snapshot(
    attempt_id: int,
    *,
    node_id: int,
    status: str,
    current_stage: str,
    snapshot_status: str,
    terminal_stage: str,
    fallback_mode: str | None = None,
    blocker_code: str | None = None,
    structured_error_code: str | None = None,
    sanitized_diagnostics: dict[str, object] | None = None,
    canonical_payload: dict[str, Any] | None = None,
) -> tuple[RollingBacktestAttempt, RollingBacktestOrchestrationSnapshot]:
    async with AsyncSessionMaker() as session:
        try:
            attempt = await _finalize_attempt_status_in_session(
                session,
                attempt_id,
                status=status,
                current_stage=current_stage,
                structured_error_code=structured_error_code,
                sanitized_diagnostics=sanitized_diagnostics,
            )
            snapshot = await _persist_orchestration_snapshot_in_session(
                session,
                attempt_id,
                node_id,
                status=snapshot_status,
                terminal_stage=terminal_stage,
                fallback_mode=fallback_mode,
                blocker_code=blocker_code,
                canonical_payload=canonical_payload,
            )
            await session.commit()
            return attempt, snapshot
        except SAIntegrityError as exc:
            await session.rollback()
            raise RollingBacktestAttemptConflictError(
                f"finalize with snapshot failed for attempt {attempt_id}"
            ) from exc
        except Exception:
            await session.rollback()
            raise


# ── Stage continuity validation (integrity reload) ───────────────────────────


async def validate_stage_continuity(
    session: AsyncSession,
    attempt_id: int,
    terminal_stage: str | None = None,
) -> None:
    """Verify no gaps in stage history, consecutive ordinals, terminal consistency.

    Called during integrity reload. Raises RollingBacktestStageIntegrityError
    on any violation.
    """
    result = await session.execute(
        select(RollingBacktestStageEvent)
        .where(RollingBacktestStageEvent.attempt_id == attempt_id)
        .order_by(RollingBacktestStageEvent.sequence_number)
    )
    events = list(result.scalars().all())

    if not events:
        # No stage events is acceptable only if the attempt never started
        return

    # Rule 1: sequence must start at 1
    if events[0].sequence_number != 1:
        raise RollingBacktestStageIntegrityError(
            f"attempt {attempt_id} first sequence is {events[0].sequence_number}, expected 1"
        )

    # Rule 2: sequence must be consecutive (1, 2, 3, ..., N)
    for i, event in enumerate(events):
        expected = i + 1
        if event.sequence_number != expected:
            raise RollingBacktestStageIntegrityError(
                f"attempt {attempt_id} stage gap: expected seq {expected} "
                f"got {event.sequence_number}"
            )

    # Rule 3: if terminal_stage is known, stages before it must be non-running
    if terminal_stage is not None:
        terminal_ordinal = _STAGE_ORDINAL.get(terminal_stage)
        if terminal_ordinal is None:
            raise RollingBacktestStageIntegrityError(f"unknown terminal_stage: {terminal_stage}")
        for event in events:
            if event.sequence_number < terminal_ordinal and event.status == "running":
                raise RollingBacktestStageIntegrityError(
                    f"attempt {attempt_id} seq {event.sequence_number} ({event.stage}) "
                    f"still running but terminal stage is {terminal_stage}"
                )

        # Rule 4: stages after terminal ordinal must not exist
        if any(e.sequence_number > terminal_ordinal for e in events):
            raise RollingBacktestStageIntegrityError(
                f"attempt {attempt_id} has stages beyond terminal {terminal_stage}"
            )

    # Rule 5: rolling_node_id consistency with attempt
    for event in events:
        attempt_result = await session.execute(
            select(RollingBacktestAttempt.rolling_node_id).where(
                RollingBacktestAttempt.id == attempt_id
            )
        )
        attempt_node_id = attempt_result.scalar_one_or_none()
        if attempt_node_id is not None and event.rolling_node_id != attempt_node_id:
            raise RollingBacktestAuthorityBindingError(
                f"stage_event {event.id} node_id {event.rolling_node_id} != "
                f"attempt {attempt_id} node_id {attempt_node_id}"
            )


async def validate_orchestration_snapshot_consistency(
    session: AsyncSession,
    attempt_id: int,
) -> str | None:
    """Cross-table consistency for orchestration_snapshot.

    Verifies: snapshot.rolling_node_id == attempt.rolling_node_id.
    """
    snapshot_result = await session.execute(
        select(RollingBacktestOrchestrationSnapshot)
        .where(RollingBacktestOrchestrationSnapshot.attempt_id == attempt_id)
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()
    if snapshot is None:
        return None

    attempt_result = await session.execute(
        select(RollingBacktestAttempt).where(RollingBacktestAttempt.id == attempt_id)
    )
    attempt = attempt_result.scalar_one_or_none()
    if attempt is None:
        raise RollingBacktestAttemptConflictError(f"attempt {attempt_id} not found")
    if snapshot.rolling_node_id != attempt.rolling_node_id:
        raise RollingBacktestAuthorityBindingError(
            f"snapshot node_id {snapshot.rolling_node_id} != "
            f"attempt {attempt_id} node_id {attempt.rolling_node_id}"
        )
    if snapshot.status != attempt.status:
        raise RollingBacktestStageIntegrityError(
            f"snapshot status {snapshot.status} != attempt status {attempt.status}"
        )
    if snapshot.terminal_stage != attempt.current_stage:
        raise RollingBacktestStageIntegrityError(
            f"snapshot terminal_stage {snapshot.terminal_stage} != "
            f"attempt current_stage {attempt.current_stage}"
        )
    if attempt.status in ("pending", "running"):
        raise RollingBacktestStageIntegrityError(
            f"attempt {attempt_id} has snapshot but non-terminal status {attempt.status}"
        )
    return snapshot.terminal_stage
