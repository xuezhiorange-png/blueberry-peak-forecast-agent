"""Synthetic-only S2 tests; no database or archive credentials."""

from datetime import date
from decimal import Decimal

import pytest

from backend.app.area_yield.v014_future_weather_features import REQUIRED_FIELDS
from backend.app.area_yield.v015_materialization import (
    base_vectors,
    daily_index,
    label_vector,
    source_quality,
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


def test_source_descriptive_audit_preserves_states_and_missing():
    from copy import deepcopy

    rows = daily()
    rows[0].update(record_state="UNKNOWN", quantity_kg=None)
    rows[1].update(record_state="PARTIAL_SUBTOTAL", quantity_kg="1000000")
    rows[2].update(record_state="REAL_ZERO", quantity_kg="1")
    rows[3].update(quantity_kg="NaN")
    rows[4].update(quantity_kg="-1")
    before = deepcopy(rows)
    result = source_quality(rows)["2023-2024"]
    assert rows == before
    assert result["record_count"] == 15
    assert result["incomplete_state_count"] == 2
    assert result["complete_quantity_missing_count"] == 0
    assert result["negative_count"] == 1
    assert result["nonfinite_count"] == 1
    assert result["real_zero_mismatch_count"] == 1


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


@pytest.mark.parametrize("mutation", ["D1", "D7", "D15", "TARGET_SOURCE", "SEASON_FINAL_SOURCE"])
def test_future_labels_leave_complete_feature_artifact_unchanged(tmp_path, mutation):
    from copy import deepcopy

    from backend.app.area_yield.v015_materialization import read_feature_artifact
    from scripts.materialize_v0_15_s2_dataset import (
        feature_row,
        immutable,
        label_row,
        pairing_record,
        sha,
    )

    row = origin()
    row["forecast_origin"] = "2024-03-31T17:00:00+08:00"
    row["target_dates"] = [f"2024-04-{i:02}" for i in range(1, 16)]
    records = daily()
    for record, day in zip(records, row["target_dates"], strict=True):
        record["date"] = day
    vector = base_vectors(row, Decimal("394"))
    common = {"row_key": row["row_hash"], "split": "TRAIN"}
    lineage = ["1" * 64, "2" * 64, "3" * 64]
    before_f = feature_row(common, vector, lineage)
    before_l = label_row(common, label_vector(row, daily_index(records)), lineage, digest(vector))
    changed = deepcopy(records)
    if mutation.startswith("D"):
        changed[int(mutation[1:]) - 1]["quantity_kg"] = "999"
    else:
        # April 15 is both D15 and the frozen business-season final day.
        changed[6 if mutation == "TARGET_SOURCE" else -1]["source_hashes"] = ["f" * 64]
    after_f = feature_row(common, vector, lineage)
    after_l = label_row(common, label_vector(row, daily_index(changed)), lineage, digest(vector))
    assert before_f["feature_hash"] == after_f["feature_hash"]
    assert before_f["row_hash"] == after_f["row_hash"]
    assert before_l["label_hash"] != after_l["label_hash"]
    assert "label_hash" not in after_f
    assert set(after_f["source_hashes"]) == set(lineage)
    before_path = tmp_path / "before" / "feature_zone" / "data.json"
    after_path = tmp_path / "after" / "feature_zone" / "data.json"
    immutable(before_path, [before_f])
    immutable(after_path, [after_f])
    assert before_path.read_bytes() == after_path.read_bytes()
    before_label = tmp_path / "before" / "label_zone" / "data.json"
    after_label = tmp_path / "after" / "label_zone" / "data.json"
    immutable(before_label, [before_l])
    immutable(after_label, [after_l])
    assert before_label.read_bytes() != after_label.read_bytes()
    audit = tmp_path / "after" / "audit" / "feature-label-pairing.json"
    pair = pairing_record(after_f, after_l)
    immutable(audit, [pair])
    assert pair["pair_hash"] == digest({k: v for k, v in pair.items() if k != "pair_hash"})
    expected = sha(after_path.read_bytes())
    assert "label_hash" not in read_feature_artifact(after_path, expected_file_sha256=expected)[0]
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        read_feature_artifact(audit, expected_file_sha256=sha(audit.read_bytes()))
    with pytest.raises(ValueError, match="FEATURE_ARTIFACT_HASH_DRIFT"):
        read_feature_artifact(after_path, expected_file_sha256="0" * 64)


def test_feature_reader_rejects_legacy_label_hash(tmp_path):
    from backend.app.area_yield.v015_materialization import read_feature_artifact
    from scripts.materialize_v0_15_s2_dataset import immutable, sha

    path = tmp_path / "feature_zone" / "data.json"
    immutable(path, [{"base10": base_vectors(origin(), Decimal("394")), "label_hash": "a" * 64}])
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        read_feature_artifact(path, expected_file_sha256=sha(path.read_bytes()))


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
    "payload",
    [
        {"quantity_kg": "1"},
        {"path": "/private/tmp/a"},
        {"latitude": 0},
        {"d1_actual": 1},
        {"labels": {"h7_total": "1"}},
        {"base10": ["1"]},
        {"weather8": ["1"]},
        {"single_day_peak_quantity": "1"},
        {"api_key": "synthetic"},
        {"connection": "postgres://synthetic"},
        {"/home/operator/private": "hash"},
    ],
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
        read_feature_artifact(label, expected_file_sha256="0" * 64)
    feature = tmp_path / "feature_zone" / "data.json"
    immutable(feature, [{"base10": base_vectors(origin(), Decimal("394"))}])
    from scripts.materialize_v0_15_s2_dataset import sha

    assert len(read_feature_artifact(feature, expected_file_sha256=sha(feature.read_bytes()))) == 1
    link = feature.parent / "symlink.json"
    link.symlink_to(label)
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        read_feature_artifact(link, expected_file_sha256="0" * 64)


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


def test_frozen_rowset_and_weather_train_zero():
    from pathlib import Path

    import scripts.materialize_v0_15_s2_dataset as module

    values, _ = module.sources(Path(module.__file__).resolve().parents[1])
    rows = values["research-forecast-origin-universe.json"]["rows"]
    base = [r for r in rows if r["base_research_eligible"]]
    weather = [r for r in rows if r["weather_comparable_eligible"]]
    assert len(base) == len({r["row_hash"] for r in base}) == 20020
    assert len(weather) == 12925
    assert len({(r["base_id"], r["season"], r["selected_run_id"]) for r in weather}) == 12925
    assert not any(r["temporal_role"] == "TRAIN" for r in weather)
    assert {r["row_hash"] for r in weather} <= {r["row_hash"] for r in base}
    assert {r["season"] for r in base} == {"2023-2024", "2024-2025", "2025-2026"}


@pytest.mark.parametrize("drift", ["missing_field", "run", "location", "late_publication"])
def test_weather_cache_provenance_fail_closed(drift):
    from backend.app.area_yield.v015_materialization import validate_weather_cache

    cache = {
        "provider": "ECMWF_IFS_OPEN_DATA",
        "status": "COMPLETE",
        "run_id": "20250201000000",
        "location_authority_sha256": (
            "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
        ),
        "raw_receipts": [
            {
                "step": s,
                "parameter": p,
                "raw_sha256": "a" * 64,
                "raw_size": 100,
                "metadata": {
                    "dataDate": 20250201,
                    "dataTime": 0,
                    "shortName": p,
                    "endStep": s,
                    "marsClass": "od",
                    "marsStream": "oper",
                    "marsType": "fc",
                },
            }
            for s, p in REQUIRED_FIELDS
        ],
    }
    row = {"selected_run_id": cache["run_id"], "forecast_origin": "2025-02-01T17:00:00+08:00"}
    cache["cache_hash"] = digest(cache)
    validate_weather_cache(cache, row)
    if drift == "missing_field":
        cache["raw_receipts"].pop()
    elif drift == "run":
        row["selected_run_id"] = "20250131000000"
    elif drift == "location":
        cache["location_authority_sha256"] = "b" * 64
    else:
        row["forecast_origin"] = "2025-02-01T15:00:00+08:00"
    cache["cache_hash"] = digest({k: v for k, v in cache.items() if k != "cache_hash"})
    with pytest.raises(ValueError):
        validate_weather_cache(cache, row)
