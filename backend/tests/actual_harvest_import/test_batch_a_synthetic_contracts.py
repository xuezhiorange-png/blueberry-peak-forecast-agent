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
    DimensionMappingHistoryConflictError,
    DimensionMappingRegistry,
    DuplicateHmacBindingIdentityError,
    DuplicateKeyIdentityError,
    ExportIdentityClaim,
    ExportIdentityLedger,
    ExportIdentityMode,
    ExportRegistrationResult,
    HmacBindingVerificationStatus,
    HmacCustodyRole,
    HmacCustodyRoleAssignment,
    HmacKeyState,
    HmacKeyUnavailableError,
    HmacPolicyIdentity,
    SchemaCompatibilityError,
    SchemaCompatibilityStatus,
    SchemaVersionHashBinding,
    SourceSchemaCompatibilityRegistry,
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


def _schema_registry() -> SourceSchemaCompatibilityRegistry:
    return SourceSchemaCompatibilityRegistry(
        compatibility_policy_id="synthetic-schema-compatibility-v1",
        bindings=(
            SchemaVersionHashBinding(
                schema_version="synthetic-schema-v1",
                schema_sha256="a" * 64,
            ),
        ),
    )


def _hmac_role_assignments() -> tuple[HmacCustodyRoleAssignment, ...]:
    return (
        HmacCustodyRoleAssignment(
            role=HmacCustodyRole.CUSTODY_OWNER,
            role_identity="synthetic-security-owner",
        ),
        HmacCustodyRoleAssignment(
            role=HmacCustodyRole.KEY_OPERATOR,
            role_identity="synthetic-key-operator",
        ),
        HmacCustodyRoleAssignment(
            role=HmacCustodyRole.BINDING_VERIFIER,
            role_identity="synthetic-binding-verifier",
        ),
        HmacCustodyRoleAssignment(
            role=HmacCustodyRole.APPROVER,
            role_identity="synthetic-security-approver",
        ),
    )


def _hmac_policy() -> HmacPolicyIdentity:
    return HmacPolicyIdentity(
        custody_policy_id="synthetic-hmac-custody-v1",
        rotation_policy_id="synthetic-hmac-rotation-v1",
        role_assignments=_hmac_role_assignments(),
    )


def _batch_payload() -> dict[str, object]:
    return {
        "import_channel": "api",
        **_source_identity().model_dump(),
        "external_batch_id": "synthetic-batch-1",
        "idempotency_key": "synthetic-idempotency-1",
        "submitted_at": "2026-08-06T00:00:00Z",
        "submitted_by_identity": "synthetic-operator",
        "raw_payload_hash": "c" * 64,
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
    for invalid_identifier in (
        "Farm-System",
        "NOT_ISSUED",
        "PENDING",
        "foo/bar",
        "https://example.com",
        "x" * 129,
    ):
        with pytest.raises(ValidationError):
            BatchASourceIdentity.model_validate(
                {
                    **identity.model_dump(),
                    "source_system": invalid_identifier,
                }
            )


def test_schema_registry_binds_version_to_hash_and_fails_closed() -> None:
    registry = _schema_registry()
    assert (
        registry.evaluate(
            schema_version="synthetic-schema-v1",
            schema_sha256="a" * 64,
        )
        == SchemaCompatibilityStatus.SUPPORTED
    )
    assert (
        registry.evaluate(
            schema_version="synthetic-schema-v1",
            schema_sha256="d" * 64,
        )
        == SchemaCompatibilityStatus.REJECTED
    )
    assert (
        registry.evaluate(
            schema_version="synthetic-schema-v2",
            schema_sha256="a" * 64,
        )
        == SchemaCompatibilityStatus.REJECTED
    )
    with pytest.raises(SchemaCompatibilityError):
        registry.assert_compatible(
            schema_version="synthetic-schema-v1",
            schema_sha256="d" * 64,
        )

    with pytest.raises(ValidationError):
        SourceSchemaCompatibilityRegistry(
            compatibility_policy_id="synthetic-schema-compatibility-v1",
            bindings=(
                SchemaVersionHashBinding(
                    schema_version="synthetic-schema-v1",
                    schema_sha256="a" * 64,
                ),
                SchemaVersionHashBinding(
                    schema_version="synthetic-schema-v1",
                    schema_sha256="b" * 64,
                ),
            ),
        )


def test_existing_batch_input_reuses_source_and_schema_contracts() -> None:
    payload = _batch_payload()
    batch = ActualHarvestImportBatchInput.model_validate(payload)
    assert batch.source_version == "synthetic-source-v1"
    assert all(
        field not in batch.model_dump(mode="python")
        for field in (
            "source_schema_sha256_or_null",
            "schema_compatibility_policy_id_or_null",
            "schema_compatibility_status_or_null",
        )
    )

    invalid_identity_payload = dict(payload)
    invalid_identity_payload["source_dataset"] = "unsafe dataset"
    with pytest.raises(ValidationError):
        ActualHarvestImportBatchInput.model_validate(invalid_identity_payload)

    for field in ("source_system", "source_dataset", "source_version", "schema_version"):
        spaced_payload = {
            **payload,
            field: f" {payload[field]} ",
        }
        with pytest.raises(ValidationError):
            ActualHarvestImportBatchInput.model_validate(spaced_payload)

    for inactive_field, value in (
        ("source_schema_sha256_or_null", "a" * 64),
        ("schema_compatibility_policy_id_or_null", "synthetic-schema-policy-v1"),
        ("schema_compatibility_status_or_null", "SUPPORTED"),
    ):
        inactive_payload = {**payload, inactive_field: value}
        with pytest.raises(ValidationError):
            ActualHarvestImportBatchInput.model_validate(inactive_payload)


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


def test_mapping_registry_policy_is_versioned_and_history_is_stable() -> None:
    with pytest.raises(ValidationError):
        DimensionMappingRegistry(
            registry_id="synthetic-dimension-registry-v1",
            policy_version="synthetic-dimension-mapping",
            entries=(
                DimensionMappingEntry(
                    dimension="farm",
                    source_text="Farm Alpha",
                    canonical_id="synthetic-farm-alpha",
                ),
            ),
        )

    prior = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v1",
        policy_version="synthetic-dimension-mapping-v1",
        entries=(
            DimensionMappingEntry(
                dimension="farm",
                source_text="Farm Alpha",
                canonical_id="synthetic-farm-alpha",
            ),
        ),
    )
    next_season = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v2",
        policy_version="synthetic-dimension-mapping-v2",
        entries=(
            DimensionMappingEntry(
                dimension="farm",
                source_text="Farm Alpha",
                canonical_id="synthetic-farm-alpha",
            ),
            DimensionMappingEntry(
                dimension="variety",
                source_text="Variety New",
                canonical_id="synthetic-variety-new",
            ),
        ),
    )
    next_season.assert_historical_compatibility(prior)
    assert (
        prior.resolve("farm", "Farm Alpha").canonical_id
        == next_season.resolve("farm", "Farm Alpha").canonical_id
    )

    conflicting_next_season = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v3",
        policy_version="synthetic-dimension-mapping-v3",
        entries=(
            DimensionMappingEntry(
                dimension="farm",
                source_text="Farm Alpha",
                canonical_id="synthetic-farm-renamed",
            ),
        ),
    )
    with pytest.raises(DimensionMappingHistoryConflictError):
        conflicting_next_season.assert_historical_compatibility(prior)

    dropped_mapping = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v4",
        policy_version="synthetic-dimension-mapping-v4",
        entries=(
            DimensionMappingEntry(
                dimension="variety",
                source_text="Variety New",
                canonical_id="synthetic-variety-new",
            ),
        ),
    )
    with pytest.raises(DimensionMappingHistoryConflictError):
        dropped_mapping.assert_historical_compatibility(prior)

    unrelated_mapping = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v5",
        policy_version="synthetic-dimension-mapping-v5",
        entries=(
            DimensionMappingEntry(
                dimension="farm",
                source_text="Farm Alpha",
                canonical_id="synthetic-farm-alpha",
            ),
            DimensionMappingEntry(
                dimension="variety",
                source_text="Variety New",
                canonical_id="synthetic-variety-new",
            ),
            DimensionMappingEntry(
                dimension="subfarm",
                source_text="Subfarm A",
                canonical_id="synthetic-subfarm-a",
            ),
        ),
    )
    unrelated_mapping.assert_historical_compatibility(prior)


def test_mapping_registry_nfc_collision_and_ordered_output_are_deterministic() -> None:
    composed = "Café"
    decomposed = "Cafe\u0301"
    assert normalize_business_text(composed) == normalize_business_text(decomposed)
    with pytest.raises(ValidationError):
        DimensionMappingRegistry(
            registry_id="synthetic-dimension-registry-v6",
            policy_version="synthetic-dimension-mapping-v6",
            entries=(
                DimensionMappingEntry(
                    dimension="farm",
                    source_text=composed,
                    canonical_id="synthetic-farm-cafe",
                ),
                DimensionMappingEntry(
                    dimension="farm",
                    source_text=decomposed,
                    canonical_id="synthetic-farm-cafe-duplicate",
                ),
            ),
        )

    entries = (
        DimensionMappingEntry(
            dimension="variety",
            source_text="Variety B",
            canonical_id="synthetic-variety-b",
        ),
        DimensionMappingEntry(
            dimension="farm",
            source_text="Farm B",
            canonical_id="synthetic-farm-b",
        ),
        DimensionMappingEntry(
            dimension="farm",
            source_text="Farm A",
            canonical_id="synthetic-farm-a",
        ),
    )
    first = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v7",
        policy_version="synthetic-dimension-mapping-v7",
        entries=entries,
    )
    second = first.model_copy(update={"entries": tuple(reversed(entries))})
    assert first.ordered_entries() == second.ordered_entries()


def test_chain_registry_has_versioned_allowed_and_null_behaviors() -> None:
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

    with pytest.raises(ValidationError):
        ChainAllowedValuesRegistry(
            policy_version="synthetic-chain-policy",
            allowed_values=("synthetic-chain-a",),
            null_policy=ChainNullPolicy.REJECT,
        )
    with pytest.raises(ValidationError):
        ChainAllowedValuesRegistry(
            policy_version="synthetic-chain-policy-v2",
            allowed_values=(" synthetic-chain-a ", "synthetic-chain-a"),
            null_policy=ChainNullPolicy.REJECT,
        )


def test_export_identity_modes_are_deterministic_and_version_bound() -> None:
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

    conflicting = source_claim.model_copy(update={"delivery_fingerprint": "synthetic-delivery-2"})
    with pytest.raises(ConflictingExportIdentityError):
        ledger.register(resolve_export_identity(conflicting))

    changed_source_version = source_claim.model_copy(
        update={
            "source_identity": source.model_copy(update={"source_version": "synthetic-source-v2"})
        }
    )
    changed_schema_version = source_claim.model_copy(
        update={
            "source_identity": source.model_copy(update={"schema_version": "synthetic-schema-v2"})
        }
    )
    assert (
        resolve_export_identity(changed_source_version).identity_key != source_identity.identity_key
    )
    assert (
        resolve_export_identity(changed_schema_version).identity_key != source_identity.identity_key
    )

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


def test_hmac_custody_roles_are_closed_and_separated() -> None:
    policy = _hmac_policy()
    assert policy.role_identity(HmacCustodyRole.KEY_OPERATOR) == "synthetic-key-operator"

    invalid_role_payload = {
        "custody_policy_id": "synthetic-hmac-custody-v1",
        "rotation_policy_id": "synthetic-hmac-rotation-v1",
        "role_assignments": [
            *[assignment.model_dump() for assignment in _hmac_role_assignments()[:-1]],
            {
                "role": "UNKNOWN_ROLE",
                "role_identity": "synthetic-unknown-role",
            },
        ],
    }
    with pytest.raises(ValidationError):
        HmacPolicyIdentity.model_validate(invalid_role_payload)

    same_operator_and_verifier = list(_hmac_role_assignments())
    same_operator_and_verifier[2] = HmacCustodyRoleAssignment(
        role=HmacCustodyRole.BINDING_VERIFIER,
        role_identity="synthetic-key-operator",
    )
    with pytest.raises(ValidationError):
        HmacPolicyIdentity(
            custody_policy_id="synthetic-hmac-custody-v1",
            rotation_policy_id="synthetic-hmac-rotation-v1",
            role_assignments=tuple(same_operator_and_verifier),
        )
    duplicate_role_assignments = list(_hmac_role_assignments())
    duplicate_role_assignments[3] = HmacCustodyRoleAssignment(
        role=HmacCustodyRole.CUSTODY_OWNER,
        role_identity="synthetic-security-approver",
    )
    with pytest.raises(ValidationError):
        HmacPolicyIdentity(
            custody_policy_id="synthetic-hmac-custody-v1",
            rotation_policy_id="synthetic-hmac-rotation-v1",
            role_assignments=tuple(duplicate_role_assignments),
        )


def test_synthetic_hmac_lifecycle_retains_history_without_real_operations() -> None:
    policy = _hmac_policy()
    with pytest.raises(ValidationError):
        HmacPolicyIdentity(
            custody_policy_id="synthetic-hmac-custody",
            rotation_policy_id="synthetic-hmac-rotation-v1",
            role_assignments=_hmac_role_assignments(),
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

    first_binding = SyntheticHmacBindingRecord(
        binding_id="synthetic-binding-1",
        key_id="synthetic-key-1",
    )
    ledger.register_historical_binding(first_binding)
    assert (
        ledger.verify_historical_binding("synthetic-binding-1")
        == HmacBindingVerificationStatus.NOT_ISSUED
    )
    with pytest.raises(DuplicateHmacBindingIdentityError):
        ledger.register_historical_binding(first_binding)

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

    revoked_ledger = SyntheticHmacLifecycleLedger()
    revoked_ledger.register_synthetic_key(
        SyntheticHmacKeyRecord(key_id="synthetic-revoked-key", policy_identity=policy)
    )
    revoked_ledger.set_terminal_status("synthetic-revoked-key", HmacKeyState.REVOKED)
    with pytest.raises(HmacKeyUnavailableError):
        revoked_ledger.register_historical_binding(
            SyntheticHmacBindingRecord(
                binding_id="synthetic-revoked-binding",
                key_id="synthetic-revoked-key",
            )
        )
    with pytest.raises(HmacKeyUnavailableError):
        ledger.register_historical_binding(
            SyntheticHmacBindingRecord(
                binding_id="synthetic-compromised-binding",
                key_id="synthetic-key-2",
            )
        )


def test_batch_a_contracts_reject_extra_fields_bad_hashes_and_mutation() -> None:
    identity = _source_identity()
    with pytest.raises(ValidationError):
        BatchASourceIdentity.model_validate({**identity.model_dump(), "unexpected": "synthetic"})

    for malformed_hash in ("a" * 63, "a" * 65, "A" * 64, "g" * 64):
        with pytest.raises(ValidationError):
            SchemaVersionHashBinding(
                schema_version="synthetic-schema-v1",
                schema_sha256=malformed_hash,
            )
    with pytest.raises(ValidationError):
        SchemaVersionHashBinding(
            schema_version="synthetic-schema-v1",
            schema_sha256="a" * 64,
            unexpected="synthetic",
        )
    with pytest.raises(ValidationError):
        SourceSchemaCompatibilityRegistry(
            compatibility_policy_id="synthetic-policy",
            bindings=(
                SchemaVersionHashBinding(
                    schema_version="synthetic-schema-v1",
                    schema_sha256="a" * 64,
                ),
            ),
        )

    with pytest.raises(ValidationError):
        identity.source_system = "synthetic-other"  # type: ignore[misc]
    registry = DimensionMappingRegistry(
        registry_id="synthetic-dimension-registry-v8",
        policy_version="synthetic-dimension-mapping-v8",
        entries=(
            DimensionMappingEntry(
                dimension="farm",
                source_text="Farm A",
                canonical_id="synthetic-farm-a",
            ),
        ),
    )
    with pytest.raises((ValidationError, TypeError)):
        registry.entries += (  # type: ignore[misc]
            DimensionMappingEntry(
                dimension="farm",
                source_text="Farm B",
                canonical_id="synthetic-farm-b",
            ),
        )
