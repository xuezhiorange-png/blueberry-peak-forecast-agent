from __future__ import annotations

from decimal import Decimal

from backend.app.models.planning import LocationReference
from backend.app.planning.importers import normalized_location_reference_address
from backend.app.planning.location import _location_candidate_text


def test_normalized_location_reference_address_prefers_address_raw_without_duplication() -> None:
    row = {
        "address_raw": "云南省 红河州 弥勒市 西三镇",
        "province": "云南省",
        "prefecture": "红河州",
        "county": "弥勒市",
        "township": "西三镇",
        "village": "",
    }

    normalized = normalized_location_reference_address(row)

    assert normalized == "云南省 红河州 弥勒市 西三镇"


def test_normalized_location_reference_address_falls_back_to_administrative_parts() -> None:
    row = {
        "address_raw": "",
        "province": "云南省",
        "prefecture": "红河州",
        "county": "弥勒市",
        "township": "西三镇",
        "village": "",
    }

    normalized = normalized_location_reference_address(row)

    assert normalized == "云南省 红河州 弥勒市 西三镇"


def test_location_candidate_text_does_not_duplicate_full_address_hierarchy() -> None:
    reference = LocationReference(
        address_raw="云南省 红河州 弥勒市 西三镇",
        address_normalized="云南省 红河州 弥勒市 西三镇",
        province="云南省",
        prefecture="红河州",
        county="弥勒市",
        township="西三镇",
        village=None,
        farm_name="农场A",
        subfarm_name=None,
        latitude=Decimal("24.400000"),
        longitude=Decimal("103.400000"),
        altitude_m=Decimal("1800"),
        location_source="synthetic",
        source_version="loc-v1",
        valid_from="2024-01-01",
        source_row_hash="hash",
    )

    candidate = _location_candidate_text(reference)

    assert candidate == "云南省 红河州 弥勒市 西三镇 农场A"
