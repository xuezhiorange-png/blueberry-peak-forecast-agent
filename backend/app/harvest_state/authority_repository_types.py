from __future__ import annotations

from dataclasses import dataclass

from backend.app.harvest_state.enums import AuthorityFamily


@dataclass(frozen=True, slots=True)
class AuthorityPersistentIdentity:
    authority_family: AuthorityFamily
    authority_stable_key: str
    authority_business_version: str
    authority_revision: int


@dataclass(frozen=True, slots=True)
class AuthorityCreateOrLoadResult[AuthorityModelT]:
    authority: AuthorityModelT
    created: bool
    persistent_identity: AuthorityPersistentIdentity
    row_hash: str


@dataclass(frozen=True, slots=True)
class RunPackageReplacementResult:
    old_holiday_id: int
    new_holiday_id: int
    old_weather_id: int
    new_weather_id: int
    old_package_id: int
    new_package_id: int
