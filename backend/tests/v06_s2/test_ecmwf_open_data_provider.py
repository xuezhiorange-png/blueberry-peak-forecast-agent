from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

import backend.app.pit.ecmwf_open_data_provider as ecmwf


@pytest.mark.unit
def test_ecmwf_grid_selection_is_deterministic_and_tie_breaks_down() -> None:
    assert ecmwf.select_nearest_grid_point(Decimal("25.124"), Decimal("99.124")) == (
        ecmwf.GridPoint(Decimal("25.00"), Decimal("99.00"))
    )
    assert ecmwf.select_nearest_grid_point(Decimal("25.125"), Decimal("99.125")) == (
        ecmwf.GridPoint(Decimal("25.00"), Decimal("99.00"))
    )
    assert ecmwf.select_nearest_grid_point(Decimal("25.126"), Decimal("99.126")) == (
        ecmwf.GridPoint(Decimal("25.25"), Decimal("99.25"))
    )


@pytest.mark.unit
def test_location_authority_loader_binds_file_hash_and_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": "BASE_REGISTRY_V1",
        "hash": "payload-hash",
        "bases": [
            {
                "base_id": "base_aaaaaaaaaaaaaaaaaaaaaaaa",
                "canonical_base_name": "Test Base",
                "latitude": "25.19",
                "longitude": "99.00",
                "coordinate_review_status": "RANGE_VALID_CRS_UNCONFIRMED",
                "coordinate_reference_system": "NOT_ESTABLISHED",
            }
        ],
    }
    path = tmp_path / "base-registry.json"
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    monkeypatch.setattr(ecmwf, "BASE_LOCATION_COUNT", 1)
    monkeypatch.setattr(ecmwf, "BASE_LOCATION_AUTHORITY_PAYLOAD_HASH", "payload-hash")
    locations = ecmwf.load_base_location_authority(
        path,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
    )
    assert locations["base_aaaaaaaaaaaaaaaaaaaaaaaa"].latitude == Decimal("25.19")


@pytest.mark.unit
def test_location_authority_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "base-registry.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(Exception, match="BASE_LOCATION_AUTHORITY_HASH_MISMATCH"):
        ecmwf.load_base_location_authority(path, expected_sha256="0" * 64)
