"""Synthetic date-bound Harvest State tests: no credentials or real labels."""

from copy import deepcopy
from datetime import date, timedelta

import pytest

from backend.app.area_yield.v015_harvest_state import (
    FEATURES,
    build_row,
    history_index,
    policy,
    read_artifact,
    target_vectors,
)
from backend.app.area_yield.v015_research_cohort import canonical, digest


def records():
    return [
        {
            "base_id": "synthetic",
            "season": "2023-2024",
            "date": (date(2023, 7, 1) + timedelta(days=i)).isoformat(),
            "quantity_kg": "1",
            "record_state": "VALID_OBSERVED",
            "logical_record_id": f"synthetic-{i}",
            "source_hashes": ["a" * 64],
            "conflict_status": ["NONE"],
        }
        for i in range(290)
    ]


def origin(day="2023-07-29"):
    return {
        "row_key": "b" * 64,
        "base_id": "synthetic",
        "season": "2023-2024",
        "split": "TRAIN",
        "forecast_origin": day + "T17:00:00+08:00",
    }


def make(rows=None, day="2023-07-29"):
    return build_row(origin(day), history_index(records() if rows is None else rows))


def test_exact_definition_and_s3_boundary():
    assert FEATURES == (
        "past_7d_harvest_kg",
        "past_14d_harvest_kg",
        "past_28d_harvest_kg",
        "season_to_date_harvest_kg",
    )
    assert policy()["s3_metrics_direct_comparison_allowed"] is False
    assert policy()["model_training_executed"] is False
    assert policy()["strict_pit"] is False


def test_windows_and_same_vector_for_fifteen_targets():
    row = make()
    assert list(row["harvest_state_v1"].values()) == ["7", "14", "28", "28"]
    assert row["harvest_state_complete"]
    assert len(target_vectors(row)) == 15
    assert all(v == row["harvest_state_v1"] for v in target_vectors(row))


@pytest.mark.parametrize("elapsed", [0, 6, 7, 13, 14, 27, 28])
def test_season_boundary_and_calendar_completeness(elapsed):
    day = (date(2023, 7, 1) + timedelta(days=elapsed)).isoformat()
    row = make(day=day)
    for n in (7, 14, 28):
        assert row["audit"][f"past_{n}d_missing_count"] == max(0, n - elapsed)
        assert row["harvest_state_v1"][f"past_{n}d_harvest_kg"] == (
            str(n) if elapsed >= n else None
        )
    assert row["audit"]["season_to_date_missing_count"] == 0
    assert row["harvest_state_v1"]["season_to_date_harvest_kg"] == str(elapsed)
    assert row["harvest_state_complete"] == (elapsed >= 28)


@pytest.mark.parametrize(
    "state", ["UNKNOWN", "PARTIAL_SUBTOTAL", "MISSING", "CONFLICTING", "INVALID"]
)
def test_bad_state_never_becomes_complete_or_zero(state):
    rows = records()
    rows[27]["record_state"] = state
    row = make(rows)
    assert all(v is None for v in row["harvest_state_v1"].values())
    assert all(v == 1 for v in row["audit"].values())
    assert not row["harvest_state_complete"]


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "bad", None])
def test_invalid_quantity_fail_closed(value):
    rows = records()
    rows[27]["quantity_kg"] = value
    row = make(rows)
    assert not row["harvest_state_complete"]
    assert "INVALID_EXCLUDE" in row["exclusion_reasons"]


def test_real_zero_exact_and_extreme_kept():
    rows = records()
    rows[27].update(record_state="REAL_ZERO", quantity_kg="0")
    assert make(rows)["harvest_state_v1"]["past_7d_harvest_kg"] == "6"
    rows[27]["quantity_kg"] = "1"
    assert not make(rows)["harvest_state_complete"]
    rows[27].update(record_state="VALID_OBSERVED", quantity_kg="999999999999")
    assert make(rows)["harvest_state_complete"]


def test_missing_day_is_not_twenty_seven_day_window():
    rows = records()
    del rows[10]
    row = make(rows)
    assert row["harvest_state_v1"]["past_28d_harvest_kg"] is None
    assert row["audit"]["past_28d_missing_count"] == 1


def test_duplicate_and_current_envelope_rejected():
    rows = records()
    with pytest.raises(ValueError, match="DUPLICATE"):
        history_index(rows + [rows[0]])
    rows.append({"season": "2026-2027"})
    with pytest.raises(ValueError, match="FAIL_CURRENT_SEASON_ACTUAL_PRESENT"):
        history_index(rows)


@pytest.mark.parametrize("offset", [0, 1, 7, 15, 261])
def test_current_future_quantity_and_source_mutations_leave_entire_bytes_unchanged(offset):
    rows = records()
    before = make(rows)
    changed = deepcopy(rows)
    changed[28 + offset].update(quantity_kg="999999", source_hashes=["c" * 64])
    after = make(changed)
    assert before["harvest_state_feature_hash"] == after["harvest_state_feature_hash"]
    assert before["row_hash"] == after["row_hash"]
    assert canonical([before]) == canonical([after])


def test_future_quantity_is_never_inspected():
    rows = records()
    rows[28]["quantity_kg"] = object()
    rows[28]["source_hashes"] = object()
    assert make(rows)["harvest_state_complete"]


def test_past_day_positive_sensitivity():
    rows = records()
    before = make(rows)
    rows[27]["quantity_kg"] = "2"
    after = make(rows)
    assert list(after["harvest_state_v1"].values()) == ["8", "15", "29", "29"]
    assert after["harvest_state_feature_hash"] != before["harvest_state_feature_hash"]
    assert after["row_hash"] != before["row_hash"]


@pytest.mark.parametrize("mutation", ["lineage", "conflict", "identity"])
def test_broken_source_identity_and_conflict(mutation):
    rows = records()
    if mutation == "lineage":
        rows[27]["source_hashes"] = []
    elif mutation == "conflict":
        rows[27]["conflict_status"] = ["KEY_MISMATCH"]
    else:
        rows[27]["base_id"] = "other"
    assert not make(rows)["harvest_state_complete"]


def test_origin_time_split_and_season_guards():
    row = origin()
    row["split"] = "VALIDATION"
    with pytest.raises(ValueError, match="SPLIT"):
        build_row(row, history_index(records()))
    row = origin("2024-04-16")
    with pytest.raises(ValueError, match="OUTSIDE"):
        build_row(row, history_index(records()))


def test_deterministic_private_reader_and_label_zone_denial(tmp_path):
    row = make()
    raw = canonical([row])
    assert raw == canonical([make()])
    path = tmp_path / "feature_zone" / "harvest.json"
    path.parent.mkdir()
    path.write_bytes(raw)
    assert read_artifact(path, digest([row]))[0]["harvest_state_v1"] == row["harvest_state_v1"]
    label_path = tmp_path / "label_zone" / "labels.json"
    label_path.parent.mkdir()
    label_path.write_bytes(raw)
    with pytest.raises(ValueError, match="ZONE"):
        read_artifact(label_path, digest([row]))
    row["label_hash"] = "c" * 64
    path.write_bytes(canonical([row]))
    with pytest.raises(ValueError, match="SCHEMA"):
        read_artifact(path, digest([row]))


def test_common_rowset_keeps_base10_and_excludes_only_harvest_state():
    from scripts.materialize_v0_15_s4_harvest_state import common_rows

    complete, early = make(), make(day="2023-07-01")
    early["row_key"] = "d" * 64
    rows = [complete, early]
    before = canonical(rows)
    common = common_rows(rows)
    assert canonical(rows) == before
    assert common == [{"row_key": "b" * 64, "split": "TRAIN", "target_rows": 15}]
    assert common == common_rows(list(reversed(rows)))
    with pytest.raises(ValueError, match="DUPLICATE"):
        common_rows([complete, complete])


def test_decimal_no_floating_point_accumulation():
    rows = records()
    for row in rows:
        row["quantity_kg"] = "0.1"
    assert make(rows)["harvest_state_v1"]["past_28d_harvest_kg"] == "2.8"


def test_public_privacy_guard_and_model_schema():
    from backend.app.area_yield.v015_benchmark_custody import validate_public

    validate_public(policy())
    with pytest.raises(ValueError, match="PRIVACY"):
        validate_public(make())
    assert set(make()["harvest_state_v1"]) == set(FEATURES)
    assert len(make()["audit"]) == 4


def test_existing_source_quality_errors_do_not_modify_source():
    rows = records()
    before = deepcopy(rows)
    make(rows)
    assert rows == before
    rows[0]["date"] = "2023-06-30"
    with pytest.raises(ValueError, match="OUTSIDE"):
        history_index(rows)


def test_real_operator_mutation_proof_on_synthetic_history():
    from scripts.materialize_v0_15_s4_harvest_state import mutation_checks

    result = mutation_checks(origin(), history_index(records()))
    assert len(result) == 7
    assert result["D_MINUS_1"]["all_four_values_changed"]
    assert result["ORIGIN_DAY"]["artifact_bytes_unchanged"]


def test_fresh_process_replay_verifier_detects_drift(tmp_path):
    from scripts.materialize_v0_15_s4_harvest_state import replay

    first, second, public = (tmp_path / name for name in ("first", "second", "public"))
    for root in (first, second):
        root.mkdir()
        (root / "sample.json").write_bytes(canonical([make()]))
    public.mkdir()
    (public / "manifest.json").write_bytes(canonical({"manifest_hash": "a" * 64}))
    replay(first, second, public)
    assert (public / "deterministic-replay-report.json").exists()
    (second / "sample.json").write_bytes(canonical([]))
    with pytest.raises(ValueError, match="REPLAY_FAILED"):
        replay(first, second, public)
