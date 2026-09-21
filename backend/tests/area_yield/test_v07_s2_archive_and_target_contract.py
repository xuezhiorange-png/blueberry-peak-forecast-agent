from __future__ import annotations

import json
import socket
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.app.area_yield.weather_features import (
    DUPLICATE_TARGET_LABEL_WEIGHTING_ALLOWED,
    HORIZON_TARGET_TYPES,
    TARGET_GRANULARITY,
    TARGET_LABEL,
    TARGET_ROW_IDENTITY,
    target_dates_for_horizon,
    target_lead_day,
    target_row_key,
)
from scripts.run_v07_s2_weather_feature_freeze import audit_ecmwf_archive

TZ = ZoneInfo("Asia/Shanghai")


def _manifest(
    *,
    issued_at: str,
    provider: str = "ECMWF_IFS_OPEN_DATA",
    known_at: str | None = "AUTO",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": provider,
        "model": "IFS",
        "run_id": issued_at.replace("-", "").replace(":", "")[:10],
        "issued_at": issued_at,
        "base_count": 38,
        "selected_grid_coordinates": {"base-a": {"latitude": "24.0", "longitude": "103.0"}},
        "field_artifacts": [
            {"parameter": "2t", "step": 24, "sha256": "a" * 64},
            {"parameter": "tp", "step": 168, "sha256": "b" * 64},
        ],
        "index_artifacts": [{"step": 24, "sha256": "c" * 64}],
    }
    if known_at == "AUTO":
        issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
        known_at = (issued + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    if known_at is not None:
        payload["known_at"] = known_at
    return payload


def _write_manifest(root: Path, payload: dict[str, object]) -> None:
    path = root / "run" / "artifact-manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.unit
def test_current_prospective_manifest_is_not_historical() -> None:
    result = audit_ecmwf_archive(
        _temporary_manifest_root(_manifest(issued_at="2026-09-19T00:00:00Z"))
    )
    item = result["saved_ecmwf_manifests"][0]
    assert item["historical_period"] is None
    assert result["requested_seasons"]["2024-2025"]["status"] == "NOT_FOUND"
    assert result["requested_seasons"]["2025-2026"]["status"] == "NOT_FOUND"


@pytest.mark.unit
def test_issued_manifest_is_assigned_to_2024_2025(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _manifest(issued_at="2024-08-01T00:00:00Z"))
    result = audit_ecmwf_archive(tmp_path)
    season = result["requested_seasons"]["2024-2025"]
    assert season["status"] == "FOUND_AS_ISSUED_ELIGIBLE"
    assert season["manifest_details"][0]["archive_provenance_eligible"] is True
    assert season["available_origin_dates"] == ["2024-08-01"]
    assert season["available_horizons"] == ["D1", "D7"]


@pytest.mark.unit
def test_issued_manifest_is_assigned_to_2025_2026(tmp_path: Path) -> None:
    _write_manifest(tmp_path, _manifest(issued_at="2025-07-22T00:00:00Z"))
    result = audit_ecmwf_archive(tmp_path)
    season = result["requested_seasons"]["2025-2026"]
    assert season["status"] == "FOUND_AS_ISSUED_ELIGIBLE"
    assert season["available_origin_dates"] == ["2025-07-22"]


@pytest.mark.unit
def test_provider_mismatch_is_rejected(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        _manifest(issued_at="2024-08-01T00:00:00Z", provider="OTHER_PROVIDER"),
    )
    result = audit_ecmwf_archive(tmp_path)
    assert result["requested_seasons"]["2024-2025"]["status"] == "NOT_FOUND"
    assert result["rejected_manifests"][0]["qualification_reasons"] == ["PROVIDER_MISMATCH"]


@pytest.mark.unit
def test_missing_known_at_is_found_but_not_as_issued_eligible(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        _manifest(issued_at="2024-08-01T00:00:00Z", known_at=None),
    )
    result = audit_ecmwf_archive(tmp_path)
    manifest = result["requested_seasons"]["2024-2025"]["manifest_details"][0]
    assert result["requested_seasons"]["2024-2025"]["status"] == (
        "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE"
    )
    assert manifest["qualification_reasons"] == ["KNOWN_AT_MISSING"]
    assert manifest["archive_provenance_eligible"] is False


@pytest.mark.unit
def test_fetched_at_does_not_substitute_for_known_at(tmp_path: Path) -> None:
    payload = _manifest(issued_at="2024-08-01T00:00:00Z", known_at=None)
    payload["fetched_at"] = "2024-08-01T00:05:00Z"
    _write_manifest(tmp_path, payload)
    result = audit_ecmwf_archive(tmp_path)
    manifest = result["requested_seasons"]["2024-2025"]["manifest_details"][0]
    assert manifest["qualification_reasons"] == ["KNOWN_AT_MISSING"]
    assert manifest["archive_provenance_eligible"] is False


@pytest.mark.unit
def test_known_at_naive_is_not_as_issued_eligible(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        _manifest(issued_at="2024-08-01T00:00:00Z", known_at="2024-08-01T00:05:00"),
    )
    result = audit_ecmwf_archive(tmp_path)
    manifest = result["requested_seasons"]["2024-2025"]["manifest_details"][0]
    assert manifest["qualification_status"] == "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE"
    assert "known_at_MISSING_TIMEZONE" in manifest["qualification_reasons"]


@pytest.mark.unit
def test_known_at_before_issued_is_not_as_issued_eligible(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        _manifest(issued_at="2024-08-01T00:05:00Z", known_at="2024-08-01T00:00:00Z"),
    )
    result = audit_ecmwf_archive(tmp_path)
    manifest = result["requested_seasons"]["2024-2025"]["manifest_details"][0]
    assert manifest["qualification_status"] == "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE"
    assert manifest["qualification_reasons"] == ["ISSUED_AFTER_KNOWN"]


@pytest.mark.unit
def test_missing_issued_at_is_not_as_issued_eligible(tmp_path: Path) -> None:
    payload = _manifest(issued_at="2024-08-01T00:00:00Z")
    payload.pop("issued_at")
    _write_manifest(tmp_path, payload)
    result = audit_ecmwf_archive(tmp_path)
    manifest = result["saved_ecmwf_manifests"][0]
    assert manifest["qualification_status"] == "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE"
    assert "ISSUED_AT_MISSING" in manifest["qualification_reasons"]


@pytest.mark.unit
def test_complete_ordered_known_at_is_archive_provenance_eligible(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        _manifest(issued_at="2024-08-01T00:00:00Z", known_at="2024-08-01T00:05:00Z"),
    )
    result = audit_ecmwf_archive(tmp_path)
    manifest = result["requested_seasons"]["2024-2025"]["manifest_details"][0]
    assert manifest["qualification_status"] == "FOUND_AS_ISSUED_ELIGIBLE"
    assert manifest["archive_provenance_eligible"] is True


@pytest.mark.unit
def test_missing_raw_provenance_is_found_but_not_eligible(tmp_path: Path) -> None:
    payload = _manifest(issued_at="2024-08-01T00:00:00Z")
    payload["field_artifacts"] = [{"parameter": "2t", "step": 24}]
    _write_manifest(tmp_path, payload)
    result = audit_ecmwf_archive(tmp_path)
    season = result["requested_seasons"]["2024-2025"]
    assert season["status"] == "FOUND_BUT_NOT_AS_ISSUED_ELIGIBLE"
    assert season["candidate_manifest_count"] == 1
    assert season["eligible_manifest_count"] == 0


@pytest.mark.unit
def test_empty_archive_is_not_found(tmp_path: Path) -> None:
    result = audit_ecmwf_archive(tmp_path)
    assert result["audit_status"] == "PASS"
    assert result["discovered_manifest_count"] == 0
    assert result["requested_seasons"]["2024-2025"]["status"] == "NOT_FOUND"
    assert result["requested_seasons"]["2025-2026"]["status"] == "NOT_FOUND"


@pytest.mark.unit
def test_archive_audit_is_filesystem_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("archive audit must not use network")

    monkeypatch.setattr(socket, "socket", fail_network)
    result = audit_ecmwf_archive(tmp_path)
    assert result["network_accessed"] is False


@pytest.mark.unit
def test_daily_target_contract_is_one_row_identity_with_horizon_views() -> None:
    origin = datetime(2025, 7, 22, tzinfo=TZ)
    assert TARGET_GRANULARITY == "DAILY"
    assert TARGET_LABEL == "ACTUAL_DAILY_HARVEST_KG"
    assert TARGET_ROW_IDENTITY == "base_id+forecast_origin+target_date"
    assert DUPLICATE_TARGET_LABEL_WEIGHTING_ALLOWED is False
    assert HORIZON_TARGET_TYPES == {
        "H1": "DAILY_VECTOR_LENGTH_1",
        "H7": "DAILY_VECTOR_LENGTH_7",
        "H15": "DAILY_VECTOR_LENGTH_15",
    }
    assert target_dates_for_horizon(forecast_origin=origin, horizon="H1") == (date(2025, 7, 22),)
    assert target_dates_for_horizon(forecast_origin=origin, horizon="H7")[0:2] == (
        date(2025, 7, 22),
        date(2025, 7, 23),
    )
    h15 = target_dates_for_horizon(forecast_origin=origin, horizon="H15")
    assert len(h15) == 15
    assert h15[-1] == date(2025, 8, 5)
    assert target_lead_day(forecast_origin=origin, target_date=h15[-1]) == 14
    assert (
        target_row_key(base_id="base-a", forecast_origin=origin, target_date=h15[-1])
        == "base-a+2025-07-22T00:00:00+08:00+2025-08-05"
    )


def _temporary_manifest_root(payload: dict[str, object]) -> Path:
    """Create a temporary directory for a one-file audit test."""

    import tempfile

    root = Path(tempfile.mkdtemp(prefix="v07-s2-ecmwf-audit-"))
    _write_manifest(root, payload)
    return root
