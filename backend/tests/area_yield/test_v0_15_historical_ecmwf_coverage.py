"""Synthetic coverage-contract tests; ordinary CI needs no private or network data."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.audit_v0_15_historical_ecmwf_coverage import (
    POLICY_HASH,
    STEPS,
    calendar,
    coverage_class,
    eligible_issues,
    encoded,
    freeze_policy,
    numerical_status,
    project_origin,
    validate_run_evidence,
    write_csv,
)


def candidate(**changes: object) -> dict:
    return {
        "base_id": "base_exact",
        "season": "2024-2025",
        "target_start_date": "2025-02-01",
        "target_end_date": "2025-02-03",
        "training_candidate": True,
        **changes,
    }


def fixtures() -> tuple[dict, dict]:
    run_id = "20250201000000"
    origin = {
        "date": "2025-02-01",
        "forecast_cutoff": "2025-02-01T17:00:00+08:00",
        "inspected_runs": [run_id],
        "recoverable_run_id": run_id,
        "strict_selected_run_id": None,
    }
    runs = {
        run_id: {
            "status": "RUN_AVAILABLE",
            "issue_time": "2025-02-01T00:00:00+00:00",
            "cycle": "00",
            "historical_availability_status": "NOT_PIT_ADMISSIBLE_MISSING_PUBLICATION_EVIDENCE",
        }
    }
    return origin, runs


def test_label_free_calendar_inclusive_and_no_tail_trimming() -> None:
    rows = calendar([candidate()])
    assert [r["date"] for r in rows] == ["2025-02-01", "2025-02-02", "2025-02-03"]
    assert rows[0]["forecast_origin"] == "2025-02-01T17:00:00+08:00"
    assert set(rows[0]) == {"base_id", "season", "forecast_origin", "forecast_cutoff", "date"}


def test_calendar_ignores_non_candidates() -> None:
    assert calendar([candidate(training_candidate=False)]) == []


@pytest.mark.parametrize("season", ["2026-2027", "UNKNOWN", "2022-2023"])
def test_current_or_unfrozen_season_rejected(season: str) -> None:
    with pytest.raises(ValueError, match="COMPLETED_HISTORICAL_SEASON"):
        calendar([candidate(season=season)])


@pytest.mark.parametrize(
    "changes",
    [
        {"target_end_date": "2026-07-01"},
        {"target_start_date": "2025-02-04"},
    ],
)
def test_invalid_date_range_rejected(changes: dict) -> None:
    with pytest.raises(ValueError, match="HISTORICAL_DATE_RANGE"):
        calendar([candidate(**changes)])


def test_duplicate_base_season_rejected() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_CANDIDATE"):
        calendar([candidate(), candidate()])


def test_cycles_cutoff_and_freshness_are_exact() -> None:
    assert eligible_issues(datetime.fromisoformat("2025-02-01T17:00:00+08:00")) == [
        "20250201000000",
        "20250131120000",
        "20250131000000",
    ]


def test_naive_cutoff_rejected() -> None:
    with pytest.raises(ValueError, match="AWARE_CUTOFF"):
        eligible_issues(datetime(2025, 2, 1, 17))


@pytest.mark.parametrize("complete", [1, 19, 95, 99])
def test_full_never_means_95_percent(complete: int) -> None:
    statuses = ["WEATHER8_COMPLETE"] * complete + ["WEATHER8_UNAVAILABLE"] * (100 - complete)
    assert coverage_class(statuses, True) == "PARTIAL_WEATHER_COVERAGE"


def test_full_requires_all_origins() -> None:
    assert coverage_class(["WEATHER8_COMPLETE"] * 100, True) == "FULL_WEATHER_COVERAGE"


def test_invalid_location_has_priority() -> None:
    assert coverage_class(["WEATHER8_COMPLETE"], False) == "INVALID_LOCATION"


def test_empty_universe_cannot_be_full() -> None:
    with pytest.raises(ValueError, match="EMPTY_BASE_SEASON"):
        coverage_class([], True)


def test_index_completeness_does_not_become_historical_known_at() -> None:
    origin, runs = fixtures()
    result = project_origin(origin, runs)
    assert result["recoverability_status"] == "INDEX_COMPLETE"
    assert result["run_status"] == "POLICY_NO_ELIGIBLE_RUN"
    assert result["selected_ecmwf_issue_time"] == ""
    assert result["weather8_status"] == "WEATHER8_UNAVAILABLE"


@pytest.mark.parametrize(
    "mutator,reason",
    [
        (lambda r: r.update(inspected_runs=[]), "RUN_ORDER"),
        (lambda r: r.update(inspected_runs=["20250201120000"]), "RUN_ORDER"),
        (lambda r: r.update(inspected_runs=["20250131000000"]), "RUN_ORDER"),
        (lambda r: r.update(recoverable_run_id=None), "RECOVERABILITY_SELECTION"),
        (lambda r: r.update(strict_selected_run_id="20250201000000"), "UNPROVEN_HISTORICAL"),
    ],
)
def test_result_driven_or_unproven_selection_rejected(mutator, reason: str) -> None:
    origin, runs = fixtures()
    mutator(origin)
    with pytest.raises(ValueError, match=reason):
        project_origin(origin, runs)


def test_missing_receipt_rejected() -> None:
    origin, _ = fixtures()
    with pytest.raises(ValueError, match="RUN_RECEIPT_MISSING"):
        project_origin(origin, {})


def test_transport_error_never_means_not_found() -> None:
    origin, runs = fixtures()
    origin["recoverable_run_id"] = None
    runs["20250201000000"]["status"] = "RUN_ACCESS_ERROR"
    result = project_origin(origin, runs)
    assert result["recoverability_status"] == "ACCESS_ERROR"
    assert result["transport_error_present"] is True


def test_historical_availability_cannot_be_silently_upgraded() -> None:
    origin, runs = fixtures()
    runs["20250201000000"]["historical_availability_status"] = "ISSUED_AT_EQUALS_KNOWN_AT"
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRES_REVIEW"):
        project_origin(origin, runs)


def test_consumes_existing_policy_without_redefining_it() -> None:
    path = Path(
        "docs/v0-15/evidence/historical-ecmwf-proof-r1/historical-run-selection-policy.json"
    )
    policy = json.loads(path.read_text())
    assert policy["policy_hash"] == POLICY_HASH
    freeze_policy(policy)
    changed = copy.deepcopy(policy)
    changed["historical_information_available_at_lte_cutoff_required"] = False
    with pytest.raises(ValueError, match="FROZEN_RUN_POLICY_CHANGED"):
        freeze_policy(changed)


def test_deterministic_csv_and_json(tmp_path: Path) -> None:
    rows = calendar([candidate()])
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    write_csv(first, rows)
    write_csv(second, rows)
    assert first.read_bytes() == second.read_bytes()
    assert encoded({"b": 2, "a": 1}) == encoded({"a": 1, "b": 2})


def test_no_training_scoring_actual_or_network_imports() -> None:
    import ast

    path = Path("scripts/audit_v0_15_historical_ecmwf_coverage.py")
    tree = ast.parse(path.read_text())
    modules = {
        n.module if isinstance(n, ast.ImportFrom) else alias.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for alias in n.names
    }
    assert not any(
        token in (module or "")
        for module in modules
        for token in ["actual", "scoring", "sqlalchemy", "httpx", "urllib", "sklearn"]
    )


def test_index_only_never_certifies_unextracted_weather_values() -> None:
    assert numerical_status("base_exact", None) == "NOT_PER_ORIGIN_VALIDATED"


def test_numeric_regression_is_fail_closed_not_tolerance() -> None:
    sample = {
        "feature_hashes": {},
        "fail_closed_errors": {"base_exact": "CUMULATIVE_WEATHER_REGRESSION"},
    }
    assert numerical_status("base_exact", sample) == "FAIL_CLOSED_CUMULATIVE_WEATHER_REGRESSION"


def test_real_reconstruction_applies_only_to_extracted_base() -> None:
    sample = {"feature_hashes": {"base_exact": "abc"}}
    assert numerical_status("base_exact", sample) == "REAL_GRIB_WEATHER8_RECONSTRUCTED"
    assert numerical_status("base_other", sample) == "NOT_PER_ORIGIN_VALIDATED"


def complete_product() -> dict:
    fields = []
    for step in STEPS:
        params = ["2t", "10u", "10v"] + (["tp", "ssrd"] if step in {168, 360} else [])
        fields.append(
            {
                "step": step,
                "status": "INDEX_FIELDS_COMPLETE",
                "receipt": {"status": 200},
                "entries": [
                    {
                        "param": p,
                        "class": "od",
                        "stream": "oper",
                        "type": "fc",
                        "levtype": "sfc",
                        "date": "20250201",
                        "time": "0000",
                        "step": str(step),
                        "expver": "0001",
                        "_offset": 0,
                        "_length": 1,
                    }
                    for p in params
                ],
            }
        )
    return {
        "run_id": "20250201000000",
        "status": "RUN_AVAILABLE",
        "products": [
            {
                "status": "RUN_AVAILABLE",
                "resolution": "0p25",
                "namespace": "20250201/00z/ifs/0p25/oper",
                "fields": fields,
            }
        ],
    }


def test_actual_complete_index_contract() -> None:
    validate_run_evidence(complete_product())


@pytest.mark.parametrize(
    "key,value",
    [
        ("param", "ssr"),
        ("class", "ei"),
        ("stream", "enfo"),
        ("type", "cf"),
        ("levtype", "pl"),
        ("date", "20250202"),
        ("time", "1200"),
        ("step", "0"),
        ("_length", 0),
        ("_offset", -1),
        ("expver", "0002"),
    ],
)
def test_non_equivalent_or_mixed_index_rejected(key: str, value: object) -> None:
    run = complete_product()
    run["products"][0]["fields"][0]["entries"][0][key] = value
    with pytest.raises(ValueError):
        validate_run_evidence(run)


def test_missing_360_cannot_be_complete() -> None:
    run = complete_product()
    run["products"][0]["fields"].pop()
    with pytest.raises(ValueError, match="NATIVE_STEPS_NOT_PROVEN"):
        validate_run_evidence(run)


def test_aifs_not_substituted_for_ifs() -> None:
    run = complete_product()
    run["products"][0]["namespace"] = "20250201/00z/aifs/0p25/oper"
    with pytest.raises(ValueError, match="PRODUCT_NOT_EQUIVALENT"):
        validate_run_evidence(run)


def test_sanitized_public_evidence_manifest_and_self_hash() -> None:
    import hashlib

    root = Path("docs/v0-15/evidence/historical-ecmwf-coverage-sweep-r1")
    manifest = json.loads((root / "manifest.json").read_bytes())
    direct = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    assert hashlib.sha256(encoded(direct)).hexdigest() == manifest["manifest_hash"]
    for member in manifest["members"]:
        data = (root / member["name"]).read_bytes()
        assert len(data) == member["bytes"]
        assert hashlib.sha256(data).hexdigest() == member["sha256"]
        assert b"/Users/" not in data and b"/tmp/" not in data
        assert b'"features":' not in data and b'"quantity_kg":' not in data


def test_public_matrix_denominators_and_no_false_full() -> None:
    import csv

    root = Path("docs/v0-15/evidence/historical-ecmwf-coverage-sweep-r1")
    summary = json.loads((root / "historical-ecmwf-coverage-summary.json").read_bytes())
    with (root / "historical-base-season-origin-weather-matrix.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == summary["total_required_forecast_origin_count"]
    assert len({(r["base_id"], r["season"], r["forecast_origin"]) for r in rows}) == len(rows)
    assert len({r["date"] for r in rows}) == summary["unique_required_forecast_origin_count"]
    assert len({(r["base_id"], r["season"]) for r in rows}) == 76
    assert all(r["forecast_origin"].endswith("T17:00:00+08:00") for r in rows)
    assert summary["index_complete_recoverable_origin_count"] == sum(
        r["index_complete_origins"] for r in summary["required_period_coverage"].values()
    )
    assert summary["weather8_complete_origin_count"] == 0
    assert summary["policy_changed"] is False
    assert summary["per_origin_numerical_reconstruction_complete"] is False
