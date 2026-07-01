from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backend.app.harvest_state.authority_schemas import (
    Task9CapacityPoolDefinitionSemanticBundle,
    Task9DailyCapacitySemanticInput,
    Task9HolidayCalendarSemanticBundle,
    Task9InitialInventorySemanticBundle,
    Task9MatureLossSemanticInput,
    Task9RunParameterPackageSemanticInput,
    Task9WeatherRuleSemanticInput,
)
from backend.app.harvest_state.enums import AuthorityFamily, ForecastQuantile


class AuthorityResolutionMode(StrEnum):
    CURRENT_OPERATIONAL = "CURRENT_OPERATIONAL"
    FIRST_TIME_HISTORICAL = "FIRST_TIME_HISTORICAL"
    EXACT_REFERENCE = "EXACT_REFERENCE"


@dataclass(frozen=True, slots=True)
class AuthorityExactReference:
    authority_id: int
    authority_stable_key: str
    business_version: str
    revision: int
    row_hash: str


@dataclass(frozen=True, slots=True)
class AuthorityCandidateSnapshot:
    authority_id: int
    authority_family: AuthorityFamily
    authority_stable_key: str
    business_version: str
    revision: int
    row_hash: str
    status: str
    available_at_local_date: date
    consumable_from_local_date: date | None
    consumable_to_local_date: date | None


@dataclass(frozen=True, slots=True)
class CapacityPoolResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    season_id: int
    destination_factory_id: int
    capacity_pool_code: str
    effective_local_date: date
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class DailyCapacityResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    season_id: int
    destination_factory_id: int
    capacity_pool_code: str
    capacity_date: date
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class HolidayCalendarResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    season_id: int
    calendar_code: str
    lifecycle_timezone_name: str
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class WeatherRuleResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    rule_code: str
    lifecycle_timezone_name: str
    effective_local_date: date
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class RunParameterPackageResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    season_id: int
    destination_factory_id: int
    farm_scope_key: str
    effective_local_date: date
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class InitialInventoryResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    season_id: int
    destination_factory_id: int
    opening_state_date: date
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class MatureLossResolutionRequest:
    mode: AuthorityResolutionMode
    as_of_local_date: date
    timezone_name: str
    season_id: int
    destination_factory_id: int
    capacity_pool_code: str
    state_date: date
    forecast_quantile: ForecastQuantile
    exact_reference: AuthorityExactReference | None = None


@dataclass(frozen=True, slots=True)
class ResolvedAuthorityBase:
    mode: AuthorityResolutionMode
    authority_id: int
    authority_family: AuthorityFamily
    authority_stable_key: str
    business_version: str
    revision: int
    row_hash: str
    status: str
    available_at_local_date: date
    consumable_from_local_date: date | None
    consumable_to_local_date: date | None


@dataclass(frozen=True, slots=True)
class ResolvedCapacityPoolAuthority(ResolvedAuthorityBase):
    semantic_bundle: Task9CapacityPoolDefinitionSemanticBundle
    child_row_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedDailyCapacityAuthority(ResolvedAuthorityBase):
    semantic_input: Task9DailyCapacitySemanticInput
    parent_pool: ResolvedCapacityPoolAuthority


@dataclass(frozen=True, slots=True)
class ResolvedHolidayCalendarAuthority(ResolvedAuthorityBase):
    semantic_bundle: Task9HolidayCalendarSemanticBundle


@dataclass(frozen=True, slots=True)
class ResolvedWeatherRuleAuthority(ResolvedAuthorityBase):
    semantic_input: Task9WeatherRuleSemanticInput


@dataclass(frozen=True, slots=True)
class ResolvedRunParameterPackageAuthority(ResolvedAuthorityBase):
    semantic_input: Task9RunParameterPackageSemanticInput
    holiday_calendar: ResolvedHolidayCalendarAuthority
    weather_rule: ResolvedWeatherRuleAuthority


@dataclass(frozen=True, slots=True)
class ResolvedInitialInventoryAuthority(ResolvedAuthorityBase):
    semantic_bundle: Task9InitialInventorySemanticBundle
    child_row_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedMatureLossAuthority(ResolvedAuthorityBase):
    semantic_input: Task9MatureLossSemanticInput
