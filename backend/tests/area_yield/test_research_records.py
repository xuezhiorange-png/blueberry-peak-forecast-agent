"""Research file-mode E2E and hostile inputs; all forecasts are TEST_ONLY."""

import copy
import json
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield import m0_baseline
from backend.app.area_yield import research_records as rr
from backend.app.area_yield.data import calendar, digest

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "backend/tests/fixtures/m0-synthetic-test-only.json"
ISSUE_CLOCK = datetime(2027, 6, 1, tzinfo=UTC)
ACTUAL_CLOCK = datetime(2028, 4, 16, tzinfo=UTC)
SCORE_CLOCK = datetime(2028, 4, 17, tzinfo=UTC)


def request() -> dict[str, Any]:
    return {
        "base_id": "base_" + "a" * 24,
        "target_area_mu": "10",
        "target_season": "2027-2028",
        "forecast_start_date": "2027-07-01",
        "forecast_end_date": "2028-04-15",
        "forecast_mode": "EXPERIMENTAL",
    }


def registry(path: Path) -> str:
    model = m0_baseline.load_model(MODEL)
    payload = {
        "default_research_model_id": "M0-ALL-HISTORY-REFERENCE-R1",
        "models": [
            {
                "model_id": "M0-ALL-HISTORY-REFERENCE-R1",
                "model_family": m0_baseline.MODEL_ID,
                "model_role": "REFERENCE_BASELINE",
                "approval_status": "RESEARCH_ONLY",
                "artifact_file_sha256": rr.file_hash(MODEL),
                "artifact_hash": model["artifact_hash"],
                "training_manifest_sha256": model["training_manifest_sha256"],
                "training_cutoff": model["training_cutoff"],
                "supported_request_window": "JULY_01_THROUGH_APRIL_15_INCLUSIVE",
            }
        ],
    }
    path.write_text(json.dumps(payload))
    return rr.file_hash(path)


def authorization(payload: dict[str, Any]) -> dict[str, Any]:
    from backend.app.area_yield.base_product import AreaForecastProductRequest

    snapshot = AreaForecastProductRequest.model_validate(payload).model_dump(mode="json")
    return {
        "status": "TEST_ONLY",
        "source_version": "SYNTHETIC_TEST_REQUEST_R1",
        "source_sha256": digest(snapshot),
        "request_snapshot_hash": digest(snapshot),
        "target_actuals_used": False,
    }


def issue(tmp_path: Path, **kwargs: Any) -> Path:
    path = tmp_path / "registry.json"
    sha = registry(path)
    payload = kwargs.pop("payload", request())
    return rr.issue(
        tmp_path / "store",
        path,
        sha,
        MODEL,
        "M0-ALL-HISTORY-REFERENCE-R1",
        payload,
        authorization(payload),
        **kwargs,
    )


def actual_source() -> dict[str, Any]:
    rows = [
        {
            "date": d.isoformat(),
            "new_quantity_kg": "100.000000" if i % 5 else "0.000000",
            "status": "OBSERVED" if i % 5 else "CONFIRMED_ZERO",
        }
        for i, d in enumerate(calendar(date(2027, 7, 1), date(2028, 4, 15)))
    ]
    return {
        "base_id": request()["base_id"],
        "target_season": "2027-2028",
        "unit": "kg",
        "source_version": "SYNTHETIC_ACTUAL_R1",
        "source_sha256": digest(rows),
        "rows": rows,
    }


def setup_records(tmp_path: Path) -> tuple[str, str]:
    seal = rr.read(issue(tmp_path, test_clock=ISSUE_CLOCK))["id"]
    actual = rr.read(
        rr.import_actuals(tmp_path / "store", seal, actual_source(), test_clock=ACTUAL_CLOCK)
    )["id"]
    return seal, actual


def test_e2e_locked_score_and_revisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        m0_baseline, "fit", lambda *a, **k: pytest.fail("NO_TRAINING"), raising=False
    )
    seal, actual = setup_records(tmp_path)
    root = tmp_path / "store"
    first = rr.evaluate(root, seal, actual, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK)
    payload = rr.read(first)
    again = rr.evaluate(
        root, seal, actual, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK, parent_id=payload["id"]
    )
    assert rr.read(again)["metrics"] == payload["metrics"]
    assert payload["test_only"] and not payload["prospective_accuracy_validated"]
    old = (root / "actuals" / actual / "record.json").read_bytes()
    changed = actual_source()
    changed.update(
        supersedes=actual, revision_reason="SYNTHETIC_SOURCE_CORRECTION", source_version="R2"
    )
    changed["rows"][1]["new_quantity_kg"] = "105.000000"
    revised = rr.import_actuals(root, seal, changed, test_clock=ACTUAL_CLOCK)
    assert rr.read(revised)["id"] != actual
    assert (root / "actuals" / actual / "record.json").read_bytes() == old
    reevaluated = rr.evaluate(
        root,
        seal,
        rr.read(revised)["id"],
        rr.CONTRACT,
        MODEL,
        test_clock=SCORE_CLOCK,
        parent_id=payload["id"],
    )
    assert rr.read(reevaluated)["parent_id"] == payload["id"]
    before = (root / "predictions" / seal / "record.json").read_bytes()
    next_run = issue(tmp_path, test_clock=ISSUE_CLOCK, parent_id=seal)
    assert rr.read(next_run)["parent_id"] == seal
    assert (root / "predictions" / seal / "record.json").read_bytes() == before


@pytest.mark.parametrize("field", ["prediction", "metrics", "issued_at", "request_snapshot"])
def test_tampered_prediction_rejected(tmp_path: Path, field: str) -> None:
    path = issue(tmp_path, test_clock=ISSUE_CLOCK)
    payload = rr.read(path)
    payload[field] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="HASH"):
        rr.load_prediction(tmp_path / "store", payload["id"], MODEL)


def test_modified_model_rejected(tmp_path: Path) -> None:
    path = issue(tmp_path, test_clock=ISSUE_CLOCK)
    model = rr.read(MODEL)
    model["pooled_yield_kg_per_mu"] += 1
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(model))
    with pytest.raises(ValueError, match="INTEGRITY"):
        rr.load_prediction(tmp_path / "store", rr.read(path)["id"], changed)


def test_diagnostic_selected_cannot_be_issued(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    registry(path)
    payload = rr.read(path)
    payload["models"][0]["model_role"] = "DIAGNOSTIC_ONLY"
    path.write_text(json.dumps(payload))
    selected = tmp_path / "ALL_HISTORY-SELECTED.json"
    selected.write_bytes(MODEL.read_bytes())
    with pytest.raises(ValueError, match="ROLE"):
        rr.issue(
            tmp_path / "store",
            path,
            rr.file_hash(path),
            selected,
            "M0-ALL-HISTORY-REFERENCE-R1",
            request(),
            authorization(request()),
            test_clock=ISSUE_CLOCK,
        )


def test_backdating_and_real_clock(tmp_path: Path) -> None:
    payload = request()
    payload["issued_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        issue(tmp_path, payload=payload, test_clock=ISSUE_CLOCK)
    with pytest.raises(TypeError):
        issue(tmp_path, issued_at=ISSUE_CLOCK)
    before = datetime.now(UTC)
    assert before <= rr._now(None) <= datetime.now(UTC)


def test_started_window_and_subwindow_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ALREADY_STARTED"):
        issue(tmp_path, test_clock=datetime(2027, 7, 1, tzinfo=UTC))
    payload = request()
    payload["forecast_start_date"] = "2027-10-01"
    with pytest.raises(ValueError, match="REASSIGNED"):
        issue(tmp_path, payload=payload, test_clock=ISSUE_CLOCK)


@pytest.mark.parametrize(
    "mutate", ["base", "season", "unit", "outside", "duplicate", "zero", "negative"]
)
def test_actual_identity_and_values_rejected(tmp_path: Path, mutate: str) -> None:
    seal = rr.read(issue(tmp_path, test_clock=ISSUE_CLOCK))["id"]
    source = actual_source()
    if mutate in {"base", "season", "unit"}:
        source[{"base": "base_id", "season": "target_season", "unit": "unit"}[mutate]] = "WRONG"
    elif mutate == "outside":
        source["rows"][0]["date"] = "2027-06-30"
    elif mutate == "duplicate":
        source["rows"].append(copy.deepcopy(source["rows"][0]))
    elif mutate == "zero":
        source["rows"][0]["new_quantity_kg"] = "1"
    else:
        source["rows"][1]["new_quantity_kg"] = "-1"
    with pytest.raises(ValueError):
        rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK)


@pytest.mark.parametrize("missing", ["row", "explicit"])
def test_missing_not_filled(tmp_path: Path, missing: str) -> None:
    seal = rr.read(issue(tmp_path, test_clock=ISSUE_CLOCK))["id"]
    source = actual_source()
    if missing == "row":
        source["rows"].pop()
    else:
        source["rows"][0].update(new_quantity_kg=None, status="MISSING")
    actual = rr.read(rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK))[
        "id"
    ]
    with pytest.raises(ValueError, match="COVERAGE"):
        rr.evaluate(tmp_path / "store", seal, actual, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK)


def test_wrong_seal_contract_unfinished_and_mode_rejected(tmp_path: Path) -> None:
    seal, actual = setup_records(tmp_path)
    root = tmp_path / "store"
    other = rr.read(issue(tmp_path, test_clock=ISSUE_CLOCK))["id"]
    with pytest.raises(ValueError, match="IDENTITY"):
        rr.evaluate(root, other, actual, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK)
    with pytest.raises(ValueError, match="CONTRACT"):
        rr.evaluate(root, seal, actual, "ALTERED", MODEL, test_clock=SCORE_CLOCK)
    with pytest.raises(ValueError, match="MODE"):
        rr.evaluate(root, seal, actual, rr.CONTRACT, MODEL)
    source = actual_source()
    source["rows"] = source["rows"][:1]
    partial = rr.read(
        rr.import_actuals(root, seal, source, test_clock=datetime(2027, 7, 2, tzinfo=UTC))
    )["id"]
    with pytest.raises(ValueError, match="NOT_ENDED"):
        rr.evaluate(
            root, seal, partial, rr.CONTRACT, MODEL, test_clock=datetime(2027, 7, 3, tzinfo=UTC)
        )


def test_aggregate_and_zero_total(tmp_path: Path) -> None:
    seal, actual = setup_records(tmp_path)
    path = rr.evaluate(tmp_path / "store", seal, actual, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK)
    metrics = rr.read(path)["metrics"]
    pooled = rr.aggregate([metrics, metrics])
    assert pooled["window_total_wape"] == metrics["window_total_wape"]
    assert Decimal(pooled["actual_total_kg"]) == 2 * Decimal(metrics["actual_total_kg"])
    source = actual_source()
    for row in source["rows"]:
        row.update(new_quantity_kg="0.000000", status="CONFIRMED_ZERO")
    actual = rr.read(rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK))[
        "id"
    ]
    path = rr.evaluate(tmp_path / "store", seal, actual, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK)
    metrics = rr.read(path)["metrics"]
    assert metrics["window_total_wape"] is None and metrics["P50"]["actual"] is None


def test_inference_target_read_guard(tmp_path: Path) -> None:
    label = tmp_path / "target.csv"
    label.write_text("new_quantity_kg\n100\n")
    code = (
        "from pathlib import Path; import sys; "
        "from backend.app.area_yield.m0_baseline_cli import _inference_guard; "
        "_inference_guard(set()); Path(sys.argv[1]).read_text()"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(label)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "M0_INFERENCE_FORBIDDEN_DATA_READ" in completed.stderr


def test_same_feature_request_replay_and_peak_roundtrip(tmp_path: Path) -> None:
    first = rr.read(issue(tmp_path, test_clock=ISSUE_CLOCK))
    second = rr.read(issue(tmp_path, test_clock=ISSUE_CLOCK))
    assert first["id"] != second["id"]
    assert first["prediction"] == second["prediction"]
    values = [Decimal(r["predicted_quantity_kg"]) for r in first["prediction"]["daily_curve"]]
    assert sum(values) == Decimal(first["metrics"]["total_kg"])
    assert len(values) == 290 and all(v >= 0 for v in values)
    assert first["prospective_class"] == "TEST_NOT_PROSPECTIVE"


def test_registry_hash_and_authorization_binding(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    sha = registry(path)
    payload = request()
    with pytest.raises(ValueError, match="REGISTRY_HASH"):
        rr.issue(
            tmp_path / "store",
            path,
            "0" * 64,
            MODEL,
            "M0-ALL-HISTORY-REFERENCE-R1",
            payload,
            authorization(payload),
            test_clock=ISSUE_CLOCK,
        )
    authority = authorization(payload)
    authority["request_snapshot_hash"] = "0" * 64
    with pytest.raises(ValueError, match="AUTHORITY"):
        rr.issue(
            tmp_path / "store",
            path,
            sha,
            MODEL,
            "M0-ALL-HISTORY-REFERENCE-R1",
            payload,
            authority,
            test_clock=ISSUE_CLOCK,
        )
