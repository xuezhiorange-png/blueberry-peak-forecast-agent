"""E1 exercises public hand-specified artifacts, never fitting or private data."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield import area_size_r1
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield import research_records_r2 as r2
from backend.app.area_yield.data import digest
from backend.app.area_yield.research_records import file_hash, read
from backend.app.area_yield.research_records_r2 import TestClock as ControlledClock
from backend.app.area_yield.v0_12_e1_fixtures import bind_actual, make_fixture


@pytest.fixture
def case(tmp_path: Path) -> dict[str, Any]:
    return make_fixture(tmp_path / "SYNTHETIC")


def issue(
    case: dict[str, Any], *, root: Path | None = None, clock: r2.Clock = None
) -> dict[str, Any]:
    record = e1.create_research_forecast(
        root or case["store"],
        case["registry"],
        file_hash(case["registry"]),
        case["request"],
        case["source"],
        case["authorization"],
        clock=clock or case["issue_clock"],
    )
    if not case["actual_source"].exists():
        bind_actual(case, record["id"])
    return record


def actual(case: dict[str, Any], forecast_id: str) -> dict[str, Any]:
    return e1.import_actuals(
        case["store"],
        forecast_id,
        case["actual"],
        case["actual_source"],
        clock=case["actual_clock"],
    )


def complete(case: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    forecast = issue(case)
    revision = actual(case, forecast["id"])
    snapshot = e1.create_actual_snapshot(
        case["store"],
        forecast["id"],
        [revision["id"]],
        clock=case["actual_clock"],
    )
    evaluation = e1.evaluate_locked_forecast(
        case["store"],
        forecast["id"],
        snapshot["id"],
        e1.CONTRACT,
        clock=case["actual_clock"],
    )
    return forecast, revision, snapshot, evaluation


def test_full_synthetic_e2e_and_deterministic_replay(
    case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Explicitly make all training and scoring-time model inference unusable.
    monkeypatch.setattr(area_size_r1, "fit", lambda *a, **k: pytest.fail("TRAINING"))
    forecast, revision, snapshot, result = complete(case)
    replay = issue(case, root=tmp_path / "other-store")
    assert forecast["prediction_hash"] == replay["prediction_hash"]
    assert e1.verify_research_forecast(case["store"], forecast["id"])["test_only"]
    monkeypatch.setattr(area_size_r1, "predict", lambda *a, **k: pytest.fail("INFERENCE"))
    second = e1.evaluate_locked_forecast(
        case["store"],
        forecast["id"],
        snapshot["id"],
        e1.CONTRACT,
        clock=case["actual_clock"],
    )
    assert second["metrics_hash"] == result["metrics_hash"]
    assert result["stable_gain_decision"] == "NOT_EXECUTED"
    assert set(result["metrics"]) == {"candidate", "comparator", "candidate_minus_comparator"}
    assert snapshot["coverage_status"] == "FINAL_SCORING_SNAPSHOT"
    assert revision["rows"][0]["quantity_status"] == "AUTHORIZED_ZERO"
    assert forecast["identity"]["window"] == ["2028-07-01", "2029-04-15"]


@pytest.mark.parametrize("component", ["prediction", "artifact", "config", "issued_at"])
def test_forecast_tamper_rejected(case: dict[str, Any], component: str) -> None:
    record = issue(case)
    path = case["store"] / "predictions" / record["id"] / "record.json"
    changed = read(path)
    if component == "prediction":
        changed["prediction"]["candidate"]["daily_curve"][0]["predicted_daily_quantity_kg"] = "1"
    elif component == "artifact":
        changed["artifact_entries"]["candidate"]["artifact_hash"] = "a" * 64
    elif component == "config":
        changed["request_snapshot"]["candidate_config_hash"] = "a" * 64
    else:
        changed["issued_at"] = "2028-07-02T00:00:00+00:00"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        e1.verify_research_forecast(case["store"], record["id"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_mode", "REAL_PROSPECTIVE"),
        ("target_area_mu", "0"),
        ("target_area_mu", "-1"),
        ("target_area_mu", "0.0000009"),
        ("candidate_artifact_hash", "g" * 64),
        ("candidate_config_hash", "a" * 64),
        ("forecast_start_date", "2028-07-02"),
        ("target_season", "2028-2030"),
    ],
)
def test_invalid_request_gate(case: dict[str, Any], field: str, value: str) -> None:
    request = {**case["request"], field: value}
    with pytest.raises(ValueError):
        e1.create_research_forecast(
            case["store"],
            case["registry"],
            file_hash(case["registry"]),
            request,
            case["source"],
            case["authorization"],
            clock=case["issue_clock"],
        )


def test_extrapolation_warning_is_not_accuracy_validation(case: dict[str, Any]) -> None:
    updated = make_fixture(case["store"].parent / "outside", area="3000")
    forecast = issue(updated)
    assert forecast["area_applicability"]["area_position"] == "EXTRAPOLATION"
    assert "AREA_EXTRAPOLATION_NOT_VALIDATED" in forecast["area_applicability"]["warnings"]
    assert forecast["prospective_accuracy_validated"] is False


def test_cutoff_completion_and_partial_write_fail_closed(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    times = iter(
        [
            datetime.fromisoformat("2028-06-30T15:59:59+00:00"),
            datetime.fromisoformat("2028-07-01T00:00:00+08:00"),
        ]
    )
    with pytest.raises(ValueError, match="CUTOFF"):
        issue(case, clock=ControlledClock(lambda: next(times)))
    assert not list((case["store"] / "predictions").glob("*/record.json"))
    monkeypatch.setattr(r2, "_write", lambda *a: (_ for _ in ()).throw(OSError("DISK")))
    with pytest.raises(OSError):
        issue(case)
    assert not list((case["store"] / "predictions").glob("*/record.json"))


def test_duplicate_and_concurrent_same_request_fail_closed(case: dict[str, Any]) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(issue, case) for _ in range(2)]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result()["id"])
        except ValueError as exc:
            assert "DUPLICATE" in str(exc)
    assert len(outcomes) == 1
    with pytest.raises(ValueError, match="DUPLICATE"):
        issue(case)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-date",
        "missing-as-zero",
        "wrong-season",
        "wrong-base",
        "precision",
        "source-hash",
        "source-conflict",
    ],
)
def test_actual_contract_failures(case: dict[str, Any], mutation: str) -> None:
    forecast = issue(case)
    changed = copy.deepcopy(case["actual"])
    if mutation == "missing-date":
        changed["rows"].pop(4)
        case["actual_source"].write_text(json.dumps(changed))
        changed["source_hash"] = file_hash(case["actual_source"])
        # Schema excludes self hash from the source canonical payload.
        case["actual_source"].write_text(json.dumps(e1.actual_source_payload(changed)))
        changed["source_hash"] = file_hash(case["actual_source"])
        revision = e1.import_actuals(
            case["store"],
            forecast["id"],
            changed,
            case["actual_source"],
            clock=case["actual_clock"],
        )
        snapshot = e1.create_actual_snapshot(
            case["store"],
            forecast["id"],
            [revision["id"]],
            clock=case["actual_clock"],
        )
        assert snapshot["coverage_status"] == "INTERIM_SNAPSHOT"
        with pytest.raises(ValueError, match="COVERAGE"):
            e1.evaluate_locked_forecast(
                case["store"],
                forecast["id"],
                snapshot["id"],
                e1.CONTRACT,
                clock=case["actual_clock"],
            )
        return
    if mutation == "missing-as-zero":
        changed["rows"][0].update(quantity_status="MISSING", new_quantity_kg="0")
    elif mutation == "wrong-season":
        changed["season"] = "2027-2028"
    elif mutation == "wrong-base":
        changed["base_id"] = "OTHER"
    elif mutation == "precision":
        changed["rows"][0]["new_quantity_kg"] = "0.0000009"
    elif mutation == "source-hash":
        changed["source_hash"] = "a" * 64
    else:
        actual(case, forecast["id"])
        changed["actual_revision_id"] = "conflict"
        changed["rows"][1]["new_quantity_kg"] = "123"
    with pytest.raises(ValueError):
        e1.import_actuals(
            case["store"],
            forecast["id"],
            changed,
            case["actual_source"],
            clock=case["actual_clock"],
        )


@pytest.mark.parametrize("kind", ["actual-revisions", "snapshots", "evaluations"])
def test_immutable_records_detect_tampering(case: dict[str, Any], kind: str) -> None:
    _, revision, snapshot, evaluation = complete(case)
    record = {"actual-revisions": revision, "snapshots": snapshot, "evaluations": evaluation}[kind]
    path = case["store"] / kind / record["id"] / "record.json"
    changed = read(path)
    changed["test_only"] = False
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        e1.get_record(case["store"], kind, record["id"])


@pytest.mark.parametrize("field", ["candidate_artifact_hash", "comparator_hash", "metric_contract"])
def test_locked_evaluation_cannot_switch_identity(case: dict[str, Any], field: str) -> None:
    forecast, _, snapshot, _ = complete(case)
    with pytest.raises(ValueError):
        e1.evaluate_locked_forecast(
            case["store"],
            forecast["id"],
            snapshot["id"],
            "OTHER" if field == "metric_contract" else e1.CONTRACT,
            expected_identity={field: "a" * 64} if field != "metric_contract" else None,
            clock=case["actual_clock"],
        )


def test_curve_invariants_and_true_seven_day_peak() -> None:
    rows = [
        {"date": f"2028-07-{day:02d}", "predicted_daily_quantity_kg": "1.000000"}
        for day in range(1, 9)
    ]
    assert e1.curve_summary(rows)["rolling_7day_peak"]["cumulative_quantity_kg"] == "7.000000"
    assert e1.curve_summary(rows)["rolling_7day_peak"]["start_date"] == "2028-07-01"
    with pytest.raises(ValueError):
        e1.curve_summary(rows[:3] + rows[4:])


def test_prediction_total_and_calendar_mismatch_rejected(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = area_size_r1.predict

    def bad(*args: Any, **kwargs: Any) -> dict[str, Any]:
        value = original(*args, **kwargs)
        value["predicted_season_total_kg"] = "1"
        value.pop("result_hash")
        value["result_hash"] = digest(value)
        return value

    monkeypatch.setattr(area_size_r1, "predict", bad)
    with pytest.raises(ValueError, match="TOTAL"):
        issue(case)


def test_final_scoring_window_not_ended_and_wrong_forecast(case: dict[str, Any]) -> None:
    forecast, _, snapshot, _ = complete(case)
    with pytest.raises(ValueError):
        e1.evaluate_locked_forecast(
            case["store"],
            forecast["id"],
            snapshot["id"],
            e1.CONTRACT,
            clock=datetime.fromisoformat("2029-04-15T00:00:00+08:00"),
        )
    other = make_fixture(case["store"].parent / "another")
    other["store"] = case["store"]
    other["request"]["request_id"] = "OTHER"
    with pytest.raises(ValueError):
        issue(other)


def test_immutable_actual_revision_and_new_snapshot(case: dict[str, Any]) -> None:
    forecast, original, snapshot, evaluation = complete(case)
    originals = {p: p.read_bytes() for p in case["store"].glob("*/*/*.json")}
    new = copy.deepcopy(case["actual"])
    new.update(
        actual_revision_id="SYNTHETIC_ACTUAL_2",
        source_version="2",
        parent_revision_id=original["id"],
        supersedes_revision_id=original["id"],
        revision_reason="SYNTHETIC_CORRECTION",
    )
    new["rows"][1]["new_quantity_kg"] = "11.000000"
    path = case["actual_source"].with_name("SYNTHETIC-source-v2.json")
    path.write_text(json.dumps(e1.actual_source_payload(new)))
    new["source_hash"] = file_hash(path)
    revised = e1.import_actuals(
        case["store"], forecast["id"], new, path, clock=case["actual_clock"]
    )
    second = e1.create_actual_snapshot(
        case["store"], forecast["id"], [revised["id"]], clock=case["actual_clock"]
    )
    result = e1.evaluate_locked_forecast(
        case["store"], forecast["id"], second["id"], e1.CONTRACT, clock=case["actual_clock"]
    )
    assert result["metrics_hash"] != evaluation["metrics_hash"]
    assert all(path.read_bytes() == old for path, old in originals.items())
    assert snapshot["id"] != second["id"]


@pytest.mark.parametrize("failure", ["missing-prediction-day", "artifact-file", "registry-role"])
def test_inference_and_registry_failure_injection(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    if failure == "missing-prediction-day":
        original = area_size_r1.predict

        def incomplete(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = original(*args, **kwargs)
            result["daily_curve"].pop(3)
            result.pop("result_hash")
            result["result_hash"] = digest(result)
            return result

        monkeypatch.setattr(area_size_r1, "predict", incomplete)
    elif failure == "artifact-file":
        registry = read(case["registry"])
        Path(registry["entries"][0]["artifact_path"]).write_text("{}")
    else:
        registry = read(case["registry"])
        registry["entries"][0]["model_role"] = "PRODUCTION_APPROVED"
        registry.pop("record_hash")
        registry["record_hash"] = digest(registry)
        case["registry"].write_text(json.dumps(registry))
    with pytest.raises(ValueError):
        issue(case)


def test_same_source_version_content_conflict_even_with_valid_source(case: dict[str, Any]) -> None:
    forecast = issue(case)
    actual(case, forecast["id"])
    changed = copy.deepcopy(case["actual"])
    changed["actual_revision_id"] = "CONFLICT"
    changed["rows"][1]["new_quantity_kg"] = "15.000000"
    source = case["actual_source"].with_name("SYNTHETIC-conflict.json")
    source.write_text(json.dumps(e1.actual_source_payload(changed)))
    changed["source_hash"] = file_hash(source)
    with pytest.raises(ValueError, match="CONFLICT"):
        e1.import_actuals(
            case["store"], forecast["id"], changed, source, clock=case["actual_clock"]
        )


def test_fresh_process_full_existing_cli(case: dict[str, Any]) -> None:
    def command(name: str, *args: Any) -> dict[str, Any]:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.app.area_yield.prospective_validation_cli",
                "v0-12-research",
                name,
                "--store",
                str(case["store"]),
                *map(str, args),
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        record: dict[str, Any] = json.loads(process.stdout)["record"]
        return record

    forecast = command(
        "issue",
        "--registry",
        case["registry"],
        "--registry-hash",
        file_hash(case["registry"]),
        "--input",
        case["source"].with_name("example-request.json"),
        "--source",
        case["source"],
        "--authorization",
        case["authorization"],
        "--test-clock",
        case["issue_clock"].isoformat(),
    )
    bind_actual(case, forecast["id"])
    checked = command("verify-seal", "--forecast-id", forecast["id"])
    assert checked["prediction_hash"] == forecast["prediction_hash"]
    revision = command(
        "import-actuals",
        "--forecast-id",
        forecast["id"],
        "--source",
        case["actual_source"],
        "--input",
        case["actual_source"].with_name("example-actual.json"),
        "--test-clock",
        case["actual_clock"].isoformat(),
    )
    snapshot = command(
        "create-snapshot",
        "--forecast-id",
        forecast["id"],
        "--revision-id",
        revision["id"],
        "--test-clock",
        case["actual_clock"].isoformat(),
    )
    evaluation = command(
        "evaluate",
        "--forecast-id",
        forecast["id"],
        "--snapshot-id",
        snapshot["id"],
        "--metric-contract",
        e1.CONTRACT,
        "--test-clock",
        case["actual_clock"].isoformat(),
    )
    assert evaluation["stable_gain_decision"] == "NOT_EXECUTED"
    assert (
        command("show-run", "--forecast-id", forecast["id"])["record_hash"]
        == forecast["record_hash"]
    )


def test_duplicate_revision_preserves_existing_record(case: dict[str, Any]) -> None:
    forecast = issue(case)
    revision = actual(case, forecast["id"])
    path = case["store"] / "actual-revisions" / revision["id"] / "record.json"
    frozen = path.read_bytes()
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        actual(case, forecast["id"])
    assert path.read_bytes() == frozen


def test_cutoff_during_persistence_is_aborted(case: dict[str, Any]) -> None:
    before = datetime.fromisoformat("2028-06-30T23:59:59+08:00")
    after = datetime.fromisoformat("2028-07-01T00:00:00+08:00")
    times = iter([before, before, before, after])
    with pytest.raises(ValueError, match="CUTOFF"):
        issue(case, clock=ControlledClock(lambda: next(times)))
    assert not list((case["store"] / "predictions").glob("*/record.json"))
    assert list((case["store"] / "ABORTED_NOT_ISSUED").glob("*/record.json"))


def test_stale_contract_cannot_reinterpret_seal(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    forecast, _, snapshot, _ = complete(case)
    monkeypatch.setattr(e1, "CONTRACT", "UPGRADED_NOT_REGISTERED")
    monkeypatch.setitem(e1.SPEC, "version", "UPGRADED_NOT_REGISTERED")
    with pytest.raises(ValueError, match="METRIC"):
        e1.evaluate_locked_forecast(
            case["store"], forecast["id"], snapshot["id"], e1.CONTRACT, clock=case["actual_clock"]
        )


def test_mismatched_authorization_is_rejected(case: dict[str, Any]) -> None:
    authorization = read(case["authorization"])
    authorization["request_hash"] = "a" * 64
    case["authorization"].write_text(json.dumps(authorization))
    with pytest.raises(ValueError, match="AUTHORIZATION"):
        issue(case)


def test_snapshot_cannot_score_against_another_forecast(case: dict[str, Any]) -> None:
    first, _, snapshot, _ = complete(case)
    other = make_fixture(case["store"].parent / "other-forecast")
    other["request"]["request_id"] = "OTHER_REQUEST"
    other["source"].write_text(json.dumps(e1.request_source_payload(other["request"])))
    other["request"]["request_source_hash"] = file_hash(other["source"])
    authorization = read(other["authorization"])
    authorization["request_hash"] = digest(other["request"])
    other["authorization"].write_text(json.dumps(authorization))
    second = issue(other, root=case["store"])
    assert second["id"] != first["id"]
    with pytest.raises(ValueError, match="FORECAST_MISMATCH"):
        e1.evaluate_locked_forecast(
            case["store"], second["id"], snapshot["id"], e1.CONTRACT, clock=case["actual_clock"]
        )


def test_metric_formulas_and_zero_denominators() -> None:
    rows = [
        {"date": f"2028-07-{day:02d}", "quantity_status": "OBSERVED", "new_quantity_kg": "1.000000"}
        for day in range(1, 9)
    ]
    predicted = {
        "daily_curve": [
            {"date": r["date"], "predicted_daily_quantity_kg": "2.000000"} for r in rows
        ]
    }
    metrics = e1._metrics(rows, predicted)
    assert metrics["daily_wape"] == "1.000000"
    assert metrics["daily_smape"] == "0.666667"
    assert metrics["season_total_absolute_error"] == "8.000000"
    assert metrics["rolling_7day_peak_quantity_absolute_error"] == "7.000000"
    for row in rows:
        row["new_quantity_kg"] = "0.000000"
    zero = e1._metrics(rows, predicted)
    assert zero["season_total_relative_error"] is None
    assert zero["daily_wape"] is None
    assert zero["single_day_peak_quantity_relative_error"] is None
    assert zero["daily_smape"] == "2.000000"


def test_declared_r1_registry_is_not_content_verified_or_synthetic() -> None:
    root = Path(__file__).resolve().parents[3]
    declaration = read(root / "configs/v0_12_e1_reported_artifact_registry.json")
    assert declaration["entries"][0]["model_id"] == "NEXT_AREA_SIZE_20261002_R1_CANDIDATE"
    with pytest.raises(ValueError, match="NOT_VERIFIED"):
        e1._resolve(
            declaration,
            "NEXT_AREA_SIZE_20261002_R1_CANDIDATE",
            "RESEARCH_CANDIDATE",
            datetime.fromisoformat("2028-06-01T00:00:00+00:00"),
        )
