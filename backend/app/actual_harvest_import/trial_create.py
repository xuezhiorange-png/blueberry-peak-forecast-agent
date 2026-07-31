from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.api_schemas import ActualHarvestApiCreateImportRequest
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
)
from backend.app.actual_harvest_import.schemas import ActualHarvestSourceSemanticsAttestation
from backend.app.actual_harvest_import.validation_service import (
    resolve_unique_sealed_mapping_registry,
)
from backend.app.rolling_backtest.canonical import canonical_json_dumps

if TYPE_CHECKING:
    from backend.app.trial import TrialActualHarvestImportCreateRequest


TRIAL_ACTUAL_HARVEST_ATTESTATION_VERSION = "actual-harvest-source-semantics-v1"
TRIAL_ACTUAL_HARVEST_SCHEMA_VERSION = "actual-harvest-canonical-schema-v1"
TRIAL_ACTUAL_HARVEST_VALIDATION_POLICY_VERSION = "actual-harvest-validation-policy-v1"
TRIAL_ACTUAL_HARVEST_CREATE_HASH_POLICY_VERSION = "trial-actual-harvest-create-hash-v1"

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ComposedTrialActualHarvestCreate:
    internal_request: ActualHarvestApiCreateImportRequest
    create_identity_hash: str
    created_at: datetime
    mapping_registry_version: str
    mapping_policy_version: str
    mapping_registry_content_hash: str


def _attestation() -> ActualHarvestSourceSemanticsAttestation:
    return ActualHarvestSourceSemanticsAttestation(
        attestation_version=TRIAL_ACTUAL_HARVEST_ATTESTATION_VERSION,
        physical_event=ActualHarvestPhysicalEvent.FARM_PICK,
        quantity_basis=ActualHarvestQuantityBasis.OBSERVED_WEIGHT,
        quantity_unit=ActualHarvestQuantityUnit.KG,
        missing_record_semantics=ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO,
    )


def _hash(value: object) -> str:
    return sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def _attestation_hash(attestation: ActualHarvestSourceSemanticsAttestation) -> str:
    return _hash(attestation.model_dump(mode="python"))


def _create_identity_hash(
    *,
    request_idempotency_key: str | None = None,
    actor_identity: str | None = None,
    source_system: str,
    source_dataset: str,
    source_version: str,
    external_batch_id: str,
    expected_record_count_or_null: int | None,
    attestation: ActualHarvestSourceSemanticsAttestation,
    attestation_hash: str,
    mapping_registry_version: str,
    mapping_policy_version: str,
    mapping_registry_content_hash: str,
) -> str:
    del request_idempotency_key, actor_identity
    return _hash(
        {
            "policy_version": TRIAL_ACTUAL_HARVEST_CREATE_HASH_POLICY_VERSION,
            "import_channel": ActualHarvestImportChannel.API,
            "source_system": source_system,
            "source_dataset": source_dataset,
            "source_version": source_version,
            "external_batch_id": external_batch_id,
            "expected_record_count_or_null": expected_record_count_or_null,
            "schema_version": TRIAL_ACTUAL_HARVEST_SCHEMA_VERSION,
            "validation_policy_version": TRIAL_ACTUAL_HARVEST_VALIDATION_POLICY_VERSION,
            "source_semantics_attestation": attestation.model_dump(mode="python"),
            "source_semantics_attestation_hash": attestation_hash,
            "mapping_registry_version": mapping_registry_version,
            "mapping_policy_version": mapping_policy_version,
            "mapping_registry_content_hash": mapping_registry_content_hash,
        }
    )


async def compose_trial_actual_harvest_create(
    session: AsyncSession,
    request: TrialActualHarvestImportCreateRequest,
    actor: ActualHarvestActorContext,
    *,
    clock: Clock,
) -> ComposedTrialActualHarvestCreate:
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Trial create clock must return a timezone-aware datetime")

    registry, _ = await session.run_sync(
        lambda sync_session: resolve_unique_sealed_mapping_registry(
            sync_session,
            source_system=request.source_system,
        )
    )
    if registry.registry_content_hash is None:
        raise RuntimeError("sealed mapping authority returned without a content hash")
    mapping_registry_content_hash = registry.registry_content_hash
    attestation = _attestation()
    attestation_hash = _attestation_hash(attestation)
    create_identity_hash = _create_identity_hash(
        source_system=request.source_system,
        source_dataset=request.source_dataset,
        source_version=request.source_version,
        external_batch_id=request.external_batch_id,
        expected_record_count_or_null=request.expected_record_count_or_null,
        attestation=attestation,
        attestation_hash=attestation_hash,
        mapping_registry_version=registry.registry_version,
        mapping_policy_version=registry.mapping_policy_version,
        mapping_registry_content_hash=mapping_registry_content_hash,
    )
    internal_request = ActualHarvestApiCreateImportRequest(
        import_channel=ActualHarvestImportChannel.API,
        source_system=request.source_system,
        source_dataset=request.source_dataset,
        source_version=request.source_version,
        external_batch_id=request.external_batch_id,
        idempotency_key=request.request_idempotency_key,
        submitted_at=now,
        submitted_by_identity=actor.identity,
        expected_record_count_or_null=request.expected_record_count_or_null,
        source_file_name_or_null=None,
        source_file_hash_or_null=None,
        raw_payload_hash=create_identity_hash,
        schema_version=TRIAL_ACTUAL_HARVEST_SCHEMA_VERSION,
        mapping_policy_version=registry.mapping_policy_version,
        validation_policy_version=TRIAL_ACTUAL_HARVEST_VALIDATION_POLICY_VERSION,
        source_semantics_attestation=attestation,
        source_semantics_attestation_hash=attestation_hash,
    )
    return ComposedTrialActualHarvestCreate(
        internal_request=internal_request,
        create_identity_hash=create_identity_hash,
        created_at=now,
        mapping_registry_version=registry.registry_version,
        mapping_policy_version=registry.mapping_policy_version,
        mapping_registry_content_hash=mapping_registry_content_hash,
    )


__all__ = [
    "ComposedTrialActualHarvestCreate",
    "TRIAL_ACTUAL_HARVEST_ATTESTATION_VERSION",
    "TRIAL_ACTUAL_HARVEST_CREATE_HASH_POLICY_VERSION",
    "TRIAL_ACTUAL_HARVEST_SCHEMA_VERSION",
    "TRIAL_ACTUAL_HARVEST_VALIDATION_POLICY_VERSION",
    "compose_trial_actual_harvest_create",
]
