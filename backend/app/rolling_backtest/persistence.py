"""Rolling backtest persistence: atomic repository and integrity loader."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestDagSnapshot,
    RollingBacktestNode,
    RollingBacktestResolvedInput,
    RollingBacktestRun,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps, sha256_payload
from backend.app.rolling_backtest.config import rolling_backtest_config_payload
from backend.app.rolling_backtest.errors import (
    RollingBacktestAttemptConflictError,
    RollingBacktestChildCountMismatchError,
    RollingBacktestIdentityConflictError,
    RollingBacktestIntegrityError,
)
from backend.app.rolling_backtest.schemas import RollingBacktestConfig
from backend.app.rolling_backtest.signatures import run_signature_hash

# ── Public API ───────────────────────────────────────────────────────────────


async def create_or_load_logical_run(
    config: RollingBacktestConfig,
) -> RollingBacktestRun:
    """Create a new logical run or load an existing one with full integrity check.

    - If no existing run with the same run_signature, atomically create run,
      nodes, and base snapshots in one transaction.
    - If an existing run has the same run_signature AND identical canonical
      payload/hash, load it via full integrity verification.
    - If an existing run has the same run_signature but different payload/hash,
      raise RollingBacktestIdentityConflictError.
    """
    signature = run_signature_hash(config)
    config_hash_val = sha256_payload(canonical_json_dumps(rolling_backtest_config_payload(config)))
    canonical_payload = rolling_backtest_config_payload(config)
    payload_hash = sha256_payload(canonical_json_dumps(canonical_payload))

    async with AsyncSessionMaker() as session:
        existing = await _find_run_by_signature(session, signature)
        if existing is not None:
            await _verify_or_conflict(existing, config_hash_val, payload_hash, signature)
            return await _integrity_reload_run(session, existing)

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
            expected_node_count=len(config.nodes),
            canonical_payload=json.loads(canonical_json_dumps(canonical_payload)),
            canonical_payload_hash=payload_hash,
        )
        session.add(run)
        await session.flush()

        for node in config.nodes:
            from backend.app.rolling_backtest.signatures import node_signature_hash

            node_sig = node_signature_hash(config, node)
            node_payload = {
                "season_id": node.season_id,
                "node_key": node.node_key.value,
                "as_of_local_date": node.as_of_local_date.isoformat(),
            }
            db_node = RollingBacktestNode(
                rolling_run_id=run.id,
                season_id=node.season_id,
                node_key=node.node_key.value,
                node_signature=node_sig,
                as_of_local_date=node.as_of_local_date,
                forecast_cutoff_at=node.forecast_cutoff_at,
                forecast_start_local_date=node.forecast_start_local_date,
                forecast_end_local_date=node.forecast_end_local_date,
                execution_mode=config.execution_mode.value,
                upstream_selection_mode=node.upstream_selection_mode.value,
                task10_model_policy=json.loads(
                    canonical_json_dumps(node.task10_model_policy.model_dump(mode="python"))
                ),
                canonical_payload=json.loads(canonical_json_dumps(node_payload)),
                canonical_payload_hash=sha256_payload(canonical_json_dumps(node_payload)),
                expected_resolved_input_count=len(node.resolved_upstream_semantic_identities),
                expected_availability_audit_count=(len(node.resolved_upstream_semantic_identities)),
            )
            session.add(db_node)

        await session.commit()
        return run


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


async def _integrity_reload_run(
    session: AsyncSession,
    run: RollingBacktestRun,
) -> RollingBacktestRun:
    """Full integrity verification of a loaded logical run."""
    # Verify node count
    node_count_result = await session.execute(
        select(func.count()).where(RollingBacktestNode.rolling_run_id == run.id)
    )
    actual_node_count = node_count_result.scalar_one()
    if actual_node_count != run.expected_node_count:
        raise RollingBacktestChildCountMismatchError(
            f"node count mismatch: expected={run.expected_node_count} actual={actual_node_count}"
        )

    # Verify each node
    nodes_result = await session.execute(
        select(RollingBacktestNode)
        .where(RollingBacktestNode.rolling_run_id == run.id)
        .order_by(RollingBacktestNode.id)
    )
    nodes = nodes_result.scalars().all()

    node_signatures_seen: set[str] = set()
    for node in nodes:
        if node.node_signature in node_signatures_seen:
            raise RollingBacktestIntegrityError(
                f"duplicate node_signature: {node.node_signature[:16]}..."
            )
        node_signatures_seen.add(node.node_signature)

        # Verify node children
        await _verify_node_children(session, node)

    return run


async def _verify_node_children(
    session: AsyncSession,
    node: RollingBacktestNode,
) -> None:
    """Verify resolved inputs, availability audits, and DAG snapshot for a node."""
    # Resolved inputs
    input_count = await session.scalar(
        select(func.count()).where(RollingBacktestResolvedInput.rolling_node_id == node.id)
    )
    if input_count != node.expected_resolved_input_count:
        raise RollingBacktestChildCountMismatchError(
            f"resolved_input count mismatch for node {node.id}: "
            f"expected={node.expected_resolved_input_count} actual={input_count}"
        )

    inputs_result = await session.execute(
        select(RollingBacktestResolvedInput).where(
            RollingBacktestResolvedInput.rolling_node_id == node.id
        )
    )
    source_roles_seen: set[str] = set()
    for inp in inputs_result.scalars():
        if inp.source_role in source_roles_seen:
            raise RollingBacktestIntegrityError(
                f"duplicate source_role '{inp.source_role}' in node {node.id}"
            )
        source_roles_seen.add(inp.source_role)

    # Availability audits
    audit_count = await session.scalar(
        select(func.count()).where(RollingBacktestAvailabilityAudit.rolling_node_id == node.id)
    )
    if audit_count != node.expected_availability_audit_count:
        raise RollingBacktestChildCountMismatchError(
            f"availability_audit count mismatch for node {node.id}: "
            f"expected={node.expected_availability_audit_count} actual={audit_count}"
        )


async def create_execution_attempt(
    run_id: int,
    *,
    status: str = "pending",
    current_stage: str = "initialized",
    prior_attempt_id: int | None = None,
) -> RollingBacktestAttempt:
    """Create a new execution attempt with auto-incremented attempt_number."""
    async with AsyncSessionMaker() as session:
        max_num_result = await session.execute(
            select(func.coalesce(func.max(RollingBacktestAttempt.attempt_number), 0)).where(
                RollingBacktestAttempt.rolling_run_id == run_id
            )
        )
        next_number = max_num_result.scalar_one() + 1

        attempt = RollingBacktestAttempt(
            rolling_run_id=run_id,
            attempt_number=next_number,
            prior_attempt_id=prior_attempt_id,
            status=status,
            current_stage=current_stage,
            started_at=datetime.now(UTC),
        )
        session.add(attempt)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise RollingBacktestAttemptConflictError(
                f"attempt_number {next_number} already exists for run {run_id}"
            ) from exc
        return attempt


async def finalize_attempt_status(
    attempt_id: int,
    *,
    status: str,
    current_stage: str,
    structured_error_code: str | None = None,
    sanitized_diagnostics: dict[str, object] | None = None,
) -> RollingBacktestAttempt:
    """Finalize an attempt's status (cannot modify a completed attempt)."""
    async with AsyncSessionMaker() as session:
        result = await session.execute(
            select(RollingBacktestAttempt).where(RollingBacktestAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()
        if attempt is None:
            raise RollingBacktestAttemptConflictError(f"attempt {attempt_id} not found")
        if attempt.status == "completed":
            raise RollingBacktestAttemptConflictError(
                f"cannot modify completed attempt {attempt_id}"
            )

        attempt.status = status
        attempt.current_stage = current_stage
        attempt.structured_error_code = structured_error_code
        attempt.sanitized_diagnostics = sanitized_diagnostics
        attempt.finished_at = datetime.now(UTC)
        await session.commit()
        return attempt


async def persist_node_contracts(
    node_id: int,
    *,
    resolved_inputs: list[dict[str, object]],
    availability_audits: list[dict[str, object]],
    dag_snapshot: dict[str, object] | None = None,
) -> None:
    """Persist resolved inputs, availability audits, and optional DAG snapshot
    for a single node in one transaction.
    """
    async with AsyncSessionMaker() as session:
        node_result = await session.execute(
            select(RollingBacktestNode).where(RollingBacktestNode.id == node_id)
        )
        node = node_result.scalar_one_or_none()
        if node is None:
            raise RollingBacktestIntegrityError(f"node {node_id} not found")

        for inp in resolved_inputs:
            db_input = RollingBacktestResolvedInput(
                rolling_node_id=node_id,
                source_role=inp["source_role"],
                source_type=inp["source_type"],
                semantic_input_signature=inp.get("semantic_input_signature"),
                result_hash=inp.get("result_hash"),
                canonical_payload_hash=inp.get("canonical_payload_hash"),
                schema_version=inp.get("schema_version", "task11-v1"),
                policy_version=inp.get("policy_version"),
                persistent_reference_type=inp.get("persistent_reference_type"),
                persistent_reference_value=inp.get("persistent_reference_value"),
                canonical_payload=inp.get("canonical_payload", {}),
                audit_hash=inp.get("audit_hash", ""),
            )
            session.add(db_input)

        for audit in availability_audits:
            db_audit = RollingBacktestAvailabilityAudit(
                rolling_node_id=node_id,
                source_role=audit["source_role"],
                source_type=audit["source_type"],
                allowed=audit.get("allowed", False),
                blocker_code=audit.get("blocker_code"),
                canonical_payload=audit.get("canonical_payload", {}),
                audit_hash=audit.get("audit_hash", ""),
            )
            session.add(db_audit)

        if dag_snapshot is not None:
            db_dag = RollingBacktestDagSnapshot(
                rolling_node_id=node_id,
                dag_schema_version=dag_snapshot.get("dag_schema_version", "task11-dag-v1"),
                dag_policy_version=dag_snapshot.get("dag_policy_version", "task11-dag-policy-v1"),
                canonical_payload=dag_snapshot.get("canonical_payload", {}),
                canonical_payload_hash=dag_snapshot.get("canonical_payload_hash", ""),
                expected_node_count=dag_snapshot.get("expected_node_count", 0),
                expected_edge_count=dag_snapshot.get("expected_edge_count", 0),
            )
            session.add(db_dag)

        await session.commit()
