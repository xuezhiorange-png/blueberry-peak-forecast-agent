"""Static public S1 contract checks; no feature generation or model execution."""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-13/evidence/v0.13-s1-gdd-scientific-definition-freeze.json"
SOURCES = ROOT / "docs/v0-13/evidence/v0.13-s1-gdd-source-register.json"
pytestmark = pytest.mark.contract


def contract() -> dict[str, Any]:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_unique_definition_and_research_not_physiology() -> None:
    c = contract()
    assert c["VERSION"] == "0.13.0"
    assert c["STAGE"] == "V0.13-S1"
    assert c["GDD_DEFINITION_SELECTED"] is True
    assert c["GDD_DEFINITION_ID"] == "V0_13_GDD_7C_SIMPLE_MEAN_R1"
    assert c["GDD_BASE_TEMPERATURE_C"] == "7.0"
    assert c["GDD_THRESHOLD_ROLE"] == (
        "PREDECLARED_HIGHBUSH_SHB_RESEARCH_HEAT_ACCUMULATION_THRESHOLD"
    )
    assert c["GDD_IS_UNIVERSAL_PHYSIOLOGY"] is False
    assert c["7C_IS_UNIVERSAL_BLUEBERRY_PHYSIOLOGICAL_BASE"] is False
    assert c["GDD_SWEEP_AUTHORIZED"] is False
    assert c["NO_RESULT_VISIBILITY"] is True
    assert c["GDD_ADDS_NEW_FEATURE_REPRESENTATION"] is True
    assert c["GDD_ADDS_NEW_RAW_INFORMATION"] is False
    assert c["BUSINESS_VARIETY_BOTANICAL_TYPE_AUTHORITY"] == "ABSENT"
    assert c["BUSINESS_VARIETY_TYPE_NOT_SILENTLY_INFERRED"] is True


def test_formula_clipping_and_precision_are_not_implicit() -> None:
    c = contract()
    assert c["DAILY_TEMPERATURE_FORMULA"] == "(TMAX_C + TMIN_C) / 2"
    assert c["DAILY_GDD_FORMULA"] == "max(0, DAILY_MEAN_C - 7.0)"
    assert c["LOWER_CLIP_POLICY"] == "CLIP_FINAL_DAILY_GDD_AT_ZERO"
    assert c["TMIN_PRECLIP_ALLOWED"] is False
    assert c["UPPER_CLIP_POLICY"] == "NONE"
    assert c["NO_UPPER_CAP_IMPLIES_UNLIMITED_BIOLOGICAL_BENEFIT"] is False
    assert c["SOURCE_TEMPERATURE_FIELDS"] == [
        "sampled_local_day_tmax_c",
        "sampled_local_day_tmin_c",
    ]
    assert c["LOCAL_DAY_TIMEZONE"] == "Asia/Shanghai"
    assert c["precision"] == {
        "source": "ACCEPTED_FROZEN_ERA5_DAILY_DECIMALS",
        "intermediate": "Decimal",
        "daily_gdd": "Decimal",
        "decimal_context_precision_minimum": 50,
        "output_decimal_places": 12,
        "rounding": "ROUND_HALF_EVEN",
        "round_once_after_window_sum": True,
        "early_daily_rounding_allowed": False,
        "units": "degree_C_days",
    }


def test_rolling_windows_missingness_and_no_future_information() -> None:
    c = contract()
    assert c["ROLLING_GDD_WINDOWS"] == [7, 14, 30]
    assert c["feature_ids"] == ["GDD_W7", "GDD_W14", "GDD_W30"]
    assert c["window_start"] == "FORECAST_ORIGIN_LOCAL_DATE_MINUS_WINDOW_DAYS"
    assert c["window_end"] == "FORECAST_ORIGIN_LOCAL_DATE_MINUS_1"
    assert c["WINDOW_BOUNDARIES_INCLUSIVE"] is True
    assert c["FORECAST_ORIGIN_DAY_EXCLUDED"] is True
    assert c["MAX_GDD_SOURCE_DATE"] == "FORECAST_ORIGIN_MINUS_1_DAY"
    assert c["FUTURE_REALIZED_TEMPERATURE_ALLOWED"] is False
    assert c["SEASON_TO_DATE_ENABLED"] is False
    assert c["PHENOLOGY_ANCHORED_GDD_IN_SCOPE"] is False
    assert c["FLOWERING_TO_HARVEST_CLAIM_ALLOWED"] is False
    assert c["MISSING_DAY_POLICY"] == "FAIL_CLOSED"
    assert c["MISSING_ROW_RESULT"] == "GDD_FEATURE_ROW_NOT_ELIGIBLE"
    assert c["IMPUTATION_ALLOWED"] is False
    assert c["COMMON_COMPARABLE_COHORT_REQUIRED"] is True
    assert c["NO_MODEL_SPECIFIC_COHORT"] is True
    assert c["input_validity"] == {
        "nonfinite_or_missing_temperature": "ROW_NOT_ELIGIBLE",
        "tmax_less_than_tmin": "ROW_NOT_ELIGIBLE",
        "duplicate_or_wrong_local_day": "ROW_NOT_ELIGIBLE",
        "temperature_unit": "degrees_C",
        "kelvin_silently_accepted": False,
    }


def test_old_authorities_are_byte_preserved_and_reconciled() -> None:
    c = contract()
    for path, expected in c["frozen_authority_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert c["internal_authority"]["S016_M012_DOI"] == "10.1080/15538362.2011.619430"
    rows = {}
    path = ROOT / "docs/v0-9/s0/evidence-conflict-and-uncertainty-register-r1.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if row and row[0] in {"U009", "U014"}:
                rows[row[0]] = row
    assert "CONTEXT_DEPENDENT" in rows["U009"]
    assert "UNRESOLVED" in rows["U014"]
    assert c["internal_authority"]["NO_UNIVERSAL_BASE_OR_CEILING_TEMPERATURE_CLAIM"] is True
    assert c["S0_CONTRACT_CHANGED"] is False
    assert c["V0_12_REOPENED"] is False
    assert c["V0_12_R1_ARTIFACT_CHANGED"] is False


def test_source_fields_and_methods_difference_are_explicit() -> None:
    register = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = register["sources"]
    assert {s["SOURCE_ID"] for s in entries} == {"A", "B", "C", "D", "E"}
    required = {
        "SOURCE_ID",
        "TITLE",
        "YEAR",
        "BLUEBERRY_TYPE",
        "CULTIVAR",
        "TARGET_STAGE",
        "GDD_BASE_C",
        "UPPER_CAP_C",
        "FORMULA",
        "ACCUMULATION_START",
        "PEER_REVIEW_STATUS",
        "DIRECT_APPLICABILITY",
        "LIMITATION",
        "URL",
        "VERIFICATION_SCOPE",
    }
    for s in entries:
        assert required <= s.keys()
        assert s["PEER_REVIEW_STATUS"] == "PEER_REVIEWED"
        assert s["URL"].startswith("https://")
        assert s["LIMITATION"]
    b = next(s for s in entries if s["SOURCE_ID"] == "B")
    assert b["GDD_BASE_C"] == "7"
    assert b["TMIN_PRECLIP_IN_SOURCE"] is True
    assert b["EXACT_S1_FORMULA_REPLICATION"] is False
    d = next(s for s in entries if s["SOURCE_ID"] == "D")
    assert d["TIME_RESOLUTION"] == "MONTHLY"
    assert d["EXACT_S1_FORMULA_REPLICATION"] is False
    assert register["UNREPORTED_FIELDS_ARE_NOT_INFERRED"] is True


@pytest.mark.parametrize("stage", ["S2", "S3", "S4", "S5"])
def test_only_s1_authorized(stage: str) -> None:
    c = contract()
    assert c["V0_13_S1_AUTHORIZED"] is True
    assert c["V0_13_S1_COMPLETE"] is True
    assert c[f"V0_13_{stage}_AUTHORIZED"] is False


@pytest.mark.parametrize(
    "field",
    [
        "MODEL_TRAINING_EXECUTED",
        "BACKTEST_EXECUTED",
        "SCORING_EXECUTED",
        "GDD_FEATURE_GENERATION_EXECUTED",
        "PRIVATE_WEATHER_DATA_READ",
        "PRIVATE_HARVEST_ROW_READ",
        "REAL_PROSPECTIVE_ENABLED",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "V0_13_VERSION_COMPLETE",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "TAG_CREATED",
        "RELEASE_CREATED",
    ],
)
def test_execution_and_downstream_gates_remain_closed(field: str) -> None:
    assert contract()[field] is False
