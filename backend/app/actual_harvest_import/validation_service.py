from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.actual_harvest_import.api_errors import (
    ActualHarvestApiError,
    ActualHarvestApiErrorCode,
)
from backend.app.actual_harvest_import.api_schemas import ActualHarvestApiValidationSummary
from backend.app.actual_harvest_import.canonical_hashes import (
    compute_canonical_record_hash,
    ordered_records,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestRecordStatus,
    ActualHarvestValidationErrorCode,
    ActualHarvestValidationSeverity,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.persistence import _record_to_schema
from backend.app.actual_harvest_import.validation_hashes import (
    compute_committed_lineage_basis_hash,
    compute_instance_identity_hash,
    compute_lineage_graph_hash,
    compute_lineage_node_hash,
    compute_mapping_entry_hash,
    compute_mapping_registry_hash,
    compute_mapping_snapshot_hash,
    compute_record_manifest_hash,
    compute_request_identity_hash,
    compute_resolved_identity_snapshot_hash,
    compute_validation_result_hash,
    digest,
)
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingPolicyRegistryModel,
    ActualHarvestMappingRegistryEntryModel,
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationAttemptModel,
    ActualHarvestValidationErrorModel,
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationLineageBasisModel,
    ActualHarvestValidationLineageEdgeModel,
    ActualHarvestValidationLineageNodeModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationRecordModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.app.rolling_backtest.canonical import canonical_json_dumps

VALIDATION_LEASE = timedelta(minutes=10)
VALIDATION_HEARTBEAT_RECORD_INTERVAL = 100
AUTHORITY_POLICY_VERSION = "actual-harvest-lineage-authority-v1"
SUBFARM_ONLY_POLICY = "SUBFARM_ONLY_PLOT_REJECTED"


@dataclass(frozen=True)
class ValidationSummary:
    validation_status: str
    validation_run_identity: str | None
    validation_result_hash: str | None
    lineage_graph_hash: str | None
    mapping_snapshot_hash: str | None
    resolved_identity_snapshot_hash: str | None
    committed_lineage_basis_hash: str | None
    valid_count: int
    invalid_count: int
    error_count: int
    warning_count: int

    def as_api(self) -> ActualHarvestApiValidationSummary:
        return ActualHarvestApiValidationSummary.model_validate(self.__dict__)


@dataclass(frozen=True)
class ValidationErrorValue:
    severity: str
    code: str
    record_index: int | None
    logical_id: str | None
    revision_id: str | None
    field_path: str | None
    details: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "error_code": self.code,
            "record_index": self.record_index,
            "external_logical_record_id": self.logical_id,
            "external_revision_id": self.revision_id,
            "field_path": self.field_path,
            "message_template_id": self.code,
            "details": self.details,
        }


@dataclass(frozen=True)
class ValidationEvidence:
    batch_id: int
    run_id: int
    attempt_id: str
    attempt_generation: int
    fencing_token: str
    request_identity_hash: str
    instance_identity_hash: str
    seal_manifest_hash: str
    mapping_policy_version: str
    validation_policy_version: str
    registry_version: str
    registry_content_hash: str
    mapping_snapshot_hash: str
    resolved_identity_snapshot_hash: str
    record_manifest_hash: str
    committed_lineage_basis_hash: str
    lineage_graph_hash: str
    validation_result_hash: str
    records: tuple[dict[str, Any], ...]
    errors: tuple[ValidationErrorValue, ...]
    warnings: tuple[ValidationErrorValue, ...]
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    basis_members: tuple[dict[str, Any], ...]
    mapping_outcomes: tuple[dict[str, Any], ...]
    mapping_entries: tuple[dict[str, Any], ...]
    counts: dict[str, int]
    status: str


@dataclass(frozen=True)
class ValidationStart:
    kind: str
    run_id: int | None = None
    attempt_id: str | None = None
    attempt_generation: int | None = None
    fencing_token: str | None = None
    summary: ValidationSummary | None = None


def _api_error(code: ActualHarvestApiErrorCode, message: str, status: int) -> ActualHarvestApiError:
    return ActualHarvestApiError(code, message, status_code=status)


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _database_utc_now(session: Session) -> datetime:
    value = session.scalar(select(func.current_timestamp()))
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, str):
        return _ensure_aware(datetime.fromisoformat(value))
    raise _api_error(
        ActualHarvestApiErrorCode.API_INTEGRITY_ERROR,
        "database clock is unavailable",
        500,
    )


def _error(
    code: ActualHarvestValidationErrorCode | str,
    *,
    record_index: int | None = None,
    logical_id: str | None = None,
    revision_id: str | None = None,
    field_path: str | None = None,
    details: dict[str, Any] | None = None,
    severity: ActualHarvestValidationSeverity = ActualHarvestValidationSeverity.ERROR,
) -> ValidationErrorValue:
    return ValidationErrorValue(
        severity=severity.value,
        code=code.value if isinstance(code, ActualHarvestValidationErrorCode) else code,
        record_index=record_index,
        logical_id=logical_id,
        revision_id=revision_id,
        field_path=field_path,
        details=details or {},
    )


def _sorted_errors(values: list[ValidationErrorValue]) -> tuple[ValidationErrorValue, ...]:
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.record_index if item.record_index is not None else 0,
                item.logical_id or "",
                item.revision_id or "",
                item.field_path or "",
                item.code,
            ),
        )
    )


def _stable_sort_key(error: ValidationErrorValue) -> str:
    ordering = canonical_json_dumps(
        [
            error.record_index if error.record_index is not None else 0,
            error.logical_id or "",
            error.revision_id or "",
            error.field_path or "",
            error.code,
        ]
    )
    return f"{ordering}|{digest(error.payload())}"


def _entry_payload(entry: ActualHarvestMappingRegistryEntryModel) -> dict[str, Any]:
    return {
        "source_field": entry.source_field,
        "source_code": entry.source_code,
        "target_type": entry.target_type,
        "target_business_key": entry.target_business_key,
        "target_parent_business_key": entry.target_parent_business_key,
        "farm_timezone": entry.farm_timezone,
    }


def create_mapping_registry(
    session: Session,
    *,
    registry_version: str,
    source_system: str,
    mapping_policy_version: str,
    entries: tuple[dict[str, Any], ...],
    now: datetime,
) -> ActualHarvestMappingPolicyRegistryModel:
    """Internal master-data operation; no public actual-harvest route calls this."""
    registry = ActualHarvestMappingPolicyRegistryModel(
        registry_version=registry_version,
        source_system=source_system,
        mapping_policy_version=mapping_policy_version,
        status="DRAFT",
        entry_count=0,
        created_at=now,
    )
    session.add(registry)
    session.flush()
    for raw_entry in entries:
        payload = {
            "source_field": raw_entry["source_field"],
            "source_code": raw_entry["source_code"],
            "target_type": raw_entry["target_type"],
            "target_business_key": raw_entry["target_business_key"],
            "target_parent_business_key": raw_entry.get("target_parent_business_key"),
            "farm_timezone": raw_entry.get("farm_timezone"),
        }
        session.add(
            ActualHarvestMappingRegistryEntryModel(
                registry_id=registry.id,
                **payload,
                entry_hash=compute_mapping_entry_hash(payload),
            )
        )
    session.flush()
    registry.entry_count = len(entries)
    return registry


def seal_mapping_registry(
    session: Session, *, mapping_policy_version: str, now: datetime
) -> ActualHarvestMappingPolicyRegistryModel:
    registry = session.scalar(
        select(ActualHarvestMappingPolicyRegistryModel)
        .where(
            ActualHarvestMappingPolicyRegistryModel.mapping_policy_version == mapping_policy_version
        )
        .with_for_update()
    )
    if registry is None:
        raise _api_error(
            ActualHarvestApiErrorCode.IDENTITY_MAPPING_POLICY_VERSION_MISSING,
            "mapping policy version is not registered",
            422,
        )
    if registry.status == "SEALED":
        return registry
    entries = session.scalars(
        select(ActualHarvestMappingRegistryEntryModel).where(
            ActualHarvestMappingRegistryEntryModel.registry_id == registry.id
        )
    ).all()
    payloads = tuple(_entry_payload(entry) for entry in entries)
    registry.entry_count = len(payloads)
    registry.registry_content_hash = compute_mapping_registry_hash(payloads)
    registry.status = "SEALED"
    registry.sealed_at = now
    session.flush()
    return registry


def _load_registry(
    session: Session, *, source_system: str, mapping_policy_version: str
) -> tuple[
    ActualHarvestMappingPolicyRegistryModel, tuple[ActualHarvestMappingRegistryEntryModel, ...]
]:
    if not mapping_policy_version:
        raise _api_error(
            ActualHarvestApiErrorCode.IDENTITY_MAPPING_POLICY_VERSION_MISSING,
            "mapping policy version is required",
            422,
        )
    registry = session.scalar(
        select(ActualHarvestMappingPolicyRegistryModel).where(
            ActualHarvestMappingPolicyRegistryModel.source_system == source_system,
            ActualHarvestMappingPolicyRegistryModel.mapping_policy_version
            == mapping_policy_version,
        )
    )
    if registry is None:
        raise _api_error(
            ActualHarvestApiErrorCode.IDENTITY_MAPPING_POLICY_VERSION_MISSING,
            "mapping policy version is not registered",
            422,
        )
    if registry.status != "SEALED" or registry.registry_content_hash is None:
        raise _api_error(
            ActualHarvestApiErrorCode.IDENTITY_MAPPING_REGISTRY_NOT_SEALED,
            "mapping registry is not sealed",
            422,
        )
    entries = tuple(
        session.scalars(
            select(ActualHarvestMappingRegistryEntryModel)
            .where(ActualHarvestMappingRegistryEntryModel.registry_id == registry.id)
            .order_by(
                ActualHarvestMappingRegistryEntryModel.source_field,
                ActualHarvestMappingRegistryEntryModel.source_code,
            )
        ).all()
    )
    computed = compute_mapping_registry_hash(_entry_payload(entry) for entry in entries)
    if computed != registry.registry_content_hash or registry.entry_count != len(entries):
        raise _api_error(
            ActualHarvestApiErrorCode.IDENTITY_MAPPING_REGISTRY_HASH_CHANGED,
            "mapping registry content hash does not match its entries",
            409,
        )
    return registry, entries


def _all_batch_records(session: Session, batch_id: int) -> tuple[Any, ...]:
    rows = session.scalars(
        select(ActualHarvestImportRecordModel)
        .where(ActualHarvestImportRecordModel.batch_id == batch_id)
        .order_by(
            ActualHarvestImportRecordModel.source_system,
            ActualHarvestImportRecordModel.external_logical_record_id,
            ActualHarvestImportRecordModel.revision_number,
            ActualHarvestImportRecordModel.external_revision_id,
        )
    ).all()
    return tuple(_record_to_schema(row) for row in rows)


def _basis_members(
    session: Session,
    *,
    batch: ActualHarvestImportBatchModel,
    logical_ids: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    if not logical_ids:
        return ()
    rows = session.scalars(
        select(ActualHarvestImportRecordModel)
        .join(
            ActualHarvestImportBatchModel,
            ActualHarvestImportBatchModel.id == ActualHarvestImportRecordModel.batch_id,
        )
        .where(
            ActualHarvestImportBatchModel.status == ActualHarvestImportBatchStatus.COMMITTED.value,
            ActualHarvestImportBatchModel.source_system == batch.source_system,
            ActualHarvestImportRecordModel.source_system == batch.source_system,
            ActualHarvestImportRecordModel.external_logical_record_id.in_(logical_ids),
        )
    ).all()
    members = []
    for row in rows:
        record = _record_to_schema(row)
        members.append(
            {
                "source_system": record.source_system,
                "committed_batch_ref": f"{record.source_system}:{record.external_batch_id}",
                "external_logical_record_id": record.external_logical_record_id,
                "external_revision_id": record.external_revision_id,
                "revision_number": record.revision_number,
                "canonical_record_hash": compute_canonical_record_hash(record),
                "predecessor_revision_id": record.supersedes_external_revision_id,
                "record_status": record.record_status.value,
                "source_recorded_at": record.source_recorded_at,
                "source_recorded_at_authority_status": (
                    record.source_recorded_at_authority_status.value
                ),
            }
        )
    return tuple(
        sorted(
            members,
            key=lambda item: (
                item["source_system"],
                item["external_logical_record_id"],
                item["revision_number"],
                item["external_revision_id"],
                item["committed_batch_ref"],
            ),
        )
    )


def _current_basis(
    session: Session, batch: ActualHarvestImportBatchModel
) -> tuple[str, tuple[dict[str, Any], ...]]:
    current_records = _all_batch_records(session, batch.id)
    logical_ids = tuple(sorted({record.external_logical_record_id for record in current_records}))
    members = _basis_members(session, batch=batch, logical_ids=logical_ids)
    return compute_committed_lineage_basis_hash(members), members


def _new_attempt(
    session: Session,
    *,
    run: ActualHarvestValidationRunModel,
    now: datetime,
) -> ActualHarvestValidationAttemptModel:
    generation = run.active_attempt_generation + 1
    attempt = ActualHarvestValidationAttemptModel(
        validation_run_id=run.id,
        attempt_id=uuid4().hex,
        attempt_generation=generation,
        fencing_token=uuid4().hex,
        started_at=now,
        heartbeat_at=now,
        lease_expires_at=now + VALIDATION_LEASE,
        status="ACTIVE",
    )
    session.add(attempt)
    session.flush()
    run.active_attempt_id = attempt.attempt_id
    run.active_attempt_generation = generation
    return attempt


def renew_validation_attempt_lease(
    session: Session,
    *,
    validation_run_id: int,
    attempt_id: str,
    attempt_generation: int,
    fencing_token: str,
) -> datetime:
    run = session.scalar(
        select(ActualHarvestValidationRunModel)
        .where(ActualHarvestValidationRunModel.id == validation_run_id)
        .with_for_update()
    )
    attempt = session.scalar(
        select(ActualHarvestValidationAttemptModel)
        .where(ActualHarvestValidationAttemptModel.attempt_id == attempt_id)
        .with_for_update()
    )
    if run is None or attempt is None:
        raise _api_error(
            ActualHarvestApiErrorCode.VALIDATION_EVIDENCE_STALE,
            "validation attempt is no longer active",
            409,
        )
    now = _database_utc_now(session)
    if not (
        run.is_current
        and run.active_attempt_id == attempt_id
        and run.active_attempt_generation == attempt_generation
        and attempt.fencing_token == fencing_token
        and attempt.status == "ACTIVE"
        and _ensure_aware(attempt.lease_expires_at) > now
    ):
        raise _api_error(
            ActualHarvestApiErrorCode.VALIDATION_EVIDENCE_STALE,
            "validation attempt is no longer active",
            409,
        )
    attempt.heartbeat_at = now
    attempt.lease_expires_at = now + VALIDATION_LEASE
    session.flush()
    return now


def _run_summary(run: ActualHarvestValidationRunModel) -> ValidationSummary:
    return ValidationSummary(
        validation_status=run.status,
        validation_run_identity=run.instance_identity_hash,
        validation_result_hash=run.validation_result_hash,
        lineage_graph_hash=run.lineage_graph_hash,
        mapping_snapshot_hash=run.mapping_snapshot_hash,
        resolved_identity_snapshot_hash=run.resolved_identity_snapshot_hash,
        committed_lineage_basis_hash=run.committed_lineage_basis_hash,
        valid_count=run.valid_count,
        invalid_count=run.invalid_count,
        error_count=run.error_count,
        warning_count=run.warning_count,
    )


def begin_validation(session: Session, *, import_id: str, now: datetime) -> ValidationStart:
    now = _database_utc_now(session)
    batch = session.scalar(
        select(ActualHarvestImportBatchModel)
        .where(ActualHarvestImportBatchModel.import_id == import_id)
        .with_for_update()
    )
    if batch is None:
        raise _api_error(ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND, "import not found", 404)
    if batch.status == ActualHarvestImportBatchStatus.CANCELLED.value:
        raise _api_error(
            ActualHarvestApiErrorCode.IMPORT_BATCH_CANCELLED, "import is cancelled", 409
        )
    if batch.status not in {
        ActualHarvestImportBatchStatus.SEALED.value,
        ActualHarvestImportBatchStatus.VALIDATING.value,
        ActualHarvestImportBatchStatus.VALIDATED.value,
        ActualHarvestImportBatchStatus.VALIDATION_FAILED.value,
    }:
        raise _api_error(ActualHarvestApiErrorCode.BATCH_NOT_SEALED, "import is not sealed", 409)
    if batch.seal_manifest_hash_or_null is None:
        raise _api_error(
            ActualHarvestApiErrorCode.BATCH_NOT_SEALED, "seal evidence is missing", 409
        )
    registry, entries = _load_registry(
        session,
        source_system=batch.source_system,
        mapping_policy_version=batch.mapping_policy_version,
    )
    del entries
    basis_hash, _ = _current_basis(session, batch)
    request_hash = compute_request_identity_hash(
        import_id=batch.import_id,
        seal_manifest_hash=batch.seal_manifest_hash_or_null,
        mapping_policy_version=batch.mapping_policy_version,
        validation_policy_version=batch.validation_policy_version,
    )
    instance_hash = compute_instance_identity_hash(
        import_id=batch.import_id,
        seal_manifest_hash=batch.seal_manifest_hash_or_null,
        mapping_policy_version=batch.mapping_policy_version,
        validation_policy_version=batch.validation_policy_version,
        committed_lineage_basis_hash=basis_hash,
    )
    current = session.scalar(
        select(ActualHarvestValidationRunModel)
        .where(
            ActualHarvestValidationRunModel.batch_id == batch.id,
            ActualHarvestValidationRunModel.is_current.is_(True),
        )
        .with_for_update()
    )
    if current is not None and current.instance_identity_hash == instance_hash:
        if current.status in {"VALIDATED", "VALIDATION_FAILED"}:
            return ValidationStart(kind="replay", summary=_run_summary(current))
        if current.status == "VALIDATING":
            active = None
            if current.active_attempt_id:
                active = session.scalar(
                    select(ActualHarvestValidationAttemptModel).where(
                        ActualHarvestValidationAttemptModel.attempt_id == current.active_attempt_id
                    )
                )
            if (
                active is not None
                and active.status == "ACTIVE"
                and _ensure_aware(active.lease_expires_at) > now
            ):
                return ValidationStart(kind="in_progress")
            if active is not None and active.status == "ACTIVE":
                active.status = "ABANDONED"
                active.abandoned_at = now
            attempt = _new_attempt(session, run=current, now=now)
            batch.status = ActualHarvestImportBatchStatus.VALIDATING.value
            session.flush()
            return ValidationStart(
                kind="execute",
                run_id=current.id,
                attempt_id=attempt.attempt_id,
                attempt_generation=attempt.attempt_generation,
                fencing_token=attempt.fencing_token,
            )
    if current is not None:
        current.is_current = False
        current.superseded_at = now
        if current.active_attempt_id:
            active = session.scalar(
                select(ActualHarvestValidationAttemptModel).where(
                    ActualHarvestValidationAttemptModel.attempt_id == current.active_attempt_id
                )
            )
            if active is not None and active.status == "ACTIVE":
                active.status = "STALE"
                active.abandoned_at = now
    run = ActualHarvestValidationRunModel(
        batch_id=batch.id,
        request_identity_hash=request_hash,
        instance_identity_hash=instance_hash,
        seal_manifest_hash=batch.seal_manifest_hash_or_null,
        mapping_policy_version=batch.mapping_policy_version,
        validation_policy_version=batch.validation_policy_version,
        committed_lineage_basis_hash=basis_hash,
        registry_content_hash=registry.registry_content_hash,
        record_manifest_hash=compute_record_manifest_hash(_all_batch_records(session, batch.id)),
        status="VALIDATING",
        is_current=True,
        active_attempt_generation=0,
        created_at=now,
    )
    session.add(run)
    session.flush()
    attempt = _new_attempt(session, run=run, now=now)
    batch.status = ActualHarvestImportBatchStatus.VALIDATING.value
    session.flush()
    return ValidationStart(
        kind="execute",
        run_id=run.id,
        attempt_id=attempt.attempt_id,
        attempt_generation=attempt.attempt_generation,
        fencing_token=attempt.fencing_token,
    )


def _resolved_master_hash(
    *,
    target_type: str,
    business_key: str,
    parent_business_key: str | None,
    season_start: Any = None,
    season_end: Any = None,
) -> str:
    return digest(
        {
            "target_type": target_type,
            "business_key": business_key,
            "parent_business_key": parent_business_key,
            "season_start_date": season_start.isoformat() if season_start else None,
            "season_end_date": season_end.isoformat() if season_end else None,
        }
    )


def _mapping_outcomes(
    session: Session,
    *,
    records: tuple[Any, ...],
    entries: tuple[ActualHarvestMappingRegistryEntryModel, ...],
    registry_version: str,
    mapping_policy_version: str,
    heartbeat: Any | None = None,
) -> tuple[list[dict[str, Any]], list[ValidationErrorValue]]:
    by_key = {(entry.source_field, entry.source_code): entry for entry in entries}
    outcomes: list[dict[str, Any]] = []
    errors: list[ValidationErrorValue] = []
    field_values = {
        "season_code": "SEASON",
        "farm_code": "FARM",
        "subfarm_or_plot_code": "SUBFARM",
        "variety_code": "VARIETY",
    }
    for index, record in enumerate(records, start=1):
        for field, expected_target in field_values.items():
            source_code = getattr(record, field)
            entry = by_key.get((field, source_code)) if source_code else None
            if field == "season_code" and not source_code:
                candidates = session.scalars(
                    select(Season).where(
                        Season.start_date <= record.harvest_business_date,
                        Season.end_date >= record.harvest_business_date,
                    )
                ).all()
                if len(candidates) == 0:
                    errors.append(
                        _error(
                            ActualHarvestValidationErrorCode.SEASON_RESOLUTION_NOT_FOUND,
                            record_index=index,
                            logical_id=record.external_logical_record_id,
                            revision_id=record.external_revision_id,
                            field_path=field,
                        )
                    )
                    continue
                if len(candidates) != 1:
                    errors.append(
                        _error(
                            ActualHarvestValidationErrorCode.SEASON_RESOLUTION_AMBIGUOUS,
                            record_index=index,
                            logical_id=record.external_logical_record_id,
                            revision_id=record.external_revision_id,
                            field_path=field,
                        )
                    )
                    continue
                season = candidates[0]
                outcomes.append(
                    {
                        "record_index": index,
                        "source_system": record.source_system,
                        "external_logical_record_id": record.external_logical_record_id,
                        "external_revision_id": record.external_revision_id,
                        "revision_number": record.revision_number,
                        "source_field": field,
                        "source_code": None,
                        "target_type": expected_target,
                        "target_business_key": season.code,
                        "target_parent_business_key": None,
                        "registry_version": registry_version,
                        "mapping_policy_version": mapping_policy_version,
                        "registry_entry_hash": None,
                        "resolved_master_business_key": season.code,
                        "resolved_master_parent_business_key": None,
                        "resolved_master_id": season.id,
                        "resolved_master_record_hash": _resolved_master_hash(
                            target_type=expected_target,
                            business_key=season.code,
                            parent_business_key=None,
                            season_start=season.start_date,
                            season_end=season.end_date,
                        ),
                        "resolution_mode": "DATE_RANGE",
                        "outcome": "MAPPED",
                    }
                )
                continue
            if source_code is None:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.IDENTITY_MAPPING_NOT_FOUND,
                        record_index=index,
                        logical_id=record.external_logical_record_id,
                        revision_id=record.external_revision_id,
                        field_path=field,
                    )
                )
                continue
            if entry is None:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.IDENTITY_MAPPING_NOT_FOUND,
                        record_index=index,
                        logical_id=record.external_logical_record_id,
                        revision_id=record.external_revision_id,
                        field_path=field,
                    )
                )
                continue
            if entry.target_type != expected_target or entry.target_type == "PLOT":
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.IDENTITY_MAPPING_TARGET_TYPE_UNSUPPORTED,
                        record_index=index,
                        logical_id=record.external_logical_record_id,
                        revision_id=record.external_revision_id,
                        field_path=field,
                        details={"policy": SUBFARM_ONLY_POLICY},
                    )
                )
                continue
            target: Any | None = None
            if expected_target == "SEASON":
                season_targets = session.scalars(
                    select(Season).where(Season.code == entry.target_business_key)
                ).all()
                if len(season_targets) > 1:
                    errors.append(
                        _error(
                            ActualHarvestValidationErrorCode.IDENTITY_MAPPING_AMBIGUOUS,
                            record_index=index,
                            logical_id=record.external_logical_record_id,
                            revision_id=record.external_revision_id,
                            field_path=field,
                        )
                    )
                    continue
                if len(season_targets) == 1:
                    target = season_targets[0]
                    if not (target.start_date <= record.harvest_business_date <= target.end_date):
                        errors.append(
                            _error(
                                ActualHarvestValidationErrorCode.SEASON_BUSINESS_DATE_MISMATCH,
                                record_index=index,
                                logical_id=record.external_logical_record_id,
                                revision_id=record.external_revision_id,
                                field_path=field,
                            )
                        )
                        continue
            elif expected_target == "FARM":
                farm_targets = session.scalars(
                    select(Farm).where(Farm.name == entry.target_business_key)
                ).all()
                if len(farm_targets) > 1:
                    errors.append(
                        _error(
                            ActualHarvestValidationErrorCode.IDENTITY_MAPPING_AMBIGUOUS,
                            record_index=index,
                            logical_id=record.external_logical_record_id,
                            revision_id=record.external_revision_id,
                            field_path=field,
                        )
                    )
                    continue
                if len(farm_targets) == 1:
                    target = farm_targets[0]
            elif expected_target == "VARIETY":
                variety_targets = session.scalars(
                    select(Variety).where(Variety.code == entry.target_business_key)
                ).all()
                if len(variety_targets) > 1:
                    errors.append(
                        _error(
                            ActualHarvestValidationErrorCode.IDENTITY_MAPPING_AMBIGUOUS,
                            record_index=index,
                            logical_id=record.external_logical_record_id,
                            revision_id=record.external_revision_id,
                            field_path=field,
                        )
                    )
                    continue
                if len(variety_targets) == 1:
                    target = variety_targets[0]
            else:
                subfarm_targets = session.execute(
                    select(Subfarm, Farm)
                    .join(Farm, Farm.id == Subfarm.farm_id)
                    .where(
                        Subfarm.name == entry.target_business_key,
                        Farm.name == entry.target_parent_business_key,
                    )
                ).all()
                if len(subfarm_targets) > 1:
                    errors.append(
                        _error(
                            ActualHarvestValidationErrorCode.IDENTITY_MAPPING_AMBIGUOUS,
                            record_index=index,
                            logical_id=record.external_logical_record_id,
                            revision_id=record.external_revision_id,
                            field_path=field,
                        )
                    )
                    continue
                if len(subfarm_targets) == 1:
                    target = subfarm_targets[0]
            if target is None:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.IDENTITY_MAPPING_NOT_FOUND,
                        record_index=index,
                        logical_id=record.external_logical_record_id,
                        revision_id=record.external_revision_id,
                        field_path=field,
                    )
                )
                continue
            if expected_target == "SEASON":
                resolved_key = target.code
                resolved_parent = None
                resolved_hash = _resolved_master_hash(
                    target_type=expected_target,
                    business_key=resolved_key,
                    parent_business_key=resolved_parent,
                    season_start=target.start_date,
                    season_end=target.end_date,
                )
            elif expected_target == "FARM":
                resolved_key = target.name
                resolved_parent = None
                resolved_hash = _resolved_master_hash(
                    target_type=expected_target,
                    business_key=resolved_key,
                    parent_business_key=resolved_parent,
                )
            elif expected_target == "VARIETY":
                resolved_key = target.code
                resolved_parent = None
                resolved_hash = _resolved_master_hash(
                    target_type=expected_target,
                    business_key=resolved_key,
                    parent_business_key=resolved_parent,
                )
            else:
                subfarm, farm = target
                resolved_key = subfarm.name
                resolved_parent = farm.name
                resolved_hash = _resolved_master_hash(
                    target_type=expected_target,
                    business_key=resolved_key,
                    parent_business_key=resolved_parent,
                )
            outcomes.append(
                {
                    "record_index": index,
                    "source_system": record.source_system,
                    "external_logical_record_id": record.external_logical_record_id,
                    "external_revision_id": record.external_revision_id,
                    "revision_number": record.revision_number,
                    "source_field": field,
                    "source_code": source_code,
                    "target_type": expected_target,
                    "target_business_key": entry.target_business_key,
                    "target_parent_business_key": entry.target_parent_business_key,
                    "registry_version": registry_version,
                    "mapping_policy_version": mapping_policy_version,
                    "registry_entry_hash": entry.entry_hash,
                    "resolved_master_business_key": resolved_key,
                    "resolved_master_parent_business_key": resolved_parent,
                    "resolved_master_id": target.id
                    if expected_target != "SUBFARM"
                    else target[0].id,
                    "resolved_master_record_hash": resolved_hash,
                    "resolution_mode": "REGISTRY_EXACT",
                    "outcome": "MAPPED",
                }
            )
        if heartbeat is not None and index % VALIDATION_HEARTBEAT_RECORD_INTERVAL == 0:
            heartbeat()
    return outcomes, errors


def _lineage_evidence(
    records: tuple[Any, ...],
    basis_members: tuple[dict[str, Any], ...],
    heartbeat: Any | None = None,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[ValidationErrorValue, ...],
]:
    nodes: list[dict[str, Any]] = []
    errors: list[ValidationErrorValue] = []
    combined: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        combined.append(
            {
                "origin": "CURRENT_BATCH_REVISION",
                "record": record,
                "committed_batch_ref": None,
            }
        )
        if heartbeat is not None and index % VALIDATION_HEARTBEAT_RECORD_INTERVAL == 0:
            heartbeat()
    for member in basis_members:
        combined.append(
            {
                "origin": "COMMITTED_HISTORY_REVISION",
                "record": None,
                "member": member,
                "committed_batch_ref": member["committed_batch_ref"],
            }
        )

    def _item_field(item: dict[str, Any], field: str) -> Any:
        record = item.get("record")
        if record is not None:
            return getattr(record, field)
        return item["member"][field]

    combined.sort(
        key=lambda item: (
            _item_field(item, "source_system"),
            _item_field(item, "external_logical_record_id"),
            _item_field(item, "revision_number"),
            _item_field(item, "external_revision_id"),
            item["origin"],
        )
    )
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in combined:
        record = item.get("record")
        history_member = cast(dict[str, Any], item.get("member"))
        source = record.source_system if record is not None else history_member["source_system"]
        revision_id = (
            record.external_revision_id
            if record is not None
            else history_member["external_revision_id"]
        )
        logical_id = (
            record.external_logical_record_id
            if record is not None
            else history_member["external_logical_record_id"]
        )
        revision_number = (
            record.revision_number if record is not None else history_member["revision_number"]
        )
        status = (
            record.record_status.value if record is not None else history_member["record_status"]
        )
        predecessor = (
            record.supersedes_external_revision_id
            if record is not None
            else history_member["predecessor_revision_id"]
        )
        record_hash = (
            compute_canonical_record_hash(record)
            if record is not None
            else history_member["canonical_record_hash"]
        )
        node = {
            "origin": item["origin"],
            "source_system": source,
            "external_logical_record_id": logical_id,
            "external_revision_id": revision_id,
            "revision_number": revision_number,
            "record_status": status,
            "supersedes_external_revision_id": predecessor,
            "canonical_record_hash": record_hash,
            "source_recorded_at": record.source_recorded_at
            if record is not None
            else history_member["source_recorded_at"],
            "source_recorded_at_authority_status": (
                record.source_recorded_at_authority_status.value
                if record is not None
                else history_member["source_recorded_at_authority_status"]
            ),
        }
        key = (source, revision_id)
        previous = by_key.get(key)
        if previous is not None and previous["canonical_record_hash"] != record_hash:
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.REVISION_IDENTITY_CONFLICT,
                    logical_id=logical_id,
                    revision_id=revision_id,
                )
            )
            continue
        by_key[key] = node
        node["node_hash"] = compute_lineage_node_hash(node)
        nodes.append(node)
    unique_nodes = tuple(
        sorted(
            by_key.values(),
            key=lambda item: (
                item["source_system"],
                item["external_logical_record_id"],
                item["revision_number"],
                item["external_revision_id"],
                item["origin"],
            ),
        )
    )
    edges: list[dict[str, Any]] = []
    successors: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for node in unique_nodes:
        predecessor = node["supersedes_external_revision_id"]
        if predecessor is None:
            if node["revision_number"] != 1:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.REVISION_PREDECESSOR_MISSING,
                        logical_id=node["external_logical_record_id"],
                        revision_id=node["external_revision_id"],
                    )
                )
            continue
        predecessor_node = by_key.get((node["source_system"], predecessor))
        if predecessor_node is None:
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.REVISION_PREDECESSOR_MISSING,
                    logical_id=node["external_logical_record_id"],
                    revision_id=node["external_revision_id"],
                )
            )
            continue
        if predecessor_node["external_logical_record_id"] != node["external_logical_record_id"]:
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.REVISION_LOGICAL_RECORD_MISMATCH,
                    logical_id=node["external_logical_record_id"],
                    revision_id=node["external_revision_id"],
                )
            )
        if predecessor_node["revision_number"] + 1 != node["revision_number"]:
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.REVISION_NUMBER_CONFLICT,
                    logical_id=node["external_logical_record_id"],
                    revision_id=node["external_revision_id"],
                )
            )
        edge = {
            "source_system": node["source_system"],
            "predecessor_revision_id": predecessor,
            "successor_revision_id": node["external_revision_id"],
            "edge_type": "SUPERSEDES",
        }
        edge["edge_hash"] = digest(edge)
        edges.append(edge)
        successors.setdefault((node["source_system"], predecessor), []).append(node)
    for _key, values in successors.items():
        if len(values) > 1:
            for node in values:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.REVISION_MULTIPLE_SUCCESSORS,
                        logical_id=node["external_logical_record_id"],
                        revision_id=node["external_revision_id"],
                    )
                )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for node in unique_nodes:
        grouped.setdefault((node["source_system"], node["external_logical_record_id"]), []).append(
            node
        )
    for logical_key, group in grouped.items():
        terminal = [
            node
            for node in group
            if (node["source_system"], node["external_revision_id"]) not in successors
        ]
        if len(terminal) > 1:
            errors.extend(
                _error(
                    ActualHarvestValidationErrorCode.MULTIPLE_TERMINAL_REVISIONS,
                    logical_id=logical_key[1],
                    revision_id=node["external_revision_id"],
                )
                for node in terminal
            )
        finalized = [
            node
            for node in terminal
            if node["record_status"] == ActualHarvestRecordStatus.FINALIZED.value
        ]
        if len(finalized) > 1:
            errors.extend(
                _error(
                    ActualHarvestValidationErrorCode.MULTIPLE_TERMINAL_REVISIONS,
                    logical_id=logical_key[1],
                    revision_id=node["external_revision_id"],
                )
                for node in finalized
            )
        for node in group:
            has_successor = (node["source_system"], node["external_revision_id"]) in successors
            if (
                node["record_status"] == ActualHarvestRecordStatus.CORRECTED.value
                and not has_successor
            ):
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.INVALID_RECORD_STATUS,
                        logical_id=logical_key[1],
                        revision_id=node["external_revision_id"],
                    )
                )
    for start in unique_nodes:
        seen: set[tuple[str, str]] = set()
        current = start
        while current["supersedes_external_revision_id"] is not None:
            key = (current["source_system"], current["external_revision_id"])
            if key in seen:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.REVISION_LINEAGE_CYCLE,
                        logical_id=start["external_logical_record_id"],
                        revision_id=start["external_revision_id"],
                    )
                )
                break
            seen.add(key)
            previous = by_key.get(
                (current["source_system"], current["supersedes_external_revision_id"])
            )
            if previous is None:
                break
            current = previous
    return (
        unique_nodes,
        tuple(sorted(edges, key=lambda item: canonical_json_dumps(item))),
        _sorted_errors(errors),
    )


def build_validation_evidence(
    session: Session,
    *,
    run_id: int,
    attempt_id: str,
) -> ValidationEvidence:
    run = session.get(ActualHarvestValidationRunModel, run_id)
    if run is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR, "validation run is missing", 500
        )
    batch = session.get(ActualHarvestImportBatchModel, run.batch_id)
    if batch is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR, "validation batch is missing", 500
        )
    attempt = session.scalar(
        select(ActualHarvestValidationAttemptModel).where(
            ActualHarvestValidationAttemptModel.attempt_id == attempt_id
        )
    )
    if attempt is None:
        raise _api_error(
            ActualHarvestApiErrorCode.VALIDATION_EVIDENCE_STALE,
            "validation attempt is no longer active",
            409,
        )

    def heartbeat() -> None:
        renew_validation_attempt_lease(
            session,
            validation_run_id=run_id,
            attempt_id=attempt_id,
            attempt_generation=run.active_attempt_generation,
            fencing_token=attempt.fencing_token,
        )

    registry, entries = _load_registry(
        session,
        source_system=batch.source_system,
        mapping_policy_version=batch.mapping_policy_version,
    )
    records = tuple(ordered_records(_all_batch_records(session, batch.id)))
    basis_hash, basis_members = _current_basis(session, batch)
    outcomes, mapping_errors = _mapping_outcomes(
        session,
        records=records,
        entries=entries,
        registry_version=registry.registry_version,
        mapping_policy_version=registry.mapping_policy_version,
        heartbeat=heartbeat,
    )
    errors = list(mapping_errors)
    if batch.status not in {
        ActualHarvestImportBatchStatus.VALIDATING.value,
        ActualHarvestImportBatchStatus.SEALED.value,
    }:
        errors.append(_error(ActualHarvestValidationErrorCode.BATCH_NOT_SEALED))
    if batch.uploaded_record_count != len(records) or batch.record_count != len(records):
        errors.append(_error(ActualHarvestValidationErrorCode.BATCH_RECORD_COUNT_MISMATCH))
    if (
        batch.expected_record_count_or_null is not None
        and batch.expected_record_count_or_null != len(records)
    ):
        errors.append(_error(ActualHarvestValidationErrorCode.BATCH_RECORD_COUNT_MISMATCH))
    if batch.source_semantics_physical_event != "FARM_PICK":
        errors.append(_error(ActualHarvestValidationErrorCode.SOURCE_SEMANTICS_NOT_FARM_PICK))
    if (
        batch.source_semantics_quantity_basis != "OBSERVED_WEIGHT"
        or batch.source_semantics_quantity_unit != "KG"
        or batch.source_semantics_missing_record_semantics != "UNKNOWN_NOT_ZERO"
    ):
        errors.append(_error(ActualHarvestValidationErrorCode.SOURCE_SEMANTICS_NOT_FARM_PICK))
    for index, record in enumerate(records, start=1):
        if (
            not isinstance(record.actual_harvest_quantity_kg, Decimal)
            or not record.actual_harvest_quantity_kg.is_finite()
        ):
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.INVALID_DECIMAL,
                    record_index=index,
                    field_path="actual_harvest_quantity_kg",
                )
            )
        if record.actual_harvest_quantity_kg < 0:
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.NEGATIVE_QUANTITY,
                    record_index=index,
                    field_path="actual_harvest_quantity_kg",
                )
            )
        if record.farm_timezone:
            try:
                ZoneInfo(record.farm_timezone)
            except ZoneInfoNotFoundError:
                errors.append(
                    _error(
                        ActualHarvestValidationErrorCode.INVALID_TIMEZONE,
                        record_index=index,
                        field_path="farm_timezone",
                    )
                )
        if (
            record.source_recorded_at_authority_status == SourceRecordedAtAuthorityStatus.MISSING
            and record.source_recorded_at is not None
        ):
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.INVALID_DATETIME,
                    record_index=index,
                    field_path="source_recorded_at",
                )
            )
        if (
            record.source_recorded_at_authority_status != SourceRecordedAtAuthorityStatus.MISSING
            and record.source_recorded_at is None
        ):
            errors.append(
                _error(
                    ActualHarvestValidationErrorCode.INVALID_DATETIME,
                    record_index=index,
                    field_path="source_recorded_at",
                )
            )
    seal_records = _all_batch_records(session, batch.id)
    if batch.seal_manifest_hash_or_null is None:
        errors.append(_error(ActualHarvestValidationErrorCode.BATCH_NOT_SEALED))
    if compute_record_manifest_hash(seal_records) != run.record_manifest_hash:
        errors.append(_error(ActualHarvestValidationErrorCode.CANONICAL_HASH_MISMATCH))
    nodes, edges, lineage_errors = _lineage_evidence(records, basis_members, heartbeat=heartbeat)
    errors.extend(lineage_errors)
    errors = list(_sorted_errors(errors))
    warnings: list[ValidationErrorValue] = []
    mapping_snapshot_payload = tuple(_entry_payload(entry) for entry in entries)
    mapping_snapshot_hash = compute_mapping_snapshot_hash(
        registry_version=registry.registry_version,
        mapping_policy_version=registry.mapping_policy_version,
        entries=mapping_snapshot_payload,
    )
    node_payload = tuple(
        {key: value for key, value in node.items() if key != "node_hash"} for node in nodes
    )
    edge_payload = tuple(
        {key: value for key, value in edge.items() if key != "edge_hash"} for edge in edges
    )
    lineage_graph_hash = compute_lineage_graph_hash(node_payload, edge_payload)
    resolved_identity_snapshot_hash = compute_resolved_identity_snapshot_hash(outcomes)
    counts = {
        "valid_count": len(records)
        if not errors
        else max(
            0,
            len(records)
            - len({error.record_index for error in errors if error.record_index is not None}),
        ),
        "invalid_count": 0
        if not errors
        else len({error.record_index for error in errors if error.record_index is not None})
        or len(records),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    result_hash = compute_validation_result_hash(
        seal_manifest_hash=run.seal_manifest_hash,
        mapping_snapshot_hash=mapping_snapshot_hash,
        mapping_policy_version=run.mapping_policy_version,
        validation_policy_version=run.validation_policy_version,
        record_hashes=(
            {
                "source_system": record.source_system,
                "external_logical_record_id": record.external_logical_record_id,
                "revision_number": record.revision_number,
                "external_revision_id": record.external_revision_id,
                "canonical_record_hash": compute_canonical_record_hash(record),
            }
            for record in records
        ),
        mapping_outcomes=outcomes,
        nodes=node_payload,
        edges=edge_payload,
        errors=(error.payload() for error in errors),
        warnings=(warning.payload() for warning in warnings),
        counts=counts,
        committed_lineage_basis_hash=basis_hash,
        lineage_graph_hash=lineage_graph_hash,
        resolved_identity_snapshot_hash=resolved_identity_snapshot_hash,
    )
    record_payloads = tuple(
        {
            "origin": "CURRENT_BATCH_REVISION",
            "record_index": index,
            "source_system": record.source_system,
            "external_logical_record_id": record.external_logical_record_id,
            "external_revision_id": record.external_revision_id,
            "revision_number": record.revision_number,
            "canonical_record_hash": compute_canonical_record_hash(record),
            "mapping_outcome": "MAPPED"
            if not any(error.record_index == index for error in errors)
            else "ERROR",
            "is_valid": not any(error.record_index == index for error in errors),
            "error_count": sum(error.record_index == index for error in errors),
        }
        for index, record in enumerate(records, start=1)
    )
    return ValidationEvidence(
        batch_id=batch.id,
        run_id=run.id,
        attempt_id=attempt_id,
        attempt_generation=run.active_attempt_generation,
        fencing_token=str(
            session.scalar(
                select(ActualHarvestValidationAttemptModel.fencing_token).where(
                    ActualHarvestValidationAttemptModel.attempt_id == attempt_id
                )
            )
        ),
        request_identity_hash=run.request_identity_hash,
        instance_identity_hash=run.instance_identity_hash,
        seal_manifest_hash=run.seal_manifest_hash,
        mapping_policy_version=run.mapping_policy_version,
        validation_policy_version=run.validation_policy_version,
        registry_version=registry.registry_version,
        registry_content_hash=registry.registry_content_hash or "0" * 64,
        mapping_snapshot_hash=mapping_snapshot_hash,
        resolved_identity_snapshot_hash=resolved_identity_snapshot_hash,
        record_manifest_hash=run.record_manifest_hash,
        committed_lineage_basis_hash=basis_hash,
        lineage_graph_hash=lineage_graph_hash,
        validation_result_hash=result_hash,
        records=record_payloads,
        errors=tuple(errors),
        warnings=tuple(warnings),
        nodes=nodes,
        edges=edges,
        basis_members=basis_members,
        mapping_outcomes=tuple(outcomes),
        mapping_entries=mapping_snapshot_payload,
        counts=counts,
        status="VALIDATED" if not errors else "VALIDATION_FAILED",
    )


def finalize_validation(
    session: Session,
    *,
    evidence: ValidationEvidence,
    now: datetime,
) -> str:
    batch = session.scalar(
        select(ActualHarvestImportBatchModel)
        .where(ActualHarvestImportBatchModel.id == evidence.batch_id)
        .with_for_update()
    )
    run = session.scalar(
        select(ActualHarvestValidationRunModel)
        .where(ActualHarvestValidationRunModel.id == evidence.run_id)
        .with_for_update()
    )
    attempt = session.scalar(
        select(ActualHarvestValidationAttemptModel)
        .where(ActualHarvestValidationAttemptModel.attempt_id == evidence.attempt_id)
        .with_for_update()
    )
    if batch is None or run is None or attempt is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR,
            "validation evidence target is missing",
            500,
        )
    database_now = _database_utc_now(session)
    now = database_now
    current_basis, _ = _current_basis(session, batch)
    current_manifest = compute_record_manifest_hash(_all_batch_records(session, batch.id))
    current_resolved_identity_hash: str | None = None
    try:
        current_registry, current_entries = _load_registry(
            session,
            source_system=batch.source_system,
            mapping_policy_version=batch.mapping_policy_version,
        )
        current_registry_hash = current_registry.registry_content_hash
        current_records = tuple(ordered_records(_all_batch_records(session, batch.id)))
        current_outcomes, _ = _mapping_outcomes(
            session,
            records=current_records,
            entries=current_entries,
            registry_version=current_registry.registry_version,
            mapping_policy_version=current_registry.mapping_policy_version,
        )
        current_resolved_identity_hash = compute_resolved_identity_snapshot_hash(current_outcomes)
    except ActualHarvestApiError:
        current_registry_hash = None
    valid_attempt = (
        run.is_current
        and run.active_attempt_id == evidence.attempt_id
        and run.active_attempt_generation == evidence.attempt_generation
        and attempt.fencing_token == evidence.fencing_token
        and attempt.status == "ACTIVE"
        and _ensure_aware(attempt.lease_expires_at) > database_now
        and batch.status == ActualHarvestImportBatchStatus.VALIDATING.value
        and batch.seal_manifest_hash_or_null == evidence.seal_manifest_hash
        and current_registry_hash == evidence.registry_content_hash
        and current_basis == evidence.committed_lineage_basis_hash
        and current_manifest == evidence.record_manifest_hash
        and current_resolved_identity_hash == evidence.resolved_identity_snapshot_hash
    )
    if not valid_attempt:
        newer_attempt_is_current = (
            run.active_attempt_id != evidence.attempt_id
            or run.active_attempt_generation != evidence.attempt_generation
        )
        if not newer_attempt_is_current:
            attempt.status = "STALE"
            attempt.abandoned_at = database_now
            batch.status = ActualHarvestImportBatchStatus.SEALED.value
            run.is_current = False
            run.superseded_at = database_now
        session.flush()
        return "STALE"
    session.add(
        ActualHarvestMappingSnapshotModel(
            validation_run_id=run.id,
            registry_version=evidence.registry_version,
            mapping_policy_version=evidence.mapping_policy_version,
            registry_content_hash=evidence.registry_content_hash,
            mapping_snapshot_hash=evidence.mapping_snapshot_hash,
            resolved_identity_snapshot_hash=evidence.resolved_identity_snapshot_hash,
            entry_count=len(evidence.mapping_entries),
            snapshot_payload=canonical_json_dumps(evidence.mapping_entries),
        )
    )
    session.add(
        ActualHarvestValidationLineageBasisModel(
            validation_run_id=run.id,
            source_system=batch.source_system,
            authority_policy_version=AUTHORITY_POLICY_VERSION,
            committed_lineage_basis_hash=evidence.committed_lineage_basis_hash,
            member_count=len(evidence.basis_members),
        )
    )
    session.flush()
    basis = session.scalar(
        select(ActualHarvestValidationLineageBasisModel).where(
            ActualHarvestValidationLineageBasisModel.validation_run_id == run.id
        )
    )
    if basis is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR, "lineage basis was not created", 500
        )
    for member in evidence.basis_members:
        session.add(
            ActualHarvestValidationLineageBasisMemberModel(
                basis_id=basis.id,
                **member,
                member_sort_key="|".join(
                    (
                        member["source_system"],
                        member["external_logical_record_id"],
                        str(member["revision_number"]),
                        member["external_revision_id"],
                    )
                ),
                member_hash=digest(member),
            )
        )
    for record in evidence.records:
        session.add(ActualHarvestValidationRecordModel(validation_run_id=run.id, **record))
    for mapping in evidence.mapping_outcomes:
        target_type = mapping["target_type"]
        mapping_payload = dict(mapping)
        resolved_master_id = mapping_payload.pop("resolved_master_id")
        mapping_fk = {
            "resolved_season_id": resolved_master_id if target_type == "SEASON" else None,
            "resolved_farm_id": resolved_master_id if target_type == "FARM" else None,
            "resolved_subfarm_id": resolved_master_id if target_type == "SUBFARM" else None,
            "resolved_variety_id": resolved_master_id if target_type == "VARIETY" else None,
        }
        session.add(
            ActualHarvestValidationMappingEvidenceModel(
                validation_run_id=run.id,
                **mapping_payload,
                **mapping_fk,
            )
        )
    for _index, node in enumerate(evidence.nodes, start=1):
        node_payload = {key: value for key, value in node.items() if key != "node_hash"}
        session.add(
            ActualHarvestValidationLineageNodeModel(
                validation_run_id=run.id,
                **node_payload,
                node_hash=node.get("node_hash") or compute_lineage_node_hash(node_payload),
            )
        )
    for edge in evidence.edges:
        edge_payload = {key: value for key, value in edge.items() if key != "edge_hash"}
        session.add(
            ActualHarvestValidationLineageEdgeModel(
                validation_run_id=run.id,
                **edge_payload,
                edge_hash=edge.get("edge_hash") or digest(edge_payload),
            )
        )
    for error in (*evidence.errors, *evidence.warnings):
        payload = error.payload()
        session.add(
            ActualHarvestValidationErrorModel(
                validation_run_id=run.id,
                severity=error.severity,
                error_code=error.code,
                record_index=error.record_index,
                external_logical_record_id=error.logical_id,
                external_revision_id=error.revision_id,
                field_path=error.field_path,
                message_template_id=error.code,
                sanitized_details=canonical_json_dumps(error.details),
                sort_key=_stable_sort_key(error),
                error_hash=digest(payload),
            )
        )
    session.add(
        ActualHarvestValidationResultModel(
            validation_run_id=run.id,
            validation_result_hash=evidence.validation_result_hash,
            lineage_graph_hash=evidence.lineage_graph_hash,
            committed_lineage_basis_hash=evidence.committed_lineage_basis_hash,
            mapping_snapshot_hash=evidence.mapping_snapshot_hash,
            resolved_identity_snapshot_hash=evidence.resolved_identity_snapshot_hash,
            valid_count=evidence.counts["valid_count"],
            invalid_count=evidence.counts["invalid_count"],
            error_count=evidence.counts["error_count"],
            warning_count=evidence.counts["warning_count"],
            result_payload=canonical_json_dumps(
                {
                    "errors": [error.payload() for error in evidence.errors],
                    "warnings": [warning.payload() for warning in evidence.warnings],
                    "counts": evidence.counts,
                }
            ),
        )
    )
    run.status = evidence.status
    run.lineage_graph_hash = evidence.lineage_graph_hash
    run.validation_result_hash = evidence.validation_result_hash
    run.mapping_snapshot_hash = evidence.mapping_snapshot_hash
    run.resolved_identity_snapshot_hash = evidence.resolved_identity_snapshot_hash
    run.valid_count = evidence.counts["valid_count"]
    run.invalid_count = evidence.counts["invalid_count"]
    run.error_count = evidence.counts["error_count"]
    run.warning_count = evidence.counts["warning_count"]
    run.completed_at = now
    run.active_attempt_id = None
    attempt.status = "COMPLETED"
    attempt.completed_at = now
    batch.status = evidence.status
    batch.valid_record_count = evidence.counts["valid_count"]
    batch.invalid_record_count = evidence.counts["invalid_count"]
    batch.validated_at_or_null = now
    session.flush()
    return evidence.status


def current_validation_summary(session: Session, import_id: str) -> ValidationSummary:
    batch = session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == import_id
        )
    )
    if batch is None:
        raise _api_error(ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND, "import not found", 404)
    run = session.scalar(
        select(ActualHarvestValidationRunModel).where(
            ActualHarvestValidationRunModel.batch_id == batch.id,
            ActualHarvestValidationRunModel.is_current.is_(True),
        )
    )
    if run is None:
        return ValidationSummary("NOT_RUN", None, None, None, None, None, None, 0, 0, 0, 0)
    return _run_summary(run)


def list_validation_errors(
    session: Session,
    *,
    import_id: str,
    page_size: int,
    after_sort_key: str | None,
) -> tuple[ValidationSummary, tuple[dict[str, Any], ...], str | None]:
    batch = session.scalar(
        select(ActualHarvestImportBatchModel).where(
            ActualHarvestImportBatchModel.import_id == import_id
        )
    )
    if batch is None:
        raise _api_error(ActualHarvestApiErrorCode.IMPORT_BATCH_NOT_FOUND, "import not found", 404)
    run = session.scalar(
        select(ActualHarvestValidationRunModel).where(
            ActualHarvestValidationRunModel.batch_id == batch.id,
            ActualHarvestValidationRunModel.is_current.is_(True),
        )
    )
    if run is None:
        return current_validation_summary(session, import_id), (), None
    query = select(ActualHarvestValidationErrorModel).where(
        ActualHarvestValidationErrorModel.validation_run_id == run.id
    )
    if after_sort_key is not None:
        query = query.where(ActualHarvestValidationErrorModel.sort_key > after_sort_key)
    rows = session.scalars(
        query.order_by(ActualHarvestValidationErrorModel.sort_key).limit(page_size + 1)
    ).all()
    page = rows[:page_size]
    token = page[-1].sort_key if len(rows) > page_size and page else None
    return (
        _run_summary(run),
        tuple(
            {
                "severity": row.severity,
                "error_code": row.error_code,
                "record_index": row.record_index,
                "external_logical_record_id": row.external_logical_record_id,
                "external_revision_id": row.external_revision_id,
                "field_path": row.field_path,
                "message_template_id": row.message_template_id,
                "details": json.loads(row.sanitized_details),
            }
            for row in page
        ),
        token,
    )


async def validate_import(session: Any, *, import_id: str, now: datetime) -> ValidationSummary:
    from sqlalchemy.ext.asyncio import AsyncSession

    if not isinstance(session, AsyncSession):
        raise TypeError("validation service requires AsyncSession")
    start = await session.run_sync(
        lambda sync_session: begin_validation(sync_session, import_id=import_id, now=now)
    )
    await session.commit()
    if start.kind == "replay" and start.summary is not None:
        return start.summary
    if start.kind == "in_progress":
        raise _api_error(
            ActualHarvestApiErrorCode.VALIDATION_IN_PROGRESS,
            "validation is already in progress",
            409,
        )
    if start.run_id is None or start.attempt_id is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR, "validation attempt is missing", 500
        )
    if start.attempt_generation is None or start.fencing_token is None:
        raise _api_error(
            ActualHarvestApiErrorCode.API_INTEGRITY_ERROR,
            "validation attempt fencing identity is missing",
            500,
        )
    run_id = start.run_id
    attempt_id = start.attempt_id
    attempt_generation = start.attempt_generation
    fencing_token = start.fencing_token
    try:
        await session.run_sync(
            lambda sync_session: renew_validation_attempt_lease(
                sync_session,
                validation_run_id=run_id,
                attempt_id=attempt_id,
                attempt_generation=attempt_generation,
                fencing_token=fencing_token,
            )
        )
        await session.commit()
        evidence = await session.run_sync(
            lambda sync_session: build_validation_evidence(
                sync_session,
                run_id=run_id,
                attempt_id=attempt_id,
            )
        )
    except Exception:
        await session.rollback()
        raise
    await session.rollback()
    await session.run_sync(
        lambda sync_session: renew_validation_attempt_lease(
            sync_session,
            validation_run_id=run_id,
            attempt_id=attempt_id,
            attempt_generation=attempt_generation,
            fencing_token=fencing_token,
        )
    )
    await session.commit()
    result = await session.run_sync(
        lambda sync_session: finalize_validation(sync_session, evidence=evidence, now=now)
    )
    await session.commit()
    if result == "STALE":
        raise _api_error(
            ActualHarvestApiErrorCode.COMMITTED_LINEAGE_BASIS_CHANGED,
            "committed lineage basis changed during validation; revalidate",
            409,
        )
    return await session.run_sync(
        lambda sync_session: current_validation_summary(sync_session, import_id)
    )


def encode_error_page_token(instance_identity: str, sort_key: str) -> str:
    payload = {"v": 1, "instance_identity": instance_identity, "last": sort_key}
    return base64.urlsafe_b64encode(canonical_json_dumps(payload).encode()).decode().rstrip("=")


def decode_error_page_token(token: str, instance_identity: str) -> str:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        if payload.get("v") != 1 or payload.get("instance_identity") != instance_identity:
            raise ValueError
        last = payload.get("last")
        if not isinstance(last, str) or len(last) > 2048:
            raise ValueError
        return last
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _api_error(
            ActualHarvestApiErrorCode.API_REQUEST_INVALID, "error page token is invalid", 400
        ) from exc


__all__ = [
    "AUTHORITY_POLICY_VERSION",
    "SUBFARM_ONLY_POLICY",
    "ValidationSummary",
    "begin_validation",
    "build_validation_evidence",
    "create_mapping_registry",
    "current_validation_summary",
    "decode_error_page_token",
    "encode_error_page_token",
    "finalize_validation",
    "renew_validation_attempt_lease",
    "list_validation_errors",
    "seal_mapping_registry",
    "validate_import",
]
