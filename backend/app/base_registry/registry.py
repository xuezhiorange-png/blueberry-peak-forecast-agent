"""Source-preserving BASE_REGISTRY_V1 import; no inferred farm areas or identities."""

import re
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from backend.app.area_yield.data import digest, fixed


def parse_coordinate(raw: str) -> tuple[str | None, str | None, str]:
    try:
        parts = raw.split(",")
        if len(parts) != 2:
            raise ValueError("longitude,latitude required")
        lon, lat = (Decimal(v.strip()) for v in parts)
        if not lon.is_finite() or not lat.is_finite():
            raise ValueError("finite coordinates required")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90) or (lon == lat == 0):
            raise ValueError("coordinate range")
        return str(lon), str(lat), "RANGE_VALID_CRS_UNCONFIRMED"
    except (ValueError, InvalidOperation):
        return None, None, "REQUIRES_REVIEW"


def area_value(raw: Any) -> str | None:
    """Workbook has numeric literals and three literal-addition formulas only.

    No eval, arbitrary Excel formula engine, reverse yield inference or defaults.
    """
    text = str(raw).strip()
    try:
        with localcontext() as ctx:
            ctx.prec = 50
            if text.startswith("="):
                if not re.fullmatch(r"=\d+(?:\.\d+)?(?:\+\d+(?:\.\d+)?)+", text):
                    return None
                value = sum((Decimal(x) for x in text[1:].split("+")), Decimal(0))
            else:
                value = Decimal(text)
            return fixed(value) if value.is_finite() and value > 0 else None
    except InvalidOperation:
        return None


def build_registry(rows: list[list[Any]], source_hash: str) -> dict[str, Any]:
    if not re.fullmatch("[0-9a-f]{64}", source_hash):
        raise ValueError("source hash required")
    bases, names, ids = [], set(), set()
    for row in rows:
        if len(row) != 4 or not isinstance(row[0], str) or not row[0].strip():
            raise ValueError("base row schema")
        name, members, raw_coordinate, raw_area = row
        if not isinstance(members, str) or not isinstance(raw_coordinate, str):
            raise ValueError("member and coordinate text required")
        base_id = "base_" + digest(name)[:24]
        if name in names or base_id in ids:
            raise ValueError("duplicate base name/id")
        names.add(name)
        ids.add(base_id)
        # Preserve each source token exactly, including any whitespace.
        farms = members.split("、")
        if any(not f.strip() for f in farms) or len(set(farms)) != len(farms):
            raise ValueError("empty or duplicate member within base")
        lon, lat, coordinate_status = parse_coordinate(raw_coordinate)
        area = area_value(raw_area)
        bases.append(
            {
                "base_id": base_id,
                "canonical_base_name": name,
                "covered_farms": farms,
                "raw_covered_farms": members,
                "raw_coordinate": raw_coordinate,
                "longitude": lon,
                "latitude": lat,
                "coordinate_source": source_hash,
                "coordinate_review_status": coordinate_status,
                "coordinate_reference_system": "NOT_ESTABLISHED",
                "elevation_m": None,
                "elevation_source": None,
                "elevation_review_status": "NOT_ESTABLISHED",
                "productive_area_mu": area,
                "raw_area": str(raw_area),
                "area_source": source_hash,
                "area_review_status": "USER_AUTHORIZED_PRODUCTIVE_AREA"
                if area
                else "REQUIRES_REVIEW",
                "province": None,
                "prefecture": None,
                "county": None,
                "township": None,
                "region_scope": "LOCATION_REVIEW_REQUIRED",
                "climate_zone_id": None,
                "climate_zone_version": None,
                "historical_seasons": [],
                "historical_season_count": 0,
                "data_completeness_level": "NOT_EVALUATED",
                "applicability_level": "NOT_ESTABLISHED",
                "active": True,
                "effective_from": None,
                "effective_to": None,
                "provenance": {
                    "workbook_hash": source_hash,
                    "authority": "USER_S1_WORKBOOK_CONFIRMATION",
                },
                "review_status": "PENDING_COORDINATOR_REVIEW",
            }
        )
        # Only the user-confirmed outside-Yunnan case can be classified without
        # a separately sourced polygon. A bounding rectangle is not a province.
        if name == "乡丰蓝莓基地" and lon == "113.81" and lat == "23.34":
            bases[-1]["region_scope"] = "OUT_OF_YUNNAN"
    coordinates = Counter((b["longitude"], b["latitude"]) for b in bases if b["longitude"])
    for b in bases:
        b["duplicate_coordinate"] = coordinates[b["longitude"], b["latitude"]] > 1
        if b["duplicate_coordinate"]:
            b["coordinate_review_status"] = "REQUIRES_REVIEW"
    payload = {
        "version": "BASE_REGISTRY_V1",
        "source_hash": source_hash,
        "bases": sorted(bases, key=lambda b: b["base_id"]),
    }
    return {**payload, "hash": digest(payload)}
