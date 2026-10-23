"""Server-owned research catalog. No client paths, implicit grants or admin defaults.

This is deployment configuration, not a new identity/approval service. Existing
sessions, CSRF, account locks and revisions remain authoritative. Disabled unless
an operator registers exact resources and principal/revision-bound capabilities.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from backend.app.local_auth.sessions import AuthError, Principal, now
from backend.app.rolling_forecast.model_artifacts import ModelReference
from backend.app.rolling_forecast.schemas import Area, Calendar, Contract, Hash, Name
from backend.research.v019_synthetic_validation import digest


class Member(Contract):
    season_business_key: Name
    farm_business_key: Name
    subfarm_business_key: Name
    variety_business_key: Name


class Snapshot(Contract):
    reference: Name
    snapshot_id: int = Field(gt=0)
    snapshot_hash: Hash
    source_system: Name
    provenance: Literal["SYNTHETIC_TEST_FIXTURE", "AUTHORIZED_HISTORICAL"]
    members: tuple[Member, ...] = Field(min_length=1)
    membership_authority_hash: Hash
    mapping_registry_hash: Hash
    completeness_authority_hash: Hash
    completeness_known_at: datetime
    complete_dates: tuple[date, ...]
    confirmed_zero_dates: tuple[date, ...] = ()
    quantity_basis: Literal["FIELD_HARVEST_WEIGHT"] = "FIELD_HARVEST_WEIGHT"

    @model_validator(mode="after")
    def unique_members(self) -> Self:
        if len(set(digest(m.model_dump(mode="json")) for m in self.members)) != len(self.members):
            raise ValueError("AMBIGUOUS_BASE_MEMBERSHIP")
        if len(set(self.complete_dates)) != len(self.complete_dates) or not set(
            self.confirmed_zero_dates
        ) <= set(self.complete_dates):
            raise ValueError("INVALID_COMPLETENESS_AUTHORITY")
        return self


class Context(Contract):
    reference: Name
    organization_id: Name
    area: Area
    calendar: Calendar
    models: tuple[ModelReference, ...] = Field(min_length=1)
    snapshots: tuple[Snapshot, ...] = Field(min_length=1)
    modes: tuple[Literal["RESEARCH_SHADOW", "RETROSPECTIVE_DATE_BOUND"], ...]
    review_snapshots: tuple["MatureSnapshot", ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.area.season != self.calendar.season or not self.modes:
            raise ValueError("SCOPE_MISMATCH")
        for resources in (self.models, self.snapshots, self.review_snapshots):
            if len({r.reference for r in resources}) != len(resources):
                raise ValueError("AMBIGUOUS_RESOURCE_REFERENCE")
        # Permission is intentionally NOT granted for current real actuals.
        if self.calendar.season == "2026-2027" and any(
            s.provenance != "SYNTHETIC_TEST_FIXTURE"
            for s in (*self.snapshots, *self.review_snapshots)
        ):
            raise ValueError("CURRENT_SEASON_REAL_READ_NOT_AUTHORIZED")
        return self


class MatureSnapshot(Snapshot):
    mature_through: date
    label_cutoff_at: datetime
    maturity_authority_hash: Hash


class Capability(Contract):
    principal_id: Name
    auth_revision: int = Field(ge=0)
    grant_revision: int = Field(ge=0)
    contexts: tuple[Name, ...]
    operations: tuple[Literal["issue", "read", "compare", "evaluate"], ...]
    valid_from: datetime
    valid_until: datetime


class Catalog(Contract):
    schema_version: Literal["ROLLING_SHADOW_CATALOG_V1"]
    revision: Name
    contexts: tuple[Context, ...]
    capabilities: tuple[Capability, ...]

    @model_validator(mode="after")
    def unambiguous(self) -> Self:
        if len({c.reference for c in self.contexts}) != len(self.contexts):
            raise ValueError("AMBIGUOUS_CONTEXT")
        # A canonical source member must never silently count toward two Bases.
        bindings: dict[tuple[str, str], str] = {}
        for c in self.contexts:
            for s in (*c.snapshots, *c.review_snapshots):
                for m in s.members:
                    key = (c.calendar.season, digest(m.model_dump(mode="json")))
                    if key in bindings and bindings[key] != c.area.base_id:
                        raise ValueError("AMBIGUOUS_BASE_MEMBERSHIP")
                    bindings[key] = c.area.base_id
        return self

    @property
    def fingerprint(self) -> str:
        return digest(self.model_dump(mode="json"))

    def allowed(self, principal: Principal, operation: str) -> list[Context]:
        names = {
            name
            for cap in self.capabilities
            if cap.principal_id == principal.principal_id
            and cap.auth_revision == principal.auth_revision
            and cap.grant_revision == principal.grant_revision
            and cap.valid_from <= now() < cap.valid_until
            and operation in cap.operations
            for name in cap.contexts
        }
        return [c for c in self.contexts if c.reference in names]


def load_catalog(path: str, organization_ids: list[str]) -> Catalog:
    try:
        file = Path(path)
        if not file.is_absolute() or any(p.is_symlink() for p in (file, *file.parents)):
            raise ValueError("INVALID_CATALOG_PATH")
        if file.stat().st_mode & 0o022 or file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("UNSAFE_CATALOG_FILE")
        catalog = Catalog.model_validate_json(file.read_bytes())
        if any(c.organization_id not in organization_ids for c in catalog.contexts):
            raise ValueError("ORGANIZATION_AUTHORITY_MISMATCH")
        return catalog
    except (OSError, ValueError):
        raise AuthError("ROLLING_FORECAST_UNAVAILABLE", 503) from None
