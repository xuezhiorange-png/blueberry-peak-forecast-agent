"""Rolling backtest persistence: typed commands, atomic repository, and integrity loader."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestBindingRow,
    RollingBacktestDagSnapshot,
    RollingBacktestManifest,
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
from backend.app.rolling_backtest.canonical import (
    canonical_json_dumps,
    sha256_payload,
)
from backend.app.rolling_backtest.config import (
    rolling_backtest_config_hash,
    rolling_backtest_config_payload,
)
from backend.app.rolling_backtest.enums import UpstreamSelectionMode
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
    S2HistoricalBacktestRequest,
    S2HistoricalBindingRow,
    s2_business_grain_hash,
)
from backend.app.rolling_backtest.signatures import (
    node_signature_hash,
    node_signature_payload,
    run_signature_hash,
    s2_binding_key_hash,
    s2_binding_row_hash,
    s2_binding_row_persistence_payload,
    s2_instance_hash,
    s2_node_identity_hash,
    s2_node_identity_payload,
    s2_request_hash,
    s2_request_payload,
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


@dataclass(frozen=True, slots=True)
class S2HistoricalBindingReadModel:
    """Verified S2 evidence returned to a consumer of the read adapter."""

    run_id: int
    request: S2HistoricalBacktestRequest
    instance_hash: str
    manifest_hash: str
    coverage_manifest: Mapping[str, object]
    exclusion_manifest: Mapping[str, object]
    authority_references: Mapping[str, object]
    rows: tuple[S2HistoricalBindingRow, ...]


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


def _extract_constraint_name(exc: SAIntegrityError) -> str | None:
    """Extract the PostgreSQL constraint name from an IntegrityError.

    Used to classify constraint violations so only the target UNIQUE key
    on (attempt_id, stage) triggers the idempotent update path. All other
    violations (FK, CHECK, NOT NULL, sequence UNIQUE) are re-raised as
    typed integrity errors.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    msg = str(orig)
    # PostgreSQL format: 'duplicate key value violates unique constraint "uq_name"'
    if "unique constraint" in msg or "UniqueViolation" in msg:
        m = re.search(r'"([^"]+)"', msg)
        if m:
            return m.group(1)
    # PostgreSQL CHECK/NOT NULL: 'violates check constraint "ck_name"'
    if "check constraint" in msg or "CheckViolation" in msg:
        m = re.search(r'"([^"]+)"', msg)
        if m:
            return m.group(1)
    # FK violation
    if "foreign key" in msg or "ForeignKeyViolation" in msg:
        return "foreign_key_violation"
    return None


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


def _validated_resolved_input_reference(
    item: ResolvedInputPersistenceCommand,
    *,
    pinned: bool,
) -> PersistentUpstreamReference | None:
    identity_ref = item.identity.persistent_reference
    command_ref = item.persistent_reference

    if identity_ref != command_ref:
        raise RollingBacktestCommandMismatchError(
            f"resolved input role={item.identity.source_role} persistent reference mismatch"
        )

    if pinned and command_ref is None:
        raise RollingBacktestCommandMismatchError(
            f"pinned resolved input role={item.identity.source_role} is missing "
            "persistent reference"
        )

    return command_ref


def _persistent_reference_from_row(
    row: RollingBacktestResolvedInput,
) -> PersistentUpstreamReference | None:
    ref_type = row.persistent_reference_type
    ref_value = row.persistent_reference_value

    if ref_type is None and ref_value is None:
        return None

    if ref_type is None or ref_value is None:
        raise RollingBacktestCanonicalParityError(
            f"resolved input role={row.source_role} has partial persistent reference"
        )

    if ref_type in {"database_run_id", "database_artifact_id", "database_row_id"}:
        try:
            parsed = int(ref_value)
        except (TypeError, ValueError) as exc:
            raise RollingBacktestCanonicalParityError(
                f"resolved input role={row.source_role} has invalid database reference"
            ) from exc

        if parsed <= 0 or str(parsed) != ref_value:
            raise RollingBacktestCanonicalParityError(
                f"resolved input role={row.source_role} has non-canonical database reference"
            )

        return PersistentUpstreamReference(
            reference_type=ref_type,
            reference_value=parsed,
        )

    raise RollingBacktestCanonicalParityError(
        f"resolved input role={row.source_role} has unsupported reference type={ref_type}"
    )


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


async def load_node_resolved_identities_with_references(
    session: AsyncSession,
    *,
    rolling_node_id: int,
) -> tuple[ResolvedUpstreamSemanticIdentity, ...]:
    resolved_result = await session.execute(
        select(RollingBacktestResolvedInput)
        .where(RollingBacktestResolvedInput.rolling_node_id == rolling_node_id)
        .order_by(
            RollingBacktestResolvedInput.source_role,
            RollingBacktestResolvedInput.role_qualifier,
            RollingBacktestResolvedInput.source_type,
        )
    )
    resolved_rows = resolved_result.scalars().all()

    identities: list[ResolvedUpstreamSemanticIdentity] = []
    seen_roles: set[str] = set()
    for row in resolved_rows:
        _assert_no_persistent_reference_fields(row.canonical_payload)
        try:
            reconstructed = _resolved_input_identity_from_payload(row.canonical_payload)
        except ValidationError as exc:
            raise RollingBacktestCanonicalParityError("resolved input payload is invalid") from exc

        reference = _persistent_reference_from_row(row)

        if row.source_role in seen_roles:
            raise RollingBacktestIntegrityError(
                f"duplicate resolved input role '{row.source_role}' for node {rolling_node_id}"
            )
        seen_roles.add(row.source_role)

        normalized_fields = {
            "source_role": reconstructed.source_role,
            "source_type": reconstructed.source_type.value,
            "role_qualifier": reconstructed.role_qualifier,
            "semantic_input_signature": reconstructed.semantic.input_signature,
            "result_hash": reconstructed.semantic.result_hash,
            "canonical_payload_hash": reconstructed.semantic.canonical_payload_hash,
            "schema_version": reconstructed.semantic.schema_version,
            "policy_version": reconstructed.semantic.policy_version,
            "audit_hash": _resolved_input_audit_hash(reconstructed),
        }
        for field_name, expected_value in normalized_fields.items():
            if getattr(row, field_name) != expected_value:
                raise RollingBacktestCanonicalParityError(
                    f"resolved input {field_name} mismatch for role '{row.source_role}'"
                )

        if row.canonical_payload != _resolved_input_canonical_payload(reconstructed):
            raise RollingBacktestCanonicalParityError("resolved input canonical payload mismatch")

        identities.append(reconstructed.model_copy(update={"persistent_reference": reference}))

    return tuple(identities)


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

        pinned = node_cmd.node.upstream_selection_mode == UpstreamSelectionMode.PINNED
        for item in node_cmd.resolved_inputs:
            _validated_resolved_input_reference(item, pinned=pinned)

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
                    validated_ref = _validated_resolved_input_reference(
                        ri_cmd,
                        pinned=node_def.upstream_selection_mode == UpstreamSelectionMode.PINNED,
                    )
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
                            validated_ref.reference_type if validated_ref is not None else None
                        ),
                        persistent_reference_value=(
                            str(validated_ref.reference_value)
                            if validated_ref is not None
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


async def _load_s2_logical_run_with_integrity(
    session: AsyncSession,
    run: RollingBacktestRun,
) -> RollingBacktestRun:
    """Reload an S2 aggregate from persisted canonical evidence only."""

    if run.backtest_request_payload is None:
        raise RollingBacktestCanonicalParityError("S2 request payload is missing")
    try:
        request = S2HistoricalBacktestRequest.model_validate(run.backtest_request_payload)
    except ValidationError as exc:
        raise RollingBacktestCanonicalParityError("S2 request payload is invalid") from exc
    request_payload = _json_value(s2_request_payload(request))
    request_hash = s2_request_hash(request)
    if (
        run.s2_contract_version != request.s2_contract_version
        or run.backtest_request_hash != request_hash
        or run.canonical_payload != request_payload
        or run.canonical_payload_hash != request_hash
        or run.config_hash != request_hash
        or run.run_signature != request_hash
        or run.forecast_cutoff_at != request.forecast_cutoff_at
        or run.label_observation_cutoff_at != request.label_observation_cutoff_at
        or run.label_visibility_mode != request.label_visibility_mode
    ):
        raise RollingBacktestCanonicalParityError("S2 run canonical identity does not round-trip")
    result = await session.execute(
        select(RollingBacktestBindingRow)
        .where(RollingBacktestBindingRow.rolling_run_id == run.id)
        .order_by(RollingBacktestBindingRow.binding_key_hash)
    )
    persisted_rows = result.scalars().all()
    try:
        rows = tuple(
            S2HistoricalBindingRow.model_validate(row.canonical_payload) for row in persisted_rows
        )
    except ValidationError as exc:
        raise RollingBacktestCanonicalParityError("S2 binding row payload is invalid") from exc
    try:
        rows = _validate_s2_row_set(request, rows)
    except RollingBacktestIntegrityError as exc:
        raise RollingBacktestCanonicalParityError(
            "S2 persisted business-grain horizon coverage is invalid"
        ) from exc
    for persisted, row in zip(persisted_rows, rows, strict=True):
        if s2_binding_row_hash(row) != row.row_hash:
            raise RollingBacktestCanonicalParityError(
                "S2 binding row hash does not match its canonical payload"
            )
        if s2_binding_key_hash(request, row) != row.binding_key_hash:
            raise RollingBacktestCanonicalParityError(
                "S2 binding key hash does not match its canonical payload"
            )
        if (
            persisted.binding_row_hash != row.row_hash
            or persisted.binding_key_hash != row.binding_key_hash
        ):
            raise RollingBacktestCanonicalParityError("S2 binding row columns do not round-trip")
        if row.actual_label is not None:
            actual = row.actual_label
            if actual.target_date != row.target_date:
                raise RollingBacktestCanonicalParityError(
                    "S2 label target date does not match binding target date"
                )
            if not (
                actual.season_business_key in request.season_business_keys
                and actual.farm_business_key in request.farm_business_keys
                and actual.subfarm_business_key in request.subfarm_business_keys
                and actual.variety_business_key in request.variety_business_keys
            ):
                raise RollingBacktestCanonicalParityError(
                    "S2 label business grain is outside request scope"
                )
            if (
                request.label_observation_cutoff_at is not None
                and actual.visibility_timestamp > request.label_observation_cutoff_at
            ):
                raise RollingBacktestCanonicalParityError(
                    "S2 label row is visible after label observation cutoff"
                )
            if actual.business_grain_hash != s2_business_grain_hash(
                season_business_key=actual.season_business_key,
                farm_business_key=actual.farm_business_key,
                subfarm_business_key=actual.subfarm_business_key,
                variety_business_key=actual.variety_business_key,
                target_date=actual.target_date,
            ):
                raise RollingBacktestCanonicalParityError(
                    "S2 label business grain hash does not round-trip"
                )
            if actual.label_row_identity_hash == actual.label_snapshot_identity_hash:
                raise RollingBacktestCanonicalParityError(
                    "S2 snapshot identity cannot substitute for exact label row identity"
                )
            winner_rows = actual.revision_or_winner_evidence.get("winner_rows")
            if isinstance(winner_rows, list):
                winner_hashes = tuple(
                    sorted(
                        str(item["winner_row_hash"])
                        for item in winner_rows
                        if isinstance(item, dict) and "winner_row_hash" in item
                    )
                )
                if (
                    len(winner_hashes) != len(winner_rows)
                    or actual.label_winner_identity_hash not in winner_hashes
                    or actual.label_winner_set_identity_hash
                    != sha256_payload({"winner_row_hashes": winner_hashes})
                ):
                    raise RollingBacktestCanonicalParityError(
                        "S2 label winner-set identity does not round-trip"
                    )
    coverage_payload, exclusions_payload, authority_payload = _s2_manifest_payloads(request, rows)
    manifest_result = await session.execute(
        select(RollingBacktestManifest).where(RollingBacktestManifest.rolling_run_id == run.id)
    )
    manifest = manifest_result.scalar_one_or_none()
    if manifest is None:
        raise RollingBacktestCanonicalParityError("S2 manifest is missing")
    expected_manifest_hash = sha256_payload(
        {
            "request_hash": request_hash,
            "instance_hash": s2_instance_hash(request, rows),
            "coverage": coverage_payload,
            "exclusions": exclusions_payload,
            "authorities": authority_payload,
        }
    )
    await _verify_existing_s2_binding(
        session,
        run=run,
        request=request,
        rows=rows,
        request_hash=request_hash,
        instance_hash=s2_instance_hash(request, rows),
        request_payload=request_payload,
        coverage_payload=coverage_payload,
        exclusions_payload=exclusions_payload,
        authority_payload=authority_payload,
        manifest_hash=expected_manifest_hash,
    )
    return run


async def load_s2_historical_binding_by_instance_hash(
    session: AsyncSession,
    *,
    instance_hash: str,
) -> S2HistoricalBindingReadModel:
    """Load a complete S2 binding by its immutable instance identity."""

    if re.fullmatch(r"[0-9a-f]{64}", instance_hash) is None:
        raise RollingBacktestCanonicalParityError("S2 instance hash is not canonical")
    result = await session.execute(
        select(RollingBacktestRun).where(RollingBacktestRun.instance_hash == instance_hash)
    )
    run = result.scalar_one_or_none()
    if run is None or run.s2_contract_version != "v0.2-s2-historical-binding-v1":
        raise RollingBacktestCanonicalParityError("S2 instance evidence is missing")
    await _load_s2_logical_run_with_integrity(session, run)
    try:
        request = S2HistoricalBacktestRequest.model_validate(run.backtest_request_payload)
    except ValidationError as exc:
        raise RollingBacktestCanonicalParityError("S2 request payload is invalid") from exc
    manifest = (
        await session.execute(
            select(RollingBacktestManifest).where(RollingBacktestManifest.rolling_run_id == run.id)
        )
    ).scalar_one_or_none()
    if manifest is None or manifest.instance_hash != instance_hash:
        raise RollingBacktestCanonicalParityError("S2 manifest identity is incomplete")
    rows_result = await session.execute(
        select(RollingBacktestBindingRow)
        .where(RollingBacktestBindingRow.rolling_run_id == run.id)
        .order_by(RollingBacktestBindingRow.binding_key_hash)
    )
    try:
        rows = tuple(
            S2HistoricalBindingRow.model_validate(row.canonical_payload)
            for row in rows_result.scalars().all()
        )
    except ValidationError as exc:
        raise RollingBacktestCanonicalParityError("S2 binding row payload is invalid") from exc
    return S2HistoricalBindingReadModel(
        run_id=run.id,
        request=request,
        instance_hash=instance_hash,
        manifest_hash=manifest.manifest_hash,
        coverage_manifest=dict(manifest.coverage_manifest_payload),
        exclusion_manifest=dict(manifest.exclusion_manifest_payload),
        authority_references=dict(manifest.authority_reference_payload),
        rows=rows,
    )


async def load_logical_run_with_integrity(
    session: AsyncSession,
    run: RollingBacktestRun,
) -> RollingBacktestRun:
    """Full integrity verification of a loaded logical run."""

    if run.s2_contract_version is not None:
        if run.s2_contract_version != "v0.2-s2-historical-binding-v1":
            raise RollingBacktestCanonicalParityError("unknown S2 contract discriminator")
        return await _load_s2_logical_run_with_integrity(session, run)

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

    resolved_identities = await load_node_resolved_identities_with_references(
        session,
        rolling_node_id=node.id,
    )
    if len(resolved_identities) != node.expected_resolved_input_count:
        raise RollingBacktestChildCountMismatchError(
            "resolved_input count mismatch for "
            f"node {node.id}: expected={node.expected_resolved_input_count} "
            f"actual={len(resolved_identities)}"
        )

    expected_resolved = {
        item.source_role: item for item in expected_node.resolved_upstream_semantic_identities
    }
    resolved_rows_by_role: dict[str, ResolvedUpstreamSemanticIdentity] = {}
    for reconstructed in resolved_identities:
        expected_identity = expected_resolved.get(reconstructed.source_role)
        if expected_identity is None:
            raise RollingBacktestIntegrityError(
                f"unexpected resolved input role '{reconstructed.source_role}' for node {node.id}"
            )
        if _resolved_input_canonical_payload(reconstructed) != _resolved_input_canonical_payload(
            expected_identity
        ):
            raise RollingBacktestCanonicalParityError(
                f"resolved input semantic mismatch for role '{reconstructed.source_role}'"
            )
        resolved_rows_by_role[reconstructed.source_role] = reconstructed

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
    session: AsyncSession | None = None,
) -> RollingBacktestAttempt:
    """Create a new execution attempt with per-node attempt_number.

    Uses SELECT ... FOR UPDATE on rolling_backtest_node to serialize
    concurrent attempt creation for the same node. Different nodes
    can create attempts in parallel.

    Repository gate: validates that rolling_run_id on the attempt
    equals the node's rolling_run_id at insert time.
    """
    if session is not None:
        # Lock the node row to serialize attempt creation for this node
        node_result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.id == node_id).with_for_update()
        )
        node_row = node_result.scalar_one_or_none()
        if node_row is None:
            raise RollingBacktestIntegrityError(f"node {node_id} not found")

        if node_row.rolling_run_id != run_id:
            raise RollingBacktestAuthorityBindingError(
                f"attempt run_id {run_id} does not match node {node_id} "
                f"run_id {node_row.rolling_run_id}"
            )

        await _run_sync_hook(_ATTEMPT_ALLOCATION_SYNC_HOOK, "after_node_lock")

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
            await session.flush()
        except SAIntegrityError as exc:
            raise RollingBacktestAttemptConflictError(
                f"attempt_number {next_number} already exists for node {node_id}"
            ) from exc
        return attempt

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
    session: AsyncSession | None = None,
) -> RollingBacktestStageEvent:
    """Insert or update a stage event for a given attempt and stage.

    Fixed ordinal: sequence_number = _STAGE_ORDINAL[stage] (no MAX()+1).
    Uses INSERT ... ON CONFLICT ON CONSTRAINT uq_rolling_backtest_stage_event_stage
    DO UPDATE for atomic insert-or-update in a single round-trip.
    On entering: status='running', finished_at=NULL.
    On completion/failure: UPDATE status, finished_at, error fields.
    entered_at is preserved unchanged on update.
    FK, CHECK, and other unique constraint violations still raise typed errors.
    """
    ordinal = _STAGE_ORDINAL.get(stage)
    if ordinal is None:
        raise RollingBacktestStageIntegrityError(f"unknown stage: {stage}")

    now = datetime.now(UTC)
    if entered_at is None:
        entered_at = now

    finished_at_value: datetime | None = None if status == "running" else (finished_at or now)

    if session is not None:
        stmt = pg_insert(RollingBacktestStageEvent).values(
            attempt_id=attempt_id,
            rolling_node_id=node_id,
            sequence_number=ordinal,
            stage=stage,
            status=status,
            structured_error_code=structured_error_code,
            sanitized_diagnostics=sanitized_diagnostics,
            entered_at=entered_at,
            finished_at=finished_at_value,
        )
        returning_stmt = stmt.on_conflict_do_update(
            constraint="uq_rolling_backtest_stage_event_stage",
            set_={
                "status": stmt.excluded.status,
                "finished_at": stmt.excluded.finished_at,
                "structured_error_code": stmt.excluded.structured_error_code,
                "sanitized_diagnostics": stmt.excluded.sanitized_diagnostics,
            },
        ).returning(RollingBacktestStageEvent)

        try:
            result = await session.execute(returning_stmt)
            return result.scalar_one()
        except SAIntegrityError as exc:
            constraint_name = _extract_constraint_name(exc)
            raise RollingBacktestStageIntegrityError(
                f"persist_stage_event constraint violation: {constraint_name or 'unknown'}"
            ) from exc

    async with AsyncSessionMaker() as session:
        stmt = pg_insert(RollingBacktestStageEvent).values(
            attempt_id=attempt_id,
            rolling_node_id=node_id,
            sequence_number=ordinal,
            stage=stage,
            status=status,
            structured_error_code=structured_error_code,
            sanitized_diagnostics=sanitized_diagnostics,
            entered_at=entered_at,
            finished_at=finished_at_value,
        )
        returning_stmt = stmt.on_conflict_do_update(
            constraint="uq_rolling_backtest_stage_event_stage",
            set_={
                "status": stmt.excluded.status,
                "finished_at": stmt.excluded.finished_at,
                "structured_error_code": stmt.excluded.structured_error_code,
                "sanitized_diagnostics": stmt.excluded.sanitized_diagnostics,
            },
        ).returning(RollingBacktestStageEvent)

        try:
            result = await session.execute(returning_stmt)
            event: RollingBacktestStageEvent = result.scalar_one()
            await session.commit()
            return event
        except SAIntegrityError as exc:
            await session.rollback()
            # ON CONFLICT DO UPDATE handles the target unique constraint.
            # Any IntegrityError reaching here is a real violation (FK,
            # CHECK, NOT NULL, or the other unique key on sequence_number).
            constraint_name = _extract_constraint_name(exc)
            raise RollingBacktestStageIntegrityError(
                f"persist_stage_event constraint violation: {constraint_name or 'unknown'}"
            ) from exc


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
    session: AsyncSession | None = None,
) -> tuple[RollingBacktestAttempt, RollingBacktestOrchestrationSnapshot]:
    if session is not None:
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
            return attempt, snapshot
        except SAIntegrityError as exc:
            raise RollingBacktestAttemptConflictError(
                f"finalize with snapshot failed for attempt {attempt_id}"
            ) from exc
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
        # No stage events — check attempt status. Only pending/unstarted
        # attempts may legitimately have no stage history.
        attempt_result = await session.execute(
            select(RollingBacktestAttempt.status).where(RollingBacktestAttempt.id == attempt_id)
        )
        attempt_status = attempt_result.scalar_one_or_none()
        if attempt_status is not None and attempt_status not in ("pending",):
            raise RollingBacktestStageIntegrityError(
                f"attempt {attempt_id} has status '{attempt_status}' "
                f"but no stage events — empty stage history is only valid for pending"
            )
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
        if attempt_node_id is not None and event.rolling_node_id != int(attempt_node_id):
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


# ── Node and run status management ───────────────────────────────────────────


async def derive_run_status_from_attempts(
    session: AsyncSession,
    run_id: int,
) -> str:
    """Derive run-level status from the latest attempt per node."""

    node_result = await session.execute(
        select(RollingBacktestNode.id).where(RollingBacktestNode.rolling_run_id == run_id)
    )
    node_ids = [row[0] for row in node_result.all()]
    statuses: list[str] = []
    for nid in node_ids:
        latest_result = await session.execute(
            select(RollingBacktestAttempt.status)
            .where(
                RollingBacktestAttempt.rolling_node_id == nid,
                RollingBacktestAttempt.rolling_run_id == run_id,
            )
            .order_by(RollingBacktestAttempt.attempt_number.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()
        if latest is not None:
            statuses.append(latest)
    if not statuses:
        return "pending"
    all_pending = all(s == "pending" for s in statuses)
    all_completed = all(s == "completed" for s in statuses)
    any_running = any(s == "running" for s in statuses)
    any_blocked = any(s == "blocked" for s in statuses)
    any_failed = any(s == "failed" for s in statuses)
    any_completed = any(s == "completed" for s in statuses)

    if all_pending:
        return "pending"
    if any_running:
        return "running"
    if any_failed:
        return "failed"
    if all_completed:
        return "forecast_completed"
    if any_completed and any_blocked:
        return "partially_completed"
    if any_blocked and not any_completed:
        return "blocked"
    return "pending"


async def update_run_status_from_attempts(
    session: AsyncSession,
    run_id: int,
) -> str:
    """Aggregate latest attempt statuses and update the run status. Returns the new status."""
    derived = await derive_run_status_from_attempts(session, run_id)
    result = await session.execute(
        select(RollingBacktestRun).where(RollingBacktestRun.id == run_id).with_for_update()
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise RollingBacktestIntegrityError(f"run {run_id} not found")
    run.status = derived
    await session.flush()
    return derived


# ── V0.2-S2 historical binding persistence ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class _S2AuthorityEvidence:
    source_role: str
    source_type: str
    canonical_payload: dict[str, Any]
    availability_payload: dict[str, Any]
    allowed: bool
    blocker_code: str | None


def _s2_manifest_payloads(
    request: S2HistoricalBacktestRequest,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ordered = tuple(sorted(rows, key=lambda item: item.binding_key_hash))
    grain_coverage: dict[tuple[object, ...], list[S2HistoricalBindingRow]] = {}
    for row in ordered:
        grain_key = (
            row.season_business_key,
            row.farm_business_key,
            row.subfarm_business_key,
            row.variety_business_key,
            row.forecast_quantile,
            row.forecast_authority.forecast_run_identity_hash,
        )
        grain_coverage.setdefault(grain_key, []).append(row)
    coverage = {
        "manifest_schema_version": "v0.2-s2-binding-manifest-v1",
        "requested_horizons_days": request.requested_horizons_days,
        "row_count": len(ordered),
        "comparable_count": sum(row.row_status == "COMPARABLE" for row in ordered),
        "excluded_count": sum(row.row_status == "EXCLUDED" for row in ordered),
        "not_computable_count": sum(row.row_status == "NOT_COMPUTABLE" for row in ordered),
        "comparison_ready": all(row.row_status == "COMPARABLE" for row in ordered),
        "grain_count": len(grain_coverage),
        "business_grain_horizon_coverage": tuple(
            {
                "season_business_key": grain[0],
                "farm_business_key": grain[1],
                "subfarm_business_key": grain[2],
                "variety_business_key": grain[3],
                "forecast_quantile": grain[4],
                "forecast_run_identity_hash": grain[5],
                "horizons_days": tuple(sorted(row.horizon_days for row in grain_rows)),
                "binding_key_hashes": tuple(sorted(row.binding_key_hash for row in grain_rows)),
                "row_statuses": tuple(
                    {
                        "horizon_days": row.horizon_days,
                        "row_status": row.row_status,
                        "reason_code": row.reason_code,
                    }
                    for row in sorted(
                        grain_rows,
                        key=lambda item: (item.horizon_days, item.binding_key_hash),
                    )
                ),
            }
            for grain, grain_rows in sorted(grain_coverage.items())
        ),
    }
    exclusions = {
        "rows": tuple(
            {
                "horizon_days": row.horizon_days,
                "target_date": row.target_date,
                "row_hash": row.row_hash,
                "binding_key_hash": row.binding_key_hash,
                "reason_code": row.reason_code,
            }
            for row in ordered
            if row.row_status != "COMPARABLE"
        )
    }
    authorities = {
        "authority_schema_version": "v0.2-s2-persisted-authority-v2",
        "resolved_authority_evidence": tuple(
            {
                "source_role": evidence.source_role,
                "source_type": evidence.source_type,
                "canonical_payload": evidence.canonical_payload,
                "canonical_payload_hash": sha256_payload(evidence.canonical_payload),
                "availability_payload": evidence.availability_payload,
                "availability_audit_hash": sha256_payload(evidence.availability_payload),
            }
            for evidence in _s2_persisted_authority_evidence(ordered)
        ),
    }
    return (
        _json_value(coverage),
        _json_value(exclusions),
        _json_value(authorities),
    )


def _s2_persisted_authority_evidence(
    rows: tuple[S2HistoricalBindingRow, ...],
) -> tuple[_S2AuthorityEvidence, ...]:
    """Build exact resolved-input and availability evidence for every binding."""

    evidence: list[_S2AuthorityEvidence] = []
    for row in sorted(rows, key=lambda item: item.binding_key_hash):
        role_suffix = row.binding_key_hash
        forecast = row.forecast_authority
        sources: tuple[tuple[str, str, dict[str, Any], datetime | None], ...] = (
            (
                f"s2_core_forecast:{role_suffix}",
                "core_forecast_daily_row",
                {
                    "authority_verification": row.authority_verification,
                    "forecast_run_identity_hash": forecast.forecast_run_identity_hash,
                    "daily_row_identity_hash": forecast.daily_row_identity_hash,
                    "forecast_code_identity": forecast.forecast_code_identity,
                    "historical_code_identity": forecast.historical_code_identity,
                    "build_artifact_hash": forecast.build_artifact_hash,
                    "config_bundle_hash": forecast.config_bundle_hash,
                    "historical_code_available_at": forecast.historical_code_available_at,
                    "model_identity": forecast.model_identity,
                    "parameter_identity": forecast.parameter_identity,
                    "data_identity": forecast.data_identity,
                    "target_date": row.target_date,
                },
                forecast.available_at,
            ),
            (
                f"s2_task9_authority:{role_suffix}",
                "task9_exact_member",
                {
                    "authority_verification": row.authority_verification,
                    "task9_authority_identity_hash": forecast.task9_authority_identity_hash,
                    "task9_member_identity_hash": forecast.task9_member_identity_hash,
                    "historical_code_identity": forecast.historical_code_identity,
                    "target_date": row.target_date,
                },
                forecast.available_at,
            ),
            (
                f"s2_task10_authority:{role_suffix}",
                "task10_exact_prediction_row",
                {
                    "authority_verification": row.authority_verification,
                    "task10_authority_identity_hash": forecast.task10_authority_identity_hash,
                    "task10_model_identity_hash": forecast.task10_model_identity_hash,
                    "task10_replay_identity_hash": forecast.task10_replay_identity_hash,
                    "task10_prediction_row_identity_hash": (
                        forecast.task10_prediction_row_identity_hash
                    ),
                    "task10_model_available_at": (forecast.task10_model_available_at),
                    "target_date": row.target_date,
                },
                forecast.task10_model_available_at,
            ),
            (
                f"s2_i7_label_authority:{role_suffix}",
                "i7_exact_label_row",
                {
                    "authority_verification": row.authority_verification,
                    "label_authority_status": (
                        row.actual_label.label_resolution_status
                        if row.actual_label is not None
                        else "NOT_AVAILABLE"
                    ),
                    "label_snapshot_identity_hash": (
                        row.actual_label.label_snapshot_identity_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "label_row_identity_hash": (
                        row.actual_label.label_row_identity_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "label_winner_identity_hash": (
                        row.actual_label.label_winner_identity_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "label_winner_set_identity_hash": (
                        row.actual_label.label_winner_set_identity_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "actual_source_identity_hash": (
                        row.actual_label.actual_source_identity_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "source_identity_hash": (
                        row.actual_label.source_identity_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "business_grain_hash": (
                        row.actual_label.business_grain_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "revision_or_winner_evidence": (
                        row.actual_label.revision_or_winner_evidence
                        if row.actual_label is not None
                        else None
                    ),
                    "absence_evidence_hash": (
                        row.actual_label.absence_evidence_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "observed_weight_kg": (
                        row.actual_label.observed_weight_kg
                        if row.actual_label is not None
                        else None
                    ),
                    "physical_alignment_status": row.physical_alignment_status,
                    "physical_alignment_policy_version": (
                        row.actual_label.physical_alignment_policy_version
                        if row.actual_label is not None
                        else None
                    ),
                    "physical_alignment_evidence_hash": (
                        row.actual_label.physical_alignment_evidence_hash
                        if row.actual_label is not None
                        else None
                    ),
                    "target_date": row.target_date,
                },
                (row.actual_label.visibility_timestamp if row.actual_label is not None else None),
            ),
        )
        for source_role, source_type, payload, authoritative_available_at in sources:
            is_label_source = source_type == "i7_exact_label_row"
            label_is_exact = (
                row.actual_label is not None
                and row.actual_label.label_resolution_status == "EXACT_LABEL"
            )
            allowed = not is_label_source or label_is_exact
            blocker_code = None
            if is_label_source and not allowed:
                blocker_code = (
                    "NO_VISIBLE_LABEL_AT_CUTOFF"
                    if row.actual_label is not None
                    and row.actual_label.label_resolution_status == "PROVEN_ABSENT"
                    else "NO_APPROVED_REAL_DATA"
                )
            canonical_payload = _json_value(
                {
                    "source_role": source_role,
                    "source_type": source_type,
                    "horizon_days": row.horizon_days,
                    "binding_key_hash": row.binding_key_hash,
                    **payload,
                }
            )
            availability_payload = _json_value(
                {
                    "source_role": source_role,
                    "source_type": source_type,
                    "allowed": allowed,
                    "blocker_code": blocker_code,
                    "authoritative_available_at": authoritative_available_at,
                    "forecast_cutoff_at": row.forecast_cutoff_at,
                    "label_observation_cutoff_at": row.label_observation_cutoff_at,
                }
            )
            evidence.append(
                _S2AuthorityEvidence(
                    source_role=source_role,
                    source_type=source_type,
                    canonical_payload=canonical_payload,
                    availability_payload=availability_payload,
                    allowed=allowed,
                    blocker_code=blocker_code,
                )
            )
    return tuple(evidence)


def _s2_group_rows_by_season(
    rows: tuple[S2HistoricalBindingRow, ...],
) -> tuple[tuple[int, str, tuple[S2HistoricalBindingRow, ...]], ...]:
    grouped: dict[tuple[int, str], list[S2HistoricalBindingRow]] = {}
    season_keys_by_id: dict[int, str] = {}
    season_ids_by_key: dict[str, int] = {}
    for row in rows:
        existing_key = season_keys_by_id.setdefault(row.season_id, row.season_business_key)
        existing_id = season_ids_by_key.setdefault(row.season_business_key, row.season_id)
        if existing_key != row.season_business_key or existing_id != row.season_id:
            raise RollingBacktestIntegrityError(
                "S2 persisted season lookup and business key mapping is ambiguous"
            )
        grouped.setdefault((row.season_id, row.season_business_key), []).append(row)
    ordered = tuple(sorted(rows, key=lambda item: item.binding_key_hash))
    anchor_season_id, anchor_season_business_key = min(
        grouped,
        key=lambda item: (item[0], item[1]),
    )
    return ((anchor_season_id, anchor_season_business_key, ordered),)


def _validate_s2_row_set(
    request: S2HistoricalBacktestRequest,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> tuple[S2HistoricalBindingRow, ...]:
    ordered = tuple(sorted(rows, key=lambda item: item.binding_key_hash))
    if not ordered:
        raise RollingBacktestIntegrityError("S2 binding requires at least one row")
    binding_keys = tuple(row.binding_key_hash for row in ordered)
    if len(set(binding_keys)) != len(binding_keys):
        raise RollingBacktestIntegrityError("S2 binding keys must be globally unique in the run")
    coverage: dict[tuple[object, ...], set[int]] = {}
    for row in ordered:
        if row.horizon_days not in request.requested_horizons_days:
            raise RollingBacktestIntegrityError(
                "binding row horizon is outside the requested horizon set"
            )
        if row.forecast_cutoff_at != request.forecast_cutoff_at:
            raise RollingBacktestIntegrityError(
                "binding row forecast cutoff must equal request forecast cutoff"
            )
        if row.label_observation_cutoff_at != request.label_observation_cutoff_at:
            raise RollingBacktestIntegrityError(
                "binding row label cutoff must inherit request label cutoff"
            )
        if s2_binding_key_hash(request, row) != row.binding_key_hash:
            raise RollingBacktestIntegrityError("binding key hash does not round-trip")
        if s2_binding_row_hash(row) != row.row_hash:
            raise RollingBacktestIntegrityError("binding row hash does not round-trip")
        grain = (
            row.season_id,
            row.season_business_key,
            row.farm_business_key,
            row.subfarm_business_key,
            row.variety_business_key,
            row.forecast_quantile,
            row.forecast_authority.forecast_run_identity_hash,
        )
        coverage.setdefault(grain, set()).add(row.horizon_days)
    required_horizons = set(request.requested_horizons_days)
    if any(horizons != required_horizons for horizons in coverage.values()):
        raise RollingBacktestIntegrityError(
            "each S2 business grain must cover every requested horizon"
        )
    _s2_group_rows_by_season(ordered)
    return ordered


def _s2_node_scope(
    *,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> dict[str, Any]:
    return _json_value(
        {
            "season_business_keys": tuple(sorted({row.season_business_key for row in rows})),
            "farm_business_keys": tuple(sorted({row.farm_business_key for row in rows})),
            "subfarm_business_keys": tuple(sorted({row.subfarm_business_key for row in rows})),
            "variety_business_keys": tuple(sorted({row.variety_business_key for row in rows})),
            "forecast_quantiles": tuple(sorted({row.forecast_quantile for row in rows})),
        }
    )


def _s2_task10_model_policy(
    rows: tuple[S2HistoricalBindingRow, ...],
) -> dict[str, Any]:
    return _json_value(
        {
            "policy": "s2_exact_task10_authority",
            "exact_authorities": tuple(
                {
                    "binding_key_hash": row.binding_key_hash,
                    "horizon_days": row.horizon_days,
                    "task10_authority_identity_hash": (
                        row.forecast_authority.task10_authority_identity_hash
                    ),
                    "task10_model_identity_hash": (
                        row.forecast_authority.task10_model_identity_hash
                    ),
                    "task10_replay_identity_hash": (
                        row.forecast_authority.task10_replay_identity_hash
                    ),
                    "task10_prediction_row_identity_hash": (
                        row.forecast_authority.task10_prediction_row_identity_hash
                    ),
                    "task10_model_available_at": (row.forecast_authority.task10_model_available_at),
                }
                for row in sorted(rows, key=lambda item: item.binding_key_hash)
            ),
        }
    )


def _s2_node_canonical_payload(
    request: S2HistoricalBacktestRequest,
    *,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> dict[str, Any]:
    evidence_count = len(_s2_persisted_authority_evidence(rows))
    as_of_local_date = request.forecast_cutoff_at.date()
    return _json_value(
        {
            "s2_contract_version": request.s2_contract_version,
            "node_identity": s2_node_identity_payload(request),
            "node_key": "s2-single-node",
            "as_of_local_date": as_of_local_date,
            "forecast_cutoff_at": request.forecast_cutoff_at,
            "label_observation_cutoff_at": request.label_observation_cutoff_at,
            "label_visibility_mode": request.label_visibility_mode,
            "forecast_start_local_date": as_of_local_date + timedelta(days=1),
            "forecast_end_local_date": max(row.target_date for row in rows),
            "execution_mode": "historical_observed",
            "upstream_selection_mode": "pinned",
            "forecast_horizon_policy_version": "v0.2-s2-horizons-7-14-21",
            "cutoff_policy_version": "v0.2-s2-dual-cutoff-v1",
            "timezone": "UTC",
            "scope": _s2_node_scope(
                rows=rows,
            ),
            "task10_model_policy": _s2_task10_model_policy(rows),
            "expected_resolved_input_count": evidence_count,
            "expected_availability_audit_count": evidence_count,
        }
    )


async def _verify_existing_s2_binding(
    session: AsyncSession,
    *,
    run: RollingBacktestRun,
    request: S2HistoricalBacktestRequest,
    rows: tuple[S2HistoricalBindingRow, ...],
    request_hash: str,
    instance_hash: str,
    request_payload: dict[str, Any],
    coverage_payload: dict[str, Any],
    exclusions_payload: dict[str, Any],
    authority_payload: dict[str, Any],
    manifest_hash: str,
) -> None:
    """Verify every immutable S2 child before accepting an idempotent replay."""

    rows = _validate_s2_row_set(request, rows)
    grouped_rows = _s2_group_rows_by_season(rows)
    node_count = len(grouped_rows)
    expected_run_fields = {
        "run_signature": request_hash,
        "config_hash": request_hash,
        "execution_mode": "historical_observed",
        "rolling_schema_version": "v0.2-s2-historical-binding-v1",
        "canonical_serialization_version": "v0.2-s2-canonical-json-v1",
        "availability_registry_version": "v0.2-s2-authority-v1",
        "node_calendar_version": "v0.2-s2-calendar-v1",
        "forecast_horizon_policy_version": "v0.2-s2-horizons-7-14-21",
        "upstream_selection_policy_version": request.authority_selection_policy_version,
        "metric_policy_version": "s2-no-metrics-v1",
        "calendar_phase_policy_version": "v0.2-s2-calendar-phase-v1",
        "cutoff_policy_version": "v0.2-s2-dual-cutoff-v1",
        "cutoff_timezone": "UTC",
        "cutoff_local_time": request.forecast_cutoff_at.timetz().replace(tzinfo=None),
        "expected_node_count": node_count,
        "canonical_payload": request_payload,
        "canonical_payload_hash": request_hash,
        "s2_contract_version": request.s2_contract_version,
        "s2_node_count": node_count,
        "backtest_request_payload": request_payload,
        "backtest_request_hash": request_hash,
        "instance_hash": instance_hash,
        "forecast_cutoff_at": request.forecast_cutoff_at,
        "label_observation_cutoff_at": request.label_observation_cutoff_at,
        "label_visibility_mode": request.label_visibility_mode,
        "master_identity_resolver_version": request.master_identity_resolver_version,
        "mapping_policy_version": request.mapping_policy_version,
        "resolved_identity_snapshot_hash": request.resolved_identity_snapshot_hash,
        "authority_selection_policy_version": request.authority_selection_policy_version,
    }
    for field_name, expected in expected_run_fields.items():
        if getattr(run, field_name) != expected:
            raise RollingBacktestIdentityConflictError(
                f"S2 run field drift detected for {field_name}"
            )

    node_result = await session.execute(
        select(RollingBacktestNode)
        .where(RollingBacktestNode.rolling_run_id == run.id)
        .order_by(RollingBacktestNode.id)
    )
    nodes = node_result.scalars().all()
    if len(nodes) != node_count:
        raise RollingBacktestIdentityConflictError(
            f"S2 node count drift: expected {node_count}, found {len(nodes)}"
        )
    if len(nodes) != 1 or len(grouped_rows) != 1:
        raise RollingBacktestIdentityConflictError("S2 requires exactly one node")
    anchor_season_id, _, season_rows = grouped_rows[0]
    node = nodes[0]
    expected_node_payload = _s2_node_canonical_payload(request, rows=season_rows)
    expected_node_hash = sha256_payload(canonical_json_dumps(expected_node_payload))
    expected_node_signature = s2_node_identity_hash(request)
    expected_evidence = _s2_persisted_authority_evidence(season_rows)
    expected_node_fields = {
        "season_id": anchor_season_id,
        "node_key": "s2-single-node",
        "node_signature": expected_node_signature,
        "as_of_local_date": request.forecast_cutoff_at.date(),
        "forecast_cutoff_at": request.forecast_cutoff_at,
        "forecast_start_local_date": request.forecast_cutoff_at.date() + timedelta(days=1),
        "forecast_end_local_date": max(row.target_date for row in season_rows),
        "execution_mode": "historical_observed",
        "upstream_selection_mode": "pinned",
        "scope": _s2_node_scope(
            rows=season_rows,
        ),
        "forecast_horizon_policy_version": "v0.2-s2-horizons-7-14-21",
        "task10_model_policy": _s2_task10_model_policy(season_rows),
        "cutoff_policy_version": "v0.2-s2-dual-cutoff-v1",
        "timezone": "UTC",
        "canonical_payload": expected_node_payload,
        "canonical_payload_hash": expected_node_hash,
        "expected_resolved_input_count": len(expected_evidence),
        "expected_availability_audit_count": len(expected_evidence),
    }
    for field_name, expected in expected_node_fields.items():
        if getattr(node, field_name) != expected:
            raise RollingBacktestIdentityConflictError(
                f"S2 node normalized field drift detected for {field_name}"
            )
    resolved_result = await session.execute(
        select(RollingBacktestResolvedInput)
        .where(RollingBacktestResolvedInput.rolling_node_id == node.id)
        .order_by(RollingBacktestResolvedInput.source_role)
    )
    audit_result = await session.execute(
        select(RollingBacktestAvailabilityAudit)
        .where(RollingBacktestAvailabilityAudit.rolling_node_id == node.id)
        .order_by(RollingBacktestAvailabilityAudit.source_role)
    )
    resolved_inputs = resolved_result.scalars().all()
    availability_audits = audit_result.scalars().all()
    expected_by_role = {item.source_role: item for item in expected_evidence}
    if len(expected_by_role) != len(expected_evidence):
        raise RollingBacktestIdentityConflictError(
            "S2 authority evidence contains duplicate source roles"
        )
    if len(resolved_inputs) != len(expected_evidence) or len(availability_audits) != len(
        expected_evidence
    ):
        raise RollingBacktestIdentityConflictError("S2 persisted authority evidence is missing")
    for resolved in resolved_inputs:
        expected = expected_by_role.get(resolved.source_role)
        if expected is None:
            raise RollingBacktestIdentityConflictError("unexpected S2 resolved authority evidence")
        evidence_hash = sha256_payload(expected.canonical_payload)
        if (
            resolved.source_type != expected.source_type
            or resolved.role_qualifier != "s2-persisted-authority"
            or resolved.semantic_input_signature != evidence_hash
            or resolved.result_hash != evidence_hash
            or resolved.canonical_payload_hash != evidence_hash
            or resolved.schema_version != "v0.2-s2-persisted-authority-v2"
            or resolved.policy_version != request.authority_selection_policy_version
            or resolved.persistent_reference_type is not None
            or resolved.persistent_reference_value is not None
            or resolved.canonical_payload != expected.canonical_payload
            or resolved.audit_hash != evidence_hash
        ):
            raise RollingBacktestIdentityConflictError(
                f"S2 resolved authority drift detected for {resolved.source_role}"
            )
    for audit in availability_audits:
        expected = expected_by_role.get(audit.source_role)
        if expected is None:
            raise RollingBacktestIdentityConflictError("unexpected S2 availability audit evidence")
        audit_hash = sha256_payload(expected.availability_payload)
        if (
            audit.source_type != expected.source_type
            or audit.allowed is not expected.allowed
            or audit.blocker_code != expected.blocker_code
            or audit.canonical_payload != expected.availability_payload
            or audit.audit_hash != audit_hash
        ):
            raise RollingBacktestIdentityConflictError(
                f"S2 availability audit drift detected for {audit.source_role}"
            )
    node_by_season = {(row.season_id, row.season_business_key): node for row in rows}

    expected_rows = rows
    row_result = await session.execute(
        select(RollingBacktestBindingRow)
        .where(RollingBacktestBindingRow.rolling_run_id == run.id)
        .order_by(RollingBacktestBindingRow.binding_key_hash)
    )
    persisted_rows = row_result.scalars().all()
    if len(persisted_rows) != len(expected_rows):
        raise RollingBacktestIdentityConflictError("S2 binding row count drift detected")
    for persisted, expected in zip(persisted_rows, expected_rows, strict=True):
        expected_node = node_by_season[(expected.season_id, expected.season_business_key)]
        if (
            persisted.rolling_node_id != expected_node.id
            or persisted.horizon_days != expected.horizon_days
            or persisted.target_date != expected.target_date
            or persisted.forecast_cutoff_at != expected.forecast_cutoff_at
            or persisted.label_observation_cutoff_at != expected.label_observation_cutoff_at
            or persisted.binding_row_hash != expected.row_hash
            or persisted.binding_key_hash != expected.binding_key_hash
            or persisted.canonical_payload != s2_binding_row_persistence_payload(expected)
            or persisted.forecast_row_identity_hash
            != expected.forecast_authority.daily_row_identity_hash
            or persisted.actual_label_row_identity_hash
            != (
                expected.actual_label.label_row_identity_hash
                if expected.actual_label is not None
                else None
            )
        ):
            raise RollingBacktestIdentityConflictError(
                "S2 binding row identity or cutoff drift detected"
            )

    manifest_result = await session.execute(
        select(RollingBacktestManifest).where(RollingBacktestManifest.rolling_run_id == run.id)
    )
    manifest = manifest_result.scalar_one_or_none()
    if manifest is None:
        raise RollingBacktestIdentityConflictError("S2 manifest is missing")
    if (
        manifest.request_hash != request_hash
        or manifest.instance_hash != instance_hash
        or manifest.coverage_manifest_payload != coverage_payload
        or manifest.exclusion_manifest_payload != exclusions_payload
        or manifest.authority_reference_payload != authority_payload
        or manifest.manifest_hash != manifest_hash
    ):
        raise RollingBacktestIdentityConflictError("S2 manifest identity drift detected")
    recomputed_manifest_hash = sha256_payload(
        {
            "request_hash": manifest.request_hash,
            "instance_hash": manifest.instance_hash,
            "coverage": manifest.coverage_manifest_payload,
            "exclusions": manifest.exclusion_manifest_payload,
            "authorities": manifest.authority_reference_payload,
        }
    )
    if recomputed_manifest_hash != manifest.manifest_hash:
        raise RollingBacktestIdentityConflictError("S2 manifest hash does not round-trip")


async def persist_s2_historical_binding(
    session: AsyncSession,
    *,
    request: S2HistoricalBacktestRequest,
    rows: tuple[S2HistoricalBindingRow, ...],
) -> RollingBacktestRun:
    """Persist one S2 run without taking ownership of the caller transaction.

    The request hash is the single idempotency key on the existing rolling
    run aggregate.  A nested transaction contains the insert race so a loser
    can reload the committed winner without leaking a raw ``IntegrityError``;
    the outer caller remains responsible for commit or rollback.
    """

    rows = _validate_s2_row_set(request, rows)
    grouped_rows = _s2_group_rows_by_season(rows)
    node_count = len(grouped_rows)

    request_hash = s2_request_hash(request)
    instance_hash = s2_instance_hash(request, rows)
    request_payload = _json_value(s2_request_payload(request))
    coverage_payload, exclusions_payload, authority_payload = _s2_manifest_payloads(request, rows)
    manifest_identity_payload = {
        "request_hash": request_hash,
        "instance_hash": instance_hash,
        "coverage": coverage_payload,
        "exclusions": exclusions_payload,
        "authorities": authority_payload,
    }
    manifest_hash = sha256_payload(manifest_identity_payload)

    existing_result = await session.execute(
        select(RollingBacktestRun).where(RollingBacktestRun.backtest_request_hash == request_hash)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        await _verify_existing_s2_binding(
            session,
            run=existing,
            request=request,
            rows=rows,
            request_hash=request_hash,
            instance_hash=instance_hash,
            request_payload=request_payload,
            coverage_payload=coverage_payload,
            exclusions_payload=exclusions_payload,
            authority_payload=authority_payload,
            manifest_hash=manifest_hash,
        )
        return existing

    try:
        async with session.begin_nested():
            run = RollingBacktestRun(
                run_signature=request_hash,
                config_hash=request_hash,
                execution_mode="historical_observed",
                rolling_schema_version="v0.2-s2-historical-binding-v1",
                canonical_serialization_version="v0.2-s2-canonical-json-v1",
                availability_registry_version="v0.2-s2-authority-v1",
                node_calendar_version="v0.2-s2-calendar-v1",
                forecast_horizon_policy_version="v0.2-s2-horizons-7-14-21",
                upstream_selection_policy_version=request.authority_selection_policy_version,
                metric_policy_version="s2-no-metrics-v1",
                calendar_phase_policy_version="v0.2-s2-calendar-phase-v1",
                cutoff_policy_version="v0.2-s2-dual-cutoff-v1",
                cutoff_timezone="UTC",
                cutoff_local_time=request.forecast_cutoff_at.timetz().replace(tzinfo=None),
                status=(
                    "completed"
                    if all(row.row_status == "COMPARABLE" for row in rows)
                    else "blocked"
                ),
                expected_node_count=node_count,
                canonical_payload=request_payload,
                canonical_payload_hash=request_hash,
                s2_contract_version=request.s2_contract_version,
                s2_node_count=node_count,
                backtest_request_payload=request_payload,
                backtest_request_hash=request_hash,
                instance_hash=instance_hash,
                forecast_cutoff_at=request.forecast_cutoff_at,
                label_observation_cutoff_at=request.label_observation_cutoff_at,
                label_visibility_mode=request.label_visibility_mode,
                master_identity_resolver_version=request.master_identity_resolver_version,
                mapping_policy_version=request.mapping_policy_version,
                resolved_identity_snapshot_hash=request.resolved_identity_snapshot_hash,
                authority_selection_policy_version=request.authority_selection_policy_version,
            )
            session.add(run)
            await session.flush()

            anchor_season_id, _, node_rows = grouped_rows[0]
            node_payload = _s2_node_canonical_payload(request, rows=node_rows)
            node_payload_hash = sha256_payload(canonical_json_dumps(node_payload))
            authority_evidence = _s2_persisted_authority_evidence(node_rows)
            node = RollingBacktestNode(
                rolling_run_id=run.id,
                season_id=anchor_season_id,
                node_key="s2-single-node",
                node_signature=s2_node_identity_hash(request),
                as_of_local_date=request.forecast_cutoff_at.date(),
                forecast_cutoff_at=request.forecast_cutoff_at,
                forecast_start_local_date=request.forecast_cutoff_at.date() + timedelta(days=1),
                forecast_end_local_date=max(row.target_date for row in node_rows),
                execution_mode="historical_observed",
                upstream_selection_mode="pinned",
                scope=_s2_node_scope(rows=node_rows),
                forecast_horizon_policy_version="v0.2-s2-horizons-7-14-21",
                task10_model_policy=_s2_task10_model_policy(node_rows),
                cutoff_policy_version="v0.2-s2-dual-cutoff-v1",
                timezone="UTC",
                canonical_payload=node_payload,
                canonical_payload_hash=node_payload_hash,
                expected_resolved_input_count=len(authority_evidence),
                expected_availability_audit_count=len(authority_evidence),
            )
            session.add(node)
            await session.flush()

            for evidence in authority_evidence:
                evidence_hash = sha256_payload(evidence.canonical_payload)
                availability_hash = sha256_payload(evidence.availability_payload)
                session.add(
                    RollingBacktestResolvedInput(
                        rolling_node_id=node.id,
                        source_role=evidence.source_role,
                        source_type=evidence.source_type,
                        role_qualifier="s2-persisted-authority",
                        semantic_input_signature=evidence_hash,
                        result_hash=evidence_hash,
                        canonical_payload_hash=evidence_hash,
                        schema_version="v0.2-s2-persisted-authority-v2",
                        policy_version=request.authority_selection_policy_version,
                        persistent_reference_type=None,
                        persistent_reference_value=None,
                        canonical_payload=evidence.canonical_payload,
                        audit_hash=evidence_hash,
                    )
                )
                session.add(
                    RollingBacktestAvailabilityAudit(
                        rolling_node_id=node.id,
                        source_role=evidence.source_role,
                        source_type=evidence.source_type,
                        allowed=evidence.allowed,
                        blocker_code=evidence.blocker_code,
                        canonical_payload=evidence.availability_payload,
                        audit_hash=availability_hash,
                    )
                )
            await session.flush()

            node_by_season = {(row.season_id, row.season_business_key): node for row in rows}
            for row in rows:
                row_payload = s2_binding_row_persistence_payload(row)
                node = node_by_season[(row.season_id, row.season_business_key)]
                session.add(
                    RollingBacktestBindingRow(
                        rolling_run_id=run.id,
                        rolling_node_id=node.id,
                        horizon_days=row.horizon_days,
                        target_date=row.target_date,
                        forecast_cutoff_at=row.forecast_cutoff_at,
                        label_observation_cutoff_at=row.label_observation_cutoff_at,
                        label_visibility_mode=row.label_visibility_mode,
                        physical_alignment_status=row.physical_alignment_status,
                        row_status=row.row_status,
                        reason_code=row.reason_code,
                        forecast_row_identity_hash=(row.forecast_authority.daily_row_identity_hash),
                        actual_label_row_identity_hash=(
                            row.actual_label.label_row_identity_hash
                            if row.actual_label is not None
                            else None
                        ),
                        forecast_value_kg=row.forecast_value_kg,
                        actual_value_kg=row.actual_value_kg,
                        canonical_payload=row_payload,
                        binding_key_hash=row.binding_key_hash,
                        binding_row_hash=row.row_hash,
                    )
                )

            await session.flush()
            pre_seal_result = await session.execute(
                select(RollingBacktestBindingRow)
                .where(RollingBacktestBindingRow.rolling_run_id == run.id)
                .order_by(RollingBacktestBindingRow.binding_key_hash)
            )
            pre_seal_rows = pre_seal_result.scalars().all()
            if len(pre_seal_rows) != len(rows) or any(
                persisted.horizon_days != expected.horizon_days
                or persisted.target_date != expected.target_date
                or persisted.binding_key_hash != expected.binding_key_hash
                or persisted.binding_row_hash != expected.row_hash
                for persisted, expected in zip(pre_seal_rows, rows, strict=True)
            ):
                raise RollingBacktestIntegrityError(
                    "exact S2 binding row set was not persisted before seal"
                )

            session.add(
                RollingBacktestManifest(
                    rolling_run_id=run.id,
                    manifest_schema_version="v0.2-s2-binding-manifest-v1",
                    request_hash=request_hash,
                    instance_hash=instance_hash,
                    coverage_manifest_payload=coverage_payload,
                    exclusion_manifest_payload=exclusions_payload,
                    authority_reference_payload=authority_payload,
                    manifest_hash=manifest_hash,
                )
            )
            await session.flush()
            await _load_s2_logical_run_with_integrity(session, run)
            return run
    except SAIntegrityError as exc:
        existing_result = await session.execute(
            select(RollingBacktestRun).where(
                RollingBacktestRun.backtest_request_hash == request_hash
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is None:
            raise RollingBacktestPersistenceError(
                "S2 historical binding persistence failed before aggregate completion"
            ) from exc
        try:
            await _verify_existing_s2_binding(
                session,
                run=existing,
                request=request,
                rows=rows,
                request_hash=request_hash,
                instance_hash=instance_hash,
                request_payload=request_payload,
                coverage_payload=coverage_payload,
                exclusions_payload=exclusions_payload,
                authority_payload=authority_payload,
                manifest_hash=manifest_hash,
            )
        except RollingBacktestIdentityConflictError as drift:
            raise RollingBacktestIdentityConflictError(
                "S2 concurrent replay carries different or drifted authority evidence"
            ) from drift
        return existing
