from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.planning.normalization import (
    normalize_address_text,
    normalize_location_name,
    normalize_variety_lookup,
    validate_coordinate_pair,
)


def test_normalize_address_text_uses_nfkc_and_collapses_spaces() -> None:
    value = " 云南省　红河州  弥勒市 / 西三镇 "

    normalized = normalize_address_text(value)

    assert normalized == "云南省 红河州 弥勒市 西三镇"


def test_normalize_location_name_preserves_empty_as_none() -> None:
    assert normalize_location_name("   ") is None


def test_normalize_variety_lookup_removes_prefixes() -> None:
    assert normalize_variety_lookup(" 蓝莓原果Dx ") == "dx"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (Decimal("24.123456"), Decimal("102.123456")),
        (-90, -180),
        (90, 180),
    ],
)
def test_validate_coordinate_pair_accepts_valid_ranges(
    latitude: Decimal | int,
    longitude: Decimal | int,
) -> None:
    validate_coordinate_pair(latitude, longitude)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91, 100),
        (-91, 100),
        (24, 181),
        (24, -181),
    ],
)
def test_validate_coordinate_pair_rejects_out_of_range(latitude: int, longitude: int) -> None:
    with pytest.raises(ValueError):
        validate_coordinate_pair(latitude, longitude)

