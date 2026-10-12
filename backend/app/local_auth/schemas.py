"""Strict end-user requests; no client-supplied actor or permission claims."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from backend.app.forecast_intelligence.read_schemas import ForecastIdentity, Hash, QualityReadQuery
from backend.app.local_auth.passwords import password, username

Role = Literal["ADMIN", "BUSINESS_USER"]
Reason = Annotated[StrictStr, Field(min_length=1, max_length=500)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Login(RequestModel):
    username: StrictStr
    password: Annotated[StrictStr, Field(min_length=15, max_length=128)]

    @field_validator("username")
    @classmethod
    def normalized(cls, value: str) -> str:
        return username(value)


class CreateAccount(RequestModel):
    username: StrictStr
    initial_password: StrictStr
    role: Role
    reason: Reason

    @field_validator("username")
    @classmethod
    def normalized(cls, value: str) -> str:
        return username(value)

    @field_validator("initial_password")
    @classmethod
    def bounded(cls, value: str) -> str:
        return password(value)


class ChangePassword(RequestModel):
    current_password: Annotated[StrictStr, Field(min_length=15, max_length=128)]
    new_password: Annotated[StrictStr, Field(min_length=15, max_length=128)]


class StatusChange(RequestModel):
    status: Literal["ACTIVE", "DISABLED"]
    expected_auth_revision: Annotated[StrictInt, Field(gt=0)]
    reason: Reason


class RoleChange(RequestModel):
    role: Role
    expected_auth_revision: Annotated[StrictInt, Field(gt=0)]
    reason: Reason


class ResetPassword(RequestModel):
    new_temporary_password: Annotated[StrictStr, Field(min_length=15, max_length=128)]
    expected_auth_revision: Annotated[StrictInt, Field(gt=0)]
    reason: Reason


class ForecastBinding(RequestModel):
    identity: ForecastIdentity
    expected_source_result_hash: Hash
    source_authority_version: Annotated[StrictStr, Field(min_length=1, max_length=200)]

    @field_validator("identity")
    @classmethod
    def no_wildcard(cls, value: ForecastIdentity) -> ForecastIdentity:
        if "*" in value.model_dump_json():
            raise ValueError("Wildcard grants forbidden")
        return value


class QualityBinding(RequestModel):
    query: QualityReadQuery
    source_split: Literal["EXPOSED_OOT"]
    target_season: Literal["2025-2026"]
    scope: Literal["BASE_COHORT_AGGREGATE"]
    evidence_policy_version: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    evidence_hashes: dict[str, Hash]
    evidence_set_digest: Hash


class GrantFields(RequestModel):
    subject_principal_id: UUID
    organization_id: Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r"^[^*]+$")]
    valid_from: datetime
    valid_until: datetime
    expected_grant_revision: Annotated[StrictInt, Field(gt=0)]
    approval_reference: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    reason: Reason

    @field_validator("valid_from", "valid_until")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone required")
        return value


class ForecastGrant(GrantFields):
    resource_kind: Literal["FORECAST"]
    capability: Literal["may_read_forecast"]
    binding: ForecastBinding


class QualityGrantRequest(GrantFields):
    resource_kind: Literal["QUALITY"]
    capability: Literal["may_read_quality"]
    binding: QualityBinding


class RevokeGrant(RequestModel):
    expected_grant_revision: Annotated[StrictInt, Field(gt=0)]
    reason: Reason


class PublisherBoundary(RequestModel):
    """Trusted server configuration; never populated from HTTP requests."""

    principal_id: UUID
    organization_ids: tuple[StrictStr, ...]
    manageable_account_ids: tuple[UUID, ...]
    create_roles: tuple[Role, ...] = ()
    approved_grants: tuple[ForecastGrant | QualityGrantRequest, ...] = ()

    def validate_scope(self) -> Self:
        if not self.organization_ids or any("*" in v for v in self.organization_ids):
            raise ValueError("Explicit publisher boundary required")
        return self
