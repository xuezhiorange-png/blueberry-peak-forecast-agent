"""Synthetic-only S4 authority, sequencing and temporal acceptance."""

import json
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app.area_yield import v013_feature_value_experiment as e
from backend.app.area_yield import v013_temporal_oracle as t
from backend.app.area_yield.data import digest
from backend.app.area_yield.gdd_features import sha256

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "field,value",
    [
        ("anchor", "TARGET_MINUS_1"),
        ("anchor", "ORIGIN_MINUS_1"),
        ("anchor", "TARGET_PLUS_2"),
        ("timezone", "UTC"),
        ("feature_count", 31),
        ("gdd", True),
        ("alpha", "5"),
        ("train_cohort", "MODEL_SPECIFIC"),
        ("labels", "DIFFERENT"),
        ("cohort_loss_allowed", True),
        ("peak_tie", "LATEST"),
        ("rolling_tie", "LATEST"),
        ("combined", "FOLD_MEAN"),
        ("shape", "MEAN_WINDOW_PERCENTAGE"),
        ("zero_mass", "EXCLUDE"),
        ("timing_support", "AMPLITUDE"),
        ("summary", "MIX_FAMILIES"),
        ("deployable", True),
        ("primary_lane", True),
        ("post_result_tuning", True),
    ],
)
def test_failure_contract_mutation(field, value):
    contract = deepcopy(t.CONTRACT)
    contract[field] = value
    with pytest.raises(t.TemporalError):
        t.validate_contract(contract)


@pytest.mark.parametrize("operation", ["labels24", "labels25", "scored", "score"])
def test_failure_unsealed_access(tmp_path, operation):
    guard = t.OracleGuard(tmp_path)
    with pytest.raises(t.TemporalError):
        if operation.startswith("labels"):
            guard.allow_label_read("2024-2025" if operation == "labels24" else "2025-2026")
        else:
            guard.begin_score()


def rows():
    start = date(2027, 1, 1)
    return [
        dict(
            season="2026-2027",
            base_id="SYNTHETIC",
            forecast_origin=start.isoformat(),
            target_date=(start + timedelta(days=i)).isoformat(),
            lead_day=i,
            actual_daily_kg="1",
            actual_status="KNOWN_MAPPED_SUBTOTAL",
            M0="2",
            M1="1",
            M2="1",
            M3="1",
            O1="1",
        )
        for i in range(15)
    ]


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "cross_origin", "wrong_date", "unknown"]
)
def test_failure_h15_mutation(mutation):
    r = rows()
    if mutation == "missing":
        r.pop()
    elif mutation == "duplicate":
        r[-1] = r[0]
    elif mutation == "cross_origin":
        r[-1]["forecast_origin"] = "2027-01-02"
    elif mutation == "wrong_date":
        r[-1]["target_date"] = "2027-02-01"
    else:
        r[0]["actual_status"] = "UNKNOWN"
    with pytest.raises(t.TemporalError):
        t.complete_windows(r)


def test_canonical_ties_shape_and_pooling():
    r = rows()
    metrics = t.temporal_metrics(t.complete_windows(r), "M0")
    assert metrics["single_date_mae"] == "0"
    assert metrics["rolling7_date_mae"] == "0"
    assert metrics["shape_error"] == "0"
    assert Decimal(metrics["single_quantity_mae"]) == 1
    assert Decimal(metrics["rolling7_quantity_mae"]) == 7
    assert metrics["canonical_semantics_parity"] is True
    assert metrics == t.temporal_metrics(t.complete_windows(r), "M0")


def test_zero_shape_mass_is_not_selectively_excluded():
    r = rows()
    for row in r:
        row["M1"] = "0"
    m = t.temporal_metrics(t.complete_windows(r), "M1")
    assert m["shape_not_computable_window_count"] == 1
    assert m["shape_error"] is None


def test_timing_gate_cannot_mix_families_or_use_quantity():
    scopes = {
        s: {
            m: dict(
                single_date_mae="3",
                rolling7_date_mae="3",
                shape_error="1",
                window_count=1,
                shape_not_computable_window_count=0,
            )
            for m in ("M0", "M1", "M2", "M3")
        }
        for s in ("fold_a", "fold_b", "combined")
    }
    for scope in scopes.values():
        scope["M1"]["single_date_mae"] = "2"
        scope["M2"]["rolling7_date_mae"] = "2"
    gates, summary, supported = t.timing_gates(scopes)
    assert summary == "INCONCLUSIVE" and supported == "NONE"
    for scope in scopes.values():
        scope["M1"]["rolling7_date_mae"] = "2"
    gates, summary, supported = t.timing_gates(scopes)
    assert gates["WEATHER_TIMING"]["status"] == "SUPPORTED"
    assert summary == "SUPPORTED" and supported == "M1"


def test_post_score_fit_forbidden(tmp_path):
    guard = t.OracleGuard(tmp_path)
    guard.scoring_started = True
    with pytest.raises(t.TemporalError):
        guard.allow_fit()


def oracle_fixture(tmp_path):
    for fold in ("fold_a", "fold_b"):
        root = tmp_path / fold
        root.mkdir()
        artifact = dict(
            schema="V0_13_ORACLE_RIDGE_ARTIFACT_V1",
            model_id=t.ORACLE_ID,
            feature_names=list(t.ORACLE_FEATURES),
            alpha=t.CONTRACT["alpha"],
            solver=t.CONTRACT["solver"],
            standardization=t.CONTRACT["standardization"],
            zero_std_policy="SCALE_1",
            nonnegative_output_clip=True,
            intercept_unpenalized=True,
            deployable=False,
            future_realized_information=True,
        )
        artifact["artifact_hash"] = digest(artifact)
        (root / "o1-artifact.json").write_text(json.dumps(artifact))
        (root / "predictions-before-scoring.jsonl").write_text("{}\n")
        seal = dict(
            fold_id=fold.upper(),
            sealed_before_validation_label_read=True,
            oracle_lane_c=True,
            future_realized_information=True,
            feature_policy_hash=digest(t.CONTRACT),
            artifact_hash=artifact["artifact_hash"],
            file_hashes={p.name: sha256(p) for p in root.iterdir()},
        )
        seal["seal_hash"] = digest(seal)
        (root / "prediction-seal.json").write_text(json.dumps(seal))
    return t.OracleGuard(tmp_path)


def test_durable_oracle_sequence(tmp_path):
    guard = oracle_fixture(tmp_path)
    guard.allow_label_read("2024-2025")
    guard.allow_label_read("2025-2026")
    guard.begin_score()
    with pytest.raises(t.TemporalError):
        guard.allow_fit()


@pytest.mark.parametrize("mutation", ["seal_hash", "file", "role", "fold", "policy", "artifact"])
def test_failure_oracle_seal_tamper(tmp_path, mutation):
    guard = oracle_fixture(tmp_path)
    root = tmp_path / "fold_b"
    if mutation in ("file", "artifact"):
        filename = (
            "o1-artifact.json" if mutation == "artifact" else "predictions-before-scoring.jsonl"
        )
        with (root / filename).open("a") as stream:
            stream.write(" ")
    else:
        path = root / "prediction-seal.json"
        seal = json.loads(path.read_text())
        key = {
            "seal_hash": "seal_hash",
            "role": "oracle_lane_c",
            "fold": "fold_id",
            "policy": "feature_policy_hash",
        }[mutation]
        seal[key] = "mutated"
        if mutation != "seal_hash":
            seal["seal_hash"] = digest({k: v for k, v in seal.items() if k != "seal_hash"})
        path.write_text(json.dumps(seal))
    with pytest.raises(t.TemporalError):
        guard.begin_score()


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_id", "M1"),
        ("standardization", "OTHER"),
        ("feature_names", list(t.ORACLE_FEATURES) + ["gdd_w7"]),
        ("alpha", "1"),
        ("deployable", True),
    ],
)
def test_failure_oracle_artifact_resealed_mutation(tmp_path, field, value):
    oracle_fixture(tmp_path)
    artifact = json.loads((tmp_path / "fold_a" / "o1-artifact.json").read_text())
    artifact[field] = value
    artifact["artifact_hash"] = digest({k: v for k, v in artifact.items() if k != "artifact_hash"})
    with pytest.raises(t.TemporalError):
        t.verify_oracle_artifact(artifact)


@pytest.mark.parametrize("change", ["report", "component"])
def test_failure_s3_authority(tmp_path, change):
    report = {**t.S3_HASHES, "metrics": {}, "comparisons": {}}
    if change == "report":
        report["report_hash"] = "0" * 64
    (tmp_path / "sanitized-evidence.json").write_text(json.dumps(report))
    with pytest.raises(t.TemporalError):
        t.verify_s3(tmp_path, t.S3_HASHES)


def test_combined_pooling_not_fold_mean():
    a, b = rows(), rows()
    for row in b:
        row["base_id"] = "SYNTHETIC_B"
        row["actual_daily_kg"] = "10"
        row["M0"] = "20"
    c = deepcopy(b)
    for row in c:
        row["base_id"] = "SYNTHETIC_C"
    combined = t.temporal_metrics(t.complete_windows(a + b + c), "M0")
    assert Decimal(combined["single_quantity_mae"]) == 7


@pytest.mark.parametrize("mutation", ["missing", "extra", "changed", "reordered"])
def test_failure_oracle_frozen_cohort(mutation):
    original = ["a", "b"]
    keys = {
        "missing": ["a"],
        "extra": ["a", "b", "c"],
        "changed": ["a", "c"],
        "reordered": ["b", "a"],
    }[mutation]
    with pytest.raises(e.ExperimentError):
        e.verify_keys(keys, 2, digest(original))


def test_shape_unknown_prevents_support_even_with_dates_improved():
    scopes = {
        s: {
            m: dict(
                single_date_mae="2",
                rolling7_date_mae="2",
                shape_error="1",
                window_count=2,
                shape_not_computable_window_count=0,
            )
            for m in ("M0", "M1", "M2", "M3")
        }
        for s in ("fold_a", "fold_b", "combined")
    }
    for scope in scopes.values():
        scope["M1"].update(
            single_date_mae="1",
            rolling7_date_mae="1",
            shape_error=None,
            shape_not_computable_window_count=1,
        )
    gates, summary, _ = t.timing_gates(scopes)
    assert gates["WEATHER_TIMING"]["status"] == "INCONCLUSIVE"
    assert summary != "SUPPORTED"


def degrading_timing_scopes():
    return {
        s: {
            m: dict(
                single_date_mae="2" if m == "M0" else "3",
                rolling7_date_mae="2" if m == "M0" else "3",
                shape_error=None,
                window_count=2,
                shape_not_computable_window_count=1,
            )
            for m in ("M0", "M1", "M2", "M3")
        }
        for s in ("fold_a", "fold_b", "combined")
    }


def test_shape_unavailable_does_not_block_not_supported_when_both_dates_degrade():
    gates, summary, family = t.timing_gates(degrading_timing_scopes())
    assert all(g["status"] == "NOT_SUPPORTED" for g in gates.values())
    assert summary == "NOT_SUPPORTED"
    assert family == "NONE"


@pytest.mark.parametrize("case", ["all_degrade", "mixed", "named_support"])
def test_overall_timing_summary(case):
    scopes = degrading_timing_scopes()
    if case == "mixed":
        scopes["combined"]["M1"]["single_date_mae"] = "1"
    if case == "named_support":
        for scope in scopes.values():
            scope["M0"].update(shape_error="1", shape_not_computable_window_count=0)
            scope["M1"].update(
                single_date_mae="1",
                rolling7_date_mae="1",
                shape_error="1",
                shape_not_computable_window_count=0,
            )
    _, summary, family = t.timing_gates(scopes)
    assert (summary, family) == {
        "all_degrade": ("NOT_SUPPORTED", "NONE"),
        "mixed": ("INCONCLUSIVE", "NONE"),
        "named_support": ("SUPPORTED", "M1"),
    }[case]


def test_synthetic_oracle_fit_predict_seal_score(tmp_path):
    from datetime import datetime

    from backend.app.area_yield.weather_aware_backtest import RollingTargetRow, fit_ridge_artifact

    training = []
    for i in range(4):
        day = date(2027, 1, 1) + timedelta(days=i)
        row = RollingTargetRow(
            key=str(i),
            base_id="SYNTHETIC",
            base_name="SYNTHETIC",
            season="2026-2027",
            forecast_origin=datetime.combine(day, datetime.min.time()).isoformat(),
            target_date=day,
            lead_day=0,
            reference_area_mu=Decimal(736),
            feature_values=tuple((f, str(i + 1)) for f in t.ORACLE_FEATURES),
            weather_feature_hash=digest([i]),
        )
        training.append((row, Decimal(i + 1)))
    fitted = fit_ridge_artifact(
        model_id=t.ORACLE_ID,
        fold_id="FOLD_A",
        rows=training,
        feature_names=t.ORACLE_FEATURES,
        training_input_hash=digest("SYNTHETIC_ONLY"),
    )
    payload = fitted.payload_without_hash()
    payload.pop("training_row_keys")
    payload.update(
        schema="V0_13_ORACLE_RIDGE_ARTIFACT_V1",
        standardization=t.CONTRACT["standardization"],
        zero_std_policy="SCALE_1",
        deployable=False,
        future_realized_information=True,
    )
    payload["artifact_hash"] = digest(payload)
    t.verify_oracle_artifact(payload)
    predicted = fitted.predict(training[0][0])
    assert predicted >= 0
    assert predicted == fitted.predict(training[0][0])
    guard = oracle_fixture(tmp_path)
    guard.begin_score()
    r = rows()
    for row in r:
        row["O1"] = str(predicted)
    assert t.temporal_metrics(t.complete_windows(r), "O1")["canonical_semantics_parity"] is True


@pytest.mark.parametrize(
    "mutation", ["target_plus1", "target_minus1", "origin_minus1", "timezone", "hour", "start"]
)
def test_failure_actual_oracle_window_binding(mutation):
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    target = date(2027, 1, 15)
    anchor = datetime(2027, 1, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    weather = SimpleNamespace(
        forecast_origin=anchor.isoformat(),
        feature_window_end=target,
        feature_window_start=target - timedelta(days=29),
    )
    t.verify_oracle_window(target, anchor, weather)
    if mutation == "target_plus1":
        weather.feature_window_end += timedelta(days=1)
    elif mutation in ("target_minus1", "origin_minus1"):
        weather.feature_window_end -= timedelta(days=1 if mutation == "target_minus1" else 14)
    elif mutation == "timezone":
        anchor = anchor.replace(tzinfo=ZoneInfo("UTC"))
    elif mutation == "hour":
        anchor = anchor.replace(hour=1)
    else:
        weather.feature_window_start += timedelta(days=1)
    with pytest.raises(t.TemporalError):
        t.verify_oracle_window(target, anchor, weather)


def label_guard(tmp_path, sealed=False):
    oracle = tmp_path / "oracle"
    oracle.mkdir()
    if sealed:
        oracle_fixture(oracle)
    s3 = tmp_path / "s3"
    for fold in ("fold_a", "fold_b"):
        (s3 / fold).mkdir(parents=True)
        (s3 / fold / "scored-rows.jsonl").write_text('{"actual_daily_kg":"SECRET"}\n')
    source24, source25 = tmp_path / "24.xls", tmp_path / "25.xls"
    source24.write_text("SYNTHETIC_SECRET")
    source25.write_text("SYNTHETIC_SECRET")
    return t.S4LabelAccessGuard(oracle, s3, source24, source25)


def test_preseal_sha256_of_label_bearing_artifact_is_rejected(tmp_path, monkeypatch):
    guard = label_guard(tmp_path)
    with guard:
        # Even the unguarded general-purpose hash helper must hit the I/O barrier.
        for fold in ("fold_a", "fold_b"):
            with pytest.raises(t.TemporalError):
                sha256(guard.scored_path(fold))
        assert not guard.first_byte_accesses


@pytest.mark.parametrize(
    "operation", ["read_bytes", "read_text", "stat", "identity", "parse", "open"]
)
def test_failure_preseal_label_access_including_metadata(tmp_path, operation):
    guard = label_guard(tmp_path)
    with guard:
        path = guard.scored_path("fold_a")
        with pytest.raises(t.TemporalError):
            if operation == "identity":
                guard.capture_s3_identity("fold_a")
            elif operation == "parse":
                guard.read_s3_scored_rows("fold_a")
            elif operation == "open":
                path.open("rb")
            else:
                getattr(path, operation)()
        assert not guard.first_byte_accesses


def test_failure_only_fold_a_seal_cannot_open_label_gate(tmp_path):
    guard = label_guard(tmp_path, sealed=True)
    (guard.oracle.root / "fold_b" / "prediction-seal.json").unlink()
    with guard:
        with pytest.raises(t.TemporalError):
            guard.open_label_gate()
        with pytest.raises(t.TemporalError):
            guard.scored_path("fold_a").read_bytes()
        assert not guard.label_gate_open


def test_postseal_label_access_and_deterministic_events(tmp_path):
    guard = label_guard(tmp_path, sealed=True)
    with guard:
        guard.open_label_gate()
        for fold in ("fold_a", "fold_b"):
            identity = guard.capture_s3_identity(fold)
            assert guard.read_s3_scored_rows(fold)[0]["actual_daily_kg"] == "SECRET"
            assert identity == guard.capture_s3_identity(fold)
        assert guard.events[:4] == [
            "BOTH_ORACLE_FOLDS_VERIFIED",
            "LABEL_GATE_OPENED",
            "FIRST_S3_SCORED_ROWS_BYTE_ACCESS:fold_a",
            "FIRST_S3_SCORED_ROWS_BYTE_ACCESS:fold_b",
        ]
        assert guard.preseal_label_access_count == 0


@pytest.mark.parametrize("operation", ["hash", "stat", "read"])
def test_failure_2025_source_preseal_access(tmp_path, operation):
    guard = label_guard(tmp_path)
    with guard:
        with pytest.raises(t.TemporalError):
            if operation == "hash":
                sha256(guard.source25)
            elif operation == "stat":
                guard.source25.stat()
            else:
                guard.source25.read_bytes()
