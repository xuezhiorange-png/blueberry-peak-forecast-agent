"""Boundary regression suite. Every issuance/source here is synthetic TEST_ONLY."""

import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield import research_records as old
from backend.app.area_yield import research_records_r2 as rr
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.area_yield.data import digest
from backend.tests.area_yield.test_research_records import (
    ACTUAL_CLOCK,
    ISSUE_CLOCK,
    MODEL,
    SCORE_CLOCK,
    actual_source,
    registry,
    request,
)


def origin(
    path: Path,
    canonical: Any,
    *,
    identity: str = "SYNTHETIC",
    version: str = "1",
    normalization: str = "IDENTITY_JSON_MICROKG_R2",
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canonical))
    return {
        "source_id": identity,
        "source_version": version,
        "raw_source_hash": rr.file_hash(path),
        "canonical_payload_hash": digest(canonical),
        "normalization_version": normalization,
        "raw_source_path": str(path),
    }


def auth(tmp_path: Path, payload: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    snapshot = AreaForecastProductRequest.model_validate(payload).model_dump(mode="json")
    local = {
        "status": "TEST_ONLY",
        "operator": "SYNTHETIC_TEST_OPERATOR",
        "request_snapshot_hash": digest(snapshot),
        "target_actuals_used": False,
        "revision_reason": reason,
    }
    return {
        "local_record": local,
        "source": origin(
            tmp_path / f"auth-{digest(local)}.json", local, normalization="EXACT_REQUEST_AUTH_R2"
        ),
    }


def issue(
    tmp_path: Path,
    *,
    payload: dict[str, Any] | None = None,
    clock: rr.Clock = ISSUE_CLOCK,
    parent_id: str | None = None,
    reason: str | None = None,
) -> Path:
    reg = tmp_path / "registry.json"
    sha = registry(reg)
    payload = request() if payload is None else payload
    return rr.issue(
        tmp_path / "store",
        reg,
        sha,
        MODEL,
        "M0-ALL-HISTORY-REFERENCE-R1",
        payload,
        auth(tmp_path, payload, reason),
        parent_id=parent_id,
        test_clock=clock,
    )


def actual(
    tmp_path: Path,
    *,
    version: str = "1",
    supersedes: str | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = actual_source()
    rows = source["rows"] if rows is None else rows
    return {
        "base_id": source["base_id"],
        "target_season": source["target_season"],
        "unit": "kg",
        "rows": rows,
        "source_identity": origin(tmp_path / f"actual-{version}.json", rows, version=version),
        "supersedes": supersedes,
        "revision_reason": "SYNTHETIC_REVISION" if supersedes else None,
    }


def setup(tmp_path: Path) -> tuple[str, str]:
    seal = rr.read(issue(tmp_path))["id"]
    snapshot = rr.read(
        rr.import_actuals(tmp_path / "store", seal, actual(tmp_path), test_clock=ACTUAL_CLOCK)
    )["id"]
    return seal, snapshot


def score(tmp_path: Path, seal: str, actual_id: str, **kwargs: Any) -> Path:
    return rr.evaluate(
        tmp_path / "store", seal, actual_id, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK, **kwargs
    )


def forge(path: Path, mutate) -> None:
    payload = rr.read(path)
    payload.pop("record_hash")
    mutate(payload)
    path.write_text(json.dumps(old._seal(payload)))


def test_normal_e2e_revision_and_original_bytes(tmp_path: Path) -> None:
    seal, snapshot = setup(tmp_path)
    result = score(tmp_path, seal, snapshot)
    before = {p: p.read_bytes() for p in (tmp_path / "store").glob("*/*/record.json")}
    changed = actual_source()["rows"]
    changed[1]["new_quantity_kg"] = "90.000000"
    revision = rr.read(
        rr.import_actuals(
            tmp_path / "store",
            seal,
            actual(tmp_path, version="2", supersedes=snapshot, rows=changed),
            test_clock=ACTUAL_CLOCK,
        )
    )["id"]
    new_score = score(
        tmp_path,
        seal,
        revision,
        parent_id=rr.read(result)["id"],
        revision_reason="SYNTHETIC_ACTUAL_UPDATE",
    )
    assert rr.read(new_score)["metrics"] != rr.read(result)["metrics"]
    assert all(p.read_bytes() == content for p, content in before.items())
    child = rr.read(
        issue(
            tmp_path,
            parent_id=seal,
            reason="SYNTHETIC_AREA_REVISION",
            payload={**request(), "target_area_mu": "11"},
        )
    )
    assert child["parent_id"] == seal


def test_default_contract_upgrade_does_not_change_seal(tmp_path: Path, monkeypatch) -> None:
    seal, snapshot = setup(tmp_path)
    monkeypatch.setattr(rr, "DEFAULT_CONTRACT", "NEW_DEFAULT")
    assert rr.read(score(tmp_path, seal, snapshot))["metric_binding"] == rr.metric_binding()
    with pytest.raises(ValueError, match="METRIC"):
        rr.evaluate(
            tmp_path / "store", seal, snapshot, rr.DEFAULT_CONTRACT, MODEL, test_clock=SCORE_CLOCK
        )


def test_metric_dependency_change_cannot_silently_rescore(tmp_path: Path, monkeypatch) -> None:
    seal, snapshot = setup(tmp_path)
    original = rr.file_hash

    def different_dependency(path):
        if str(path).endswith("core_forecast/canonical.py"):
            return "0" * 64
        return original(path)

    monkeypatch.setattr(rr, "file_hash", different_dependency)
    with pytest.raises(ValueError, match="METRIC"):
        score(tmp_path, seal, snapshot)


@pytest.mark.parametrize("field", ["specification_hash", "implementation_hash", "version"])
def test_sealed_metric_identity_conflict(tmp_path: Path, field: str) -> None:
    seal, snapshot = setup(tmp_path)
    path = tmp_path / "store/predictions" / seal / "record.json"
    forge(path, lambda record: record["metric_binding"].update({field: "f" * 64}))
    with pytest.raises(ValueError, match="METRIC"):
        score(tmp_path, seal, snapshot)


@pytest.mark.parametrize(
    "fault", ["base", "season", "window", "target", "mode", "time", "type", "reason"]
)
def test_prediction_lineage_boundaries(tmp_path: Path, fault: str) -> None:
    parent_path = issue(tmp_path)
    parent = rr.read(parent_path)
    payload = request()
    clock = ISSUE_CLOCK
    reason = "SYNTHETIC_REVISION"
    if fault == "base":
        payload["base_id"] = "base_" + "b" * 24
    elif fault == "season":
        payload.update(
            target_season="2028-2029",
            forecast_start_date="2028-07-01",
            forecast_end_date="2029-04-15",
        )
    elif fault in {"window", "target"}:
        key = "window" if fault == "window" else "target_definition"
        forge(
            parent_path,
            lambda record: record["identity"].update(
                {key: ["2027-07-02", "2028-04-15"] if key == "window" else "OTHER"}
            ),
        )
    elif fault == "mode":
        forge(parent_path, lambda record: record.update(test_only=False))
    elif fault == "time":
        clock -= timedelta(seconds=1)
    elif fault == "type":
        forge(parent_path, lambda record: record.update(kind="actuals"))
    else:
        reason = None
    with pytest.raises(ValueError):
        issue(tmp_path, payload=payload, clock=clock, parent_id=parent["id"], reason=reason)


def test_actual_and_evaluation_wrong_seal_and_time(tmp_path: Path) -> None:
    seal, snapshot = setup(tmp_path)
    other = rr.read(issue(tmp_path))["id"]
    source = actual(tmp_path, version="2", supersedes=snapshot)
    with pytest.raises(ValueError, match="SEAL"):
        rr.import_actuals(tmp_path / "store", other, source, test_clock=ACTUAL_CLOCK)
    with pytest.raises(ValueError):
        rr.evaluate(tmp_path / "store", other, snapshot, rr.CONTRACT, MODEL, test_clock=SCORE_CLOCK)
    result = rr.read(score(tmp_path, seal, snapshot))
    with pytest.raises(ValueError, match="TIME"):
        rr.evaluate(
            tmp_path / "store",
            seal,
            snapshot,
            rr.CONTRACT,
            MODEL,
            test_clock=ACTUAL_CLOCK,
            parent_id=result["id"],
            revision_reason="TEST",
        )
    # Equal timestamps are legal; no unnecessary strictly-increasing rule.
    assert rr.evaluate(
        tmp_path / "store", seal, snapshot, rr.CONTRACT, MODEL, test_clock=ACTUAL_CLOCK
    ).exists()


@pytest.mark.parametrize("phase", ["inference", "stage", "publication"])
def test_deadline_crossing_has_no_valid_seal(tmp_path: Path, phase: str) -> None:
    before = datetime(2027, 6, 30, 15, 59, 59, tzinfo=UTC)
    after = datetime(2027, 6, 30, 16, 0, tzinfo=UTC)
    crossing = {"inference": 1, "stage": 2, "publication": 3}[phase]
    stamps = iter([before] * crossing + [after] * 5)
    with pytest.raises(ValueError, match="CUTOFF"):
        issue(tmp_path, clock=rr.TestClock(lambda: next(stamps)))
    assert not list((tmp_path / "store/predictions").glob("*/record.json"))


def test_partial_write_not_readable(tmp_path: Path, monkeypatch) -> None:
    def crash(path, payload):
        path.write_text("{")
        raise OSError("SYNTHETIC_CRASH")

    monkeypatch.setattr(rr, "_write", crash)
    with pytest.raises(OSError, match="CRASH"):
        issue(tmp_path)
    assert not list((tmp_path / "store/predictions").glob("*/record.json"))
    assert list((tmp_path / "store/ABORTED_NOT_ISSUED").glob("*"))


def test_crash_after_rename_before_completion_marker_not_valid(tmp_path: Path) -> None:
    calls = 0

    def abrupt_clock():
        nonlocal calls
        calls += 1
        if calls == 4:
            raise KeyboardInterrupt("SYNTHETIC_PROCESS_CRASH_AFTER_RENAME")
        return ISSUE_CLOCK

    with pytest.raises(KeyboardInterrupt):
        issue(tmp_path, clock=rr.TestClock(abrupt_clock))
    assert not list((tmp_path / "store/predictions").glob("*/record.json"))


@pytest.mark.parametrize("phase", [4, 5])
def test_hard_process_exit_before_finalization_not_valid(tmp_path: Path, phase: int) -> None:
    code = (
        "import os,sys; from pathlib import Path; "
        "from backend.app.area_yield import research_records_r2 as rr; "
        "from backend.tests.area_yield.test_research_records_r2 import issue,ISSUE_CLOCK; "
        "count=0\n"
        "def clock():\n"
        " global count\n count+=1\n"
        f" if count=={phase}: os._exit(77)\n"
        " return ISSUE_CLOCK\n"
        "issue(Path(sys.argv[1]),clock=rr.TestClock(clock))\n"
    )
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=False)
    assert result.returncode == 77
    records = list((tmp_path / "store/predictions").glob("*/record.json"))
    assert len(records) == 1
    with pytest.raises(ValueError, match="NOT_FINAL"):
        rr.load_prediction(tmp_path / "store", records[0].parent.name, MODEL)


@pytest.mark.parametrize(
    "fault", ["nonhex", "file_hash", "canonical", "declaration", "authorization"]
)
def test_source_authorization_identity(tmp_path: Path, fault: str) -> None:
    reg = tmp_path / "registry.json"
    sha = registry(reg)
    authority = auth(tmp_path, request())
    if fault == "nonhex":
        authority["source"]["raw_source_hash"] = "z" * 64
    elif fault == "file_hash":
        authority["source"]["raw_source_hash"] = "0" * 64
    elif fault == "canonical":
        authority["source"]["canonical_payload_hash"] = "0" * 64
    elif fault == "declaration":
        authority["source"]["raw_source_path"] = None
    else:
        authority["local_record"]["request_snapshot_hash"] = "0" * 64
    with pytest.raises(ValueError):
        rr.issue(
            tmp_path / "store",
            reg,
            sha,
            MODEL,
            "M0-ALL-HISTORY-REFERENCE-R1",
            request(),
            authority,
            test_clock=ISSUE_CLOCK,
        )


def test_source_conflict_revision_and_duplicate_policy(tmp_path: Path) -> None:
    seal, snapshot = setup(tmp_path)
    assert (
        rr.read(
            rr.import_actuals(tmp_path / "store", seal, actual(tmp_path), test_clock=ACTUAL_CLOCK)
        )["id"]
        == snapshot
    )
    rows = actual_source()["rows"]
    rows[1]["new_quantity_kg"] = "90.000000"
    with pytest.raises(ValueError, match="CONFLICT"):
        rr.import_actuals(
            tmp_path / "store",
            seal,
            actual(tmp_path, rows=rows, supersedes=snapshot),
            test_clock=ACTUAL_CLOCK,
        )
    with pytest.raises(ValueError, match="REVISION"):
        rr.import_actuals(
            tmp_path / "store",
            seal,
            actual(tmp_path, version="2", rows=rows),
            test_clock=ACTUAL_CLOCK,
        )
    source = actual(tmp_path, version="2", supersedes=snapshot, rows=rows)
    source["source_identity"]["raw_source_path"] = None
    path = rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK)
    assert rr.read(path)["source_identity"]["verification"] == "DECLARED_NOT_CONTENT_VERIFIED"


@pytest.mark.parametrize("value", ["0.0000009", "NaN", "Infinity", "-1", 1.0, None, "bad"])
def test_precision_rejected_at_import(tmp_path: Path, value: Any) -> None:
    seal = rr.read(issue(tmp_path))["id"]
    rows = actual_source()["rows"]
    rows[1]["new_quantity_kg"] = value
    with pytest.raises(ValueError):
        rr.import_actuals(
            tmp_path / "store", seal, actual(tmp_path, rows=rows), test_clock=ACTUAL_CLOCK
        )


def test_trailing_zeros_and_same_canonical_series(tmp_path: Path) -> None:
    assert rr.quantity("1.2300000") == "1.230000"
    seal = rr.read(issue(tmp_path))["id"]
    rows = actual_source()["rows"]
    rows[1]["new_quantity_kg"] = "1.2300000"
    source = actual(tmp_path, rows=rows)
    source["source_identity"]["canonical_payload_hash"] = digest(rr.normalize_rows(rows))
    snapshot = rr.read(rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK))
    assert snapshot["source"]["rows"][1]["new_quantity_kg"] == "1.230000"
    result = rr.read(score(tmp_path, seal, snapshot["id"]))
    assert result["metrics"] == old.score_curve(
        snapshot["source"]["rows"],
        rr.load_prediction(tmp_path / "store", seal, MODEL)["prediction"],
    )


def test_known_source_version_reusable_after_newer_revision(tmp_path: Path) -> None:
    seal, snapshot = setup(tmp_path)
    rr.import_actuals(
        tmp_path / "store",
        seal,
        actual(tmp_path, version="2", supersedes=snapshot),
        test_clock=ACTUAL_CLOCK,
    )
    another = rr.read(issue(tmp_path))["id"]
    path = rr.import_actuals(tmp_path / "store", another, actual(tmp_path), test_clock=ACTUAL_CLOCK)
    assert rr.read(path)["prediction_seal_id"] == another


def test_normalization_upgrade_declared_not_falsely_verified(tmp_path: Path) -> None:
    seal, snapshot = setup(tmp_path)
    source = actual(tmp_path, supersedes=snapshot)
    source["source_identity"].update(
        normalization_version="CALLER_DECLARED_TRANSFORM_V2", raw_source_path=None
    )
    revised = rr.read(rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK))
    prior = rr.read(tmp_path / "store/actuals" / snapshot / "record.json")
    assert (
        revised["source_identity"]["raw_source_hash"] == prior["source_identity"]["raw_source_hash"]
    )
    assert revised["source_identity"]["verification"] == "DECLARED_NOT_CONTENT_VERIFIED"


def test_legacy_read_only_compatibility(tmp_path: Path) -> None:
    from backend.tests.area_yield.test_research_records import setup_records

    seal, snapshot = setup_records(tmp_path)
    before = {p: p.read_bytes() for p in (tmp_path / "store").glob("*/*/record.json")}
    assert rr.replay_legacy(tmp_path / "store", seal, snapshot, MODEL)["scope"].startswith(
        "R1_HISTORICAL"
    )
    with pytest.raises(ValueError, match="LEGACY"):
        rr.load_prediction(tmp_path / "store", seal, MODEL)
    assert all(p.read_bytes() == content for p, content in before.items())


def test_real_mode_not_authorized(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        issue(tmp_path, clock=None)


def test_missing_future_and_mode_preserved(tmp_path: Path) -> None:
    seal, snapshot = setup(tmp_path)
    source = actual(tmp_path, version="2", supersedes=snapshot)
    source["rows"].pop()
    source["source_identity"] = origin(tmp_path / "missing.json", source["rows"], version="2")
    missing = rr.read(rr.import_actuals(tmp_path / "store", seal, source, test_clock=ACTUAL_CLOCK))[
        "id"
    ]
    with pytest.raises(ValueError, match="COVERAGE"):
        score(tmp_path, seal, missing)
    unfinished = tmp_path / "unfinished"
    unfinished.mkdir()
    early_seal = rr.read(issue(unfinished))["id"]
    last_day = datetime(2028, 4, 15, tzinfo=UTC)
    early_actual = rr.read(
        rr.import_actuals(unfinished / "store", early_seal, actual(unfinished), test_clock=last_day)
    )["id"]
    with pytest.raises(ValueError, match="NOT_ENDED"):
        rr.evaluate(
            unfinished / "store",
            early_seal,
            early_actual,
            rr.CONTRACT,
            MODEL,
            test_clock=last_day,
        )
    with pytest.raises(ValueError, match="MODE"):
        rr.import_actuals(tmp_path / "store", seal, actual(tmp_path), test_clock=None)


def test_model_and_prediction_tampering(tmp_path: Path) -> None:
    seal, _ = setup(tmp_path)
    path = tmp_path / "store/predictions" / seal / "record.json"
    data = rr.read(path)
    data["prediction"]["daily_curve"][0]["predicted_quantity_kg"] = "100.000000"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="HASH"):
        rr.load_prediction(tmp_path / "store", seal, MODEL)
    model = tmp_path / "wrong-model.json"
    model.write_text(MODEL.read_text() + " ")
    other = rr.read(issue(tmp_path))["id"]
    with pytest.raises(ValueError, match="COMPONENT"):
        rr.load_prediction(tmp_path / "store", other, model)


def test_type_mode_and_seal_relationship_function() -> None:
    parent = {
        "kind": "evaluations",
        "identity": {},
        "test_only": True,
        "prospective_class": "TEST_NOT_PROSPECTIVE",
        "committed_at": ISSUE_CLOCK.isoformat(),
        "prediction_seal_id": "a",
        "actual_snapshot_id": "x",
    }
    child = {
        **copy.deepcopy(parent),
        "occurred_at": ISSUE_CLOCK.isoformat(),
        "revision_reason": "TEST",
        "actual_snapshot_id": "y",
        "actual_supersedes": "z",
    }
    with pytest.raises(ValueError, match="ACTUAL_REVISION"):
        rr.relation(child, parent)
    child.update(actual_supersedes="x", prediction_seal_id="b")
    with pytest.raises(ValueError, match="SEAL"):
        rr.relation(child, parent)
    child.update(prediction_seal_id="a", test_only=False)
    with pytest.raises(ValueError, match="MODE|LINEAGE"):
        rr.relation(child, parent)


@pytest.mark.parametrize(
    "fault",
    [
        "subwindow",
        "backdating_field",
        "diagnostic_role",
        "authorization_string",
        "wrong_unit",
        "future_actual",
    ],
)
def test_original_guards_revalidated_on_r2(tmp_path: Path, fault: str) -> None:
    payload = request()
    if fault == "subwindow":
        payload["forecast_start_date"] = "2027-08-01"
        with pytest.raises(ValueError, match="SUBWINDOW"):
            issue(tmp_path, payload=payload)
    elif fault == "backdating_field":
        payload["issued_at"] = ISSUE_CLOCK.isoformat()
        with pytest.raises(ValueError):
            issue(tmp_path, payload=payload)
    elif fault == "diagnostic_role":
        reg = tmp_path / "registry.json"
        registry(reg)
        data = rr.read(reg)
        data["models"][0]["model_role"] = "DIAGNOSTIC_ONLY"
        reg.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="ROLE"):
            rr.issue(
                tmp_path / "store",
                reg,
                rr.file_hash(reg),
                MODEL,
                "M0-ALL-HISTORY-REFERENCE-R1",
                payload,
                auth(tmp_path, payload),
                test_clock=ISSUE_CLOCK,
            )
    elif fault == "authorization_string":
        reg = tmp_path / "registry.json"
        sha = registry(reg)
        with pytest.raises((ValueError, KeyError, TypeError)):
            rr.issue(
                tmp_path / "store",
                reg,
                sha,
                MODEL,
                "M0-ALL-HISTORY-REFERENCE-R1",
                payload,
                {"status": "OWNER_AUTHORIZED"},
                test_clock=ISSUE_CLOCK,
            )
    else:
        seal = rr.read(issue(tmp_path))["id"]
        source = actual(tmp_path)
        if fault == "wrong_unit":
            source["unit"] = "tonne"
            clock = ACTUAL_CLOCK
        else:
            clock = ISSUE_CLOCK
        with pytest.raises(ValueError):
            rr.import_actuals(tmp_path / "store", seal, source, test_clock=clock)
