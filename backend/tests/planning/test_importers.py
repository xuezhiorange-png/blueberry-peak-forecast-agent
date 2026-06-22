from __future__ import annotations

from backend.app.planning.importers import normalized_location_reference_address


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
