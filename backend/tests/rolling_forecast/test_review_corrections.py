"""Independent-review regressions; SYNTHETIC fixtures and no real labels."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.app.rolling_forecast import application, engine, evaluation, model_artifacts
from backend.tests.rolling_forecast.test_engine import inputs
from backend.tests.rolling_forecast.test_model_artifacts import reference
from backend.tests.rolling_forecast.training_fixture import frozen_pair


@pytest.fixture(scope="module")
def saved():
    calendar, area, origin, cutoff, rows = inputs()
    result = engine.forecast(calendar, area, origin, cutoff, rows, frozen_pair(), "RESEARCH_SHADOW")
    result["feature_snapshot"]["quantity_basis"] = "FIELD_HARVEST_WEIGHT"
    for model in result["models"].values():
        model["model_training_target_quantity_basis"] = "FIELD_HARVEST_WEIGHT"
        model["forecast_target_quantity_basis"] = "FIELD_HARVEST_WEIGHT"
        model["model_provenance"] = "SYNTHETIC_TEST_FIXTURE"
    return {
        "run_id": 1,
        "base_id": area.base_id,
        "target_season": calendar.season,
        "origin_date": str(origin),
        "result_hash": "a" * 64,
        "input": {"context_reference": "SYNTHETIC-CONTEXT"},
        "result": result,
    }


@pytest.mark.parametrize(
    "changed", ["base", "season", "model", "basis", "target", "unknown", "unknown_target"]
)
def test_noncomparable_never_contains_numeric_deltas(saved, changed):
    left, right = deepcopy(saved), deepcopy(saved)
    if changed == "base":
        right["base_id"] = "SYNTHETIC-OTHER"
    elif changed == "season":
        right["target_season"] = "2027-2028"
    elif changed == "model":
        for model in right["result"]["models"].values():
            model["model_artifact_hash"] = "b" * 64
    elif changed == "basis":
        right["result"]["feature_snapshot"]["quantity_basis"] = "INBOUND_NET_WEIGHT"
    elif changed == "target":
        for model in right["result"]["models"].values():
            model["forecast_target_quantity_basis"] = "RECORDED_INBOUND_WEIGHT"
    elif changed == "unknown":
        left["result"]["feature_snapshot"]["quantity_basis"] = None
        right["result"]["feature_snapshot"]["quantity_basis"] = None
    else:
        for run in (left, right):
            for model in run["result"]["models"].values():
                model["forecast_target_quantity_basis"] = None
                model["model_training_target_quantity_basis"] = None
    for value in application.compare(left, right)["models"].values():
        assert value["status"] == "NOT_COMPARABLE"
        assert "windows" not in value and "common_target_daily_delta_kg" not in value
        assert value["reasons"]


def test_incomplete_models_remain_not_computable(saved):
    right = deepcopy(saved)
    right["result"]["models"]["M1"]["status"] = "NOT_COMPUTABLE"
    result = application.compare(saved, right)["models"]
    assert result["M0"]["status"] == "COMPARABLE"
    assert result["M1"]["status"] == "NOT_COMPUTABLE"
    assert "windows" not in result["M1"]


def test_real_model_target_does_not_follow_observation_basis(tmp_path):
    import hashlib
    import json

    ref, _ = reference(tmp_path)
    manifest = {
        "code_git_sha": ref.source_code_sha,
        "code_identity": ref.source_code_identity,
        "task_id": "V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1",
        "phase": "predict",
        "file_sha256": {"SYNTHETIC-models.json": ref.file_sha256},
    }
    path = tmp_path.resolve() / "SYNTHETIC-manifest.json"
    raw = json.dumps(manifest).encode()
    path.write_bytes(raw)
    real = ref.model_copy(
        update={
            "provenance": "REAL_FROZEN_S6",
            "model_training_target_quantity_basis": "RECORDED_INBOUND_WEIGHT",
            "execution_manifest_path": str(path),
            "execution_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    pair = model_artifacts.load(real)
    assert pair.artifacts == model_artifacts.load(ref).artifacts
    assert getattr(pair, "model_training_target_quantity_basis", None) == "RECORDED_INBOUND_WEIGHT"
    calendar, area, origin, cutoff, rows = inputs()
    result = engine.forecast(calendar, area, origin, cutoff, rows, pair, "RESEARCH_SHADOW")
    assert result["feature_observation_quantity_basis"] == "INBOUND_NET_WEIGHT"
    for model in result["models"].values():
        assert model["model_training_target_quantity_basis"] == "RECORDED_INBOUND_WEIGHT"
        assert model["forecast_target_quantity_basis"] == "RECORDED_INBOUND_WEIGHT"


@pytest.mark.asyncio
async def test_cross_source_target_is_rejected_before_label_reads(saved, monkeypatch):
    from datetime import UTC, date, datetime

    value = deepcopy(saved)
    for model in value["result"]["models"].values():
        model.update(
            model_provenance="REAL_FROZEN_S6",
            model_training_target_quantity_basis="RECORDED_INBOUND_WEIGHT",
            forecast_target_quantity_basis="RECORDED_INBOUND_WEIGHT",
        )

    async def get(*args):
        return value

    async def forbidden(*args):
        raise AssertionError("LABEL_READ_BEFORE_BASIS_ADMISSION")

    source = SimpleNamespace(
        reference="SYNTHETIC-LABEL",
        mature_through=date(2030, 1, 1),
        label_cutoff_at=datetime(2026, 9, 1, tzinfo=UTC),
        provenance="SYNTHETIC_TEST_FIXTURE",
        quantity_basis="FIELD_HARVEST_WEIGHT",
    )
    context = SimpleNamespace(reference="SYNTHETIC-CONTEXT", review_snapshots=[source])
    monkeypatch.setattr(application, "get", get)
    monkeypatch.setattr(application, "contexts", lambda *args: [context])
    monkeypatch.setattr(evaluation.observations, "load", forbidden)
    with pytest.raises(ValueError, match="CROSS_SOURCE_TARGET_BASIS_UNVERIFIED"):
        await evaluation.review(None, None, None, 1, source.reference)


@pytest.mark.asyncio
async def test_scoring_matches_forecast_target_not_feature_input(saved, monkeypatch):
    from datetime import UTC, date, datetime

    value = deepcopy(saved)
    value["result"]["feature_snapshot"]["quantity_basis"] = "INBOUND_NET_WEIGHT"

    async def get(*args):
        return value

    reads = []

    async def empty(*args):
        reads.append(True)
        return []

    source = SimpleNamespace(
        reference="SYNTHETIC-LABEL",
        mature_through=date(2030, 1, 1),
        label_cutoff_at=datetime(2026, 9, 1, tzinfo=UTC),
        provenance="SYNTHETIC_TEST_FIXTURE",
        quantity_basis="FIELD_HARVEST_WEIGHT",
        snapshot_hash="a" * 64,
        maturity_authority_hash="b" * 64,
    )
    context = SimpleNamespace(reference="SYNTHETIC-CONTEXT", review_snapshots=[source])
    monkeypatch.setattr(application, "get", get)
    monkeypatch.setattr(application, "contexts", lambda *args: [context])
    monkeypatch.setattr(evaluation.observations, "load", empty)
    result = await evaluation.review(None, None, None, 1, source.reference)
    assert reads
    assert result["feature_observation_quantity_basis"] == "INBOUND_NET_WEIGHT"
    assert result["evaluation_label_quantity_basis"] == "FIELD_HARVEST_WEIGHT"
    assert result["groups"]["H15_LOCAL"]["metrics"]["DAILY_WAPE"]["common_count"] == 0
    source.provenance = "AUTHORIZED_HISTORICAL"
    reads.clear()
    with pytest.raises(ValueError, match="CROSS_SOURCE_TARGET_BASIS_UNVERIFIED"):
        await evaluation.review(None, None, None, 1, source.reference)
    assert not reads


def persisted_fixture():
    from datetime import date, timedelta
    from decimal import Decimal

    from backend.app.rolling_forecast.models import RollingDaily

    origin = date(2026, 11, 5)
    rows = [
        RollingDaily(
            run_id=1,
            model="M0",
            target_date=origin + timedelta(days=i),
            quantity_kg=Decimal("10.000000"),
        )
        for i in range(1, 16)
    ]

    def summary(total):
        return {
            "forecast_total_kg": total,
            "single_day_peak_date": "2026-11-06",
            "single_day_peak_kg": "10.000000",
            "rolling_7day_peak_start": "2026-11-06",
            "rolling_7day_peak_end": "2026-11-12",
            "rolling_7day_peak_cumulative_kg": "70.000000",
            "scope": "THIS_FORECAST_WINDOW_ONLY",
        }

    result = {
        "models": {
            "M0": {
                "status": "COMPUTED",
                "daily_forecast_kg": [
                    {"date": str(r.target_date), "kg": "10.000000"} for r in rows
                ],
                "H7": summary("70.000000"),
                "H15": summary("150.000000"),
            },
            "M1": {"status": "NOT_COMPUTABLE", "daily_forecast_kg": [], "H7": None, "H15": None},
        }
    }
    return rows, result, origin


def test_persisted_flat_curve_uses_earliest_ties_and_never_reruns_ridge(monkeypatch):
    from backend.app.rolling_forecast.persistence import verify_persisted_metrics

    def forbidden(*args):
        raise AssertionError("RIDGE_DURING_RELOAD")

    monkeypatch.setattr(
        "backend.app.area_yield.weather_aware_backtest.RidgeArtifact.predict", forbidden
    )
    verify_persisted_metrics(*persisted_fixture())
    # Also require the winning seven-day window to be inside the 15-day support,
    # not just the first window. Expected values are hand-computable integers.
    from decimal import Decimal

    rows, result, origin = persisted_fixture()
    for i, row in enumerate(rows):
        row.quantity_kg = Decimal(20 if 2 <= i <= 8 else 1)
        result["models"]["M0"]["daily_forecast_kg"][i]["kg"] = format(row.quantity_kg, ".6f")
    for window, total in (("H7", "102.000000"), ("H15", "148.000000")):
        result["models"]["M0"][window].update(
            forecast_total_kg=total,
            single_day_peak_date="2026-11-08",
            single_day_peak_kg="20.000000",
        )
    result["models"]["M0"]["H7"]["rolling_7day_peak_cumulative_kg"] = "102.000000"
    result["models"]["M0"]["H15"].update(
        rolling_7day_peak_start="2026-11-08",
        rolling_7day_peak_end="2026-11-14",
        rolling_7day_peak_cumulative_kg="140.000000",
    )
    verify_persisted_metrics(rows, result, origin)


@pytest.mark.parametrize("window", ["H7", "H15"])
@pytest.mark.parametrize(
    "field",
    [
        "forecast_total_kg",
        "single_day_peak_date",
        "single_day_peak_kg",
        "rolling_7day_peak_start",
        "rolling_7day_peak_end",
        "rolling_7day_peak_cumulative_kg",
        "scope",
    ],
)
def test_each_summary_field_is_recomputed_from_saved_rows(window, field):
    from backend.app.rolling_forecast.persistence import verify_persisted_metrics

    rows, result, origin = persisted_fixture()
    result["models"]["M0"][window][field] = "INCORRECT_BUT_REHASHABLE_SUMMARY"
    with pytest.raises(ValueError, match="ROLLING_PERSISTED_METRIC_MISMATCH"):
        verify_persisted_metrics(rows, result, origin)


@pytest.mark.parametrize("change", ["missing", "duplicate", "out_of_support", "snapshot_order"])
def test_persisted_dates_and_row_count_are_checked(change):
    from datetime import timedelta

    from backend.app.rolling_forecast.persistence import verify_persisted_metrics

    rows, result, origin = persisted_fixture()
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[-1].target_date = rows[0].target_date
    elif change == "out_of_support":
        rows[-1].target_date += timedelta(days=1)
    else:
        result["models"]["M0"]["daily_forecast_kg"].reverse()
    with pytest.raises(ValueError, match="ROLLING_DAILY_CALENDAR_MISMATCH"):
        verify_persisted_metrics(rows, result, origin)
