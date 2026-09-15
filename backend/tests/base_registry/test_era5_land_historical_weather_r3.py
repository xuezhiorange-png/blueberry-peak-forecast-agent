"""R3 authorization tests; synthetic fixtures are not real dataset evidence."""

import gzip
import json
import math
import shutil
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.tests.base_registry.test_era5_land_historical_weather_r2 import source_fixture
from scripts.climate_source_r2 import file_hash, write_json
from scripts.era5_historical_dataset_r3 import (
    load,
    preflight,
    prepare_grid_review,
    recover_submitted,
    retrieve,
)
from scripts.era5_source_artifact_correction_r3 import VERSION, correct_value, validate_policy
from scripts.normalize_era5_land_historical_weather_r1 import no_network
from scripts.normalize_era5_land_historical_weather_r2 import verified_source
from scripts.normalize_era5_land_historical_weather_r3 import corrected_day, replay

pytestmark = pytest.mark.unit


def test_explicit_grid_provider_mismatch_still_blocks_before_network(tmp_path, monkeypatch):
    root, _, entry = r3_fixture(tmp_path, monkeypatch, lon=102.1)
    destination = tmp_path / "explicit-grid"
    prepare_grid_review(root, destination)
    revised, _ = load(destination)
    key = revised["requests"][0]["request_hash"]
    raw = destination / f"{key}.raw"
    shutil.copy2(root / f"{entry['request_hash']}.raw", raw)
    write_json(
        destination / f"{key}.completed.json",
        {"request_hash": key, "filename": raw.name, "raw_sha256": file_hash(raw)},
    )
    monkeypatch.setitem(sys.modules, "cdsapi", None)
    with pytest.raises(ValueError, match="PROVIDER_GRID_SELECTION_MISMATCH"):
        retrieve(destination)


@pytest.mark.parametrize("reuse", [False, True])
def test_reviewed_grid_query_preserves_original_and_only_reuses_qualified(
    tmp_path, monkeypatch, reuse
):
    root, original, entry = r3_fixture(tmp_path, monkeypatch)
    if reuse:
        preflight(root)
    before = {p.name: file_hash(p) for p in root.iterdir() if p.is_file()}
    destination = tmp_path / "explicit-grid"
    prepare_grid_review(root, destination)
    revised, _ = load(destination)
    assert revised["locations"] == original["locations"]
    assert revised["explicit_grid_review"] == "5204323324"
    for current in revised["requests"]:
        assert current["original_request_hash"] == entry["request_hash"]
        if reuse:
            assert current["query_mode"] == "REUSED_QUALIFIED_PROVIDER_POINT"
        else:
            assert current["query_mode"] == "EXPLICIT_FROZEN_GRID"
            for coordinate in ("latitude", "longitude"):
                assert current["request"]["location"][coordinate] == float(
                    current[f"expected_selected_grid_{coordinate}"]
                )
    assert preflight(destination)["raw_checked"] == (1 if reuse else 0)
    assert {p.name: file_hash(p) for p in root.iterdir() if p.is_file()} == before


def test_submitted_recovery_downloads_existing_job_without_submit(tmp_path, monkeypatch):
    root, _, entry = r3_fixture(tmp_path, monkeypatch)
    raw = root / f"{entry['request_hash']}.raw"
    raw_bytes = raw.read_bytes()
    write_json(
        root / f"{entry['request_hash']}.submitted.json",
        {"request_hash": entry["request_hash"], "remote_request_id": "synthetic-job-id"},
    )
    raw.unlink()
    (root / f"{entry['request_hash']}.completed.json").unlink()
    receipt = json.loads((root / f"{entry['request_hash']}.submitted.json").read_text())

    class Remote:
        request_id = receipt["remote_request_id"]
        status = "successful"

        def download(self, path):
            Path(path).write_bytes(raw_bytes)

    class Client:
        def check_authentication(self):
            return None

        def get_remote(self, remote_id):
            assert remote_id == receipt["remote_request_id"]
            return Remote()

        def submit(self, *args):
            pytest.fail("SUBMIT_FORBIDDEN_DURING_SUBMITTED_RECOVERY")

    monkeypatch.setitem(
        sys.modules, "cdsapi", SimpleNamespace(Client=lambda **k: SimpleNamespace(client=Client()))
    )
    result = recover_submitted(root)
    assert result["status"] == "PASS"
    assert result["submitted_receipt_count"] == 1
    assert result["recovered_count"] == 1
    assert result["resubmitted"] is False
    assert (root / f"{entry['request_hash']}.completed.json").exists()


def test_submitted_recovery_stops_when_resubmission_would_be_required(tmp_path, monkeypatch):
    root, _, entry = r3_fixture(tmp_path, monkeypatch)
    raw = root / f"{entry['request_hash']}.raw"
    write_json(
        root / f"{entry['request_hash']}.submitted.json",
        {"request_hash": entry["request_hash"], "remote_request_id": "synthetic-job-id"},
    )
    raw.unlink()
    (root / f"{entry['request_hash']}.completed.json").unlink()
    receipt = json.loads((root / f"{entry['request_hash']}.submitted.json").read_text())

    class Remote:
        request_id = receipt["remote_request_id"]
        status = "server_failed"

    class Client:
        def check_authentication(self):
            return None

        def get_remote(self, remote_id):
            return Remote()

        def submit(self, *args):
            pytest.fail("RESUBMIT_FORBIDDEN_DURING_SUBMITTED_RECOVERY")

    monkeypatch.setitem(
        sys.modules, "cdsapi", SimpleNamespace(Client=lambda **k: SimpleNamespace(client=Client()))
    )
    with pytest.raises(RuntimeError, match="CDS_RESUBMISSION_AUTHORIZATION_REQUIRED"):
        recover_submitted(root)
    record = json.loads(sorted(root.glob("stop-*.json"))[-1].read_text())
    assert record["blocker"] == "CDS_RESUBMISSION_AUTHORIZATION_REQUIRED"
    assert record["remote_request_id"] == receipt["remote_request_id"]
    assert record["cds_status"] == "server_failed"
    assert record["automatic_resubmission"] is False


@pytest.mark.parametrize("var,edge", [("tp", -3e-8), ("ssrd", -4.0)])
def test_frozen_envelope_inclusive_and_next_float_outside(var, edge):
    assert correct_value(var, edge) == 0.0
    assert correct_value(var, math.nextafter(edge, 0.0)) == 0.0
    with pytest.raises(ValueError, match="NEGATIVE_VALUE_OUTSIDE_CERTIFIED_ARTIFACT_ENVELOPE"):
        correct_value(var, math.nextafter(edge, -math.inf))


@pytest.mark.parametrize("var", ["tp", "ssrd", "t2m", "d2m", "u10", "v10"])
@pytest.mark.parametrize("value", [0.0, 1e-20, 0.001, 100.0])
def test_positive_values_bitwise_unchanged(var, value):
    assert correct_value(var, value).hex() == value.hex()


@pytest.mark.parametrize("var", ["t2m", "d2m", "u10", "v10"])
def test_other_variables_never_corrected(var):
    assert correct_value(var, -2.0) == -2.0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_rejected(value):
    with pytest.raises(ValueError, match="NONFINITE_NATIVE_VALUE"):
        correct_value("tp", value)


def r3_fixture(tmp_path, monkeypatch, **kwargs):
    root, m, entry = source_fixture(tmp_path, **kwargs)
    config = json.loads(Path("configs/era5_land_historical_weather_r3.json").read_text())
    config["source_manifest_r2_hash"] = m["manifest_hash"]
    write_json(root / "correction-policy.json", config)
    import scripts.era5_historical_dataset_r3 as stage

    monkeypatch.setattr(stage, "CONFIG", root / "correction-policy.json")
    return root, m, entry


def test_correction_metadata_units_raw_retention_and_two_offline_replays(tmp_path, monkeypatch):
    root, _, entry = r3_fixture(tmp_path, monkeypatch, negative="tp")
    raw = root / f"{entry['request_hash']}.raw"
    original = file_hash(raw)
    assert preflight(root)["status"] == "PASS"
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    first = replay(root, tmp_path / "one")
    second = replay(root, tmp_path / "two")
    assert first == second
    assert first["hourly_row_count"] == 38 * 24 * 6
    assert first["daily_row_count"] == 38
    assert first["corrected_tp_count"] == 38
    rows = [
        json.loads(s) for s in (tmp_path / "one" / "corrections.jsonl").read_text().splitlines()
    ]
    assert len({r["base_id"] for r in rows}) == 38
    assert all(r["corrected_value"] == "0" and r["raw_artifact_sha256"] == original for r in rows)
    assert all(
        r["correction_version"] == VERSION and float(r["raw_negative_value"]) < 0 for r in rows
    )
    assert file_hash(raw) == original
    with gzip.open(tmp_path / "one" / "hourly.jsonl.gz", "rt") as stream:
        hours = [json.loads(s) for s in stream]
    changed = [r for r in hours if r["source_artifact_correction_applied"]]
    assert all(
        float.fromhex(r["native_value_exact_hex"]) < 0 and r["source_corrected_native_value"] == "0"
        for r in changed
    )
    assert all(
        r["native_unit"] == "K" and r["normalized_unit"] == "degC"
        for r in hours
        if r["native_variable"] in {"t2m", "d2m"}
    )
    days = [json.loads(s) for s in (tmp_path / "one" / "daily.jsonl").read_text().splitlines()]
    assert all(
        r["temperature_unit"] == "degC" and r["local_day_mean_temperature_c"] == "6.850000000000"
        for r in days
    )


def test_tiny_positive_source_string_is_not_thresholded(tmp_path, monkeypatch):
    root, _, entry = r3_fixture(tmp_path, monkeypatch)
    native, a = verified_source(root, entry)
    start = datetime(2024, 1, 1, 16, tzinfo=UTC)
    native["tp", start.replace(hour=17)] = 1e-20
    corrected = {k: correct_value(k[0], v) for k, v in native.items()}
    hours, _ = corrected_day(native, corrected, start, a["raw_sha256"])
    row = next(r for r in hours if r["native_variable"] == "tp")
    assert float(row["source_corrected_native_value"]) == 1e-20
    assert not row["source_artifact_correction_applied"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("tp_negative_artifact_envelope_min_m", "-4e-8"),
        ("ssrd_negative_artifact_envelope_min_j_m2", "-5"),
        ("positive_value_thresholding", True),
        ("automatic_tolerance_widening", True),
        ("normalized_temperature_unit", "K"),
    ],
)
def test_policy_cannot_widen_or_change_units(field, value):
    c = json.loads(Path("configs/era5_land_historical_weather_r3.json").read_text())
    c[field] = value
    with pytest.raises(ValueError, match="FROZEN_CORRECTION_POLICY_MISMATCH"):
        validate_policy(c)


def test_preflight_failure_precedes_any_cds_access(tmp_path, monkeypatch):
    root, _, entry = r3_fixture(tmp_path, monkeypatch)
    raw = root / f"{entry['request_hash']}.raw"
    raw.write_bytes(raw.read_bytes() + b"tamper")
    monkeypatch.setitem(
        sys.modules,
        "cdsapi",
        SimpleNamespace(Client=lambda **k: pytest.fail("NETWORK_BEFORE_PREFLIGHT")),
    )
    with pytest.raises(ValueError, match="RAW_HASH_MISMATCH"):
        retrieve(root)


@pytest.mark.parametrize("failure_phase", ["AUTHENTICATE", "SUBMIT_OR_RESUME", "POLL", "DOWNLOAD"])
def test_request_failure_stops_and_redacts_no_automatic_resubmit(
    tmp_path, monkeypatch, failure_phase
):
    root, m, entry = r3_fixture(tmp_path, monkeypatch)
    # Fixture completion is removed before retrieval so it represents a not-yet-downloaded request.
    (root / f"{entry['request_hash']}.completed.json").unlink()
    (root / f"{entry['request_hash']}.raw").unlink()
    calls = []

    def fail():
        raise RuntimeError("private token URL must not be copied")

    class Remote:
        request_id = "synthetic-request-id"

        @property
        def status(self):
            if failure_phase == "POLL":
                fail()
            return "successful"

        def download(self, path):
            fail()

    class Client:
        def check_authentication(self):
            if failure_phase == "AUTHENTICATE":
                fail()

        def submit(self, *args):
            calls.append("submit")
            if failure_phase == "SUBMIT_OR_RESUME":
                fail()
            return Remote()

    monkeypatch.setitem(
        sys.modules, "cdsapi", SimpleNamespace(Client=lambda **k: SimpleNamespace(client=Client()))
    )
    with pytest.raises(RuntimeError, match="CDS_REQUEST_OR_DOWNLOAD_FAILED"):
        retrieve(root)
    stop = next(root.glob("stop-*.json"))
    record = json.loads(stop.read_text())
    assert record["phase"] == failure_phase
    assert "private token" not in stop.read_text()
    assert len(calls) <= 1
    with pytest.raises(ValueError, match="PRIOR_RETRIEVAL_STOP_REQUIRES_REVIEW"):
        retrieve(root)
