from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.actual_harvest_import.batch_a_contracts import (
    BatchASourceIdentity,
    ChainAllowedValuesRegistry,
    ChainNullPolicy,
    ChainResolutionStatus,
    ConflictingExportIdentityError,
    DimensionMappingEntry,
    DimensionMappingRegistry,
    DuplicateKeyIdentityError,
    ExportIdentityClaim,
    ExportIdentityLedger,
    ExportIdentityMode,
    ExportRegistrationResult,
    HmacBindingVerificationStatus,
    HmacKeyState,
    HmacPolicyIdentity,
    SyntheticHmacBindingRecord,
    SyntheticHmacKeyRecord,
    SyntheticHmacLifecycleLedger,
    UnknownChainValueError,
    UnknownDimensionMappingError,
    normalize_business_text,
    resolve_export_identity,
)
from backend.app.actual_harvest_import.schemas import ActualHarvestImportBatchInput


def _source_identity() -> BatchASourceIdentity:
    return BatchASourceIdentity(
        source_system="synthetic-scan-weight-system",
        source_dataset="synthetic-daily-marketable-net-kg",
        source_version="synthetic-source-v1",
        schema_version="synthetic-schema-v1",
    )


def _hmac_policy() -> HmacPolicyIdentity:
    return HmacPolicyIdentity(
        custody_policy_id="synthetic-hmac-custody-v1",
        rotation_policy_id="synthetic-hmac-rotation-v1",
    )


def test_source_identity_is_strict_and_fail_closed() -> None:
    identity = _source_identity()
    assert identity.source_system == "synthetic-scan-weight-system"

    for field in ("source_system", "source_dataset", "source_version", "schema_version"):
        payload = identity.model_dump()
        payload[field] = "NOT_PROVIDED"
        with pytest.raises(ValidationError):
            BatchASourceIdentity.model_validate(payload)

    with pytest.raises(ValidationError):
        BatchASourceIdentity.model_validate(
            {
                **identity.model_dump(),
                "source_system": "https://source.invalid/system",
            }
        )
    with pytest.raises(ValidationError):
        BatchASourceIdentity.model_validate(
            {
                **identity.model_dump(),
                "schema_version": " synthetic-schema-v1",
            }
        )


def test_existing_batch_input_reuses_batch_a_source_identity_contract() -> None:
    payload = {
        "import_channel": "api",
        **_source_identity().model_dump(),
        "external_batch_id": "synthetic-batch-1",
        "idempotency_key": "synthetic-idempotency-1",
        "submitted_at": "2026-08-06T00:00:00Z",
        "submitted_by_identity": "synthetic-operator",
        "raw_payload_hash": "a" * 64,
        "mapping_policy_version": "synthetic-mapping-v1",
        "validation_policy_version": "synthetic-validation-v1",
        "source_semantics_attestation": {
            "attestation_version": "synthetic-attestation-v1",
            "physical_event": "FARM_PICK",
            "quantity_basis": "OBSERVED_WEIGHT",
            "quantity_unit": "KG",
            "missing_record_semantics": "UNKNOWN_NOT_ZERO",
        },
        "source_semantics_attestation_hash": "b" * 64,
    }
    assert ActualHarvestImportBatchInput.model_validate(payload).source_version == (
        "synthetic-source-v1"
    )
    valid_payload = dict(payload)
    payload["source_dataset"] = "unsafe dataset"
    with pytest.raises(ValidationError):
        ActualHarvestImportBatchInput.model_validate(payload)

    for field in ("source_system", "source_dataset", "source_version", "schema_version"):
        spaced_payload = {
            **valid_payload,
            field: f" {valid_payload[field]} ",
        }
        with pytest.raises(ValidationError):
            ActualHarvestImportBatchInput.model_validate(spaced_payload)


def test_mapping_registry_preserves_raw_text_and_rejects_unknown_values() -> None:
    assert normalize_business_text("  蓝莓́  ") == "蓝莓́"
    registry = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v1",
        policy_version="synthetic-dimension-mapping-v1",
        entries=(
            DimensionMappingEntry(
                dimension="farm",
                source_text=" Farm Alpha ",
                canonical_id="synthetic-farm-alpha",
            ),
        ),
    )
    resolved = registry.resolve("farm", " Farm Alpha ")
    assert resolved.original_text == " Farm Alpha "
    assert resolved.normalized_text == "Farm Alpha"
    assert resolved.canonical_id == "synthetic-farm-alpha"

    with pytest.raises(UnknownDimensionMappingError):
        registry.resolve("farm", "Farm Beta")

    with pytest.raises(ValidationError):
        DimensionMappingRegistry(
            registry_id="synthetic-dimension-registry-v1",
            policy_version="synthetic-dimension-mapping-v1",
            entries=(
                DimensionMappingEntry(
                    dimension="farm",
                    source_text="Farm Alpha",
                    canonical_id="synthetic-farm-alpha",
                ),
                DimensionMappingEntry(
                    dimension="farm",
                    source_text=" Farm Alpha ",
                    canonical_id="synthetic-farm-alpha-2",
                ),
            ),
        )


def test_chain_registry_has_explicit_allowed_and_null_behaviors() -> None:
    registry = ChainAllowedValuesRegistry(
        policy_version="synthetic-chain-policy-v1",
        allowed_values=("synthetic-chain-a",),
        null_policy=ChainNullPolicy.NOT_PROVIDED,
    )
    assert registry.resolve("synthetic-chain-a").status == ChainResolutionStatus.ALLOWED
    assert registry.resolve(None).status == ChainResolutionStatus.NOT_PROVIDED
    with pytest.raises(UnknownChainValueError):
        registry.resolve("synthetic-chain-unknown")

    rejecting_registry = registry.model_copy(update={"null_policy": ChainNullPolicy.REJECT})
    with pytest.raises(UnknownChainValueError):
        rejecting_registry.resolve("")


def test_export_identity_modes_are_deterministic_and_idempotent() -> None:
    source = _source_identity()
    source_claim = ExportIdentityClaim(
        mode=ExportIdentityMode.SOURCE_PROVIDED,
        source_identity=source,
        source_export_id="synthetic-export-1",
        delivery_fingerprint="synthetic-delivery-1",
    )
    source_identity = resolve_export_identity(source_claim)
    ledger = ExportIdentityLedger()
    assert ledger.register(source_identity) == ExportRegistrationResult.FIRST_SEEN
    assert ledger.register(source_identity) == ExportRegistrationResult.EXACT_REPLAY

    conflicting = source_claim.model_copy(
        update={"delivery_fingerprint": "synthetic-delivery-2"}
    )
    with pytest.raises(ConflictingExportIdentityError):
        ledger.register(resolve_export_identity(conflicting))

    derived_claim = ExportIdentityClaim(
        mode=ExportIdentityMode.PROJECT_DERIVED,
        source_identity=source,
        raw_file_sha256="c" * 64,
        delivery_fingerprint="c" * 64,
    )
    derived_identity = resolve_export_identity(derived_claim)
    assert derived_identity.identity_key[-1] == "c" * 64
    assert derived_identity.identity_key != source_identity.identity_key

    with pytest.raises(ValidationError):
        ExportIdentityClaim(
            mode=ExportIdentityMode.PROJECT_DERIVED,
            source_identity=source,
            delivery_fingerprint="synthetic-delivery-3",
        )


def test_synthetic_hmac_lifecycle_retains_history_without_real_operations() -> None:
    policy = _hmac_policy()
    with pytest.raises(ValidationError):
        HmacPolicyIdentity(
            custody_policy_id="synthetic-hmac-custody",
            rotation_policy_id="synthetic-hmac-rotation-v1",
        )
    ledger = SyntheticHmacLifecycleLedger()
    first = SyntheticHmacKeyRecord(key_id="synthetic-key-1", policy_identity=policy)
    ledger.register_synthetic_key(first)
    second = ledger.rotate_key(
        previous_key_id="synthetic-key-1",
        new_key_id="synthetic-key-2",
        policy_identity=policy,
    )
    assert second.status == HmacKeyState.ACTIVE
    assert ledger.get_key("synthetic-key-1").status == HmacKeyState.RETIRED
    assert ledger.key_ids == ("synthetic-key-1", "synthetic-key-2")

    ledger.register_historical_binding(
        SyntheticHmacBindingRecord(
            binding_id="synthetic-binding-1",
            key_id="synthetic-key-1",
        )
    )
    assert (
        ledger.verify_historical_binding("synthetic-binding-1")
        == HmacBindingVerificationStatus.NOT_ISSUED
    )

    ledger.register_historical_binding(
        SyntheticHmacBindingRecord(
            binding_id="synthetic-binding-2",
            key_id="synthetic-key-2",
            digest_or_not_issued="d" * 64,
        )
    )
    assert (
        ledger.verify_historical_binding("synthetic-binding-2")
        == HmacBindingVerificationStatus.ALLOWED
    )
    ledger.set_terminal_status("synthetic-key-2", HmacKeyState.COMPROMISED)
    assert (
        ledger.verify_historical_binding("synthetic-binding-2")
        == HmacBindingVerificationStatus.CUSTODY_REQUIRED
    )
    with pytest.raises(DuplicateKeyIdentityError):
        ledger.register_synthetic_key(first)
    with pytest.raises(ValueError):
        ledger.rotate_key(
            previous_key_id="synthetic-key-2",
            new_key_id="synthetic-key-3",
            policy_identity=policy,
        )
