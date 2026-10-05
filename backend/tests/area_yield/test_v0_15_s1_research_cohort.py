"""Offline research-boundary tests; no private labels or network."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield.v015_research_cohort import (
    admit_base,
    assert_same_rowset,
    digest,
    past_features,
    split_roles,
    target_dates,
)
from scripts.freeze_v0_15_s1_research_cohort import (
    FEATURE_HASH,
    PRECIP_HASH,
    PUBLICATION_HASH,
    derive,
    load_sources,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def reports() -> dict:
    return derive(Path(__file__).resolve().parents[3])


def source_row() -> dict:
    return {
        "season": "2024-2025",
        "identity_status": "ACCEPTED_RETROSPECTIVE",
        "area_pit_tier": "PIT_EVIDENCE_TIER_C_RETROSPECTIVE",
        "season_status": "FROZEN_BUSINESS_WINDOW_NOT_FULL_YEAR",
        "target_start_date": "2024-07-01",
        "target_end_date": "2025-04-15",
        "logical_record_count": 289,
        "unknown_count": 0,
        "partial_subtotal_count": 0,
        "missing_count": 0,
        "conflict_count": 0,
        "invalid_count": 0,
    }


def test_retrospective_admission_not_strict() -> None:
    assert admit_base(source_row()) == (True, [])


@pytest.mark.parametrize(
    "field",
    ["unknown_count", "partial_subtotal_count", "missing_count", "conflict_count", "invalid_count"],
)
def test_bad_states_are_not_zero_or_complete(field: str) -> None:
    row = source_row()
    row[field] = 1
    assert not admit_base(row)[0]


def test_unresolved_identity_rejected() -> None:
    row = source_row()
    row["identity_status"] = "UNRESOLVED"
    assert not admit_base(row)[0]


def test_current_season_rejected() -> None:
    row = source_row()
    row["season"] = "2026-2027"
    with pytest.raises(ValueError, match="UNAUTHORIZED_SEASON"):
        admit_base(row)


def test_chronology_and_exposed_oot() -> None:
    assert split_roles(["2025-2026", "2023-2024", "2024-2025"]) == {
        "2023-2024": "TRAIN",
        "2024-2025": "VALIDATION",
        "2025-2026": "EXPOSED_OOT",
    }


def test_two_seasons_cannot_fake_three_splits() -> None:
    with pytest.raises(ValueError, match="THREE_SEASONS_REQUIRED"):
        split_roles(["2024-2025", "2025-2026"])


def test_h15_excludes_tail_and_current_actual() -> None:
    assert target_dates("2026-03-31T17:00:00+08:00", "2026-04-15")[-1] == "2026-04-15"
    assert target_dates("2026-04-01T17:00:00+08:00", "2026-04-15") == []


def past_rows() -> list[dict]:
    return [
        {
            "base_id": "b",
            "season": "2024-2025",
            "business_date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
            "state": "VALID_OBSERVED",
            "quantity_kg": Decimal(i + 1),
            "zone": "FEATURE_ZONE",
        }
        for i in range(31)
    ]


@pytest.mark.parametrize("day", [1, 7, 15, 73])
def test_future_actual_mutation_does_not_change_features(day: int) -> None:
    origin = "2025-02-01T17:00:00+08:00"
    rows = past_rows()
    before = digest(past_features(rows, origin, "b", "2024-2025", "2025-01-01"))
    future = {
        "base_id": "b",
        "season": "2024-2025",
        "business_date": (date(2025, 2, 1) + timedelta(days=day)).isoformat(),
        "state": "VALID_OBSERVED",
        "quantity_kg": Decimal("999999"),
        "zone": "LABEL_ZONE",
    }
    for value in (Decimal(0), Decimal("123456789"), Decimal("NaN")):
        future["quantity_kg"] = value
        assert before == digest(
            past_features(rows + [future], origin, "b", "2024-2025", "2025-01-01")
        )


def test_current_business_day_is_not_known_complete_at_1700() -> None:
    rows = past_rows()
    current = {**rows[-1], "business_date": "2025-02-01", "quantity_kg": Decimal("999999")}
    assert past_features(
        rows, "2025-02-01T17:00:00+08:00", "b", "2024-2025", "2025-01-01"
    ) == past_features(
        rows + [current], "2025-02-01T17:00:00+08:00", "b", "2024-2025", "2025-01-01"
    )


def test_unknown_past_feature_is_masked_not_zero() -> None:
    rows = past_rows()
    rows[-1].update(state="UNKNOWN", quantity_kg=None)
    result = past_features(rows, "2025-02-01T17:00:00+08:00", "b", "2024-2025", "2025-01-01")
    assert result["past_7d_kg"] is None
    assert result["past_7d_missing_count"] == 1


def test_label_zone_cannot_supply_past_feature() -> None:
    rows = past_rows()
    rows[0]["zone"] = "LABEL_ZONE"
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        past_features(rows, "2025-02-01T17:00:00+08:00", "b", "2024-2025", "2025-01-01")


def test_different_algorithm_rowsets_rejected() -> None:
    assert_same_rowset({"Ridge": ["a", "b"], "CatBoost": ["a", "b"], "LightGBM": ["a", "b"]})
    with pytest.raises(ValueError, match="COMMON_ROWSET_MISMATCH"):
        assert_same_rowset({"Ridge": ["a", "b"], "CatBoost": ["a"]})


def test_duplicate_comparison_row_rejected() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_COMPARISON_ROW"):
        assert_same_rowset({"Ridge": ["a", "a"]})


def test_committed_source_admission_and_origin_counts(reports: dict) -> None:
    summary = reports["s1-readiness-recommendation.json"]
    assert summary["total_base_season_count"] == 117
    assert summary["base_research_base_season_count"] == 76
    assert summary["weather_comparable_base_season_count"] == 61
    assert summary["total_research_forecast_origin_count"] == 20020
    assert summary["weather_comparable_forecast_origin_count"] == 12925
    assert not summary["weather_benchmark_training_ready"]


def test_source_weather_policy_inherited_exactly(reports: dict) -> None:
    policy = reports["retrospective-research-admission-policy.json"]
    assert policy["publication_policy_hash"] == PUBLICATION_HASH
    assert policy["precipitation_policy_hash"] == PRECIP_HASH
    assert policy["feature_policy_hash"] == FEATURE_HASH
    assert policy["precipitation_threshold_mm"] == "0.08"
    assert not policy["strict_pit"]
    assert not policy["prospective_claim_allowed"]


def test_origin_and_target_labels_never_cross_splits(reports: dict) -> None:
    origin_roles: dict[tuple, str] = {}
    label_roles: dict[tuple, str] = {}
    base_roles: dict[tuple, str] = {}
    for row in reports["research-forecast-origin-universe.json"]["rows"]:
        role = row["temporal_role"]
        base_key = row["base_id"], row["season"]
        key = (*base_key, row["forecast_origin"])
        assert key not in origin_roles
        origin_roles[key] = role
        assert base_roles.setdefault(base_key, role) == role
        for day in row["target_dates"]:
            assert label_roles.setdefault((*base_key, day), role) == role
        assert digest({k: v for k, v in row.items() if k != "row_hash"}) == row["row_hash"]
        assert row["season"] != "2026-2027"


def test_exposure_unknown_is_not_unexposed(reports: dict) -> None:
    rows = reports["benchmark-exposure-ledger.json"]["rows"]
    assert len(rows) == 117
    assert all(r["exposure_status"] == "KNOWN_EXPOSED" for r in rows if r["season"] == "2025-2026")
    assert all(
        r["exposure_status"] == "UNKNOWN_EXPOSURE" for r in rows if r["season"] != "2025-2026"
    )
    assert not any(r["exposure_status"] == "KNOWN_UNEXPOSED" for r in rows)


def test_common_rowset_exact_order_and_masks(reports: dict) -> None:
    rows = reports["research-forecast-origin-universe.json"]["rows"]
    common = reports["common-comparison-rowset-contract.json"]
    expected = [r["row_hash"] for r in rows if r["weather_comparable_eligible"]]
    assert common["ordered_row_hashes"] == expected
    assert common["rowset_hash"] == digest(expected)
    assert_same_rowset({model: expected for model in common["models"]})
    assert all(
        r["label_status"] == "COMPLETE" and r["weather_available"]
        for r in rows
        if r["weather_comparable_eligible"]
    )


def test_two_fresh_derivations_are_byte_equal(reports: dict) -> None:
    from backend.app.area_yield.v015_research_cohort import canonical

    replay = derive(Path(__file__).resolve().parents[3])
    assert set(replay) == set(reports)
    for name in reports:
        assert canonical(reports[name]) == canonical(replay[name])


def test_manifest_bindings_and_no_actual_values(reports: dict) -> None:
    import hashlib

    from backend.app.area_yield.v015_research_cohort import canonical

    manifest = reports["manifest.json"]
    for member in manifest["members"]:
        content = canonical(reports[member["name"]])
        assert hashlib.sha256(content).hexdigest() == member["sha256"]
        assert len(content) == member["size"]
    rows = reports["research-forecast-origin-universe.json"]["rows"]
    assert all("quantity_kg" not in row for row in rows)


@pytest.mark.parametrize("origin", ["2025-02-01T17:00:00", "2025-02-01T18:00:00+08:00"])
def test_timezone_and_cutoff_fail_closed(origin: str) -> None:
    with pytest.raises(ValueError):
        target_dates(origin, "2025-04-15")


def test_invalid_zero_claim_and_duplicate_past_day() -> None:
    rows = past_rows()
    rows[0]["state"] = "REAL_ZERO"
    with pytest.raises(ValueError, match="INVALID_COMPLETE_QUANTITY"):
        past_features(rows, "2025-02-01T17:00:00+08:00", "b", "2024-2025", "2025-01-01")
    rows = past_rows()
    with pytest.raises(ValueError, match="DUPLICATE_PAST_DAY"):
        past_features(rows + [rows[0]], "2025-02-01T17:00:00+08:00", "b", "2024-2025", "2025-01-01")


def test_source_manifest_drift_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "docs/v0-15/evidence/business-data-closure-r1"
    parent.mkdir(parents=True)
    (parent / "report-manifest.json").write_text("{}\n")
    with pytest.raises(ValueError, match="S0_MANIFEST_DRIFT"):
        load_sources(tmp_path)


def test_cli_has_no_actual_or_training_capability() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.freeze_v0_15_s1_research_cohort", "--actual", "denied"],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "error" in result.stderr
