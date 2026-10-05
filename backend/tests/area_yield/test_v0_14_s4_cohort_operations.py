"""Synthetic fixed-slot operations: no network, private inputs or actuals."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from backend.app.area_yield import v014_cohort_operations as o
from backend.app.area_yield.data import digest
from scripts.materialize_v0_14_s3a_area_authority import build_revision, revision_input


def dt(value):
    return datetime.fromisoformat(value + "+08:00")


def test_policy_and_schedule():
    o.validate_policy(o.POLICY)
    assert len(o.slot_dates()) == 177
    assert o.slot_origin("2027-03-31") == dt("2027-04-01T00:00:00")
    assert o.slot_origin("2026-10-06") == dt("2026-10-07T00:00:00")
    o.validate_attempt("2026-10-06", dt("2026-10-06T17:00:00"))
    o.validate_attempt("2026-10-06", dt("2026-10-06T17:15:00"))


@pytest.mark.parametrize("field", list(o.POLICY))
def test_policy_mutation_rejected(field):
    changed = deepcopy(o.POLICY)
    changed[field] = "unauthorized"
    with pytest.raises(ValueError):
        o.validate_policy(changed)


@pytest.mark.parametrize(
    "slot,started",
    [
        ("2026-10-05", "2026-10-05T17:00:00"),
        ("2027-04-01", "2027-04-01T17:00:00"),
        ("2026-10-06", "2026-10-06T16:59:59"),
        ("2026-10-06", "2026-10-06T17:15:01"),
        ("2026-10-06", "2026-10-07T17:00:00"),
    ],
)
def test_invalid_attempt(slot, started):
    with pytest.raises(ValueError):
        o.validate_attempt(slot, dt(started))


def test_no_roll_to_second_day():
    with pytest.raises(ValueError, match="LATE_CAPTURE_CUTOFF"):
        o.validate_created("2026-10-06", dt("2026-10-06T18:00:01"))
    o.validate_created("2026-10-06", dt("2026-10-06T18:00:00"))


def test_scope_priority_and_no_retroactive_replacement():
    area = build_revision(revision_input())
    raw = area.model_dump()
    raw.update(
        area_revision_id="formal",
        area_type="PLANTED_AREA",
        known_at=dt("2026-10-07T16:00:00"),
        recorded_at=dt("2026-10-07T16:00:00"),
        supersedes_revision_id=area.area_revision_id,
        payload_hash=None,
    )
    child = o.AreaRevisionInput.model_validate(raw)
    child = child.model_copy(update={"payload_hash": child.computed_payload_hash()})
    assert (
        o.select_scope([area, child], dt("2026-10-06T17:00:00"), o.slot_origin("2026-10-06"))
        == area
    )
    assert (
        o.select_scope([area, child], dt("2026-10-07T17:00:00"), o.slot_origin("2026-10-07"))
        == child
    )


def test_genesis_determinism(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    o.initialize(a, o.SEED)
    o.initialize(b, o.SEED)
    assert o.audit_registry(a)[0] == o.audit_registry(b)[0]
    for name in ("cohort-registry.jsonl", "cohort-registry-manifest.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_missed_append_idempotency_and_conflict(tmp_path):
    o.initialize(tmp_path, o.SEED)
    now = dt("2026-10-06T18:00:01")
    record = o.record_missed(tmp_path, "2026-10-06", now)
    assert record["status"] == "MISSED_SLOT"
    assert o.record_missed(tmp_path, "2026-10-06", now) == record
    changed = o.nonissued("2026-10-06", "TECHNICAL_FAILURE", now, "failure")
    with pytest.raises(ValueError, match="SLOT_CONFLICT"):
        o.append_record(tmp_path, changed)


@pytest.mark.parametrize("mutation", ["delete", "reorder", "previous", "seed", "head"])
def test_registry_tamper(tmp_path, mutation):
    o.initialize(tmp_path, o.SEED)
    o.record_missed(tmp_path, "2026-10-06", dt("2026-10-06T18:01:00"))
    path = tmp_path / "cohort-registry.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    if mutation == "delete":
        lines.pop()
    elif mutation == "reorder":
        lines.reverse()
    elif mutation in {"previous", "seed"}:
        import json

        row = json.loads(lines[0 if mutation == "seed" else 1])
        row["previous_record_hash"] = "bad"
        row["record_hash"] = digest({k: v for k, v in row.items() if k != "record_hash"})
        lines[0 if mutation == "seed" else 1] = o.line_bytes(row)
    else:
        (tmp_path / "cohort-registry-manifest.json").write_text("{}")
    path.write_bytes(b"".join(lines))
    with pytest.raises(ValueError):
        o.audit_registry(tmp_path)


@pytest.mark.parametrize(
    "operation", ["actual", "hash-actual", "stat-actual", "score", "fit", "refit"]
)
def test_forbidden_operations(operation):
    with pytest.raises(ValueError):
        o.execution_gate(operation)


def test_attempt_claim_blocks_hidden_retry(tmp_path):
    o.initialize(tmp_path, o.SEED)
    o.claim_attempt(tmp_path, "2026-10-06", dt("2026-10-06T17:01:00"))
    with pytest.raises(ValueError, match="RETRY_FORBIDDEN"):
        o.claim_attempt(tmp_path, "2026-10-06", dt("2026-10-06T17:02:00"))


def test_no_early_missed_record(tmp_path):
    o.initialize(tmp_path, o.SEED)
    with pytest.raises(ValueError):
        o.record_missed(tmp_path, "2026-10-06", dt("2026-10-06T18:00:00"))


@pytest.mark.parametrize("hours", [36.0001, 37, -1])
def test_weather_age_failure(hours):
    created = dt("2026-10-06T17:30:00")
    with pytest.raises(ValueError, match="WEATHER_RUN_TOO_OLD"):
        o.verify_freshness(created - timedelta(hours=hours), created)


def test_weather_age_boundary():
    created = dt("2026-10-06T17:30:00")
    o.verify_freshness(created - timedelta(hours=36), created)


@pytest.mark.parametrize("mutation", ["planned", "previous", "hash", "ineffective", "conflict"])
def test_scope_fail_closed(mutation):
    area = build_revision(revision_input())
    raw = area.model_dump()
    changes = {
        "planned": {"area_type": "PLANNED_AREA"},
        "previous": {"season": "2025-2026"},
        "ineffective": {"effective_to": dt("2026-10-05T00:00:00")},
    }
    raw.update(changes.get(mutation, {}), payload_hash=None)
    child = o.AreaRevisionInput.model_validate(raw)
    child = child.model_copy(update={"payload_hash": child.computed_payload_hash()})
    revisions = [child]
    if mutation == "hash":
        revisions = [child.model_copy(update={"payload_hash": "bad"})]
    if mutation == "conflict":
        revisions.append(
            child.model_copy(update={"area_revision_id": "conflict", "payload_hash": None})
        )
        revisions[-1] = revisions[-1].model_copy(
            update={"payload_hash": revisions[-1].computed_payload_hash()}
        )
    with pytest.raises(ValueError):
        o.select_scope(revisions, dt("2026-10-06T17:00:00"), o.slot_origin("2026-10-06"))


def test_missing_previous_slots_rejected(tmp_path):
    o.initialize(tmp_path, o.SEED)
    with pytest.raises(ValueError):
        o.record_missed(tmp_path, "2026-10-07", dt("2026-10-07T18:01:00"))


def test_interrupted_attempt_becomes_technical_not_retry(tmp_path):
    o.initialize(tmp_path, o.SEED)
    o.claim_attempt(tmp_path, "2026-10-06", dt("2026-10-06T17:00:00"))
    assert (
        o.record_missed(tmp_path, "2026-10-06", dt("2026-10-06T18:01:00"))["status"]
        == "TECHNICAL_FAILURE"
    )


@pytest.fixture
def slot_fixture(tmp_path, monkeypatch):
    from argparse import Namespace

    from backend.app.area_yield.v014_future_weather_features import FEATURE_NAMES
    from scripts import run_v0_14_cohort_slot as runner

    o.initialize(tmp_path, o.SEED)
    args = Namespace(
        registry=tmp_path,
        slot_date="2026-10-06",
        scope_store=tmp_path,
        bundle=tmp_path,
        locations=tmp_path,
        cache=tmp_path,
    )
    started, created, sealed = (dt("2026-10-06T" + t) for t in ("17:00:00", "17:30:00", "17:30:01"))
    clock = iter([started, created, sealed, sealed + timedelta(seconds=1)])

    class Clock:
        @staticmethod
        def now(_):
            return next(clock)

        fromisoformat = datetime.fromisoformat

    monkeypatch.setattr(runner, "datetime", Clock)
    area = build_revision(revision_input())
    monkeypatch.setattr(o, "read_scope_store", lambda *a: area)
    monkeypatch.setattr(runner.s, "recover_bundle", lambda *a: {})
    monkeypatch.setattr(runner, "ECMWFDenseFeatureSurfaceProvider", lambda **k: None)
    features = {k: "1.000000000000" for k in FEATURE_NAMES}
    monkeypatch.setattr(runner, "aggregate_ifs", lambda _: features)
    surface = {
        "issued_at": dt("2026-10-06T08:00:00").isoformat(),
        "run_id": "20261006000000",
        "raw_manifest_sha256": "a" * 64,
        "acquisition_receipt": {
            "fetched_at": created.isoformat(),
            "known_at": created.isoformat(),
            "manifest_sha256": "a" * 64,
        },
        "fields_by_base": {o.s.BASE_ID: {}},
    }
    # Use UTC encoding: provider cycles are 00/12 UTC, not local clock hour.
    surface["issued_at"] = "2026-10-06T00:00:00+00:00"
    monkeypatch.setattr(runner, "capture_latest", lambda *a: (surface, []))
    monkeypatch.setattr(
        runner.s,
        "predict_pair",
        lambda models, rows: {
            role: [[r["key"], "1.000000000000"] for r in rows] for role in ("c0", "w1")
        },
    )
    return args, runner, surface


def test_synthetic_full_slot_package_and_audit(slot_fixture):
    args, runner, _ = slot_fixture
    row = runner.issue_slot(args)
    assert row["status"] == "ISSUED"
    assert len(o.audit_registry(args.registry)) == 2
    assert runner.register_package(args.registry, args.slot_date) == row
    with pytest.raises(ValueError):
        o.claim_attempt(args.registry, args.slot_date, dt("2026-10-06T17:01:00"))


@pytest.mark.parametrize(
    "failure,status",
    [
        ("NO_VALID_SCOPE_AUTHORITY", "NO_VALID_SCOPE_AUTHORITY"),
        ("AUTHORITY_CONFLICT", "AUTHORITY_CONFLICT"),
        ("SELECTED_SCOPE_W1_FEATURE_SURFACE_INCOMPLETE", "NO_COMPLETE_WEATHER_RUN"),
        ("WEATHER_RUN_TOO_OLD", "WEATHER_RUN_TOO_OLD"),
        ("LATE_CAPTURE_CUTOFF", "LATE_CAPTURE_CUTOFF"),
        ("S2_BUNDLE_MISMATCH", "TECHNICAL_FAILURE"),
    ],
)
def test_slot_failures_terminal_and_no_retry(slot_fixture, monkeypatch, failure, status):
    args, runner, _ = slot_fixture

    def reject(*a):
        raise ValueError(failure)

    monkeypatch.setattr(o, "read_scope_store", reject)
    row = runner.issue_slot(args)
    assert row["status"] == status
    assert not (args.registry / "slot-packages").exists()
    assert len(o.audit_registry(args.registry)) == 2


@pytest.mark.parametrize(
    "member",
    [
        "c0-predictions.json",
        "prediction-seal.json",
        "metric-contract.json",
        "request-snapshot.json",
    ],
)
def test_issued_package_tamper(slot_fixture, member):
    args, runner, _ = slot_fixture
    runner.issue_slot(args)
    path = args.registry / "slot-packages" / o.slot_id(args.slot_date) / member
    path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        o.audit_registry(args.registry)


def test_cli_has_no_actual_or_scoring_inputs():
    from pathlib import Path

    source = Path("scripts/run_v0_14_cohort_slot.py").read_text()
    for forbidden in ("--actual", "--harvest", "--source25", "--source26", "fit_ridge_artifact"):
        assert forbidden not in source


def test_public_closeout_privacy():
    from backend.app.area_yield.v014_shadow_issuance import validate_public

    validate_public({"policy": o.POLICY, "seed": o.SEED})
    for body in ({"predicted_daily_kg": "1"}, {"coordinates": [1, 2]}, {"path": "/Users/private"}):
        with pytest.raises(ValueError):
            validate_public(body)


@pytest.mark.parametrize(
    "mutation,status",
    [
        ("old", "WEATHER_RUN_TOO_OLD"),
        ("future_known", "TECHNICAL_FAILURE"),
        ("06_cycle", "TECHNICAL_FAILURE"),
        ("manifest", "TECHNICAL_FAILURE"),
        ("missing_weather", "NO_COMPLETE_WEATHER_RUN"),
    ],
)
def test_capture_receipt_fail_closed(slot_fixture, monkeypatch, mutation, status):
    args, runner, surface = slot_fixture
    if mutation == "old":
        surface.update(issued_at="2026-10-04T00:00:00+00:00", run_id="20261004000000")
    elif mutation == "future_known":
        surface["acquisition_receipt"]["known_at"] = dt("2026-10-06T19:00:00").isoformat()
    elif mutation == "06_cycle":
        surface.update(issued_at="2026-10-06T06:00:00+00:00", run_id="20261006060000")
    elif mutation == "manifest":
        surface["raw_manifest_sha256"] = "bad"
    else:

        def missing(*a):
            raise ValueError("SELECTED_SCOPE_W1_FEATURE_SURFACE_INCOMPLETE")

        monkeypatch.setattr(runner, "aggregate_ifs", missing)
    assert runner.issue_slot(args)["status"] == status
    assert not (args.registry / "slot-packages").exists()


def test_checkpoint_genesis_tamper(tmp_path):
    o.initialize(tmp_path, o.SEED)
    (tmp_path / "checkpoints" / "000000.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        o.audit_registry(tmp_path)


def test_every_due_slot_reported(tmp_path):
    o.initialize(tmp_path, o.SEED)
    assert o.missing_due_slots(o.audit_registry(tmp_path), dt("2026-10-07T18:01:00")) == [
        "2026-10-06",
        "2026-10-07",
    ]


def test_future_scoring_reserved_not_executed():
    metric = o.s.metric_contract()
    assert digest(metric) == o.METRIC_HASH
    assert metric["missing_is_zero"] is False
    assert metric["horizons"] == {"H7": list(range(7)), "H15": list(range(15))}
    assert metric["business_promotion_threshold"] is None


def test_committed_public_closeout_matches_code_and_frozen_inputs():
    import hashlib
    import json
    from pathlib import Path

    root = Path("docs/v0-14")
    evidence = json.loads(
        (root / "evidence/v0.14-s4-prospective-cohort-operations-closeout-r1.json").read_bytes()
    )
    o.s.validate_public(evidence)
    assert evidence["operations_policy"] == o.POLICY
    assert (
        digest(evidence["operations_policy"]) == evidence["operations_policy_hash"] == o.POLICY_HASH
    )
    assert evidence["seed"] == o.SEED
    assert evidence["registry"]["genesis_record_hash"] == o.genesis(o.SEED)["record_hash"]
    files = {
        "s0": "v0.14.0-version-plan-and-prospective-protocol-freeze-r1.json",
        "s1": "v0.14-s1-ecmwf-as-issued-surface-qualification-r1.json",
        "s2": "v0.14-s2-future-weather-feature-and-artifact-freeze-r1.json",
        "s3a": "v0.14-s3a-current-season-area-reference-authority-r1.json",
        "s3": "v0.14-s3-real-shadow-prediction-seal-r2.json",
    }
    for key, name in files.items():
        assert (
            hashlib.sha256((root / "evidence" / name).read_bytes()).hexdigest()
            == evidence["public_input_sha256"][key]
        )
    assert evidence["governance"]["v0_14_version_complete"] is True
    for key in (
        "production_use_approved",
        "prospective_accuracy_validated",
        "v0_15_authorized",
        "ready_authorized",
        "merge_authorized",
        "tag_created",
        "release_created",
    ):
        assert evidence["governance"][key] is False
