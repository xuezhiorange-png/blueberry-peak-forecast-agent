"""SQLite-backed tests for ``resolve_location`` adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from backend.app.agent.adapters.location import DefaultLocationAdapter
from backend.app.agent.enums import BlockerCode
from backend.app.agent.ports import LocationResolverPort
from backend.app.agent.schemas import (
    AdvancedOverrides,
    LocationInput,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    ResolveLocationInput,
)


def _mk_nr(
    *,
    status: str,
    candidates: list[dict] | None = None,
    warning: str | None = None,
    location_reference_id: int | None = None,
) -> NormalizedAgentRequest:
    return NormalizedAgentRequest(
        request_id="r1",
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
        effective_as_of_date=date(2026, 3, 1),
        effective_forecast_season=2026,
        season_resolution_policy_version="season-calendar/v1",
        season_calendar_config_hash="a" * 64,
        requested_as_of_date_provenance=RequestedAsOfDateProvenance(
            caller_requested_as_of_date=date(2026, 3, 1),
            effective_as_of_date=date(2026, 3, 1),
            override_applied=False,
            override_kind=None,
            source_attestation=None,
            source_ref=None,
        ),
        normalized_location=ResolvedLocation(
            status=status,
            location_reference_id=location_reference_id,
            matched_location_method="REFERENCE_ID",
            warning=warning,
            candidates=candidates or [],
        ),
        location_input=LocationInput(
            raw_text="云南曲靖",
            location_reference_id=location_reference_id,
        ),
        varieties=[NormalizedVarietyInput(variety_id="101", planting_area_mu="100.0")],
        advanced_overrides=AdvancedOverrides(),
        canonical_request_hash="0" * 64,
    )


class _StaticPort(LocationResolverPort):
    """Returns a pre-canned ResolvedLocation per-test."""

    def __init__(
        self,
        *,
        status: str,
        candidates: list[dict] | None = None,
        warning: str | None = None,
        location_reference_id: int | None = None,
    ):
        self._resolved = ResolvedLocation(
            status=status,
            location_reference_id=location_reference_id,
            matched_location_method="REFERENCE_ID",
            warning=warning,
            candidates=candidates or [],
        )

    async def resolve(
        self, *, session: Any, location: dict[str, Any], as_of_date: Any
    ) -> ResolvedLocation:
        return self._resolved


@pytest.mark.asyncio
async def test_resolve_location_unresolved_emits_blocker(sqlite_session):
    adapter = DefaultLocationAdapter(resolver=_StaticPort(status="unresolved"))
    out = await adapter.execute(
        sqlite_session, input=ResolveLocationInput(normalized_request=_mk_nr(status="unresolved"))
    )
    # P0-3.6: catalog_version is now derived per-resolution (sha256), not a
    # hardcoded constant.  Confirm it is a 64-char lowercase hex string.
    assert len(out.location_catalog_version) == 64
    assert all(c in "0123456789abcdef" for c in out.location_catalog_version)
    codes = {b.code for b in out.blockers}
    assert BlockerCode.LOCATION_UNRESOLVED in codes


@pytest.mark.asyncio
async def test_resolve_location_emits_no_blocker_for_resolved_status(sqlite_session):
    adapter = DefaultLocationAdapter(
        resolver=_StaticPort(status="resolved", location_reference_id=1)
    )
    out = await adapter.execute(
        sqlite_session, input=ResolveLocationInput(normalized_request=_mk_nr(status="resolved"))
    )
    codes = {b.code for b in out.blockers}
    assert BlockerCode.LOCATION_UNRESOLVED not in codes
    assert BlockerCode.LOCATION_AMBIGUOUS not in codes


@pytest.mark.asyncio
async def test_resolve_location_ambiguous_emits_blocker_and_top_n(sqlite_session):
    candidates = [
        {"location_reference_id": 1, "score": "0.500", "distance_km": "1.0"},
        {"location_reference_id": 2, "score": "0.500", "distance_km": "1.5"},
    ]
    port = _StaticPort(status="ambiguous", candidates=candidates)
    adapter = DefaultLocationAdapter(resolver=port, ambiguous_top_n=5)
    out = await adapter.execute(
        sqlite_session,
        input=ResolveLocationInput(
            normalized_request=_mk_nr(status="ambiguous", candidates=candidates)
        ),
    )
    codes = {b.code for b in out.blockers}
    assert BlockerCode.LOCATION_AMBIGUOUS in codes
    assert len(out.candidates) == 2


@pytest.mark.asyncio
async def test_resolve_location_stale_catalog_warning(sqlite_session):
    port = _StaticPort(status="resolved", warning="location_catalog_stale", location_reference_id=1)
    adapter = DefaultLocationAdapter(resolver=port)
    out = await adapter.execute(
        sqlite_session,
        input=ResolveLocationInput(
            normalized_request=_mk_nr(
                status="resolved", warning="location_catalog_stale", location_reference_id=1
            )
        ),
    )
    codes = {b.code for b in out.blockers}
    assert BlockerCode.LOCATION_CATALOG_STALE in codes


@pytest.mark.asyncio
async def test_resolve_location_deterministic_same_input(sqlite_session):
    port = _StaticPort(status="resolved", location_reference_id=42)
    adapter = DefaultLocationAdapter(resolver=port)
    nr = _mk_nr(status="resolved", location_reference_id=42)
    out1 = await adapter.execute(sqlite_session, input=ResolveLocationInput(normalized_request=nr))
    out2 = await adapter.execute(sqlite_session, input=ResolveLocationInput(normalized_request=nr))
    assert out1.resolved_location == out2.resolved_location


def test_resolve_location_requires_port_or_rules():
    """The adapter MUST refuse to operate without either a port or rules."""

    adapter = DefaultLocationAdapter()
    assert adapter._resolver is None
    assert adapter._rules is None
