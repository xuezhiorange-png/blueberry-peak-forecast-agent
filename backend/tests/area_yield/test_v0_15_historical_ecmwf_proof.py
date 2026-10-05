"""Synthetic metadata only. Real retrieval remains independent operator evidence."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.validate_v0_15_historical_ecmwf_proof import (
    PARAM_IDS,
    REQUIRED,
    UNITS,
    validate_dense_metadata,
)


def fixture():
    issued = datetime(2025, 2, 1, tzinfo=UTC)
    fields = []
    for step, param in sorted(REQUIRED):
        valid = issued + timedelta(hours=step)
        fields.append(
            {
                "step": step,
                "parameter": param,
                "file_size": 100,
                "sha256": "a" * 64,
                "metadata": {
                    "shortName": param,
                    "paramId": PARAM_IDS[param],
                    "units": UNITS[param],
                    "stepType": "accum" if param in {"tp", "ssrd"} else "instant",
                    "startStep": 0 if param in {"tp", "ssrd"} else step,
                    "endStep": step,
                    "dataDate": 20250201,
                    "dataTime": 0,
                    "validityDate": int(valid.strftime("%Y%m%d")),
                    "validityTime": valid.hour * 100,
                    "marsClass": "od",
                    "marsStream": "oper",
                    "marsType": "fc",
                    "centre": "ecmf",
                    "edition": 2,
                    "gridType": "regular_ll",
                    "iDirectionIncrementInDegrees": 0.25,
                    "jDirectionIncrementInDegrees": 0.25,
                    "numberOfDataPoints": 100,
                    "values_decoded_count": 100,
                },
            }
        )
    return {
        "provider_issued_at": issued.isoformat(),
        "provider_run_id": "20250201000000",
        "fields": fields,
    }


def test_complete_native_surface():
    result = validate_dense_metadata(fixture())
    assert result["field_count"] == 256
    assert result["forecast_step_count"] == 84
    assert result["radiation_semantics_match"]


def test_committed_real_proof_manifest_and_policy():
    root = Path(__file__).resolve().parents[3] / "docs/v0-15/evidence/historical-ecmwf-proof-r1"
    manifest = json.loads((root / "report-manifest.json").read_text())
    assert len(manifest["members"]) == 7
    for member in manifest["members"]:
        raw = (root / member["name"]).read_bytes()
        assert len(raw) == member["size"]
        assert hashlib.sha256(raw).hexdigest() == member["sha256"]
    dense = json.loads((root / "real-grib-metadata-validation.json").read_text())
    assert validate_dense_metadata(dense)["field_count"] == 256
    policy = json.loads((root / "historical-run-selection-policy.json").read_text())
    policy_hash = policy.pop("policy_hash")
    encoded = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == policy_hash
    assert policy["historical_information_available_at_lte_cutoff_required"]
    assert policy["missing_historical_publication_evidence"] == "NOT_PIT_ADMISSIBLE"
    assert policy["result_independent_selection"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("shortName", "ssr"),
        ("paramId", 176),
        ("units", "degC"),
        ("dataDate", 20250202),
        ("dataTime", 1200),
        ("validityDate", 20250202),
        ("stepType", "accum"),
        ("startStep", 0),
        ("marsClass", "ea"),
        ("marsStream", "enfo"),
        ("marsType", "pf"),
        ("values_decoded_count", 0),
        ("iDirectionIncrementInDegrees", 0.5),
    ],
)
def test_wrong_metadata_rejected(key, value):
    report = fixture()
    report["fields"][0]["metadata"][key] = value
    with pytest.raises(ValueError):
        validate_dense_metadata(report)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "step_zero", "missing_360"])
def test_incomplete_or_mutated_surface_rejected(mutation):
    report = fixture()
    if mutation == "missing":
        report["fields"].pop()
    elif mutation == "duplicate":
        report["fields"][-1] = deepcopy(report["fields"][0])
    elif mutation == "step_zero":
        report["fields"][0]["step"] = 0
    else:
        report["fields"] = [r for r in report["fields"] if r["step"] != 360]
    with pytest.raises(ValueError):
        validate_dense_metadata(report)


def test_naive_issue_rejected():
    report = fixture()
    report["provider_issued_at"] = "2025-02-01T00:00:00"
    with pytest.raises(ValueError):
        validate_dense_metadata(report)


def test_current_season_weather_not_substituted_for_history():
    report = fixture()
    report["provider_issued_at"] = "2026-10-05T00:00:00+00:00"
    report["provider_run_id"] = "20261005000000"
    with pytest.raises(ValueError, match="AUTHORIZED_HISTORICAL_PERIOD"):
        validate_dense_metadata(report)


def test_accumulation_origin_and_ssr_substitution_rejected():
    for key, value in [("startStep", 162), ("shortName", "ssr"), ("units", "W m**-2")]:
        report = fixture()
        row = next(r for r in report["fields"] if r["parameter"] == "ssrd")
        row["metadata"][key] = value
        with pytest.raises(ValueError):
            validate_dense_metadata(report)
