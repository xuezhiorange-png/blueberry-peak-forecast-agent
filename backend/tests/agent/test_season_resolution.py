from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.agent.schemas import LocationInput, MinimalInputRequest, MinimalVarietyInput
from backend.app.agent.season_resolution import (
    SEASON_RESOLUTION_POLICY_CONFIG_HASH,
    DatabaseForecastSeasonResolver,
)
from backend.app.models.master_data import Season


class _Rows:
    def __init__(self, rows: list[Season]) -> None:
        self._rows = rows

    def all(self) -> list[Season]:
        return self._rows


class _ResolverSession:
    def __init__(self, rows: list[Season] | None = None, *, fail: bool = False) -> None:
        self.rows = rows or []
        self.fail = fail

    async def scalars(self, _statement):
        if self.fail:
            raise RuntimeError("registry unavailable")
        return _Rows(self.rows)


@pytest.mark.asyncio
async def test_integer_token_matches_exact_code_not_database_id(sqlite_session) -> None:
    sqlite_session.add(
        Season(
            id=1,
            code="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
    )
    await sqlite_session.flush()

    result = await DatabaseForecastSeasonResolver().resolve(
        sqlite_session,
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season=2026,
    )

    assert result.blocker is None
    assert result.identity is not None
    assert result.identity.season_snapshot.season_id == 1
    assert result.identity.season_snapshot.season_code == "2026"
    assert (
        result.identity.season_resolution_policy_config_hash
        == "7452669a4cc8723010b2276dbab714d6c218401d44f4aa948768524400ffe708"
        == SEASON_RESOLUTION_POLICY_CONFIG_HASH
    )


@pytest.mark.asyncio
async def test_string_token_is_not_normalized(sqlite_session) -> None:
    sqlite_session.add(
        Season(
            id=2,
            code="2025-2026",
            start_date=date(2025, 11, 1),
            end_date=date(2026, 4, 30),
        )
    )
    await sqlite_session.flush()
    resolver = DatabaseForecastSeasonResolver()

    exact = await resolver.resolve(
        sqlite_session,
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season="2025-2026",
    )
    altered = await resolver.resolve(
        sqlite_session,
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season=" 2025-2026 ",
    )

    assert exact.identity is not None
    assert altered.blocker is not None
    assert altered.blocker.details == {"reason": "SEASON_TOKEN_NOT_FOUND"}


@pytest.mark.asyncio
async def test_no_token_uses_formal_inclusive_date_range(sqlite_session) -> None:
    sqlite_session.add(
        Season(
            id=77,
            code="non-year-code",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
    )
    await sqlite_session.flush()

    result = await DatabaseForecastSeasonResolver().resolve(
        sqlite_session,
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season=None,
    )

    assert result.identity is not None
    assert result.identity.season_snapshot.season_id == 77
    assert result.identity.season_snapshot.season_code == "non-year-code"


@pytest.mark.asyncio
async def test_no_match_returns_typed_reason(sqlite_session) -> None:
    result = await DatabaseForecastSeasonResolver().resolve(
        sqlite_session,
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season=2026,
    )
    assert result.blocker is not None
    assert result.blocker.code.value == "INPUT_INVALID_SEASON"
    assert result.blocker.details == {"reason": "SEASON_TOKEN_NOT_FOUND"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token", "reason"),
    [
        (2026, "SEASON_TOKEN_AMBIGUOUS"),
        (None, "SEASON_DATE_RANGE_AMBIGUOUS"),
    ],
)
async def test_multiple_matches_fail_closed(token, reason: str) -> None:
    rows = [
        Season(id=1, code="2026", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30)),
        Season(id=2, code="2026", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30)),
    ]
    result = await DatabaseForecastSeasonResolver().resolve(
        _ResolverSession(rows),
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season=token,
    )
    assert result.blocker is not None
    assert result.blocker.details == {"reason": reason}


@pytest.mark.asyncio
async def test_registry_read_failure_is_typed() -> None:
    result = await DatabaseForecastSeasonResolver().resolve(
        _ResolverSession(fail=True),
        effective_as_of_date=date(2026, 3, 1),
        requested_forecast_season=2026,
    )
    assert result.blocker is not None
    assert result.blocker.code.value == "UPSTREAM_READ_FAILURE"
    assert result.blocker.details == {"reason": "SEASON_REGISTRY_READ_FAILED"}


@pytest.mark.parametrize("token", [True, 0, -1, ""])
def test_request_rejects_invalid_season_tokens(token: object) -> None:
    with pytest.raises(ValidationError):
        MinimalInputRequest(
            request_id="request",
            location=LocationInput(raw_text="Yunnan"),
            varieties=[MinimalVarietyInput(variety_id="101", planting_area_mu="1")],
            requested_forecast_season=token,
        )
