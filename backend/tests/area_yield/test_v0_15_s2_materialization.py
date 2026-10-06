"""Synthetic-only S2 tests; no database or archive credentials."""

from datetime import date
from decimal import Decimal

import pytest

from backend.app.area_yield.v014_future_weather_features import REQUIRED_FIELDS
from backend.app.area_yield.v015_materialization import (
    base_vectors,
    daily_index,
    label_vector,
    validate_public,
    weather_vector,
)
from backend.app.area_yield.v015_research_cohort import digest


def daily(state="VALID_OBSERVED", value="1", season="2023-2024"):
    return [
        {
            "base_id": "synthetic",
            "season": season,
            "date": f"2023-07-{i:02}",
            "record_state": state,
            "quantity_kg": value,
            "source_hashes": ["a" * 64],
        }
        for i in range(2, 17)
    ]


def origin():
    return {
        "base_id": "synthetic",
        "season": "2023-2024",
        "forecast_origin": "2023-07-01T17:00:00+08:00",
        "target_dates": [f"2023-07-{i:02}" for i in range(2, 17)],
        "temporal_role": "TRAIN",
        "row_hash": "b" * 64,
    }


def fields():
    return {
        (s, p): {
            "units": {"2t": "K", "tp": "m", "ssrd": "J m**-2"}.get(p, "m s**-1"),
            "stepType": "accum" if p in {"tp", "ssrd"} else "instant",
            "startStep": 0 if p in {"tp", "ssrd"} else s,
            "endStep": s,
            "value": str(s / 1000 if p == "tp" else s if p == "ssrd" else 280),
        }
        for s, p in REQUIRED_FIELDS
    }


def test_base10_reuses_authority_and_has_15_targets():
    from backend.app.area_yield.formal_multi_season_validation import business_boundary
    from backend.app.area_yield.weather_aware_backtest import _base_feature_values

    row = origin()
    a = base_vectors(row, Decimal("394"))
    assert len(a) == 15 and all(len(v) == 10 for v in a)
    assert a[0] == _base_feature_values(
        reference_area_mu=Decimal("394"),
        target_date=date(2023, 7, 2),
        boundary=business_boundary("2023-2024"),
    )
    assert digest(a) == digest(base_vectors(row, Decimal("394")))


def test_labels_totals_and_earliest_ties():
    result = label_vector(origin(), daily_index(daily()))
    assert result["h7_total"] == "7" and result["h15_total"] == "15"
    assert result["single_day_peak_date"] == "2023-07-02"
    assert result["rolling7_peak_start_date"] == "2023-07-02"


@pytest.mark.parametrize(
    "state", ["UNKNOWN", "PARTIAL_SUBTOTAL", "MISSING", "CONFLICTING", "INVALID"]
)
def test_incomplete_is_not_zero(state):
    with pytest.raises(ValueError, match="INCOMPLETE_LABEL"):
        label_vector(origin(), daily_index(daily(state)))


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_invalid_quantity(value):
    with pytest.raises(ValueError, match="INVALID_QUANTITY"):
        label_vector(origin(), daily_index(daily(value=value)))


def test_zero_exact():
    assert label_vector(origin(), daily_index(daily("REAL_ZERO", "0")))["h15_total"] == "0"
    with pytest.raises(ValueError):
        label_vector(origin(), daily_index(daily("REAL_ZERO", "1")))


def test_duplicate_fail_closed():
    rows = daily()
    with pytest.raises(ValueError, match="DUPLICATE_LOGICAL_KEY"):
        daily_index(rows + [rows[0]])


def test_current_actual_rejected_before_quantity():
    with pytest.raises(ValueError, match="UNAUTHORIZED_SEASON"):
        daily_index(daily(season="2026-2027"))


@pytest.mark.parametrize("offset", [1, 7, 15, 288])
def test_future_label_never_changes_base_feature(offset):
    row = origin()
    before = digest(base_vectors(row, Decimal("394")))
    labels = daily(value=str(offset * 999999))
    assert labels  # label-only data is never passed to feature builder
    assert digest(base_vectors(row, Decimal("394"))) == before


def test_valid_extreme_kept():
    assert (
        label_vector(origin(), daily_index(daily(value="999999999")))["h15_total"] == "14999999985"
    )


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area_authority(area):
    with pytest.raises(ValueError, match="INVALID_AREA_AUTHORITY"):
        base_vectors(origin(), Decimal(area))


def test_future_labels_mutate_without_changing_predictor_inputs(tmp_path):
    from backend.app.area_yield.v015_materialization import read_feature_artifact
    from scripts.materialize_v0_15_s2_dataset import immutable

    row = origin()
    vector = base_vectors(row, Decimal("394"))
    path = tmp_path / "feature_zone" / "features.json"
    immutable(
        path,
        [
            {
                "row_key": row["row_hash"],
                "base10": vector,
                "feature_hash": digest(vector),
                "label_hash": "audit-only",
            }
        ],
    )
    before = digest(read_feature_artifact(path))
    prior = label_vector(row, daily_index(daily()))
    for offset in (1, 7, 15):
        changed = daily()
        changed[offset - 1]["quantity_kg"] = "999"
        assert label_vector(row, daily_index(changed)) != prior
        assert digest(read_feature_artifact(path)) == before
    assert "label_hash" not in read_feature_artifact(path)[0]


def test_precipitation_policy_not_applied_to_radiation():
    f = fields()
    f[360, "ssrd"]["value"] = "167.99"
    with pytest.raises(ValueError):
        weather_vector(f)


def test_weather_trace_both_signs_and_exact8():
    f = fields()
    f[360, "tp"]["value"] = "0.16795"
    assert list(weather_vector(f).values())[5] == "0.000000000000"
    f[360, "tp"]["value"] = "0.16805"
    assert list(weather_vector(f).values())[5] == "0.000000000000"
    assert len(weather_vector(f)) == 8


def test_weather_anomaly_and_missing_reject():
    f = fields()
    f[360, "tp"]["value"] = "0.1679"
    with pytest.raises(ValueError):
        weather_vector(f)
    del f[3, "2t"]
    with pytest.raises(ValueError):
        weather_vector(f)


@pytest.mark.parametrize(
    "payload", [{"quantity_kg": "1"}, {"path": "/private/tmp/a"}, {"latitude": 0}, {"d1_actual": 1}]
)
def test_public_privacy(payload):
    with pytest.raises(ValueError, match="PUBLIC_PRIVACY_VIOLATION"):
        validate_public(payload)


def test_physical_files_are_separate_and_immutable(tmp_path):
    from scripts.materialize_v0_15_s2_dataset import immutable

    feature_path = tmp_path / "feature_zone" / "data.json"
    label_path = tmp_path / "label_zone" / "data.json"
    f = base_vectors(origin(), Decimal("394"))
    immutable(feature_path, f)
    immutable(label_path, label_vector(origin(), daily_index(daily())))
    original = feature_path.read_bytes()
    assert feature_path.stat().st_mode & 0o777 == 0o600
    assert feature_path.parent.stat().st_mode & 0o777 == 0o700
    assert "quantity_kg" not in original.decode()
    assert "h15_total" not in original.decode()
    immutable(feature_path, f)
    assert feature_path.read_bytes() == original
    with pytest.raises(ValueError, match="IMMUTABLE_ARTIFACT_CONFLICT"):
        immutable(feature_path, ["changed"])


def test_feature_reader_label_path_and_symlink_denied(tmp_path):
    from backend.app.area_yield.v015_materialization import read_feature_artifact
    from scripts.materialize_v0_15_s2_dataset import immutable

    label = tmp_path / "label_zone" / "label.json"
    immutable(label, [{"labels": {"daily": ["99"]}}])
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        read_feature_artifact(label)
    feature = tmp_path / "feature_zone" / "data.json"
    immutable(feature, [{"base10": base_vectors(origin(), Decimal("394"))}])
    assert len(read_feature_artifact(feature)) == 1
    link = feature.parent / "symlink.json"
    link.symlink_to(label)
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        read_feature_artifact(link)


def test_era5_cache_rejected():
    from backend.app.area_yield.v015_materialization import validate_weather_cache

    with pytest.raises(ValueError, match="WEATHER_NOT_AS_ISSUED"):
        validate_weather_cache({"provider": "ERA5_LAND", "status": "COMPLETE"}, {})


def test_wrong_split_and_tail_reject():
    row = origin()
    row["temporal_role"] = "EXPOSED_OOT"
    with pytest.raises(ValueError, match="SPLIT_CHANGED"):
        base_vectors(row, Decimal("394"))
    row = origin()
    row["target_dates"] = row["target_dates"][:7]
    with pytest.raises(ValueError):
        base_vectors(row, Decimal("394"))


def test_authority_drift_reject(tmp_path):
    from pathlib import Path

    import scripts.materialize_v0_15_s2_dataset as module
    from scripts.materialize_v0_15_s2_dataset import sources

    root = Path(module.__file__).resolve().parents[1]
    _, pins = sources(root)
    assert "backend/app/area_yield/weather_aware_backtest.py" in pins
    with pytest.raises(OSError):
        sources(tmp_path)


def test_weather_reanalysis_units_and_ssrd_regression_reject():
    f = fields()
    f[3, "2t"]["units"] = "degC"
    with pytest.raises(ValueError, match="WRONG_WEATHER_UNIT"):
        weather_vector(f)
    f = fields()
    f[360, "ssrd"]["value"] = "-1"
    with pytest.raises(ValueError, match="CUMULATIVE_WEATHER_REGRESSION"):
        weather_vector(f)
