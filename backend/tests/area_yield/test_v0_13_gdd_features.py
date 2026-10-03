"""Synthetic S2 acceptance: no labels, fitting, predictions or scoring."""

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield import gdd_features as g

pytestmark = pytest.mark.contract


def rows() -> list[dict]:
    return [
        {
            "base_id": "synthetic",
            "local_date": (date(2028, 7, 1) + timedelta(days=i)).isoformat(),
            "sampled_local_day_tmax_c": "20",
            "sampled_local_day_tmin_c": "10",
            "processing_version": "BASE_WEATHER_DAILY_V1",
            "hourly_sample_count": 24,
        }
        for i in range(30)
    ]


def context(data: list[dict] | None = None) -> dict:
    return g.build_gdd_context(
        g.index_daily(rows() if data is None else data),
        "synthetic",
        "2028-07-31T00:00:00+08:00",
        "a" * 64,
    )


@pytest.mark.parametrize(
    "tmax,tmin,expected", [("20", "10", "8"), ("10", "2", "0"), ("7", "7", "0"), ("20", "0", "3")]
)
def test_golden_no_tmin_preclip(tmax: str, tmin: str, expected: str) -> None:
    assert g.daily_gdd(tmax, tmin) == Decimal(expected)


def test_decimal_no_early_rounding_and_nested_windows() -> None:
    r = rows()
    for item in r:
        item["sampled_local_day_tmax_c"] = "7.00000000000006"
        item["sampled_local_day_tmin_c"] = "7.00000000000006"
    c = context(r)
    assert c["gdd_w30"] == "0.000000000002"
    assert Decimal(c["gdd_w30"]) >= Decimal(c["gdd_w14"]) >= Decimal(c["gdd_w7"]) >= 0
    assert context()["gdd_w7"] == "56.000000000000"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("sampled_local_day_tmin_c", None, "MISSING_TMIN"),
        ("sampled_local_day_tmax_c", None, "MISSING_TMAX"),
        ("sampled_local_day_tmin_c", "NaN", "NONFINITE"),
        ("sampled_local_day_tmax_c", "Infinity", "NONFINITE"),
        ("sampled_local_day_tmin_c", "30", "TMAX_LT_TMIN"),
        ("timezone", "UTC", "WRONG_TIMEZONE"),
        ("temperature_unit", "K", "WRONG_UNIT"),
        ("sampled_local_day_tmax_c", "293.15", "WRONG_UNIT"),
        ("hourly_sample_count", 23, "DATE_MISMATCH"),
    ],
)
def test_failure_invalid_temperature(field: str, value: object, reason: str) -> None:
    r = rows()
    r[0][field] = value
    assert context(r)["reason"] == reason
    assert context(r)["eligible"] is False


def test_failure_missing_and_duplicate_day() -> None:
    assert context(rows()[1:])["reason"] == "MISSING_REQUIRED_LOCAL_DAY"
    assert context(rows() + [rows()[0]])["reason"] == "DUPLICATE_DAY"


@pytest.mark.parametrize(
    "mutation",
    [
        {"tbase_c": "5"},
        {"tbase_c": "10"},
        {"upper_clip": "30"},
        {"tmin_preclip": True},
        {"windows": [7, 14, 21]},
        {"early_daily_rounding": True},
        {"formula": "local_day_mean_temperature_c"},
        {"season_to_date": True},
        {"timezone": "UTC"},
    ],
)
def test_failure_policy_mutations(mutation: dict) -> None:
    p = {**g.POLICY, **mutation}
    with pytest.raises(g.GDDError, match="GDD_POLICY_MISMATCH"):
        g.validate_policy(p)


@pytest.mark.parametrize("end", ["2028-07-31", "2028-08-01"])
def test_failure_origin_and_future_source_window(end: str) -> None:
    c = context()
    c["source_window_end"] = end
    with pytest.raises(g.GDDError):
        g.verify_context(c)


def test_failure_wrong_origin_projection_and_model_specific_cohort() -> None:
    key = "synthetic+2028-07-31T00:00:00+08:00+2028-07-31"
    c = context()
    with pytest.raises(g.GDDError):
        g.project_rows([key.replace("07-31T", "08-01T")], {(c["base_id"], c["forecast_origin"]): c})
    with pytest.raises(g.GDDError, match="MODEL_SPECIFIC_COHORT"):
        g.require_common_models({"M0": [key], "M1": [], "M2": [key], "M3": [key]})


def test_replay_projection_manifest_and_views() -> None:
    c = context()
    assert c == context()
    keys = [
        f"synthetic+2028-07-31T00:00:00+08:00+{date(2028, 7, 31) + timedelta(days=i)}"
        for i in range(15)
    ]
    contexts = {(c["base_id"], c["forecast_origin"]): c}
    result = g.project_rows(keys, contexts)
    assert result["common_row_count"] == 15
    assert result["views"]["H15"]["count"] == 1
    assert g.build_gdd_manifest([c], "a" * 64) == g.build_gdd_manifest([deepcopy(c)], "a" * 64)


def test_failure_wrong_file_hash(tmp_path) -> None:
    p = tmp_path / "weather.jsonl"
    p.write_text("{}\n")
    with pytest.raises(g.GDDError, match="WEATHER_ARTIFACT_HASH_MISMATCH"):
        g.load_daily(p, "a" * 64)


@pytest.mark.parametrize(
    "field,value",
    [
        ("standardization", "WRONG"),
        ("standardization", "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD"),
        ("unexpected", True),
        ("model_id", "ARBITRARY_SELF_HASH_MISMATCH"),
        ("model_id", "AREA_DAILY_RIDGE_V1_PLUS_LEAKAGE_SAFE_WEATHER_FEATURES"),
        ("fold_id", "FOLD_C"),
        ("artifact_hash", "a" * 64),
        ("training_input_hash", "a" * 64),
        ("training_label_hash", "a" * 64),
        ("training_row_keys", ["changed"]),
        ("coefficients", ["changed"]),
        ("alpha", "5"),
        ("solver", None),
    ],
)
def test_failure_legacy_cannot_generalize(field: str, value: object) -> None:
    import json
    from pathlib import Path

    from scripts.run_v0_13_s2_gdd_feature_audit import verify_v0_7_s3_legacy_model_a_artifact

    root = Path(__file__).resolve().parents[3]
    public = json.loads(
        (
            root / "docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"
        ).read_text()
    )["folds"]["fold_a"]["model_a"]
    artifact = {k: v for k, v in public.items() if k != "training_row_key_count"}
    # Synthetic identities cannot pass the pinned row hash, even if metadata matches.
    artifact["training_row_keys"] = ["synthetic"] * public["training_row_key_count"]
    artifact[field] = value
    if field == "solver":
        del artifact[field]
    with pytest.raises(g.GDDError):
        verify_v0_7_s3_legacy_model_a_artifact(artifact, public, "FOLD_A")


def test_pipeline_does_not_depend_on_model_or_actuals(monkeypatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "backend.app.area_yield.weather_aware_backtest", None)
    c = context()
    key = "synthetic+2028-07-31T00:00:00+08:00+2028-07-31"
    assert g.project_rows([key], {(c["base_id"], c["forecast_origin"]): c})["common_row_count"] == 1
    assert g.build_gdd_manifest([c], "a" * 64)["context_count"] == 1


def frozen_validation_fold(name: str) -> dict:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    fold = json.loads(
        (
            root / "docs/v0-7/evidence/s3-weather-aware-model-training-and-oot-backtest.json"
        ).read_text()
    )["folds"][name]
    fold["validation_base_count"] = 1
    fold["validation_dataset_meta"] = {"incomplete_origin_count_by_base": {"synthetic": 0}}
    return fold


@pytest.mark.parametrize(
    "name,start,end",
    [("fold_a", "2024-07-01", "2025-04-15"), ("fold_b", "2025-07-22", "2026-04-15")],
)
def test_validation_calendar_reconstruction_without_labels(name: str, start: str, end: str) -> None:
    from scripts.run_v0_13_s2_gdd_feature_audit import reconstruct_validation

    # Complete prior weather makes the FIRST candidate origin observable.
    # A hardcoded July-1 calendar therefore cannot hide behind weather coverage.
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    day = first.replace(day=1) - timedelta(days=30)
    daily = []
    while day <= last:
        daily.append({"base_id": "synthetic", "local_date": day.isoformat()})
        day += timedelta(days=1)
    keys = reconstruct_validation(frozen_validation_fold(name), daily)
    assert keys[0] == f"synthetic+{start}T00:00:00+08:00+{start}"
    assert keys[-1] == f"synthetic+{end}T00:00:00+08:00+{end}"
    if name == "fold_b":
        assert not any("2025-07-01T" in key for key in keys)


@pytest.mark.parametrize("name", ["fold_a", "fold_b"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("business_start", "2025-07-01"),
        ("business_end", "2026-04-14"),
        ("season", "2028-2029"),
        ("policy", "INFERRED_CALENDAR"),
        ("authority_hash", "0" * 64),
        ("business_boundary", None),
        ("business_start", None),
    ],
)
def test_failure_frozen_business_boundary(name: str, field: str, value: object) -> None:
    from scripts.run_v0_13_s2_gdd_feature_audit import reconstruct_validation

    fold = frozen_validation_fold(name)
    if field == "business_boundary":
        del fold["prediction_manifest"][field]
    elif value is None:
        del fold["prediction_manifest"]["business_boundary"][field]
    else:
        fold["prediction_manifest"]["business_boundary"][field] = value
    with pytest.raises(g.GDDError, match="FROZEN_BUSINESS_BOUNDARY"):
        reconstruct_validation(fold, [])


def test_frozen_s1_and_public_s2_evidence() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    s1 = json.loads(
        (root / "docs/v0-13/evidence/v0.13-s1-gdd-scientific-definition-freeze.json").read_text()
    )
    assert s1["GDD_DEFINITION_ID"] == g.DEFINITION_ID
    assert s1["GDD_BASE_TEMPERATURE_C"] == g.POLICY["tbase_c"]
    assert s1["ROLLING_GDD_WINDOWS"] == g.POLICY["windows"]
    assert s1["precision"]["decimal_context_precision_minimum"] == g.POLICY["precision"]
    assert s1["precision"]["output_decimal_places"] == g.POLICY["decimal_places"]
    s2 = json.loads(
        (root / "docs/v0-13/evidence/v0.13-s2-gdd-feature-coverage-audit-r2.json").read_text()
    )
    assert s2["V0_13_S2_COMPLETE"] is True
    for key in (
        "V0_13_S3_AUTHORIZED",
        "V0_13_S4_AUTHORIZED",
        "V0_13_S5_AUTHORIZED",
        "MODEL_TRAINING_EXECUTED",
        "BACKTEST_EXECUTED",
        "SCORING_EXECUTED",
        "PRIVATE_HARVEST_ROW_READ",
        "VALIDATION_ACTUAL_LABEL_READ",
    ):
        assert s2[key] is False
    assert s2["GDD_INCREMENTAL_VALUE"] == "NOT_EVALUATED"
    assert s2["VALIDATION_BOUNDARY_AUTHORITY_BINDING"] == "PASS"
    assert s2["FOLD_A_VALIDATION_BUSINESS_START"] == "2024-07-01"
    assert s2["FOLD_A_VALIDATION_BUSINESS_END"] == "2025-04-15"
    assert s2["FOLD_B_VALIDATION_BUSINESS_START"] == "2025-07-22"
    assert s2["FOLD_B_VALIDATION_BUSINESS_END"] == "2026-04-15"
    for key in (
        "FOLD_B_HARDCODED_JULY1_USED",
        "BOUNDARY_CORRECTION_CHANGED_ROW_UNIVERSE",
        "BOUNDARY_CORRECTION_CHANGED_GDD_IDENTITIES",
    ):
        assert s2[key] is False
    assert s2["manifest"]["ineligible_context_count"] == 0
    expected_mtime_ns = {
        "era5": 1789447418494479417,
        "fold_a": 1790069672201429844,
        "fold_b": 1790069714609488545,
    }
    for phase in ("before", "after"):
        identities = s2["source_immutability"][phase]
        assert {key: value["mtime_ns"] for key, value in identities.items()} == expected_mtime_ns
    for name in ("fold_a", "fold_b"):
        legacy = s2["folds"][name]["legacy"]
        assert legacy["direct_self_hash_valid"] is False
        assert legacy["legacy_compatibility_hash_valid"] is True
        assert legacy["public_evidence_parity"] == "PASS"
        for split in ("train", "validation"):
            c = s2["folds"][name][split]
            assert c["common_row_count"] == c["original_row_count"]
            assert c["common_row_keys_hash"] == c["original_row_keys_hash"]
