"""Independent mandatory MCP credentials and trusted transport configuration."""

import os
from hmac import compare_digest
from typing import Self

from pydantic import Field, StrictBool, ValidationError, field_validator, model_validator

from backend.app.forecast_intelligence.read_access import ServiceAccount
from backend.app.forecast_intelligence.read_schemas import ReadModel

AUTH_HEADER = b"x-forecast-intelligence-key"


class MCPServiceConfig(ReadModel):
    accounts: tuple[ServiceAccount, ...] = Field(min_length=1)
    allowed_hosts: tuple[str, ...] = Field(min_length=1)
    allowed_origins: tuple[str, ...]
    require_https: StrictBool = True

    @field_validator("allowed_hosts", "allowed_origins")
    @classmethod
    def exact_allowlist(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not v.strip() or "*" in v or v != v.strip() for v in values):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return values

    @model_validator(mode="after")
    def distinct_accounts(self) -> Self:
        ids = [a.principal_id for a in self.accounts]
        secrets = [a.secret.get_secret_value() for a in self.accounts]
        if len(set(ids)) != len(ids) or len(set(secrets)) != len(secrets):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return self


def environment_config() -> MCPServiceConfig | None:
    try:
        return MCPServiceConfig.model_validate_json(
            os.environ.get("FORECAST_INTELLIGENCE_MCP_CONFIG", "")
        )
    except (ValidationError, ValueError):
        return None


def authenticate(
    config: MCPServiceConfig, headers: list[tuple[bytes, bytes]]
) -> ServiceAccount | None:
    supplied = [v for k, v in headers if k.lower() == AUTH_HEADER]
    if len(supplied) != 1:
        return None
    account = None
    # Do not stop at the first matching credential; no client identity is trusted.
    for candidate in config.accounts:
        if compare_digest(supplied[0], candidate.secret.get_secret_value().encode("utf-8")):
            account = candidate
    return account
