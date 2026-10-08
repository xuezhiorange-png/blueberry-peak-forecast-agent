"""Server-owned service-account grants, checked before any repository/evidence read.

These exact grants deliberately do not claim dynamic source-domain or end-user ACLs.
Existing HTTP authorization is unchanged; both transports use the existing permission names.
"""

from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator

from backend.app.forecast_intelligence.read_schemas import (
    ForecastIdentity,
    ForecastReadQuery,
    Hash,
    Identifier,
    QualityReadQuery,
    ReadError,
    ReadModel,
)


class RunGrant(ReadModel):
    principal_id: Identifier
    forecast_identity: ForecastIdentity
    source_result_hash: Hash


class QualityGrant(ReadModel):
    mode: Literal["HISTORICAL_VALIDATION", "CURRENT_PRODUCTION_ACCURACY"]
    model_id: Literal["V0_15_S5_M1_RIDGE"] = "V0_15_S5_M1_RIDGE"


class ServiceAccount(ReadModel):
    principal_id: Identifier
    secret: SecretStr
    permissions: frozenset[Literal["may_read_forecast", "may_read_quality"]]
    run_grants: tuple[RunGrant, ...]
    quality_grants: tuple[QualityGrant, ...]

    @field_validator("principal_id")
    @classmethod
    def explicit_identity(cls, value: str) -> str:
        if not value.strip() or "*" in value:
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return value

    @field_validator("secret")
    @classmethod
    def mandatory_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return value

    @model_validator(mode="after")
    def exact_grants(self) -> Self:
        if not self.permissions or not (self.run_grants or self.quality_grants):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        identities = []
        for grant in self.run_grants:
            if grant.principal_id != self.principal_id:
                raise ValueError("AUTHORIZATION_UNAVAILABLE")
            identity = grant.forecast_identity.model_dump_json()
            if "*" in identity or identity in identities:
                raise ValueError("AUTHORIZATION_UNAVAILABLE")
            identities.append(identity)
        quality = [(g.mode, g.model_id) for g in self.quality_grants]
        if len(quality) != len(set(quality)):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return self


def require_capability(account: ServiceAccount, *, quality: bool = False) -> None:
    permission = "may_read_quality" if quality else "may_read_forecast"
    if permission not in account.permissions:
        raise ReadError("FORBIDDEN", 403)


def authorize_run(account: ServiceAccount, query: ForecastReadQuery) -> ForecastReadQuery:
    require_capability(account)
    identity = ForecastIdentity.model_validate(
        query.model_dump(exclude={"expected_source_result_hash"})
    )
    for grant in account.run_grants:
        if grant.forecast_identity == identity:
            if query.expected_source_result_hash not in (None, grant.source_result_hash):
                raise ReadError("FORBIDDEN", 403)
            return query.model_copy(
                update={"expected_source_result_hash": grant.source_result_hash}
            )
    raise ReadError("FORBIDDEN", 403)


def authorize_quality(account: ServiceAccount, query: QualityReadQuery) -> None:
    require_capability(account, quality=True)
    if not any(
        g.mode == query.mode and g.model_id == query.model_id for g in account.quality_grants
    ):
        raise ReadError("FORBIDDEN", 403)


def verify_granted_result(query: ForecastReadQuery, source_hash: str | None) -> None:
    if source_hash != query.expected_source_result_hash:
        raise ReadError("AUTHORITY_MISMATCH", 409)
