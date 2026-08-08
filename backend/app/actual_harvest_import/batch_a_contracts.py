"""Synthetic-only V0.3-S1 Batch A contract foundations.

This module defines the shapes and fail-closed boundaries needed before a real
source export is activated. It deliberately does not read files, calculate a
source hash, create a secret, or calculate an HMAC digest.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BATCH_A_CONTRACT_VERSION = "actual-harvest-batch-a-contract-v1"
IDENTIFIER_PATTERN = r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$"
POLICY_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[1-9][0-9]*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
_UNRESOLVED_SENTINELS = frozenset({"NOT_PROVIDED", "NOT_ISSUED", "PENDING"})


class BatchAContractError(ValueError):
    """Base error for deterministic Batch A contract rejection."""


class SchemaCompatibilityError(BatchAContractError):
    """Raised when a schema version/hash pair is not explicitly supported."""


class UnknownDimensionMappingError(BatchAContractError):
    """Raised when a source dimension value has no registered mapping."""


class DimensionMappingHistoryConflictError(BatchAContractError):
    """Raised when a newer registry changes or drops a historical mapping."""


class UnknownChainValueError(BatchAContractError):
    """Raised when a chain value is not in the explicit allowed-value registry."""


class DuplicateExportIdentityError(BatchAContractError):
    """Raised when an export identity is registered more than once."""


class ConflictingExportIdentityError(BatchAContractError):
    """Raised when one export identity is presented with different content."""


class DuplicateKeyIdentityError(BatchAContractError):
    """Raised when a key ID would overwrite a historical key identity."""


class DuplicateHmacBindingIdentityError(BatchAContractError):
    """Raised when a binding ID would overwrite historical binding metadata."""


class HmacKeyUnavailableError(BatchAContractError):
    """Raised when a real binding would use a revoked or compromised key."""


def validate_batch_a_identifier(value: object, *, field_name: str) -> str:
    """Validate a non-sensitive, opaque lower-case identifier.

    The rule intentionally permits synthetic values and existing repository
    values such as ``farm-system`` and ``2026-07``. It rejects whitespace,
    URI-like values, paths, and unresolved status sentinels.
    """

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    if not value or len(value) > 128:
        raise ValueError(f"{field_name} must be a non-empty identifier of at most 128 characters")
    if value.upper() in _UNRESOLVED_SENTINELS:
        raise ValueError(f"{field_name} must not use an unresolved status sentinel")
    if re.fullmatch(IDENTIFIER_PATTERN, value) is None:
        raise ValueError(
            f"{field_name} must match {IDENTIFIER_PATTERN} and must not contain a URL or path"
        )
    return value


def validate_sha256(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(SHA256_PATTERN, value) is None:
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 hex value")
    return value


def validate_policy_identity(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(POLICY_ID_PATTERN, value) is None:
        raise ValueError(
            f"{field_name} must match the versioned policy identity pattern {POLICY_ID_PATTERN}"
        )
    return value


def normalize_business_text(value: object, *, field_name: str = "business_text") -> str:
    """Apply the approved deterministic text normalization policy.

    NFC and surrounding-whitespace removal are the only transformations. The
    caller retains the original text separately; internal whitespace and case
    are deliberately not changed and locale inference is never attempted.
    """

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty after normalization")
    return normalized


class BatchASourceIdentity(BaseModel):
    """The four source identity fields required by the Batch A boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    source_system: str = Field(strict=True, min_length=1, max_length=128)
    source_dataset: str = Field(strict=True, min_length=1, max_length=128)
    source_version: str = Field(strict=True, min_length=1, max_length=128)
    schema_version: str = Field(strict=True, min_length=1, max_length=128)

    @field_validator("source_system", "source_dataset", "source_version", "schema_version")
    @classmethod
    def _validate_identifiers(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "source_identity")
        return validate_batch_a_identifier(value, field_name=field_name)


class SchemaCompatibilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"


class SchemaVersionHashBinding(BaseModel):
    """One immutable schema-version to schema-hash binding."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    schema_version: str = Field(strict=True, min_length=1, max_length=128)
    schema_sha256: str = Field(strict=True)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="schema_version")

    @field_validator("schema_sha256")
    @classmethod
    def _validate_schema_hash(cls, value: object) -> str:
        return validate_sha256(value, field_name="schema_sha256")


class SourceSchemaCompatibilityRegistry(BaseModel):
    """Versioned closed registry for deterministic schema compatibility checks."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    compatibility_policy_id: str = Field(strict=True, min_length=1, max_length=128)
    bindings: tuple[SchemaVersionHashBinding, ...] = Field(min_length=1)

    @field_validator("compatibility_policy_id")
    @classmethod
    def _validate_policy_id(cls, value: object) -> str:
        return validate_policy_identity(value, field_name="compatibility_policy_id")

    @model_validator(mode="after")
    def _reject_duplicate_bindings(self) -> SourceSchemaCompatibilityRegistry:
        seen_versions: set[str] = set()
        for binding in self.bindings:
            if binding.schema_version in seen_versions:
                raise ValueError("schema compatibility registry contains duplicate schema versions")
            seen_versions.add(binding.schema_version)
        return self

    def evaluate(
        self,
        *,
        schema_version: str,
        schema_sha256: str,
    ) -> SchemaCompatibilityStatus:
        validated_version = validate_batch_a_identifier(
            schema_version,
            field_name="schema_version",
        )
        validated_hash = validate_sha256(schema_sha256, field_name="schema_sha256")
        for binding in self.bindings:
            if binding.schema_version == validated_version:
                if binding.schema_sha256 == validated_hash:
                    return SchemaCompatibilityStatus.SUPPORTED
                return SchemaCompatibilityStatus.REJECTED
        return SchemaCompatibilityStatus.REJECTED

    def assert_compatible(
        self,
        *,
        schema_version: str,
        schema_sha256: str,
    ) -> None:
        if (
            self.evaluate(
                schema_version=schema_version,
                schema_sha256=schema_sha256,
            )
            != SchemaCompatibilityStatus.SUPPORTED
        ):
            raise SchemaCompatibilityError(
                "schema version/hash pair is not supported by the compatibility registry"
            )


DimensionName = Literal["farm", "subfarm", "variety"]


class DimensionMappingEntry(BaseModel):
    """One explicit source-text to canonical-dimension mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    dimension: DimensionName
    source_text: str = Field(strict=True, min_length=1, max_length=256)
    canonical_id: str = Field(strict=True, min_length=1, max_length=128)

    @field_validator("source_text")
    @classmethod
    def _validate_source_text(cls, value: object) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("source_text must be non-empty")
        return value

    @field_validator("canonical_id")
    @classmethod
    def _validate_canonical_id(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="canonical_id")

    @property
    def normalized_source_text(self) -> str:
        return normalize_business_text(self.source_text, field_name="source_text")


class ResolvedDimensionMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: DimensionName
    original_text: str
    normalized_text: str
    canonical_id: str


class DimensionMappingRegistry(BaseModel):
    """Versioned registry with unknown-value and history fail-closed behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    registry_id: str = Field(strict=True, min_length=1, max_length=128)
    policy_version: str = Field(strict=True, min_length=1, max_length=128)
    entries: tuple[DimensionMappingEntry, ...] = Field(min_length=1)

    @field_validator("registry_id")
    @classmethod
    def _validate_registry_id(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="registry_id")

    @field_validator("policy_version")
    @classmethod
    def _validate_policy_version(cls, value: object) -> str:
        return validate_policy_identity(value, field_name="policy_version")

    @model_validator(mode="after")
    def _reject_duplicate_source_values(self) -> DimensionMappingRegistry:
        seen: set[tuple[str, str]] = set()
        for entry in self.entries:
            key = (entry.dimension, entry.normalized_source_text)
            if key in seen:
                raise ValueError("dimension mapping registry contains duplicate source values")
            seen.add(key)
        return self

    def resolve(self, dimension: DimensionName, source_text: str) -> ResolvedDimensionMapping:
        normalized = normalize_business_text(source_text, field_name="source_text")
        for entry in self.entries:
            if entry.dimension == dimension and entry.normalized_source_text == normalized:
                return ResolvedDimensionMapping(
                    dimension=dimension,
                    original_text=source_text,
                    normalized_text=normalized,
                    canonical_id=entry.canonical_id,
                )
        raise UnknownDimensionMappingError(
            f"no mapping registered for dimension={dimension!r}, source_text={source_text!r}"
        )

    def assert_historical_compatibility(
        self,
        previous: DimensionMappingRegistry,
    ) -> None:
        current_by_source = {
            (entry.dimension, entry.normalized_source_text): entry.canonical_id
            for entry in self.entries
        }
        for previous_entry in previous.entries:
            key = (
                previous_entry.dimension,
                previous_entry.normalized_source_text,
            )
            current_canonical_id = current_by_source.get(key)
            if current_canonical_id is None:
                raise DimensionMappingHistoryConflictError(
                    "new registry dropped a historical dimension mapping"
                )
            if current_canonical_id != previous_entry.canonical_id:
                raise DimensionMappingHistoryConflictError(
                    "new registry changed a historical canonical dimension ID"
                )

    def ordered_entries(self) -> tuple[DimensionMappingEntry, ...]:
        return tuple(
            sorted(
                self.entries,
                key=lambda entry: (
                    entry.dimension,
                    entry.normalized_source_text,
                    entry.canonical_id,
                ),
            )
        )


class ChainNullPolicy(StrEnum):
    REJECT = "REJECT"
    NOT_PROVIDED = "NOT_PROVIDED"


class ChainResolutionStatus(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_PROVIDED = "NOT_PROVIDED"


class ChainValueResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ChainResolutionStatus
    original_value: str | None
    normalized_value: str | None


class ChainAllowedValuesRegistry(BaseModel):
    """Explicit versioned chain enum and explicit null policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    policy_version: str = Field(strict=True, min_length=1, max_length=128)
    allowed_values: tuple[str, ...] = Field(min_length=1)
    null_policy: ChainNullPolicy

    @field_validator("policy_version")
    @classmethod
    def _validate_policy_version(cls, value: object) -> str:
        return validate_policy_identity(value, field_name="policy_version")

    @field_validator("allowed_values", mode="before")
    @classmethod
    def _normalize_allowed_values(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("allowed_values must be a list or tuple")
        normalized = tuple(
            normalize_business_text(item, field_name="allowed_chain_value") for item in value
        )
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_values must not contain duplicates")
        return normalized

    def resolve(self, value: str | None) -> ChainValueResolution:
        if value is None or (isinstance(value, str) and not value.strip()):
            if self.null_policy == ChainNullPolicy.REJECT:
                raise UnknownChainValueError("null chain value is rejected by the registry")
            return ChainValueResolution(
                status=ChainResolutionStatus.NOT_PROVIDED,
                original_value=value,
                normalized_value=None,
            )
        normalized = normalize_business_text(value, field_name="chain_value")
        if normalized not in self.allowed_values:
            raise UnknownChainValueError(f"chain value {value!r} is not registered")
        return ChainValueResolution(
            status=ChainResolutionStatus.ALLOWED,
            original_value=value,
            normalized_value=normalized,
        )


class ExportIdentityMode(StrEnum):
    SOURCE_PROVIDED = "SOURCE_PROVIDED"
    PROJECT_DERIVED = "PROJECT_DERIVED"


class ExportIdentityClaim(BaseModel):
    """A source export identity claim; no file or hash is read here."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    mode: ExportIdentityMode
    source_identity: BatchASourceIdentity
    source_export_id: str | None = Field(default=None, strict=True, max_length=128)
    raw_file_sha256: str | None = Field(default=None, strict=True)
    delivery_fingerprint: str = Field(strict=True, min_length=1, max_length=128)

    @field_validator("source_export_id", "delivery_fingerprint")
    @classmethod
    def _validate_optional_identifiers(cls, value: object, info: object) -> str | None:
        if value is None:
            return None
        field_name = getattr(info, "field_name", "export_identity")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("raw_file_sha256")
    @classmethod
    def _validate_optional_hash(cls, value: object) -> str | None:
        if value is None:
            return None
        return validate_sha256(value, field_name="raw_file_sha256")

    @model_validator(mode="after")
    def _validate_mode_requirements(self) -> ExportIdentityClaim:
        if self.mode == ExportIdentityMode.SOURCE_PROVIDED:
            if self.source_export_id is None:
                raise ValueError("SOURCE_PROVIDED mode requires source_export_id")
        elif self.raw_file_sha256 is None:
            raise ValueError("PROJECT_DERIVED mode requires raw_file_sha256")
        return self


@dataclass(frozen=True, slots=True)
class ResolvedExportIdentity:
    mode: ExportIdentityMode
    identity_key: tuple[str, ...]
    delivery_fingerprint: str


def resolve_export_identity(claim: ExportIdentityClaim) -> ResolvedExportIdentity:
    identity = claim.source_identity
    common_key = (
        claim.mode.value,
        identity.source_system,
        identity.source_dataset,
        identity.source_version,
        identity.schema_version,
    )
    key: tuple[str, ...]
    if claim.mode == ExportIdentityMode.SOURCE_PROVIDED:
        assert claim.source_export_id is not None
        key = (*common_key, claim.source_export_id)
    else:
        assert claim.raw_file_sha256 is not None
        key = (*common_key, claim.raw_file_sha256)
    return ResolvedExportIdentity(
        mode=claim.mode,
        identity_key=key,
        delivery_fingerprint=claim.delivery_fingerprint,
    )


class ExportRegistrationResult(StrEnum):
    FIRST_SEEN = "FIRST_SEEN"
    EXACT_REPLAY = "EXACT_REPLAY"


class ExportIdentityLedger:
    """In-memory synthetic ledger for idempotency and conflict tests."""

    def __init__(self) -> None:
        self._fingerprints: dict[tuple[str, ...], str] = {}

    def register(self, identity: ResolvedExportIdentity) -> ExportRegistrationResult:
        prior = self._fingerprints.get(identity.identity_key)
        if prior is None:
            self._fingerprints[identity.identity_key] = identity.delivery_fingerprint
            return ExportRegistrationResult.FIRST_SEEN
        if prior == identity.delivery_fingerprint:
            return ExportRegistrationResult.EXACT_REPLAY
        raise ConflictingExportIdentityError(
            "export identity was presented with a different delivery fingerprint"
        )

    @property
    def registered_count(self) -> int:
        return len(self._fingerprints)


class HmacKeyState(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REVOKED = "REVOKED"
    COMPROMISED = "COMPROMISED"


class HmacBindingVerificationStatus(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_ISSUED = "NOT_ISSUED"
    CUSTODY_REQUIRED = "CUSTODY_REQUIRED"
    REJECTED = "REJECTED"


class HmacCustodyRole(StrEnum):
    CUSTODY_OWNER = "CUSTODY_OWNER"
    KEY_OPERATOR = "KEY_OPERATOR"
    BINDING_VERIFIER = "BINDING_VERIFIER"
    APPROVER = "APPROVER"


class HmacCustodyRoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    role: HmacCustodyRole
    role_identity: str = Field(strict=True, min_length=1, max_length=128)

    @field_validator("role_identity")
    @classmethod
    def _validate_role_identity(cls, value: object) -> str:
        return validate_batch_a_identifier(value, field_name="role_identity")


class HmacPolicyIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    custody_policy_id: str = Field(strict=True, min_length=1, max_length=128)
    rotation_policy_id: str = Field(strict=True, min_length=1, max_length=128)
    role_assignments: tuple[HmacCustodyRoleAssignment, ...] = Field(
        min_length=4,
        max_length=4,
    )

    @field_validator("custody_policy_id", "rotation_policy_id")
    @classmethod
    def _validate_policy_ids(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "hmac_policy_identity")
        return validate_policy_identity(value, field_name=field_name)

    @model_validator(mode="after")
    def _validate_role_assignments(self) -> HmacPolicyIdentity:
        by_role: dict[HmacCustodyRole, str] = {}
        for assignment in self.role_assignments:
            if assignment.role in by_role:
                raise ValueError("HMAC custody policy contains a duplicate role assignment")
            by_role[assignment.role] = assignment.role_identity
        if set(by_role) != set(HmacCustodyRole):
            raise ValueError("HMAC custody policy must assign every required role exactly once")
        if by_role[HmacCustodyRole.KEY_OPERATOR] == by_role[HmacCustodyRole.BINDING_VERIFIER]:
            raise ValueError("HMAC key operator and binding verifier must be separate roles")
        return self

    def role_identity(self, role: HmacCustodyRole) -> str:
        for assignment in self.role_assignments:
            if assignment.role == role:
                return assignment.role_identity
        raise ValueError(f"unknown HMAC custody role: {role!r}")


class SyntheticHmacKeyRecord(BaseModel):
    """Synthetic key metadata only; no secret material is represented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key_id: str = Field(strict=True, min_length=1, max_length=128)
    policy_identity: HmacPolicyIdentity
    status: HmacKeyState = HmacKeyState.ACTIVE
    replaced_by_key_id: str | None = None

    @field_validator("key_id", "replaced_by_key_id")
    @classmethod
    def _validate_key_ids(cls, value: object, info: object) -> str | None:
        if value is None:
            return None
        field_name = getattr(info, "field_name", "key_id")
        return validate_batch_a_identifier(value, field_name=field_name)

    @model_validator(mode="after")
    def _validate_replacement_state(self) -> SyntheticHmacKeyRecord:
        if self.status == HmacKeyState.ACTIVE and self.replaced_by_key_id is not None:
            raise ValueError("an active key must not point to a replacement")
        if self.status == HmacKeyState.RETIRED and self.replaced_by_key_id is None:
            raise ValueError("a retired key must retain its replacement key ID")
        return self


class SyntheticHmacBindingRecord(BaseModel):
    """Historical binding metadata; no HMAC operation is performed here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str = Field(strict=True, min_length=1, max_length=128)
    key_id: str = Field(strict=True, min_length=1, max_length=128)
    digest_or_not_issued: str = "NOT_ISSUED"

    @field_validator("binding_id", "key_id")
    @classmethod
    def _validate_binding_ids(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "binding_id")
        return validate_batch_a_identifier(value, field_name=field_name)

    @field_validator("digest_or_not_issued")
    @classmethod
    def _validate_digest(cls, value: object) -> str:
        if value == "NOT_ISSUED":
            return value
        return validate_sha256(value, field_name="digest_or_not_issued")


class SyntheticHmacLifecycleLedger:
    """Retains synthetic key and binding history without performing HMAC."""

    def __init__(self) -> None:
        self._keys: dict[str, SyntheticHmacKeyRecord] = {}
        self._bindings: dict[str, SyntheticHmacBindingRecord] = {}

    def register_synthetic_key(self, key: SyntheticHmacKeyRecord) -> None:
        if key.key_id in self._keys:
            raise DuplicateKeyIdentityError(f"key ID already exists: {key.key_id}")
        self._keys[key.key_id] = key

    def rotate_key(
        self,
        *,
        previous_key_id: str,
        new_key_id: str,
        policy_identity: HmacPolicyIdentity,
    ) -> SyntheticHmacKeyRecord:
        previous = self._keys.get(previous_key_id)
        if previous is None or previous.status != HmacKeyState.ACTIVE:
            raise HmacKeyUnavailableError("only an active key may be rotated")
        if new_key_id in self._keys:
            raise DuplicateKeyIdentityError(f"key ID already exists: {new_key_id}")
        retired = previous.model_copy(
            update={
                "status": HmacKeyState.RETIRED,
                "replaced_by_key_id": new_key_id,
            }
        )
        new_key = SyntheticHmacKeyRecord(
            key_id=new_key_id,
            policy_identity=policy_identity,
        )
        self._keys[previous.key_id] = retired
        self._keys[new_key.key_id] = new_key
        return new_key

    def set_terminal_status(self, key_id: str, status: HmacKeyState) -> None:
        if status not in {HmacKeyState.REVOKED, HmacKeyState.COMPROMISED}:
            raise ValueError("terminal status must be REVOKED or COMPROMISED")
        key = self._keys.get(key_id)
        if key is None:
            raise HmacKeyUnavailableError(f"unknown key ID: {key_id}")
        self._keys[key_id] = key.model_copy(update={"status": status})

    def register_historical_binding(self, binding: SyntheticHmacBindingRecord) -> None:
        if binding.binding_id in self._bindings:
            raise DuplicateHmacBindingIdentityError(
                f"binding ID already exists: {binding.binding_id}"
            )
        key = self._keys.get(binding.key_id)
        if key is None:
            raise HmacKeyUnavailableError(f"unknown key ID: {binding.key_id}")
        if key.status in {HmacKeyState.REVOKED, HmacKeyState.COMPROMISED}:
            raise HmacKeyUnavailableError("new binding cannot use a revoked or compromised key")
        self._bindings[binding.binding_id] = binding

    def verify_historical_binding(self, binding_id: str) -> HmacBindingVerificationStatus:
        binding = self._bindings.get(binding_id)
        if binding is None:
            return HmacBindingVerificationStatus.NOT_ISSUED
        if binding.digest_or_not_issued == "NOT_ISSUED":
            return HmacBindingVerificationStatus.NOT_ISSUED
        key = self._keys.get(binding.key_id)
        if key is None:
            return HmacBindingVerificationStatus.REJECTED
        if key.status in {HmacKeyState.REVOKED, HmacKeyState.COMPROMISED}:
            return HmacBindingVerificationStatus.CUSTODY_REQUIRED
        return HmacBindingVerificationStatus.ALLOWED

    def get_key(self, key_id: str) -> SyntheticHmacKeyRecord:
        key = self._keys.get(key_id)
        if key is None:
            raise HmacKeyUnavailableError(f"unknown key ID: {key_id}")
        return key

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    @property
    def binding_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))


__all__ = [
    "BATCH_A_CONTRACT_VERSION",
    "BatchAContractError",
    "BatchASourceIdentity",
    "ChainAllowedValuesRegistry",
    "ChainNullPolicy",
    "ChainResolutionStatus",
    "ChainValueResolution",
    "ConflictingExportIdentityError",
    "DimensionMappingEntry",
    "DimensionMappingHistoryConflictError",
    "DimensionMappingRegistry",
    "DuplicateExportIdentityError",
    "DuplicateHmacBindingIdentityError",
    "DuplicateKeyIdentityError",
    "ExportIdentityClaim",
    "ExportIdentityLedger",
    "ExportIdentityMode",
    "ExportRegistrationResult",
    "HmacBindingVerificationStatus",
    "HmacCustodyRole",
    "HmacCustodyRoleAssignment",
    "HmacKeyState",
    "HmacKeyUnavailableError",
    "HmacPolicyIdentity",
    "ResolvedDimensionMapping",
    "ResolvedExportIdentity",
    "SchemaCompatibilityError",
    "SchemaCompatibilityStatus",
    "SchemaVersionHashBinding",
    "SourceSchemaCompatibilityRegistry",
    "SyntheticHmacBindingRecord",
    "SyntheticHmacKeyRecord",
    "SyntheticHmacLifecycleLedger",
    "UnknownChainValueError",
    "UnknownDimensionMappingError",
    "normalize_business_text",
    "resolve_export_identity",
    "validate_batch_a_identifier",
    "validate_policy_identity",
    "validate_sha256",
]
