from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.app.planning.hashing import input_hash, source_signature


def test_input_hash_is_stable_for_same_normalized_payload() -> None:
    payload = {
        "location": {"address_normalized": "云南省 红河州 弥勒市 西三镇"},
        "varieties": [
            {"variety_id": 2, "planted_area_mu": Decimal("300")},
            {"variety_id": 1, "planted_area_mu": Decimal("700")},
        ],
    }

    first = input_hash(payload, as_of_date=date(2026, 1, 1))
    second = input_hash(payload, as_of_date=date(2026, 1, 1))

    assert first == second
    assert len(first) == 64


def test_source_signature_is_stable_for_sorted_pure_values() -> None:
    first = source_signature(
        input_hash_value="a" * 64,
        resolver_version="task5-v1",
        library_version="lib-v1",
        config_hash="cfg-v1",
        eligible_observation_ids=[3, 1, 2],
        selected_location_version="loc-v1",
    )
    second = source_signature(
        input_hash_value="a" * 64,
        resolver_version="task5-v1",
        library_version="lib-v1",
        config_hash="cfg-v1",
        eligible_observation_ids=[1, 2, 3],
        selected_location_version="loc-v1",
    )

    assert first == second

