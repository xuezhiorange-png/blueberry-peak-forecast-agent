from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest

from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.planning.config import (
    ConfidenceRules,
    FallbackRule,
    FallbackRules,
    ParameterInferenceRules,
    ResolverRules,
    SimilarityRules,
    UncertaintyRules,
)
from backend.app.planning.location import resolve_location_input


def _rules() -> ParameterInferenceRules:
    return ParameterInferenceRules(
        resolver_version="task5-v1",
        resolver=ResolverRules(
            address_fuzzy_match_min_score=Decimal("0.75"),
            nearest_reference_distance_km=Decimal("20"),
            climate_zone_radius_km=Decimal("80"),
        ),
        similarity=SimilarityRules(
            max_distance_km=Decimal("300"),
            max_altitude_difference_m=Decimal("800"),
            township_bonus=Decimal("0.30"),
            county_bonus=Decimal("0.20"),
            climate_zone_bonus=Decimal("0.25"),
            same_farm_bonus=Decimal("1.00"),
            distance_weight=Decimal("0.25"),
            altitude_weight=Decimal("0.20"),
            recency_weight=Decimal("0.10"),
            ambiguity_margin=Decimal("0.05"),
        ),
        fallback=FallbackRules(
            same_farm_variety=FallbackRule(2, 2, Decimal("0.20")),
            same_township_altitude_variety=FallbackRule(3, 2, Decimal("0.25")),
            same_county_climate_zone_variety=FallbackRule(4, 2, Decimal("0.30")),
            same_province_variety=FallbackRule(1, 1, Decimal("0.35")),
            literature_variety_prior=FallbackRule(1, 0, None),
        ),
        uncertainty=UncertaintyRules(
            widen_low_confidence_factor=Decimal("1.50"),
            widen_below_minimum_factor=Decimal("1.25"),
        ),
        confidence=ConfidenceRules(
            high_min_score=Decimal("0.80"),
            medium_min_score=Decimal("0.50"),
            same_farm_high_min_seasons=2,
            high_max_historical_mape=Decimal("0.20"),
            medium_max_historical_mape=Decimal("0.30"),
            missing_error_penalty=Decimal("0.15"),
            fallback_below_minimum_penalty=Decimal("0.20"),
            unresolved_location_penalty=Decimal("0.20"),
        ),
    )


def _zone(
    *,
    zone_id: int = 10,
    code: str = "zone-a",
    province: str = "云南省",
    prefecture: str | None = "红河州",
    county: str | None = "弥勒市",
    latitude: str = "24.400000",
    longitude: str = "103.400000",
    min_altitude_m: str | None = "1700",
    max_altitude_m: str | None = "1900",
    zone_version: str = "zone-v1",
) -> AgroClimateZone:
    return AgroClimateZone(
        id=zone_id,
        code=code,
        name="Zone A",
        country="China",
        province=province,
        prefecture=prefecture,
        county=county,
        centroid_latitude=Decimal(latitude),
        centroid_longitude=Decimal(longitude),
        min_altitude_m=Decimal(min_altitude_m) if min_altitude_m is not None else None,
        max_altitude_m=Decimal(max_altitude_m) if max_altitude_m is not None else None,
        zone_version=zone_version,
        valid_from=date(2024, 1, 1),
        valid_to=None,
        source_name="synthetic",
        source_version="src-v1",
    )


def _reference(
    *,
    climate_zone_id: int | None = 10,
    altitude_m: str | None = "1800",
) -> LocationReference:
    return LocationReference(
        id=1,
        farm_id=None,
        subfarm_id=None,
        farm_code="farm-a",
        farm_name="农场A",
        subfarm_name=None,
        address_raw="云南省 红河州 弥勒市 西三镇",
        address_normalized="云南省 红河州 弥勒市 西三镇",
        province="云南省",
        prefecture="红河州",
        county="弥勒市",
        township="西三镇",
        village=None,
        latitude=Decimal("24.400000"),
        longitude=Decimal("103.400000"),
        altitude_m=Decimal(altitude_m) if altitude_m is not None else None,
        climate_zone_id=climate_zone_id,
        location_source="synthetic",
        source_version="loc-v1",
        valid_from=date(2024, 1, 1),
        valid_to=None,
        source_row_hash="row-hash",
    )


@pytest.mark.asyncio
async def test_resolve_location_reference_reports_reference_zone_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone = _zone()
    reference = _reference()

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return [reference]

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return [zone]

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={"location_reference_id": 1},
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "resolved"
    assert result.climate_zone_mapping_method == "reference"
    assert result.climate_zone_distance_km is None
    assert result.climate_zone_altitude_difference_m == Decimal("0")
    assert result.climate_zone_score == Decimal("1")


@pytest.mark.asyncio
async def test_resolve_location_coordinate_county_mapping_reports_altitude_boundary_distance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone = _zone()

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return []

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return [zone]

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={
            "latitude": "24.400000",
            "longitude": "103.400000",
            "altitude_m": "2000",
            "province": "云南省",
            "county": "弥勒市",
        },
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "resolved"
    assert result.climate_zone_mapping_method == "county"
    assert result.climate_zone_distance_km is None
    assert result.climate_zone_altitude_difference_m == Decimal("100")
    assert result.climate_zone_score == Decimal("1")


@pytest.mark.asyncio
async def test_resolve_location_coordinate_prefecture_mapping_reports_missing_altitude_difference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone = _zone(county=None)

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return []

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return [zone]

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={
            "latitude": "24.400000",
            "longitude": "103.400000",
            "prefecture": "红河州",
            "province": "云南省",
        },
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "resolved"
    assert result.climate_zone_mapping_method == "prefecture"
    assert result.climate_zone_distance_km is None
    assert result.climate_zone_altitude_difference_m is None
    assert result.climate_zone_score == Decimal("0.8")


@pytest.mark.asyncio
async def test_resolve_location_coordinate_nearest_mapping_reports_distance_and_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone = _zone(county=None, prefecture=None, latitude="24.450000", longitude="103.450000")

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return []

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return [zone]

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={
            "latitude": "24.400000",
            "longitude": "103.400000",
            "altitude_m": "1800",
        },
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "resolved"
    assert result.climate_zone_mapping_method == "nearest_zone"
    assert result.climate_zone_distance_km is not None
    assert result.climate_zone_altitude_difference_m == Decimal("0")
    assert result.climate_zone_score == result.climate_zone_confidence


@pytest.mark.asyncio
async def test_resolve_location_coordinate_conflict_clears_zone_audit_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zones = [_zone(zone_id=10), _zone(zone_id=11, code="zone-b")]

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return []

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return zones

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={
            "latitude": "24.400000",
            "longitude": "103.400000",
            "province": "云南省",
            "county": "弥勒市",
        },
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "unresolved"
    assert result.climate_zone_mapping_method is None
    assert result.climate_zone_distance_km is None
    assert result.climate_zone_altitude_difference_m is None
    assert result.climate_zone_score is None


@pytest.mark.asyncio
async def test_resolve_location_coordinate_without_any_zone_candidates_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return []

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return []

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={
            "latitude": "24.400000",
            "longitude": "103.400000",
            "altitude_m": "1800",
        },
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "unresolved"
    assert "climate_zone_unresolved" in result.warnings
    assert result.climate_zone_mapping_method is None
    assert result.climate_zone_distance_km is None
    assert result.climate_zone_altitude_difference_m is None
    assert result.climate_zone_score is None


@pytest.mark.asyncio
async def test_resolve_location_reference_without_bound_climate_zone_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference(climate_zone_id=None)

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return [reference]

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return []

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={"location_reference_id": 1},
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "unresolved"
    assert "climate_zone_unresolved" in result.warnings
    assert result.climate_zone_mapping_method is None


@pytest.mark.asyncio
async def test_resolve_location_reference_with_invalid_zone_as_of_date_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference(climate_zone_id=10)

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return [reference]

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return []

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={"location_reference_id": 1},
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "unresolved"
    assert "climate_zone_not_valid_as_of_date" in result.warnings
    assert result.climate_zone_mapping_method is None


@pytest.mark.asyncio
async def test_resolve_location_reference_with_conflicting_zone_versions_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference(climate_zone_id=10)
    zones = [
        _zone(zone_id=10, code="ZONE-A"),
        _zone(zone_id=11, code="ZONE-A", zone_version="zone-v2"),
    ]

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return [reference]

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return zones

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={"location_reference_id": 1},
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "unresolved"
    assert "climate_zone_conflict" in result.warnings
    assert result.climate_zone_mapping_method is None


@pytest.mark.asyncio
async def test_resolve_ambiguous_address_keeps_ambiguous_status_when_reference_zone_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    references = [
        _reference(climate_zone_id=None),
        LocationReference(
            id=2,
            farm_id=None,
            subfarm_id=None,
            farm_code="farm-b",
            farm_name="农场B",
            subfarm_name=None,
            address_raw="云南省 红河州 弥勒市 西三镇",
            address_normalized="云南省 红河州 弥勒市 西三镇",
            province="云南省",
            prefecture="红河州",
            county="弥勒市",
            township="西三镇",
            village=None,
            latitude=Decimal("24.401000"),
            longitude=Decimal("103.401000"),
            altitude_m=Decimal("1800"),
            climate_zone_id=None,
            location_source="synthetic",
            source_version="loc-v1",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            source_row_hash="row-hash-b",
        ),
    ]

    async def fake_references(session: object, *, as_of_date: date) -> list[LocationReference]:
        return references

    async def fake_zones(session: object, *, as_of_date: date) -> list[AgroClimateZone]:
        return []

    monkeypatch.setattr(
        "backend.app.planning.location._valid_location_references",
        fake_references,
    )
    monkeypatch.setattr(
        "backend.app.planning.location._valid_climate_zones",
        fake_zones,
    )

    result = await resolve_location_input(
        cast(Any, object()),
        location={"address": "云南省 红河州 弥勒市 西三镇"},
        as_of_date=date(2026, 1, 1),
        rules=_rules(),
    )

    assert result.status == "ambiguous"
    assert "address_ambiguous" in result.warnings
    assert "climate_zone_unresolved" in result.warnings
    assert result.climate_zone_mapping_method is None
