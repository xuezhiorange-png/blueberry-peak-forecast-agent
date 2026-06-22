from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

_PUNCTUATION_PATTERN = re.compile(r"[，,、/／;；:：\-]+")
_SPACE_PATTERN = re.compile(r"\s+")
_VARIETY_PREFIXES = ("蓝莓原果",)


def _nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def normalize_location_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _SPACE_PATTERN.sub(" ", _nfkc(value)).strip()
    return normalized or None


def normalize_address_text(value: str) -> str:
    normalized = _nfkc(value)
    normalized = _PUNCTUATION_PATTERN.sub(" ", normalized)
    normalized = _SPACE_PATTERN.sub(" ", normalized).strip()
    return normalized


def normalize_variety_lookup(value: str) -> str:
    normalized = normalize_address_text(value)
    for prefix in _VARIETY_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    return normalized.lower()


def coerce_optional_decimal(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def validate_coordinate_pair(
    latitude: Decimal | int | float,
    longitude: Decimal | int | float,
) -> None:
    latitude_value = Decimal(str(latitude))
    longitude_value = Decimal(str(longitude))
    if latitude_value < Decimal("-90") or latitude_value > Decimal("90"):
        raise ValueError("latitude must be between -90 and 90")
    if longitude_value < Decimal("-180") or longitude_value > Decimal("180"):
        raise ValueError("longitude must be between -180 and 180")
