"""Formal TASK-013 forecast-season resolution against ``dim_season``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.canonical import sha256_payload
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import Blocker, ResolvedForecastSeasonIdentity
from backend.app.harvest_state.canonical import make_season_record_hash
from backend.app.harvest_state.schemas import ForecastSeasonIdentitySnapshot
from backend.app.models.master_data import Season

SEASON_RESOLUTION_POLICY_VERSION = "task13-season-resolution-policy-v1"
SEASON_RESOLUTION_POLICY_CONFIG = {
    "schema_version": "task13-season-resolution-policy-config-v1",
    "explicit_token_resolution": "exact_season_code",
    "integer_token_canonicalization": "base10_text",
    "string_token_normalization": "none",
    "empty_token_policy": "reject",
    "no_token_resolution": "inclusive_effective_as_of_date_range",
    "required_match_cardinality": 1,
    "date_range_start_operator": "less_than_or_equal",
    "date_range_end_operator": "greater_than_or_equal",
    "geographic_scope": "global",
    "availability_filter": "none",
    "season_id_derivation": "forbidden",
    "date_year_derivation": "forbidden",
}
SEASON_RESOLUTION_POLICY_CONFIG_HASH = sha256_payload(SEASON_RESOLUTION_POLICY_CONFIG)


@dataclass(frozen=True)
class SeasonResolutionResult:
    identity: ResolvedForecastSeasonIdentity | None = None
    blocker: Blocker | None = None

    def __post_init__(self) -> None:
        if bool(self.identity) == bool(self.blocker):
            raise ValueError("season resolution must contain exactly one identity or blocker")


class ForecastSeasonResolver(Protocol):
    async def resolve(
        self,
        session: AsyncSession,
        *,
        effective_as_of_date: date,
        requested_forecast_season: int | str | None,
    ) -> SeasonResolutionResult: ...


def _failure(code: BlockerCode, reason: str, message: str) -> SeasonResolutionResult:
    return SeasonResolutionResult(
        blocker=Blocker(
            code=code,
            message=message,
            details={"reason": reason},
            retry_hint="FIX_INPUT" if code == BlockerCode.INPUT_INVALID_SEASON else "WAIT_FOR_DATA",
        )
    )


class DatabaseForecastSeasonResolver:
    """Resolve exactly one authoritative Season row without date-year inference."""

    async def resolve(
        self,
        session: AsyncSession,
        *,
        effective_as_of_date: date,
        requested_forecast_season: int | str | None,
    ) -> SeasonResolutionResult:
        if isinstance(requested_forecast_season, bool):
            return _failure(
                BlockerCode.INPUT_INVALID_SEASON,
                "SEASON_TOKEN_INVALID",
                "forecast season token must be a positive integer or non-empty string",
            )
        if isinstance(requested_forecast_season, int):
            if requested_forecast_season <= 0:
                return _failure(
                    BlockerCode.INPUT_INVALID_SEASON,
                    "SEASON_TOKEN_INVALID",
                    "forecast season integer token must be positive",
                )
            statement = select(Season).where(Season.code == str(requested_forecast_season))
            no_match_reason = "SEASON_TOKEN_NOT_FOUND"
            ambiguous_reason = "SEASON_TOKEN_AMBIGUOUS"
        elif isinstance(requested_forecast_season, str):
            if requested_forecast_season == "":
                return _failure(
                    BlockerCode.INPUT_INVALID_SEASON,
                    "SEASON_TOKEN_INVALID",
                    "forecast season string token must be non-empty",
                )
            statement = select(Season).where(Season.code == requested_forecast_season)
            no_match_reason = "SEASON_TOKEN_NOT_FOUND"
            ambiguous_reason = "SEASON_TOKEN_AMBIGUOUS"
        elif requested_forecast_season is None:
            statement = select(Season).where(
                Season.start_date <= effective_as_of_date,
                Season.end_date >= effective_as_of_date,
            )
            no_match_reason = "SEASON_DATE_RANGE_NOT_FOUND"
            ambiguous_reason = "SEASON_DATE_RANGE_AMBIGUOUS"
        else:
            return _failure(
                BlockerCode.INPUT_INVALID_SEASON,
                "SEASON_TOKEN_INVALID",
                "forecast season token type is invalid",
            )
        try:
            rows = list((await session.scalars(statement)).all())
        except Exception:  # noqa: BLE001 - stable typed boundary
            return _failure(
                BlockerCode.UPSTREAM_READ_FAILURE,
                "SEASON_REGISTRY_READ_FAILED",
                "forecast season registry could not be read",
            )
        if not rows:
            return _failure(
                BlockerCode.INPUT_INVALID_SEASON,
                no_match_reason,
                "forecast season did not resolve to an authoritative row",
            )
        if len(rows) != 1:
            return _failure(
                BlockerCode.INPUT_INVALID_SEASON,
                ambiguous_reason,
                "forecast season resolved to multiple authoritative rows",
            )
        season = rows[0]
        snapshot = ForecastSeasonIdentitySnapshot(
            season_id=season.id,
            season_code=season.code,
            start_date=season.start_date,
            end_date=season.end_date,
            season_record_hash=make_season_record_hash(
                season_id=season.id,
                season_code=season.code,
                start_date=season.start_date,
                end_date=season.end_date,
            ),
        )
        return SeasonResolutionResult(
            identity=ResolvedForecastSeasonIdentity(
                season_snapshot=snapshot,
                season_resolution_policy_version=SEASON_RESOLUTION_POLICY_VERSION,
                season_resolution_policy_config_hash=SEASON_RESOLUTION_POLICY_CONFIG_HASH,
            )
        )


__all__ = [
    "DatabaseForecastSeasonResolver",
    "ForecastSeasonResolver",
    "SEASON_RESOLUTION_POLICY_CONFIG",
    "SEASON_RESOLUTION_POLICY_CONFIG_HASH",
    "SEASON_RESOLUTION_POLICY_VERSION",
    "SeasonResolutionResult",
]
