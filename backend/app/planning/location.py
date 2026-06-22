from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.planning import AgroClimateZone, LocationReference
from backend.app.planning.config import ParameterInferenceRules
from backend.app.planning.normalization import (
    normalize_address_text,
    normalize_location_name,
    validate_coordinate_pair,
)
from backend.app.planning.schemas import ResolvedLocation
from backend.app.planning.similarity import haversine_distance_km

type ResolvedStatus = Literal["resolved", "ambiguous", "unresolved"]
type ClimateZoneResolution = tuple[
    int | None,
    str | None,
    str | None,
    str | None,
    Decimal | None,
    str | None,
]


def _text_or_none(location: dict[str, object], key: str) -> str | None:
    value = location.get(key)
    if not isinstance(value, str):
        return None
    return normalize_location_name(value)


def _location_candidate_text(reference: LocationReference) -> str:
    parts = (
        reference.address_normalized,
        reference.province,
        reference.prefecture,
        reference.county,
        reference.township,
        reference.village,
        reference.farm_name,
        reference.subfarm_name,
    )
    return normalize_address_text(" ".join(part for part in parts if part))


async def _valid_location_references(
    session: AsyncSession,
    *,
    as_of_date: date,
) -> list[LocationReference]:
    statement: Select[tuple[LocationReference]] = (
        select(LocationReference)
        .where(
            LocationReference.valid_from <= as_of_date,
            (LocationReference.valid_to.is_(None) | (LocationReference.valid_to >= as_of_date)),
        )
        .order_by(LocationReference.id.asc())
    )
    return list((await session.scalars(statement)).all())


async def _valid_climate_zones(
    session: AsyncSession,
    *,
    as_of_date: date,
) -> list[AgroClimateZone]:
    statement: Select[tuple[AgroClimateZone]] = (
        select(AgroClimateZone)
        .where(
            AgroClimateZone.valid_from <= as_of_date,
            (AgroClimateZone.valid_to.is_(None) | (AgroClimateZone.valid_to >= as_of_date)),
        )
        .order_by(
            AgroClimateZone.code.asc(),
            AgroClimateZone.zone_version.asc(),
            AgroClimateZone.id.asc(),
        )
    )
    return list((await session.scalars(statement)).all())


def _zone_version_conflict(zones: list[AgroClimateZone]) -> bool:
    seen: set[str] = set()
    for zone in zones:
        if zone.code in seen:
            return True
        seen.add(zone.code)
    return False


def _resolved_from_reference(
    reference: LocationReference,
    *,
    zone: AgroClimateZone | None,
    status: ResolvedStatus = "resolved",
    candidate_count: int = 1,
    confidence_score: Decimal = Decimal("1"),
    warnings: tuple[str, ...] = (),
    candidates: tuple[dict[str, object], ...] = (),
) -> ResolvedLocation:
    return ResolvedLocation(
        status=status,
        location_reference_id=reference.id,
        address_raw=reference.address_raw,
        address_normalized=reference.address_normalized,
        province=reference.province,
        prefecture=reference.prefecture,
        county=reference.county,
        township=reference.township,
        village=reference.village,
        farm_name=reference.farm_name,
        latitude=reference.latitude,
        longitude=reference.longitude,
        altitude_m=reference.altitude_m,
        climate_zone_id=reference.climate_zone_id,
        climate_zone_code=zone.code if zone is not None else None,
        climate_zone_mapping_method=(
            "reference" if reference.climate_zone_id is not None else None
        ),
        climate_zone_confidence=(
            Decimal("1") if reference.climate_zone_id is not None else None
        ),
        candidate_count=candidate_count,
        confidence_score=confidence_score,
        warnings=warnings,
        candidates=candidates,
        reproducibility_snapshot={
            "location_reference_id": reference.id,
            "source_version": reference.source_version,
            "source_row_hash": reference.source_row_hash,
            "climate_zone_version": zone.zone_version if zone is not None else None,
        },
        climate_zone_version=zone.zone_version if zone is not None else None,
    )


async def _zone_for_reference(
    session: AsyncSession,
    *,
    climate_zone_id: int | None,
    as_of_date: date,
) -> AgroClimateZone | None:
    if climate_zone_id is None:
        return None
    zones = await _valid_climate_zones(session, as_of_date=as_of_date)
    return next((zone for zone in zones if zone.id == climate_zone_id), None)


async def _map_climate_zone(
    session: AsyncSession,
    *,
    province: str | None,
    prefecture: str | None,
    county: str | None,
    latitude: Decimal,
    longitude: Decimal,
    altitude_m: Decimal | None,
    as_of_date: date,
    rules: ParameterInferenceRules,
) -> ClimateZoneResolution:
    zones = await _valid_climate_zones(session, as_of_date=as_of_date)

    county_matches = [
        zone for zone in zones if county is not None and zone.county == county
    ]
    if county_matches:
        if len(county_matches) == 1:
            zone = county_matches[0]
            return zone.id, zone.code, zone.zone_version, "county", Decimal("1"), None
        return None, None, None, None, None, "climate_zone_conflict"

    prefecture_matches = [
        zone
        for zone in zones
        if prefecture is not None
        and zone.prefecture == prefecture
        and zone.province == province
    ]
    if prefecture_matches:
        if len(prefecture_matches) == 1:
            zone = prefecture_matches[0]
            return (
                zone.id,
                zone.code,
                zone.zone_version,
                "prefecture",
                Decimal("0.8"),
                None,
            )
        return None, None, None, None, None, "climate_zone_conflict"

    nearest_candidates: list[tuple[AgroClimateZone, Decimal]] = []
    for zone in zones:
        distance = haversine_distance_km(
            float(latitude),
            float(longitude),
            float(zone.centroid_latitude),
            float(zone.centroid_longitude),
        )
        if distance > rules.resolver.climate_zone_radius_km:
            continue
        if altitude_m is not None:
            if zone.min_altitude_m is not None and altitude_m < zone.min_altitude_m:
                continue
            if zone.max_altitude_m is not None and altitude_m > zone.max_altitude_m:
                continue
        nearest_candidates.append((zone, distance))

    if not nearest_candidates:
        return None, None, None, None, None, None

    candidate_zones = [zone for zone, _ in nearest_candidates]
    if _zone_version_conflict(candidate_zones):
        return None, None, None, None, None, "climate_zone_conflict"

    zone, distance = min(nearest_candidates, key=lambda item: (item[1], item[0].id))
    confidence = max(Decimal("0"), Decimal("1") - distance / Decimal("100"))
    return (
        zone.id,
        zone.code,
        zone.zone_version,
        "nearest_zone",
        confidence,
        None,
    )


def _unresolved_location(
    *,
    address_raw: str | None,
    address_normalized: str | None,
    warning: str,
) -> ResolvedLocation:
    return ResolvedLocation(
        status="unresolved",
        location_reference_id=None,
        address_raw=address_raw,
        address_normalized=address_normalized,
        province=None,
        prefecture=None,
        county=None,
        township=None,
        village=None,
        farm_name=None,
        latitude=None,
        longitude=None,
        altitude_m=None,
        climate_zone_id=None,
        climate_zone_code=None,
        climate_zone_mapping_method=None,
        climate_zone_confidence=None,
        candidate_count=0,
        confidence_score=Decimal("0"),
        warnings=(warning,),
        candidates=(),
        reproducibility_snapshot={},
        climate_zone_version=None,
    )


async def resolve_location_input(
    session: AsyncSession,
    *,
    location: dict[str, object],
    as_of_date: date,
    rules: ParameterInferenceRules,
) -> ResolvedLocation:
    location_reference_id = location.get("location_reference_id")
    address = location.get("address")
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    altitude = location.get("altitude_m")

    if location_reference_id is not None:
        if not isinstance(location_reference_id, (int, str)):
            return _unresolved_location(
                address_raw=None,
                address_normalized=None,
                warning="location_reference_invalid",
            )
        references = await _valid_location_references(session, as_of_date=as_of_date)
        reference = next(
            (item for item in references if item.id == int(location_reference_id)),
            None,
        )
        if reference is None:
            return _unresolved_location(
                address_raw=None,
                address_normalized=None,
                warning="location_reference_not_valid_as_of_date",
            )
        zone = await _zone_for_reference(
            session,
            climate_zone_id=reference.climate_zone_id,
            as_of_date=as_of_date,
        )
        return _resolved_from_reference(reference, zone=zone)

    if latitude is not None and longitude is not None:
        latitude_value = Decimal(str(latitude))
        longitude_value = Decimal(str(longitude))
        validate_coordinate_pair(latitude_value, longitude_value)

        references = await _valid_location_references(session, as_of_date=as_of_date)
        nearest: tuple[LocationReference, Decimal] | None = None
        for reference in references:
            distance = haversine_distance_km(
                float(latitude_value),
                float(longitude_value),
                float(reference.latitude),
                float(reference.longitude),
            )
            if nearest is None or distance < nearest[1]:
                nearest = (reference, distance)

        altitude_value = Decimal(str(altitude)) if altitude is not None else None
        chosen_altitude = altitude_value
        warnings: list[str] = []
        if (
            chosen_altitude is None
            and nearest is not None
            and nearest[1] <= rules.resolver.nearest_reference_distance_km
        ):
            chosen_altitude = nearest[0].altitude_m
        elif chosen_altitude is None:
            warnings.append("altitude_unresolved")

        province = _text_or_none(location, "province")
        prefecture = _text_or_none(location, "prefecture")
        county = _text_or_none(location, "county")
        township = _text_or_none(location, "township")
        village = _text_or_none(location, "village")
        farm_name = _text_or_none(location, "farm_name")

        nearest_reference = nearest[0] if nearest is not None else None
        (
            zone_id,
            zone_code,
            zone_version,
            mapping_method,
            zone_confidence,
            zone_warning,
        ) = await _map_climate_zone(
            session,
            province=province or (nearest_reference.province if nearest_reference else None),
            prefecture=(
                prefecture or (nearest_reference.prefecture if nearest_reference else None)
            ),
            county=county or (nearest_reference.county if nearest_reference else None),
            latitude=latitude_value,
            longitude=longitude_value,
            altitude_m=chosen_altitude,
            as_of_date=as_of_date,
            rules=rules,
        )
        if zone_warning is not None:
            warnings.append(zone_warning)
        location_reference_value = None
        if (
            nearest is not None
            and nearest[1] <= rules.resolver.nearest_reference_distance_km
        ):
            location_reference_value = nearest[0].id
        status: ResolvedStatus = "resolved" if zone_warning is None else "unresolved"
        return ResolvedLocation(
            status=status,
            location_reference_id=location_reference_value,
            address_raw=address if isinstance(address, str) else None,
            address_normalized=(
                normalize_address_text(address) if isinstance(address, str) else None
            ),
            province=province or (nearest_reference.province if nearest_reference else None),
            prefecture=(
                prefecture or (nearest_reference.prefecture if nearest_reference else None)
            ),
            county=county or (nearest_reference.county if nearest_reference else None),
            township=township or (nearest_reference.township if nearest_reference else None),
            village=village or (nearest_reference.village if nearest_reference else None),
            farm_name=farm_name or (nearest_reference.farm_name if nearest_reference else None),
            latitude=latitude_value,
            longitude=longitude_value,
            altitude_m=chosen_altitude,
            climate_zone_id=zone_id,
            climate_zone_code=zone_code,
            climate_zone_mapping_method=mapping_method,
            climate_zone_confidence=zone_confidence,
            candidate_count=1,
            confidence_score=(
                Decimal("1") if nearest_reference is not None else Decimal("0.8")
            ),
            warnings=tuple(warnings),
            candidates=(),
            reproducibility_snapshot={
                "nearest_location_reference_id": (
                    nearest_reference.id if nearest_reference is not None else None
                ),
                "nearest_reference_distance_km": (
                    str(nearest[1]) if nearest is not None else None
                ),
                "climate_zone_version": zone_version,
            },
            climate_zone_version=zone_version,
        )

    if isinstance(address, str):
        normalized = normalize_address_text(address)
        references = await _valid_location_references(session, as_of_date=as_of_date)
        scored: list[tuple[Decimal, LocationReference]] = []
        for reference in references:
            candidate_text = _location_candidate_text(reference)
            if candidate_text == normalized:
                scored.append((Decimal("1"), reference))
                continue
            score = Decimal(
                str(SequenceMatcher(None, normalized, candidate_text).ratio())
            ).quantize(Decimal("0.000001"))
            if score >= rules.resolver.address_fuzzy_match_min_score:
                scored.append((score, reference))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        if not scored:
            return _unresolved_location(
                address_raw=address,
                address_normalized=normalized,
                warning="address_unresolved",
            )
        if len(scored) >= 2 and (
            scored[0][0] - scored[1][0] <= rules.similarity.ambiguity_margin
        ):
            candidates: tuple[dict[str, object], ...] = tuple(
                {
                    "location_reference_id": item.id,
                    "farm_name": item.farm_name,
                    "address_normalized": item.address_normalized,
                    "score": str(score),
                }
                for score, item in scored[:5]
            )
            zone = await _zone_for_reference(
                session,
                climate_zone_id=scored[0][1].climate_zone_id,
                as_of_date=as_of_date,
            )
            return _resolved_from_reference(
                scored[0][1],
                zone=zone,
                status="ambiguous",
                candidate_count=len(scored),
                confidence_score=scored[0][0],
                warnings=("address_ambiguous",),
                candidates=candidates,
            )
        zone = await _zone_for_reference(
            session,
            climate_zone_id=scored[0][1].climate_zone_id,
            as_of_date=as_of_date,
        )
        return _resolved_from_reference(
            scored[0][1],
            zone=zone,
            candidate_count=len(scored),
            confidence_score=scored[0][0],
        )

    return _unresolved_location(
        address_raw=None,
        address_normalized=None,
        warning="no_supported_location_input",
    )


def resolved_location_payload(location: ResolvedLocation) -> dict[str, object]:
    return asdict(location)
